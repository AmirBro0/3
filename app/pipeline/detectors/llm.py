"""Детектор на модели команды: режет видео на куски и спрашивает модель про каждый.

Сама модель и её адрес — в app/llm.py и .env (OKO_LLM_URL / OKO_LLM_KEY / OKO_LLM_MODEL).
"""
from __future__ import annotations

from ... import llm
from .base import AnalysisContext, Candidate, Detector


class LLMDetector(Detector):
    name = "llm"

    def end(self, ctx: AnalysisContext) -> list[Candidate]:
        s = ctx.settings
        duration = ctx.info.duration
        out: list[Candidate] = []
        t0 = 0.0
        while t0 < duration:
            # не начинаем новый запрос, если он может не успеть до дедлайна
            if ctx.time_left() < s.reserve_sec + min(s.llm_timeout_sec, 10.0):
                ctx.log.warning("llm: остановились на %.0f с из %.0f — мало времени", t0, duration)
                break
            t1 = min(duration, t0 + s.llm_window_sec)
            step = (t1 - t0) / s.llm_frames
            times = [t0 + step * (i + 0.5) for i in range(s.llm_frames)]
            read = ctx.read_frames(times)
            frames = [read[t] for t in times if t in read]
            timeout = max(5.0, min(s.llm_timeout_sec, ctx.time_left() - s.reserve_sec))
            for v in llm.ask(frames, s, timeout):
                tc = v["timecode_sec"]
                out.append(Candidate(
                    rule_id=v["rule_id"], t_start=tc, timecode=tc, confidence=v["confidence"],
                    observed=v["observed"], evidence_times=[tc, max(0.0, tc - 1.0), min(duration, tc + 1.0)],
                    source="llm-mock" if llm.is_mock(s) else "llm", meta={"score": v.get("score", 0.0)},
                ))
            t0 = t1
        if llm.is_mock(s) and out:
            out = [max(out, key=lambda c: c.meta.get("score", 0.0))]  # заглушка: один пример на видео
        return out
