"""Что за железо под сервисом: GPU (через torch или nvidia-smi) или CPU.

Показывается в интерфейсе и в /ui/v1/status, чтобы перед прогоном жюри было видно,
что модели действительно на GPU. OKO_DEVICE=cpu|cuda принудительно задаёт режим.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import time
from functools import lru_cache

_cache: dict = {"at": 0.0, "info": None}


@lru_cache(maxsize=1)
def preferred_device() -> str:
    forced = os.getenv("OKO_DEVICE", "auto").strip().lower()
    if forced in ("cpu", "cuda"):
        return forced
    try:
        import torch  # noqa: PLC0415 — torch необязателен

        if torch.cuda.is_available():
            return "cuda"
    except Exception:  # noqa: BLE001
        pass
    return "cuda" if shutil.which("nvidia-smi") else "cpu"


def device_info() -> dict:
    """Кэш на 15 с: nvidia-smi не дёргаем на каждый запрос."""
    now = time.monotonic()
    if _cache["info"] is not None and now - _cache["at"] < 15:
        return _cache["info"]
    info = {"device": preferred_device(), "name": "CPU", "memory": None}
    if info["device"] == "cuda" and shutil.which("nvidia-smi"):
        try:
            out = subprocess.run(
                ["nvidia-smi", "--query-gpu=name,memory.used,memory.total", "--format=csv,noheader,nounits"],
                capture_output=True, text=True, timeout=3,
            ).stdout.strip().splitlines()
            if out:
                name, used, total = [x.strip() for x in out[0].split(",")[:3]]
                info.update(name=name, memory=f"{used}/{total} MiB")
        except (OSError, subprocess.SubprocessError, ValueError):
            info["name"] = "GPU"
    _cache.update(at=now, info=info)
    return info
