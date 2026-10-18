"""Детектор на модели команды: режет видео на куски и спрашивает модель про каждый.

Куски уходят в модель параллельно (OKO_LLM_PARALLEL), поэтому длинное видео
проверяется почти так же быстро, как короткое. Сама модель и её адрес — в
app/llm.py и .env (OKO_LLM_URL / OKO_LLM_KEY / OKO_LLM_MODEL).
"""
from __future__ import annotations

import math
from concurrent.futures import ThreadPoolExecutor

from ... import llm
from .base import AnalysisContext, Candidate, Detector


class LLMDetector(Detector):
    name = "llm"

    def end(self, ctx: AnalysisContext) -> list[Candidate]:
        s = ctx.settings
        duration = ctx.info.duration
        # 1) кадры всех кусков читаем заранее (чтение видео — в одном потоке)
        windows: list[list] = []
        t0 = 0.0
        while t0 < duration:
            t1 = min(duration, t0 + s.llm_window_sec)
            step = (t1 - t0) / s.llm_frames
            times = [t0 + step * (i + 0.5) for i in range(s.llm_frames)]
            read = ctx.read_frames(times)
            windows.append([read[t] for t in times if t in read])
            t0 = t1
        if not windows:
            return []
        # 2) запросы к модели — параллельно, с общим лимитом времени до дедлайна
        budget = ctx.time_left() - s.reserve_sec
        rounds = math.ceil(len(windows) / max(1, s.llm_parallel))
        timeout = min(s.llm_timeout_sec, budget / rounds)
        if timeout < 3:
            ctx.log.warning("llm: пропуск — до дедлайна осталось %.0f с", budget)
            return []
        with ThreadPoolExecutor(max_workers=max(1, s.llm_parallel)) as pool:
            answers = list(pool.map(lambda frames: llm.ask(frames, s, timeout), windows))

        out: list[Candidate] = []
        for items in answers:
            for v in items:
                tc = v["timecode_sec"]
                out.append(Candidate(
                    rule_id=v["rule_id"], t_start=tc, timecode=tc, confidence=v["confidence"],
                    observed=v["observed"], evidence_times=[tc, max(0.0, tc - 1.0), min(duration, tc + 1.0)],
                    source="llm-mock" if llm.is_mock(s) else "llm", meta={"score": v.get("score", 0.0)},
                ))
        if llm.is_mock(s) and out:
            out = [max(out, key=lambda c: c.meta.get("score", 0.0))]  # заглушка: один пример на видео
        return out
