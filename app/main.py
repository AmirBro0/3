"""OKO — веб-сервис проверки кассовой дисциплины по видео.

Запуск:  uvicorn app.main:app --host 0.0.0.0 --port 8000
API для жюри (раздел 10 ТЗ):
  POST /api/v1/analyze      multipart, поле file (.mov), заголовок X-API-Key → {"job_id": ...}
  GET  /api/v1/jobs/{id}    статус processing | done | failed и результат
Интерфейс: GET /  и  GET /report/{id} (печатная форма). Служебные запросы страницы — /ui/v1/*.
"""
from __future__ import annotations

import hashlib
import logging
import secrets
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import Cookie, Depends, FastAPI, File, Form, Header, HTTPException, Query, Response, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

from .config import VERSION, get_settings
from .device import device_info
from .jobs import JobManager
from .page import render_page
from .rules.catalog import catalog_payload
from .views import api_view, ui_view

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("oko")

ALLOWED_EXT = {".mov", ".qt", ".mp4", ".m4v", ".avi", ".mkv", ".webm"}

settings = get_settings()
manager: JobManager | None = None


@asynccontextmanager
async def lifespan(_: FastAPI):
    global manager
    manager = JobManager(settings)
    key = settings.api_keys[0]
    dev = device_info()
    log.info("OKO %s: детекторы %s, воркеров %d, бюджет %.0f с, устройство %s (%s)", VERSION,
             ",".join(settings.detectors), settings.workers, settings.deadline_sec, dev["device"], dev["name"])
    log.info("API-ключ для жюри: %s…%s (полностью — в OKO_API_KEYS или %s)", key[:6], key[-3:],
             settings.data_dir / "api_key.txt")
    yield
    manager.shutdown()


app = FastAPI(title="OKO", version=VERSION, lifespan=lifespan,
              description="Поиск признаков нарушений кассовой дисциплины по видео. Работает локально.")
app.add_middleware(GZipMiddleware, minimum_size=2000)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["GET", "POST"],
                   allow_headers=["X-API-Key", "Content-Type"])


def jobs() -> JobManager:
    if manager is None:
        raise HTTPException(503, "Сервис запускается, повторите через несколько секунд.")
    return manager


def require_api_key(x_api_key: str | None = Header(default=None, alias="X-API-Key")) -> None:
    if not x_api_key or not any(secrets.compare_digest(x_api_key, k) for k in settings.api_keys):
        raise HTTPException(status_code=401, detail="Неверный или отсутствующий заголовок X-API-Key.")


# ── Вход в интерфейс: тот же X-API ключ, после входа — cookie на 12 часов ────
SESSION_COOKIE = "oko_session"


def _key_ok(key: str | None) -> bool:
    return bool(key) and any(secrets.compare_digest(key, k) for k in settings.api_keys)


def _session_token(key: str) -> str:
    # В cookie лежит не сам ключ, а его хеш
    return hashlib.sha256(f"oko-ui:{key}".encode()).hexdigest()


def _session_ok(token: str | None) -> bool:
    return bool(token) and any(secrets.compare_digest(token, _session_token(k)) for k in settings.api_keys)


def require_ui_session(x_api_key: str | None = Header(default=None, alias="X-API-Key"),
                       oko_session: str | None = Cookie(default=None)) -> None:
    if not (_key_ok(x_api_key) or _session_ok(oko_session)):
        raise HTTPException(status_code=401, detail="Войдите по X-API ключу.")


UI_AUTH = [Depends(require_ui_session)]


async def _accept_upload(file: UploadFile | None, origin: str, meta: dict) -> dict:
    if file is None:
        raise HTTPException(400, "Передайте видео в поле file (multipart/form-data).")
    m = jobs()
    filename = Path(file.filename or "video.mov").name
    ext = Path(filename).suffix.lower() or ".mov"
    if ext not in ALLOWED_EXT:
        raise HTTPException(415, "Поддерживаются видео .mov и .mp4 (а также .m4v, .avi, .mkv, .webm).")
    if m.active_count() >= settings.max_queue:
        raise HTTPException(503, "Очередь заполнена. Повторите через минуту.")

    job_id = m.new_id()
    dest = settings.uploads_dir / f"{job_id}{ext}"
    limit = settings.max_upload_mb * 1024 * 1024
    size = 0
    try:
        with dest.open("wb") as out:
            while chunk := await file.read(1024 * 1024):
                size += len(chunk)
                if size > limit:
                    raise HTTPException(413, f"Файл больше {settings.max_upload_mb} МБ.")
                out.write(chunk)
    except HTTPException:
        dest.unlink(missing_ok=True)
        raise
    if size == 0:
        dest.unlink(missing_ok=True)
        raise HTTPException(400, "Файл пустой.")

    m.submit(job_id, dest, filename, origin, meta)
    return {"job_id": job_id, "status": "processing"}


# ── API для жюри ─────────────────────────────────────────────────────────────
@app.post("/api/v1/analyze", dependencies=[Depends(require_api_key)], tags=["API"])
async def api_analyze(
    file: UploadFile | None = File(default=None),
    branch: str = Form(default=""), desk: str = Form(default=""), shot_date: str = Form(default=""),
) -> dict:
    return await _accept_upload(file, "api", {"branch": branch, "desk": desk, "shot_date": shot_date})


