"""Клипы для кнопки «Смотреть»: кадры ±3 с вокруг таймкода.

Нужны, когда браузер не может проиграть исходный .mov (например, HEVC) и когда отчёт
открыт из истории, а видео уже удалено с сервера. Делаются только для загрузок через
интерфейс и уже после ответа: на время ответа жюри не влияют.
"""
from __future__ import annotations

from pathlib import Path

from ..config import Settings
from .evidence import encode_jpeg_b64
from .video import probe, read_window, resize_to_width

SPAN_SEC = 3.0
CLIP_FPS = 4.0
CLIP_WIDTH = 480


def extract_clips(path: Path, moments: dict[str, float], settings: Settings) -> dict[str, dict]:
    """moments: {"v0": 19.4, "r0": 3.2} → {"v0": {"fps", "t0", "t1", "tc", "frames": [{t, b64}]}}."""
    if not moments:
        return {}
    info = probe(path)
    clips: dict[str, dict] = {}
    for key, tc in moments.items():
        frames = read_window(info, tc - SPAN_SEC, tc + SPAN_SEC, CLIP_FPS)
        if not frames:
            continue
        clips[key] = {
            "fps": CLIP_FPS,
            "tc": round(tc, 2),
            "t0": round(frames[0][0], 2),
            "t1": round(frames[-1][0], 2),
            "frames": [
                {"t": round(t, 2), "b64": encode_jpeg_b64(resize_to_width(f, CLIP_WIDTH), 70)}
                for t, f in frames
            ],
        }
    return clips
