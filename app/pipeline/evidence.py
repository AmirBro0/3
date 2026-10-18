"""Кадры-доказательства: рамки, пикселизация лиц, подпись с таймкодом, JPEG в base64."""
from __future__ import annotations

import base64
import logging
from functools import lru_cache
from pathlib import Path

import cv2
import numpy as np

from ..config import Settings
from .detectors.base import Box
from .video import resize_to_width

log = logging.getLogger("oko.evidence")

RED = (58, 58, 224)       # BGR
INK = (28, 17, 19)
WHITE = (255, 255, 255)

FONT_CANDIDATES = (
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/dejavu/DejaVuSans-Bold.ttf",
    "/Library/Fonts/Arial Unicode.ttf",
    "C:/Windows/Fonts/arialbd.ttf",
)

_TRANSLIT = dict(zip(
    "абвгдеёжзийклмнопрстуфхцчшщъыьэюя",
    ["a", "b", "v", "g", "d", "e", "e", "zh", "z", "i", "y", "k", "l", "m", "n", "o", "p", "r", "s", "t",
     "u", "f", "h", "ts", "ch", "sh", "sch", "", "y", "", "e", "yu", "ya"],
))


@lru_cache(maxsize=8)
def _pil_font(size: int):
    try:
        from PIL import ImageFont
    except ImportError:
        return None
    for path in FONT_CANDIDATES:
        if Path(path).exists():
            try:
                return ImageFont.truetype(path, size)
            except OSError:
                continue
    return None


@lru_cache(maxsize=1)
def _face_cascade():
    if not hasattr(cv2, "CascadeClassifier") or not hasattr(cv2, "data"):
        return None
    cascade = cv2.CascadeClassifier(cv2.data.haarcascades + "haarcascade_frontalface_default.xml")
    return None if cascade.empty() else cascade


def _translit(text: str) -> str:
    return "".join(_TRANSLIT.get(ch.lower(), ch) if ch.lower() in _TRANSLIT else ch for ch in text)


def _pixelate(img: np.ndarray, x1: int, y1: int, x2: int, y2: int) -> None:
    roi = img[y1:y2, x1:x2]
    if roi.size == 0:
        return
    h, w = roi.shape[:2]
    small = cv2.resize(roi, (max(1, w // 12), max(1, h // 12)), interpolation=cv2.INTER_AREA)
    img[y1:y2, x1:x2] = cv2.resize(small, (w, h), interpolation=cv2.INTER_NEAREST)


def _faces(img: np.ndarray) -> list[tuple[int, int, int, int]]:
    cascade = _face_cascade()
    if cascade is None:
        return []
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    min_side = max(24, int(img.shape[0] * 0.04))
    found = cascade.detectMultiScale(gray, scaleFactor=1.1, minNeighbors=7, minSize=(min_side, min_side))
    return [(int(x), int(y), int(x + w), int(y + h)) for (x, y, w, h) in found]


def _draw_labels(img: np.ndarray, labels: list[tuple[int, int, str, tuple[int, int, int]]], size: int) -> np.ndarray:
    """Подписи на плашках. Кириллица — через PIL, если найден шрифт; иначе транслитом."""
    font = _pil_font(size)
    if font is None:
        for x, y, text, color in labels:
            text = _translit(text)
            (tw, th), base = cv2.getTextSize(text, cv2.FONT_HERSHEY_SIMPLEX, size / 30, 2)
            cv2.rectangle(img, (x, y), (x + tw + 12, y + th + base + 10), color, -1)
            cv2.putText(img, text, (x + 6, y + th + 5), cv2.FONT_HERSHEY_SIMPLEX, size / 30, WHITE, 2, cv2.LINE_AA)
        return img
    from PIL import Image, ImageDraw

    pil = Image.fromarray(cv2.cvtColor(img, cv2.COLOR_BGR2RGB))
    draw = ImageDraw.Draw(pil)
    pad = max(4, size // 4)
    for x, y, text, color in labels:
        l, t, r, b = draw.textbbox((0, 0), text, font=font)
        w, h = r - l, b - t
        rgb = (color[2], color[1], color[0])
        draw.rectangle([x, y, x + w + 2 * pad, y + h + 2 * pad], fill=rgb)
        draw.text((x + pad - l, y + pad - t), text, font=font, fill=(255, 255, 255))
    return cv2.cvtColor(np.asarray(pil), cv2.COLOR_RGB2BGR)


def render_evidence(
    frame: np.ndarray,
    t: float,
    rule_id: str,
    boxes: list[Box],
    settings: Settings,
) -> np.ndarray:
    img = resize_to_width(frame, settings.evidence_max_width).copy()
    h, w = img.shape[:2]

    def px(b: Box) -> tuple[int, int, int, int]:
        x1, x2 = sorted((int(b.x1 * w), int(b.x2 * w)))
        y1, y2 = sorted((int(b.y1 * h), int(b.y2 * h)))
        return max(0, x1), max(0, y1), min(w, x2), min(h, y2)

    # 1. Приватность: пикселизация лиц (распознавания и идентификации нет — FAQ п. 29).
    if settings.face_blur != "off":
        regions = [px(b) for b in boxes if b.kind == "face"]
        if settings.face_blur == "auto":
            regions += _faces(img)
        for x1, y1, x2, y2 in regions:
            _pixelate(img, x1, y1, x2, y2)

    # 2. Рамки объектов.
    thick = max(2, w // 320)
    labels: list[tuple[int, int, str, tuple[int, int, int]]] = []
    font_size = max(14, w // 60)
    for b in boxes:
        if b.kind == "face":
            continue
        x1, y1, x2, y2 = px(b)
        cv2.rectangle(img, (x1, y1), (x2, y2), RED, thick)
        if b.label:
            labels.append((x1, max(0, y1 - font_size - 12), b.label, RED))

    # 3. Плашка с типом и временем — кадр понятен и вне интерфейса.
    minutes, seconds = divmod(max(0.0, t), 60)
    stamp = f"{int(minutes)}:{seconds:05.2f}".replace(".", ",")
    labels.append((thick * 3, thick * 3, f"OKO · {rule_id} · {stamp}", INK))
    return _draw_labels(img, labels, font_size)


def encode_jpeg_b64(img: np.ndarray, quality: int) -> str:
    ok, buf = cv2.imencode(".jpg", img, [int(cv2.IMWRITE_JPEG_QUALITY), int(quality)])
    if not ok:
        raise RuntimeError("Не удалось закодировать кадр в JPEG")
    return base64.b64encode(buf.tobytes()).decode("ascii")


def thumb_b64(small: np.ndarray, width: int = 144, quality: int = 60) -> str:
    return encode_jpeg_b64(resize_to_width(small, width), quality)
