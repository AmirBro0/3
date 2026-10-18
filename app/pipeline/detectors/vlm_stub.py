"""Заготовка детектора на локальной VLM (например, Qwen3-VL-4B/8B, Apache-2.0).

Не подключён по умолчанию. Чтобы включить: реализуйте _ask(), зарегистрируйте класс
в detectors/__init__.py и добавьте "vlm" в OKO_DETECTORS.

Схема работы (2 канала):
  1. Проверка кандидатов: другие детекторы кладут гипотезы в ctx.notes / meta,
     VLM смотрит клип ±2 с и подтверждает или снимает — меньше ложных срабатываний.
  2. Обход окнами: каждые ~4 с берём 8 кадров и спрашиваем по чек-листу из каталога —
     так ловятся типы, которых не было в обучении (FAQ п. 9).

Модель должна выбрать rule_id из каталога или "X00". Пункт и документ она не пишет.
Видео, кадры и описания НЕ отправляются во внешние сервисы (ТЗ, раздел 7).
"""
from __future__ import annotations

import json

from ...rules.catalog import RULES
from .base import AnalysisContext, Candidate, Detector

PROMPT = """Ты проверяешь видео с камеры над банковской кассой (вид сверху).
Кадры идут по порядку, у каждого есть время в секундах.
Опиши только то, что видно. Не определяй личность людей, называй их по роли:
кассир, клиент, инкассатор.
Если на кадрах есть одно из действий ниже, верни JSON:
{"rule_id": "...", "t_start": секунды, "confidence": 0..1, "observed": "что видно, одной фразой"}
Если ничего нет, верни {"rule_id": null}.
Список действий:
""" + "\n".join(f"{r.id}: {r.hint}" for r in RULES.values() if r.id != "X00")


class VLMDetector(Detector):
    name = "vlm"
    WINDOW_SEC = 4.0
    FRAMES_PER_WINDOW = 8

    def end(self, ctx: AnalysisContext) -> list[Candidate]:
        out: list[Candidate] = []
        t = 0.0
        while t < ctx.info.duration and ctx.time_left() > ctx.settings.reserve_sec + 10:
            times = [t + i * self.WINDOW_SEC / self.FRAMES_PER_WINDOW for i in range(self.FRAMES_PER_WINDOW)]
            frames = ctx.read_frames([x for x in times if x < ctx.info.duration])
            answer = self._ask(PROMPT, frames)
            if answer and answer.get("rule_id") in RULES:
                out.append(Candidate(
                    rule_id=answer["rule_id"],
                    t_start=float(answer.get("t_start", t)),
                    confidence=float(answer.get("confidence", 0.5)),
                    observed=str(answer.get("observed", "")),
                    source=self.name,
                ))
            t += self.WINDOW_SEC
        return out

    def _ask(self, prompt: str, frames: dict) -> dict | None:
        """TODO команды: вызвать локальную модель (transformers / vLLM на своём GPU) и разобрать JSON."""
        raise NotImplementedError

    @staticmethod
    def _parse(text: str) -> dict | None:
        start, end = text.find("{"), text.rfind("}")
        if start < 0 or end <= start:
            return None
        try:
            return json.loads(text[start:end + 1])
        except json.JSONDecodeError:
            return None
