"""Настройки сервиса OKO.

Всё задаётся переменными окружения (пример — в .env.example). Значения по умолчанию
подобраны под требования ТЗ: ответ жюри не позже чем через 5 минут после загрузки.
"""
from __future__ import annotations

import logging
import os
import secrets
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
VERSION = "0.2.0"

log = logging.getLogger("oko.config")


def _load_dotenv(path: Path) -> None:
    """Читает .env рядом с проектом (KEY=VALUE). Переменные окружения важнее файла."""
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


_load_dotenv(BASE_DIR / ".env")


def _env_str(name: str, default: str) -> str:
    raw = os.getenv(name)
    return raw.strip() if raw and raw.strip() else default


def _env_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None or not raw.strip():
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on", "да"}


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, default))
    except (TypeError, ValueError):
        return default


def _env_float(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, default))
    except (TypeError, ValueError):
        return default


@dataclass(frozen=True)
class Settings:
    data_dir: Path
    api_keys: tuple[str, ...]
    workers: int                # сколько видео обрабатывается одновременно (ограничено памятью GPU)
    deadline_sec: float         # бюджет от момента загрузки до готового ответа
    reserve_sec: float          # запас на кадры-доказательства и ответ
    max_upload_mb: int
    max_queue: int
    sample_fps: float           # сколько кадров в секунду смотрят детекторы
    threshold: float            # с этой уверенности нарушение попадает в API и вердикт
    review_threshold: float     # от этой уверенности до threshold — «на проверку» (только в интерфейсе)
    detectors: tuple[str, ...]
    keep_videos: bool           # хранить ли загруженные видео после обработки (по умолчанию нет)
    face_blur: str              # "auto" | "detector" | "off"
    evidence_max_width: int
    jpeg_quality: int
    api_extra_fields: bool      # добавлять ли в ответ API поля сверх схемы ТЗ
    max_violations: int
    # ── МОДЕЛЬ (LLM/VLM). Подключается в .env: OKO_LLM_URL, OKO_LLM_KEY, OKO_LLM_MODEL ──
    llm_url: str                # адрес OpenAI-совместимого API модели; пусто → заглушка (mock)
    llm_key: str                # ключ к этому API (если нужен)
    llm_model: str              # имя модели на сервере
    llm_timeout_sec: float      # сколько ждать один ответ модели
    llm_window_sec: float       # кусок видео на один запрос
    llm_frames: int             # сколько кадров из куска отправлять

    @property
    def uploads_dir(self) -> Path:
        return self.data_dir / "uploads"

    @property
    def jobs_dir(self) -> Path:
        return self.data_dir / "jobs"


def _load_api_keys(data_dir: Path) -> tuple[str, ...]:
    raw = os.getenv("OKO_API_KEYS", "")
    keys = tuple(k.strip() for k in raw.split(",") if k.strip())
    if keys:
        return keys
    key_file = data_dir / "api_key.txt"
    if key_file.exists():
        saved = key_file.read_text(encoding="utf-8").strip()
        if saved:
            return (saved,)
    key = "oko_" + secrets.token_urlsafe(24)
    key_file.write_text(key + "\n", encoding="utf-8")
    log.warning("OKO_API_KEYS не задан. Сгенерирован ключ и сохранён в %s", key_file)
    return (key,)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    data_dir = Path(_env_str("OKO_DATA_DIR", str(BASE_DIR / "data"))).resolve()
    for sub in ("", "uploads", "jobs"):
        (data_dir / sub).mkdir(parents=True, exist_ok=True)

    detectors = tuple(
        d.strip() for d in _env_str("OKO_DETECTORS", "obstruction,llm").split(",") if d.strip()
    )
    return Settings(
        data_dir=data_dir,
        api_keys=_load_api_keys(data_dir),
        workers=max(1, _env_int("OKO_WORKERS", 2)),
        deadline_sec=_env_float("OKO_DEADLINE_SEC", 240.0),
        reserve_sec=_env_float("OKO_RESERVE_SEC", 20.0),
        max_upload_mb=_env_int("OKO_MAX_UPLOAD_MB", 500),
        max_queue=_env_int("OKO_MAX_QUEUE", 50),
        sample_fps=_env_float("OKO_SAMPLE_FPS", 5.0),
        threshold=_env_float("OKO_THRESHOLD", 0.5),
        review_threshold=_env_float("OKO_REVIEW_THRESHOLD", 0.3),
        detectors=detectors,
        keep_videos=_env_bool("OKO_KEEP_VIDEOS", False),
        face_blur=_env_str("OKO_FACE_BLUR", "auto").lower(),
        evidence_max_width=_env_int("OKO_EVIDENCE_MAX_WIDTH", 1280),
        jpeg_quality=_env_int("OKO_JPEG_QUALITY", 85),
        api_extra_fields=_env_bool("OKO_API_EXTRA_FIELDS", False),
        max_violations=_env_int("OKO_MAX_VIOLATIONS", 10),
        llm_url=_env_str("OKO_LLM_URL", ""),
        llm_key=_env_str("OKO_LLM_KEY", ""),
        llm_model=_env_str("OKO_LLM_MODEL", "oko"),
        llm_timeout_sec=_env_float("OKO_LLM_TIMEOUT_SEC", 40.0),
        llm_window_sec=_env_float("OKO_LLM_WINDOW_SEC", 16.0),
        llm_frames=max(1, _env_int("OKO_LLM_FRAMES", 8)),
    )
