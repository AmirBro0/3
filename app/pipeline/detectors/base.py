"""Контракт детектора. Сюда команда подключает CV-модели и VLM.

Жизненный цикл на одно видео:
    begin(ctx) → on_sample(sample, ctx) для каждого кадра (sample_fps) → end(ctx) → [Candidate]

Правила для детекторов:
  * rule_id — только из app/rules/catalog.py. Пункт и документ детектор не пишет.
  * observed — только то, что видно: «в 0:44 кассир встаёт и выходит из кабины».
    Без «украл», «умышленно», догадок о сумме и личности.
  * Тяжёлые модели грузите один раз на процесс (на уровне модуля), а не в begin().
  * Следите за ctx.time_left(): ответ жюри нужен не позже чем через 5 минут после загрузки.
"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field

import numpy as np

from ...config import Settings
from ..video import Sample, VideoInfo, read_frames_at


@dataclass
class Box:
    """Рамка в долях кадра (0..1). kind="face" — область размывается и не подписывается."""

    x1: float
    y1: float
    x2: float
    y2: float
    label: str = ""
    kind: str = "object"


@dataclass
class Candidate:
    rule_id: str
    t_start: float
    t_end: float | None = None
    timecode: float | None = None          # момент нарушения; по умолчанию t_start
    confidence: float = 0.5
    observed: str = ""
    evidence_times: list[float] | None = None  # 1–3 момента, первый — главный кадр
    boxes: dict[float, list[Box]] = field(default_factory=dict)  # время кадра → рамки
    source: str = ""
    meta: dict = field(default_factory=dict)

    @property
    def tc(self) -> float:
        return self.t_start if self.timecode is None else self.timecode


class AnalysisContext:
    def __init__(self, info: VideoInfo, settings: Settings, deadline: float, log: logging.Logger):
        self.info = info
        self.settings = settings
        self.deadline = deadline  # time.monotonic()
        self.log = log
        self.notes: list[str] = []

    def time_left(self) -> float:
        return self.deadline - time.monotonic()

    def read_frames(self, times: list[float]) -> dict[float, tuple[float, np.ndarray]]:
        """Точные кадры по времени (например, клип для VLM вокруг кандидата)."""
        return read_frames_at(self.info, times)


class Detector:
    name = "base"

    def begin(self, ctx: AnalysisContext) -> None:
        pass

    def on_sample(self, sample: Sample, ctx: AnalysisContext) -> None:
        pass

    def end(self, ctx: AnalysisContext) -> list[Candidate]:
        return []