@app.get("/api/v1/jobs/{job_id}", dependencies=[Depends(require_api_key)], tags=["API"])
def api_job(job_id: str) -> dict:
    job = jobs().get(job_id)
    if job is None:
        raise HTTPException(404, "Задача не найдена.")
    return api_view(job, settings)


@app.get("/healthz", tags=["service"])
def healthz() -> dict:
    return {"status": "ok", "version": VERSION, "queue": jobs().active_count()}


# ── Интерфейс ────────────────────────────────────────────────────────────────
def _boot() -> dict:
    return {
        "backend": True,
        "version": VERSION,
        "catalog": catalog_payload(),
        "limits": {"deadline_sec": settings.deadline_sec, "max_upload_mb": settings.max_upload_mb},
        "detectors": list(settings.detectors),
    }


@app.get("/", response_class=HTMLResponse, include_in_schema=False)
def index() -> HTMLResponse:
    return HTMLResponse(render_page(_boot()), headers={"Cache-Control": "no-store"})


@app.get("/report/{job_id}", response_class=HTMLResponse, include_in_schema=False)
def report_page(job_id: str) -> HTMLResponse:
    """Печатная форма отчёта: та же страница, открывается сразу в режиме печати."""
    return HTMLResponse(render_page(_boot()), headers={"Cache-Control": "no-store"})


class SessionIn(BaseModel):
    key: str


@app.post("/ui/v1/session", tags=["ui"])
def ui_login(body: SessionIn, response: Response) -> dict:
    key = body.key.strip()
    if not _key_ok(key):
        raise HTTPException(status_code=401, detail="Неверный X-API ключ.")
    response.set_cookie(SESSION_COOKIE, _session_token(key), max_age=12 * 3600, httponly=True, samesite="strict")
    return {"ok": True}


@app.get("/ui/v1/session", tags=["ui"])
def ui_session(oko_session: str | None = Cookie(default=None)) -> dict:
    return {"authenticated": _session_ok(oko_session)}


@app.delete("/ui/v1/session", tags=["ui"])
def ui_logout(response: Response) -> dict:
    response.delete_cookie(SESSION_COOKIE)
    return {"ok": True}


@app.get("/ui/v1/health", tags=["ui"])
def ui_health() -> dict:
    return {"ok": True, "version": VERSION, "detectors": list(settings.detectors), "local_only": True}


@app.get("/ui/v1/status", dependencies=UI_AUTH, tags=["ui"])
def ui_status() -> dict:
    return jobs().status_info()


@app.get("/ui/v1/catalog", tags=["ui"])
def ui_catalog() -> dict:
    return catalog_payload()


@app.post("/ui/v1/analyze", dependencies=UI_AUTH, tags=["ui"])
async def ui_analyze(
    file: UploadFile | None = File(default=None),
    branch: str = Form(default=""), desk: str = Form(default=""), shot_date: str = Form(default=""),
    batch_id: str = Form(default=""),
) -> dict:
    meta = {"branch": branch, "desk": desk, "shot_date": shot_date, "batch_id": batch_id}
    return await _accept_upload(file, "ui", meta)


@app.get("/ui/v1/history", dependencies=UI_AUTH, tags=["ui"])
def ui_history() -> dict:
    return {"items": jobs().history()}


@app.get("/ui/v1/jobs/status", dependencies=UI_AUTH, tags=["ui"])
def ui_jobs_status(ids: str = Query(default="")) -> dict:
    return {"items": jobs().statuses([x for x in ids.split(",") if x.strip()])}


@app.get("/ui/v1/jobs/{job_id}", dependencies=UI_AUTH, tags=["ui"])
def ui_job(job_id: str) -> dict:
    m = jobs()
    job = m.get(job_id)
    if job is None:
        raise HTTPException(404, "Задача не найдена.")
    return ui_view(job, m, settings)


@app.get("/ui/v1/jobs/{job_id}/api", dependencies=UI_AUTH, tags=["ui"])
def ui_job_api(job_id: str) -> dict:
    job = jobs().get(job_id)
    if job is None:
        raise HTTPException(404, "Задача не найдена.")
    return api_view(job, settings)


@app.post("/ui/v1/jobs/{job_id}/seen", dependencies=UI_AUTH, tags=["ui"])
def ui_job_seen(job_id: str) -> dict:
    if not jobs().mark_seen(job_id):
        raise HTTPException(404, "Задача не найдена.")
    return {"ok": True}


class ReviewIn(BaseModel):
    key: str
    decision: str | None = None   # confirmed | false_positive | null
    comment: str = ""


@app.post("/ui/v1/jobs/{job_id}/review", dependencies=UI_AUTH, tags=["ui"])
def ui_job_review(job_id: str, body: ReviewIn) -> dict:
    reviews = jobs().set_review(job_id, body.key, body.decision, body.comment)
    if reviews is None:
        raise HTTPException(404, "Задача или нарушение не найдены.")
    return {"reviews": reviews}


@app.get("/ui/v1/jobs/{job_id}/clip/{key}", dependencies=UI_AUTH, tags=["ui"])
def ui_job_clip(job_id: str, key: str) -> dict:
    clip = jobs().clip(job_id, key)
    if clip is None:
        raise HTTPException(404, "Клип для этого эпизода не сохранён.")
    return clip
