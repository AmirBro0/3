"""Оркестратор анализа: видео → детекторы → отбор → кадры-доказательства → вердикт."""
from __future__ import annotations

import logging
import math
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

import cv2
import numpy as np

from ..config import Settings
from ..rules.catalog import RuleType, build_description, get_rule, rule_to_dict
from .detectors import AnalysisContext, Candidate, build_detectors
from .evidence import encode_jpeg_b64, render_evidence, thumb_b64
from .video import VideoInfo, clamp_time, iter_samples, probe, read_frames_at

Progress = Callable[[str, float], None]


@dataclass
class EvidenceFrame:
    timestamp_sec: float
    image_base64: str


@dataclass
class Finding:
    rule: RuleType
    timecode: float
    t_end: float | None
    confidence: float
    observed: str
    description: str
    source: str
    status: str                       # "reported" — в API; "review" — только в интерфейсе
    review_reason: str | None = None
    frames: list[EvidenceFrame] = field(default_factory=list)
    candidate: Candidate | None = None

    def to_api(self, extra: bool = False) -> dict:
        item = {
            "type": self.rule.title,
            "timecode_sec": round(self.timecode, 2),
            "description": self.description,
            "evidence_frames": [
                {"timestamp_sec": round(f.timestamp_sec, 2), "image_base64": f.image_base64}
                for f in self.frames
            ],
        }
        if extra:
            item["rule_id"] = self.rule.id
            item["confidence"] = round(self.confidence, 3)
        return item

    def to_ui(self) -> dict:
        return {
            "rule": rule_to_dict(self.rule),
            "timecode": round(self.timecode, 2),
            "t_end": None if self.t_end is None else round(self.t_end, 2),
            "confidence": round(self.confidence, 3),
            "observed": self.observed,
            "description": self.description,
            "source": self.source,
            "status": self.status,
            "review_reason": self.review_reason,
            "frames": [
                {"timestamp_sec": round(f.timestamp_sec, 2), "image_base64": f.image_base64}
                for f in self.frames
            ],
        }


@dataclass
class AnalysisResult:
    verdict: str
    findings: list[Finding]
    review: list[Finding]
    video: dict
    activity: list[float]
    thumbs: list[str]
    timings: dict
    coverage_sec: float
    degraded: bool
    notes: list[str]
    detectors: list[str]


def analyze(
    path: Path,
    settings: Settings,
    deadline: float,
    progress: Progress | None = None,
    log: logging.Logger | None = None,
) -> AnalysisResult:
    log = log or logging.getLogger("oko.analyzer")
    progress = progress or (lambda stage, frac: None)
    started = time.monotonic()

    progress("decode", 0.02)
    info = probe(path)
    ctx = AnalysisContext(info, settings, deadline, log)

    active = []
    for det in build_detectors(settings.detectors):
        try:
            det.begin(ctx)
            active.append(det)
        except Exception:  # noqa: BLE001 — один сломанный детектор не должен ронять задачу
            log.exception("detector %s failed in begin()", det.name)
            ctx.notes.append(f"Детектор {det.name} отключён: ошибка запуска.")

    expected = max(1, int(info.duration * settings.sample_fps) + 1)
    thumbs: list[str] = []
    motion: dict[int, float] = {}
    prev = None
    last_t = 0.0

    def should_stop() -> bool:
        return ctx.time_left() < settings.reserve_sec

    for sample in iter_samples(info, settings.sample_fps, should_stop):
        sec = int(sample.t)
        if sec >= len(thumbs):
            b64 = thumb_b64(sample.small)
            while len(thumbs) <= sec:
                thumbs.append(b64)
        gray = cv2.cvtColor(cv2.resize(sample.small, (96, 54)), cv2.COLOR_BGR2GRAY).astype(np.float32)
        if prev is not None:
            motion[sec] = max(motion.get(sec, 0.0), float(np.abs(gray - prev).mean()))
        prev = gray

        for det in list(active):
            try:
                det.on_sample(sample, ctx)
            except Exception:  # noqa: BLE001
                log.exception("detector %s failed on frame %s", det.name, sample.frame_idx)
                ctx.notes.append(f"Детектор {det.name} отключён на {sample.t:.1f} с: ошибка обработки кадра.")
                active.remove(det)
        last_t = sample.t
        if sample.index % 5 == 0:
            progress("detect", 0.05 + 0.75 * min(1.0, (sample.index + 1) / expected))

    coverage = min(info.duration, last_t + 1.0 / settings.sample_fps)
    degraded = coverage < info.duration - 0.5
    if degraded:
        ctx.notes.append(
            f"Проанализированы первые {coverage:.0f} с из {info.duration:.0f} с: не хватило времени на всё видео."
        )
    t_detect = time.monotonic()

    candidates: list[Candidate] = []
    for det in active:
        try:
            for cand in det.end(ctx):
                cand.source = cand.source or det.name
                candidates.append(cand)
        except NotImplementedError:
            ctx.notes.append(f"Детектор {det.name} ещё не реализован.")
        except Exception:  # noqa: BLE001
            log.exception("detector %s failed in end()", det.name)
            ctx.notes.append(f"Детектор {det.name} завершился с ошибкой.")

    progress("evidence", 0.85)
    reported, review = _select(_merge(_sanitize(candidates, info)), settings)
    _attach_evidence(reported + review, info, settings, ctx)
    progress("done", 1.0)

    finished = time.monotonic()
    duration_secs = max(1, math.ceil(info.duration))
    raw = np.array([motion.get(i, 0.0) for i in range(duration_secs)], dtype=np.float32)
    scale = float(np.percentile(raw, 95)) if raw.size and raw.max() > 0 else 1.0
    activity = [round(float(x), 3) for x in np.clip(raw / max(scale, 1e-6), 0, 1)]

    return AnalysisResult(
        verdict="violation" if reported else "no_violation",
        findings=reported,
        review=review,
        video=info.to_dict(),
        activity=activity,
        thumbs=thumbs,
        timings={
            "total_sec": round(finished - started, 2),
            "detect_sec": round(t_detect - started, 2),
            "evidence_sec": round(finished - t_detect, 2),
        },
        coverage_sec=round(coverage, 2),
        degraded=degraded,
        notes=ctx.notes,
        detectors=[d.name for d in active],
    )


