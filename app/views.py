"""Представления задачи: строгий ответ API для жюри и расширенный — для интерфейса."""
from __future__ import annotations

import time

from .config import Settings
from .jobs import STAGES, Job, JobManager


def api_view(job: Job, s: Settings) -> dict:
    """Ровно схема из раздела 10 ТЗ. «В очереди» для жюри тоже processing."""
    if job.stored_api is not None:
        return job.stored_api
    status = "processing" if job.status in ("queued", "processing") else job.status
    body: dict = {"job_id": job.id, "status": status, "verdict": None, "violations": []}
    if job.status == "done" and job.result is not None:
        body["verdict"] = job.result.verdict
        body["violations"] = [f.to_api(s.api_extra_fields) for f in job.result.findings]
    elif job.status == "failed":
        body["error"] = job.error or "Не удалось обработать видео."
    return body


def ui_view(job: Job, manager: JobManager, s: Settings, with_meta: bool = True) -> dict:
    if job.stored_ui is not None:
        data = dict(job.stored_ui)
    else:
        now = time.monotonic()
        elapsed = (job.finished_mono or now) - job.created_mono
        data = {
            "job_id": job.id,
            "status": job.status,
            "stage": job.stage,
            "stage_label": STAGES.get(job.stage, job.stage),
            "progress": job.progress,
            "queue_position": manager.queue_position(job) if job.status == "queued" else 0,
            "elapsed_sec": round(elapsed, 1),
            "deadline_sec": s.deadline_sec,
            "filename": job.filename,
            "error": job.error,
            "result": None,
        }
        r = job.result
        if job.status == "done" and r is not None:
            data["result"] = {
                "verdict": r.verdict,
                "violations": [{**f.to_ui(), "key": f"v{i}"} for i, f in enumerate(r.findings)],
                "review": [{**f.to_ui(), "key": f"r{i}"} for i, f in enumerate(r.review)],
                "video": r.video,
                "activity": r.activity,
                "thumbs": r.thumbs,
                "timings": r.timings,
                "coverage_sec": r.coverage_sec,
                "degraded": r.degraded,
                "notes": r.notes,
                "detectors": r.detectors,
                "threshold": s.threshold,
            }
    if with_meta:
        data["meta"] = manager.record(job.id)
    return data
