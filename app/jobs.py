"""Очередь задач и журнал проверок.

* Очередь: пул из OKO_WORKERS потоков. Бюджет времени считается от загрузки, а не от
  начала обработки: если жюри пришлёт пачку, хвост очереди закончит анализ раньше,
  но всё равно ответит до 5-минутного лимита.
* Журнал: на каждую проверку — папка data/jobs/<id>/ с файлами
    api.json   — ответ API строго по схеме ТЗ;
    ui.json    — расширенный отчёт для интерфейса (кадры, превью);
    meta.json  — запись журнала: отделение, касса, дата, вердикт, решения проверяющего;
    clips.json — кадры ±3 с для кнопки «Смотреть» (только загрузки через интерфейс).
  Видео после анализа удаляется (OKO_KEEP_VIDEOS=false).
"""
from __future__ import annotations

import json
import logging
import os
import re
import secrets
import statistics
import threading
import time
from collections import OrderedDict
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from .config import Settings
from .device import device_info
from .pipeline.analyzer import AnalysisResult, analyze
from .pipeline.clips import extract_clips
from .pipeline.video import VideoError

log = logging.getLogger("oko.jobs")

STAGES = {
    "queued": "В очереди",
    "decode": "Чтение видео",
    "detect": "Поиск нарушений",
    "evidence": "Кадры-доказательства",
    "done": "Готово",
    "failed": "Ошибка",
}
DECISIONS = {"confirmed", "false_positive"}
DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def write_json(path: Path, data: dict) -> None:
    """Запись через временный файл: при сбое не остаётся полузаписанного JSON."""
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    os.replace(tmp, path)


def clean_meta(raw: dict) -> dict:
    def text(v: object, limit: int = 80) -> str:
        return str(v or "").strip()[:limit]

    shot = text(raw.get("shot_date"), 10)
    return {
        "branch": text(raw.get("branch")),
        "desk": text(raw.get("desk"), 40),
        "shot_date": shot if DATE_RE.match(shot) else "",
        "batch_id": re.sub(r"[^A-Za-z0-9_-]", "", text(raw.get("batch_id"), 40)),
    }


@dataclass
class Job:
    id: str
    filename: str
    path: Path
    origin: str                       # "api" | "ui"
    created_mono: float = field(default_factory=time.monotonic)
    status: str = "queued"            # queued | processing | done | failed
    stage: str = "queued"
    progress: float = 0.0
    error: str | None = None
    finished_mono: float | None = None
    result: AnalysisResult | None = None
    stored_api: dict | None = None    # прочитано с диска после перезапуска
    stored_ui: dict | None = None


