"""Базовый детектор без обучения: камера перекрыта (V13).

Идея: у неподвижной камеры над кассой «нормальный» кадр всегда содержит детали (стол,
лоток, люди). Если объектив закрыт рукой, предметом или камеру затемнили, резко падают
контраст и энергия границ — по всему кадру или в большинстве клеток сетки 4×4.
Пороги относительные (к верхнему квартилю этого же видео), поэтому не зависят от ракурса.
"""
from __future__ import annotations

import cv2
import numpy as np

from ..video import Sample
from .base import AnalysisContext, Candidate, Detector


def fmt_clock(t: float) -> str:
    t = max(0.0, t)
    return f"{int(t // 60)}:{int(t % 60):02d}"


def fmt_dur(sec: float) -> str:
    return f"{sec:.1f}".replace(".", ",") + " с"


class ObstructionDetector(Detector):
    name = "obstruction"

    GRID = 4
    MIN_SEC = 1.0          # короче — не считаем (моргание света, рука прошла мимо)
    MAX_GAP_SEC = 0.4      # склеиваем куски, разорванные одним «светлым» кадром

    def begin(self, ctx: AnalysisContext) -> None:
        self.t: list[float] = []
        self.mu: list[float] = []
        self.sd: list[float] = []
        self.edge: list[float] = []
        self.cells: list[np.ndarray] = []

    def on_sample(self, sample: Sample, ctx: AnalysisContext) -> None:
        gray = cv2.cvtColor(sample.small, cv2.COLOR_BGR2GRAY)
        h, w = gray.shape
        g = cv2.resize(gray, (160, max(1, round(h * 160 / w))), interpolation=cv2.INTER_AREA)
        lap = np.abs(cv2.Laplacian(g, cv2.CV_32F, ksize=3))
        gh, gw = lap.shape
        cells = np.array([
            lap[r * gh // self.GRID:(r + 1) * gh // self.GRID, c * gw // self.GRID:(c + 1) * gw // self.GRID].mean()
            for r in range(self.GRID) for c in range(self.GRID)
        ], dtype=np.float32)
        self.t.append(sample.t)
        self.mu.append(float(g.mean()))
        self.sd.append(float(g.std()))
        self.edge.append(float(lap.mean()))
        self.cells.append(cells)

    def end(self, ctx: AnalysisContext) -> list[Candidate]:
        n = len(self.t)
        if n < 3:
            return []
        t = np.array(self.t)
        mu, sd, edge = np.array(self.mu), np.array(self.sd), np.array(self.edge)
        cells = np.stack(self.cells)

        ref_edge = max(np.percentile(edge, 75), 1e-3)
        ref_sd = max(np.percentile(sd, 75), 1e-3)
        ref_cells = np.percentile(cells, 75, axis=0)
        textured = ref_cells > 1.0  # клетки, где в норме есть детали

        full = (edge < 0.25 * ref_edge) & (sd < 0.45 * ref_sd)
        black = (mu < 14) & (sd < 10)
        flat = (edge < 0.6) & (sd < 6)
        if textured.sum() >= 4:
            dead = (cells[:, textured] < 0.2 * ref_cells[textured]).mean(axis=1)
            partial = dead >= 0.6
        else:
            partial = np.zeros(n, dtype=bool)
        covered = full | black | flat | partial

        candidates: list[Candidate] = []
        dt = 1.0 / max(ctx.settings.sample_fps, 0.1)
        for start, stop in self._segments(t, covered, dt):
            seg = slice(start, stop + 1)
            t0, t1 = float(t[start]), float(t[stop]) + dt
            dur = t1 - t0
            if dur < self.MIN_SEC:
                continue
            only_partial = not bool((full | black | flat)[seg].mean() >= 0.5)
            conf = min(0.95, 0.6 + 0.12 * dur) * (0.9 if only_partial else 1.0)
            how = (
                "объектив почти полностью перекрыт: в большей части кадра нет деталей"
                if only_partial else
                "изображение с камеры перекрыто: кадр тёмный или однотонный, без деталей"
            )
            observed = (
                f"С {fmt_clock(t0)} по {fmt_clock(t1)} ({fmt_dur(dur)}) {how}; "
                f"рабочая зона кассира на видео не просматривается"
            )
            info = ctx.info
            main = t0 + min(0.6, dur * 0.4)
            times = [main]
            if t0 - 1.0 >= 0:
                times.append(t0 - 1.0)
            if t1 + 0.6 <= info.duration - 1.0 / info.fps:
                times.append(t1 + 0.6)
            candidates.append(Candidate(
                rule_id="V13",
                t_start=t0,
                t_end=t1,
                confidence=round(conf, 3),
                observed=observed,
                evidence_times=times[:3],
                source=self.name,
                meta={"partial": only_partial, "duration_sec": round(dur, 2)},
            ))
        return candidates

    def _segments(self, t: np.ndarray, mask: np.ndarray, dt: float) -> list[tuple[int, int]]:
        segs: list[tuple[int, int]] = []
        start = None
        last = None
        for i, m in enumerate(mask):
            if m:
                if start is None:
                    start = i
                elif last is not None and t[i] - t[last] > self.MAX_GAP_SEC + dt:
                    segs.append((start, last))
                    start = i
                last = i
        if start is not None and last is not None:
            segs.append((start, last))
        return segs
