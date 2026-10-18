"""Реестр детекторов. Имя из OKO_DETECTORS → класс.

Как добавить свой детектор:
  1. Создайте файл рядом (например, cv_rules.py) с классом-наследником Detector.
  2. Добавьте его в REGISTRY ниже.
  3. Перечислите имя в OKO_DETECTORS через запятую.
"""
from __future__ import annotations

import logging

from .base import AnalysisContext, Box, Candidate, Detector
from .demo import DemoDetector
from .llm import LLMDetector
from .obstruction import ObstructionDetector

log = logging.getLogger("oko.detectors")

REGISTRY: dict[str, type[Detector]] = {
    ObstructionDetector.name: ObstructionDetector,
    LLMDetector.name: LLMDetector,     # модель команды; адрес — OKO_LLM_URL в .env
    DemoDetector.name: DemoDetector,   # только для проверки интерфейса
}


def build_detectors(names: tuple[str, ...]) -> list[Detector]:
    detectors = []
    for name in names:
        cls = REGISTRY.get(name)
        if cls is None:
            log.warning("Неизвестный детектор %r пропущен. Доступны: %s", name, ", ".join(REGISTRY))
            continue
        detectors.append(cls())
    return detectors


__all__ = ["AnalysisContext", "Box", "Candidate", "Detector", "REGISTRY", "build_detectors"]