def _sanitize(cands: list[Candidate], info: VideoInfo) -> list[Candidate]:
    out = []
    for c in cands:
        c.t_start = clamp_time(info, float(c.t_start))
        c.t_end = None if c.t_end is None else clamp_time(info, float(c.t_end))
        c.timecode = None if c.timecode is None else clamp_time(info, float(c.timecode))
        c.confidence = float(min(1.0, max(0.0, c.confidence)))
        if get_rule(c.rule_id).id != c.rule_id:
            c.meta["original_rule_id"] = c.rule_id
            c.rule_id = "X00"
        out.append(c)
    return out


def _merge(cands: list[Candidate], gap: float = 2.0) -> list[Candidate]:
    """Одно и то же нарушение от разных кадров/детекторов склеиваем в одно событие."""
    merged: list[Candidate] = []
    for c in sorted(cands, key=lambda c: (c.rule_id, c.tc)):
        last = merged[-1] if merged else None
        if last and last.rule_id == c.rule_id and c.tc - (last.t_end or last.tc) <= gap:
            best = c if c.confidence > last.confidence else last
            last.t_end = max(x for x in (last.t_end, c.t_end, c.tc) if x is not None)
            last.observed = best.observed or last.observed
            last.evidence_times = best.evidence_times or last.evidence_times
            last.boxes = {**last.boxes, **c.boxes}
            last.confidence = max(last.confidence, c.confidence)
            last.source = ",".join(sorted(set(f"{last.source},{c.source}".split(",")) - {""}))
            continue
        merged.append(c)
    return merged


def _select(cands: list[Candidate], s: Settings) -> tuple[list[Finding], list[Finding]]:
    reported: list[Finding] = []
    review: list[Finding] = []
    for c in cands:
        if c.confidence < s.review_threshold:
            continue
        rule = get_rule(c.rule_id)
        observed = c.observed.strip() or f"На видео: {rule.hint.rstrip('.').lower()}"
        finding = Finding(
            rule=rule,
            timecode=c.tc,
            t_end=c.t_end,
            confidence=c.confidence,
            observed=observed,
            description=build_description(rule, observed),
            source=c.source,
            status="reported",
            candidate=c,
        )
        if not rule.is_reportable:
            finding.status, finding.review_reason = "review", "Тип не сопоставлен с проверенным пунктом нормы."
            review.append(finding)
        elif c.confidence < s.threshold:
            finding.status, finding.review_reason = "review", "Низкая уверенность — нужен взгляд человека."
            review.append(finding)
        else:
            reported.append(finding)

    if len(reported) > s.max_violations:
        reported = sorted(reported, key=lambda f: -f.confidence)[: s.max_violations]
    reported.sort(key=lambda f: f.timecode)
    review = sorted(review, key=lambda f: -f.confidence)[:10]
    review.sort(key=lambda f: f.timecode)
    return reported, review


def _evidence_times(f: Finding, info: VideoInfo, limit: int) -> list[float]:
    c = f.candidate
    base = (c.evidence_times if c and c.evidence_times else None) or [f.timecode, f.timecode - 1.0, f.timecode + 1.0]
    out: list[float] = []
    for t in base:
        t = clamp_time(info, t)
        if all(abs(t - x) > 0.05 for x in out):
            out.append(t)
        if len(out) >= limit:
            break
    return out or [clamp_time(info, f.timecode)]


def _attach_evidence(items: list[Finding], info: VideoInfo, s: Settings, ctx: AnalysisContext) -> None:
    if not items:
        return
    limit = 3 if ctx.time_left() > 5 else 1
    plan = {id(f): _evidence_times(f, info, limit) for f in items}
    frames = read_frames_at(info, [t for ts in plan.values() for t in ts])
    for f in items:
        boxes_by_t = f.candidate.boxes if f.candidate else {}
        for t in plan[id(f)]:
            if t not in frames:
                continue
            actual_t, frame = frames[t]
            near = [b for bt, bs in boxes_by_t.items() if abs(bt - t) <= 0.25 for b in bs]
            img = render_evidence(frame, actual_t, f.rule.id, near, s)
            f.frames.append(EvidenceFrame(actual_t, encode_jpeg_b64(img, s.jpeg_quality)))
