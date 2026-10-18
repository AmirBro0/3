"""Демо-детектор для проверки интерфейса и API без моделей.

Включается только явно: OKO_DETECTORS=obstruction,demo. На сдаче его быть не должно.
"""
from __future__ import annotations

from .base import AnalysisContext, Box, Candidate, Detector


class DemoDetector(Detector):
    name = "demo"

    def end(self, ctx: AnalysisContext) -> list[Candidate]:
        d = ctx.info.duration
        t = round(d * 0.35, 2)
        return [Candidate(
            rule_id="V03",
            t_start=t,
            t_end=round(min(d, t + 4.0), 2),
            confidence=0.9,
            observed=f"[ДЕМО] Тестовая отметка на {t:.1f} с, создана демо-детектором для проверки интерфейса",
            evidence_times=[t, max(0.0, t - 1.5)],
            boxes={t: [Box(0.35, 0.15, 0.65, 0.55, "зона кассира")]},
            source=self.name,
        )]
