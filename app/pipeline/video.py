"""Чтение видео: метаданные, проход по кадрам с заданной частотой, точные кадры по времени."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Iterator

import cv2
import numpy as np


class VideoError(RuntimeError):
    """Видео не удалось открыть или прочитать."""


@dataclass(frozen=True)
class VideoInfo:
    path: Path
    fps: float
    frame_count: int
    duration: float
    width: int
    height: int

    def to_dict(self) -> dict:
        return {
            "fps": round(self.fps, 3),
            "frames": self.frame_count,
            "duration_sec": round(self.duration, 3),
            "width": self.width,
            "height": self.height,
        }


@dataclass
class Sample:
    """Кадр, который видят детекторы. t — секунды от начала видео."""

    index: int
    frame_idx: int
    t: float
    frame: np.ndarray  # BGR, исходное разрешение
    small: np.ndarray  # BGR, ширина 320 px — для быстрых эвристик


def _open(path: Path) -> cv2.VideoCapture:
    cap = cv2.VideoCapture(str(path))
    if not cap.isOpened():
        raise VideoError("Не удалось открыть видео. Проверьте, что файл не повреждён и это .mov или .mp4.")
    return cap


def probe(path: Path) -> VideoInfo:
    cap = _open(path)
    try:
        fps = float(cap.get(cv2.CAP_PROP_FPS) or 0.0)
        if not (1.0 <= fps <= 240.0):
            fps = 30.0
        frame_count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
        width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH) or 0)
        height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT) or 0)
        ok, frame = cap.read()
        if not ok or frame is None:
            raise VideoError("В видео не найдено ни одного кадра.")
        height, width = frame.shape[:2]
        if frame_count <= 0:
            frame_count = 1
            while cap.grab():
                frame_count += 1
    finally:
        cap.release()
    return VideoInfo(path, fps, frame_count, frame_count / fps, width, height)


def resize_to_width(img: np.ndarray, width: int) -> np.ndarray:
    h, w = img.shape[:2]
    if w <= width:
        return img
    return cv2.resize(img, (width, max(1, round(h * width / w))), interpolation=cv2.INTER_AREA)


def iter_samples(
    info: VideoInfo,
    sample_fps: float,
    should_stop: Callable[[], bool] | None = None,
) -> Iterator[Sample]:
    """Последовательный проход по видео: декодируем всё, отдаём каждый N-й кадр."""
    cap = _open(info.path)
    step = max(1.0, info.fps / max(0.1, sample_fps))
    next_target = 0.0
    frame_idx = -1
    index = 0
    try:
        while True:
            if not cap.grab():
                break
            frame_idx += 1
            if frame_idx + 1e-6 < next_target:
                continue
            next_target += step
            ok, frame = cap.retrieve()
            if not ok or frame is None:
                continue
            yield Sample(index, frame_idx, frame_idx / info.fps, frame, resize_to_width(frame, 320))
            index += 1
            if should_stop and should_stop():
                break
    finally:
        cap.release()


def clamp_time(info: VideoInfo, t: float) -> float:
    last = max(0.0, (info.frame_count - 1) / info.fps)
    return min(max(0.0, t), last)


def read_frames_at(info: VideoInfo, times: list[float]) -> dict[float, tuple[float, np.ndarray]]:
    """Точные кадры для кадров-доказательств: {запрошенное t: (фактическое t, кадр)}."""
    result: dict[float, tuple[float, np.ndarray]] = {}
    if not times:
        return result
    cap = _open(info.path)
    try:
        for t in sorted(set(times)):
            idx = int(round(clamp_time(info, t) * info.fps))
            cap.set(cv2.CAP_PROP_POS_FRAMES, idx)
            ok, frame = cap.read()
            if not ok or frame is None:
                # Некоторые .mov плохо переносят переход к кадру: читаем последовательно с начала.
                frame, idx = _read_sequential(info, idx)
                if frame is None:
                    continue
            result[t] = (idx / info.fps, frame)
    finally:
        cap.release()
    return result


def read_window(info: VideoInfo, t0: float, t1: float, fps: float) -> list[tuple[float, np.ndarray]]:
    """Кадры отрезка [t0, t1] с шагом 1/fps: один переход к началу, дальше подряд (быстро)."""
    t0, t1 = clamp_time(info, t0), clamp_time(info, t1)
    start = int(round(t0 * info.fps))
    end = int(round(t1 * info.fps))
    step = max(1.0, info.fps / max(fps, 0.1))
    out: list[tuple[float, np.ndarray]] = []
    cap = _open(info.path)
    try:
        cap.set(cv2.CAP_PROP_POS_FRAMES, start)
        idx, target = start, float(start)
        while idx <= end:
            ok, frame = cap.read()
            if not ok or frame is None:
                break
            if idx + 1e-6 >= target:
                out.append((idx / info.fps, frame))
                target += step
            idx += 1
    finally:
        cap.release()
    return out


def _read_sequential(info: VideoInfo, target_idx: int) -> tuple[np.ndarray | None, int]:
    cap = _open(info.path)
    try:
        last = None
        idx = -1
        while idx < target_idx and cap.grab():
            idx += 1
        ok, frame = cap.retrieve()
        if ok:
            last = frame
        return last, max(idx, 0)
    finally:
        cap.release()