class JobManager:
    def __init__(self, settings: Settings):
        self.s = settings
        self.jobs: OrderedDict[str, Job] = OrderedDict()
        self.index: dict[str, dict] = {}
        self.lock = threading.RLock()
        self.pool = ThreadPoolExecutor(max_workers=settings.workers, thread_name_prefix="oko-worker")
        self._stop = threading.Event()
        self._load_index()
        self._watchdog = threading.Thread(target=self._watch, name="oko-watchdog", daemon=True)
        self._watchdog.start()

    # ── журнал ───────────────────────────────────────────────────────────────
    def _folder(self, job_id: str) -> Path:
        return self.s.jobs_dir / job_id

    def _load_index(self) -> None:
        for path in self.s.jobs_dir.glob("*/meta.json"):
            try:
                rec = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            if rec.get("status") in ("queued", "processing"):
                rec.update(status="failed", error="Сервис перезапустили во время анализа.")
            self.index[rec["job_id"]] = rec
        log.info("журнал: %d проверок", len(self.index))

    def _save_meta(self, job_id: str) -> None:
        rec = self.index.get(job_id)
        if rec is None:
            return
        folder = self._folder(job_id)
        folder.mkdir(parents=True, exist_ok=True)
        write_json(folder / "meta.json", rec)

    def _update(self, job_id: str, **fields) -> None:
        with self.lock:
            rec = self.index.get(job_id)
            if rec is None:
                return
            rec.update(fields)
            self._save_meta(job_id)

    # ── приём задач ──────────────────────────────────────────────────────────
    def new_id(self) -> str:
        while True:
            job_id = secrets.token_hex(4)
            if job_id not in self.index and not self._folder(job_id).exists():
                return job_id

    def active_count(self) -> int:
        with self.lock:
            return sum(1 for j in self.jobs.values() if j.status in ("queued", "processing"))

    def submit(self, job_id: str, path: Path, filename: str, origin: str, meta: dict) -> Job:
        job = Job(id=job_id, filename=filename, path=path, origin=origin)
        meta = clean_meta(meta)
        with self.lock:
            self.jobs[job_id] = job
            self.index[job_id] = {
                "job_id": job_id, "created_at": now_iso(), "filename": filename, "origin": origin,
                **meta,
                "status": "queued", "verdict": None, "error": None,
                "duration_sec": None, "processing_sec": None,
                "items": [], "reviews": {}, "seen": False, "seen_at": None, "clips_ready": False,
            }
            self._save_meta(job_id)
            self._evict()
        self.pool.submit(self._run, job)
        log.info("job %s queued (%s, %s)", job_id, filename, origin)
        return job

    def _evict(self) -> None:
        """В памяти держим последние 200 задач; старые готовые читаются с диска."""
        while len(self.jobs) > 200:
            old_id, old = next(iter(self.jobs.items()))
            if old.status in ("queued", "processing"):
                break
            self.jobs.pop(old_id)

    # ── чтение ───────────────────────────────────────────────────────────────
    def get(self, job_id: str) -> Job | None:
        if not job_id.isalnum() or len(job_id) > 32:
            return None
        with self.lock:
            job = self.jobs.get(job_id)
        if job:
            return job
        folder = self._folder(job_id)
        if (folder / "api.json").exists():
            stored = json.loads((folder / "api.json").read_text(encoding="utf-8"))
            job = Job(id=job_id, filename="", path=Path(), origin="disk", status=stored.get("status", "done"),
                      stage="done", progress=1.0)
            job.stored_api = stored
            ui_file = folder / "ui.json"
            job.stored_ui = json.loads(ui_file.read_text(encoding="utf-8")) if ui_file.exists() else None
            return job
        return None

    def record(self, job_id: str) -> dict | None:
        with self.lock:
            rec = self.index.get(job_id)
            return dict(rec) if rec else None

    def queue_position(self, job: Job) -> int:
        with self.lock:
            queued = [j.id for j in self.jobs.values() if j.status == "queued"]
        return queued.index(job.id) + 1 if job.id in queued else 0

    def statuses(self, ids: list[str]) -> list[dict]:
        out = []
        for job_id in ids[:100]:
            rec = self.record(job_id)
            if rec is None:
                out.append({"job_id": job_id, "status": "missing"})
                continue
            with self.lock:
                job = self.jobs.get(job_id)
            item = {
                "job_id": job_id, "status": rec["status"], "filename": rec["filename"],
                "verdict": rec["verdict"], "error": rec["error"],
                "n_violations": sum(1 for i in rec["items"] if i["status"] == "reported"),
                "stage": job.stage if job else rec["status"],
                "stage_label": STAGES.get(job.stage if job else rec["status"], ""),
                "progress": job.progress if job else (1.0 if rec["status"] == "done" else 0.0),
                "queue_position": self.queue_position(job) if job and job.status == "queued" else 0,
            }
            out.append(item)
        return out

    def history(self) -> list[dict]:
        with self.lock:
            items = [dict(r) for r in self.index.values()]
        items.sort(key=lambda r: r["created_at"], reverse=True)
        return items

    def clip(self, job_id: str, key: str) -> dict | None:
        path = self._folder(job_id) / "clips.json"
        if not job_id.isalnum() or not path.exists():
            return None
        try:
            return json.loads(path.read_text(encoding="utf-8")).get(key)
        except (OSError, json.JSONDecodeError):
            return None

    def status_info(self) -> dict:
        with self.lock:
            queued = sum(1 for j in self.jobs.values() if j.status == "queued")
            processing = sum(1 for j in self.jobs.values() if j.status == "processing")
            times = [r["processing_sec"] for r in self.index.values()
                     if r.get("status") == "done" and r.get("processing_sec") is not None]
        times = sorted(times[-50:])
        p95 = times[min(len(times) - 1, int(len(times) * 0.95))] if times else None
        return {
            "queued": queued, "processing": processing, "workers": self.s.workers,
            "deadline_sec": self.s.deadline_sec, "device": device_info(),
            "processing_sec": {
                "avg": round(statistics.mean(times), 1) if times else None,
                "p95": p95, "max": times[-1] if times else None, "n": len(times),
            },
        }

    # ── действия проверяющего ────────────────────────────────────────────────
    def mark_seen(self, job_id: str) -> bool:
        if self.record(job_id) is None:
            return False
        self._update(job_id, seen=True, seen_at=now_iso())
        return True

    def set_review(self, job_id: str, key: str, decision: str | None, comment: str) -> dict | None:
        with self.lock:
            rec = self.index.get(job_id)
            if rec is None or key not in {i["key"] for i in rec["items"]}:
                return None
            if decision not in DECISIONS:
                decision = None
            comment = (comment or "").strip()[:1000]
            if decision is None and not comment:
                rec["reviews"].pop(key, None)
            else:
                rec["reviews"][key] = {"decision": decision, "comment": comment, "at": now_iso()}
            self._save_meta(job_id)
            return dict(rec["reviews"])

    # ── обработка ────────────────────────────────────────────────────────────
    def _deadline(self, job: Job) -> float:
        return job.created_mono + self.s.deadline_sec

    def _run(self, job: Job) -> None:
        if job.status == "failed":
            return
        job.status, job.stage = "processing", "decode"
        self._update(job.id, status="processing")
        jlog = logging.getLogger(f"oko.job.{job.id}")

        def progress(stage: str, frac: float) -> None:
            if job.status == "processing":
                job.stage, job.progress = stage, round(frac, 3)

        try:
            result = analyze(job.path, self.s, self._deadline(job), progress, jlog)
            if job.status != "processing":  # сторож уже закрыл задачу по таймауту
                return
            job.result = result
            job.status, job.stage, job.progress = "done", "done", 1.0
            job.finished_mono = time.monotonic()
            items = (
                [self._item(f"v{i}", f, "reported") for i, f in enumerate(result.findings)]
                + [self._item(f"r{i}", f, "review") for i, f in enumerate(result.review)]
            )
            self._persist(job)
            self._update(job.id, status="done", verdict=result.verdict, items=items,
                         duration_sec=result.video.get("duration_sec"),
                         processing_sec=round(job.finished_mono - job.created_mono, 1))
            jlog.info("done: %s, %d violations, %.1fs", result.verdict, len(result.findings),
                      result.timings["total_sec"])
            if job.origin == "ui" and items:
                self._make_clips(job, {i["key"]: i["timecode"] for i in items})
        except VideoError as exc:
            self._fail(job, str(exc))
            jlog.warning("failed: %s", exc)
        except Exception as exc:  # noqa: BLE001
            self._fail(job, "Внутренняя ошибка анализа.")
            jlog.exception("crashed: %s", exc)
        finally:
            if not self.s.keep_videos:
                job.path.unlink(missing_ok=True)

    @staticmethod
    def _item(key: str, finding, status: str) -> dict:
        return {"key": key, "rule_id": finding.rule.id, "title": finding.rule.title,
                "timecode": round(finding.timecode, 2), "confidence": round(finding.confidence, 3),
                "status": status}

    def _make_clips(self, job: Job, moments: dict[str, float]) -> None:
        try:
            clips = extract_clips(job.path, moments, self.s)
            write_json(self._folder(job.id) / "clips.json", clips)
            self._update(job.id, clips_ready=bool(clips))
        except Exception:  # noqa: BLE001 — клипы не обязательны
            log.exception("clips failed for %s", job.id)

    def _fail(self, job: Job, message: str) -> None:
        job.status, job.stage, job.error = "failed", "failed", message
        job.finished_mono = time.monotonic()
        self._persist(job)
        self._update(job.id, status="failed", error=message)

    def _watch(self) -> None:
        grace = 40.0
        while not self._stop.wait(2.0):
            now = time.monotonic()
            with self.lock:
                stuck = [j for j in self.jobs.values()
                         if j.status in ("queued", "processing") and now > self._deadline(j) + grace]
            for job in stuck:
                log.error("job %s timed out", job.id)
                self._fail(job, "Обработка не уложилась в лимит времени.")

    def _persist(self, job: Job) -> None:
        from .views import api_view, ui_view  # локальный импорт: views зависит от Job

        folder = self._folder(job.id)
        try:
            folder.mkdir(parents=True, exist_ok=True)
            write_json(folder / "api.json", api_view(job, self.s))
            write_json(folder / "ui.json", ui_view(job, self, self.s, with_meta=False))
        except OSError:
            log.exception("cannot persist job %s", job.id)

    def shutdown(self) -> None:
        self._stop.set()
        self.pool.shutdown(wait=False, cancel_futures=True)
