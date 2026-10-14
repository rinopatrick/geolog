"""In-process background job registry.

Shared by every async endpoint: the batch-petrophysics, synthetic-seismogram and
electrofacies routes all create and update jobs through these helpers, and
/api/jobs reads them back.

Deliberately in-process and in-memory: the state is lost on restart and is not
shared between workers. That is adequate for a single-process deployment, which
is what this app targets. Running multiple uvicorn workers would mean a job
created on one worker is invisible to /api/jobs served by another — at which
point this needs a real queue.

shortcut: in-memory job registry, single process only. Upgrade to a real queue
(Celery/RQ or a jobs table) if the app is ever run with more than one worker.
"""

from __future__ import annotations

import datetime
import uuid
from concurrent.futures import ThreadPoolExecutor
from threading import Lock
try:
    from timeutils import utcnow
except ImportError:
    from backend.timeutils import utcnow

JOB_EXECUTOR = ThreadPoolExecutor(max_workers=2)
JOBS: dict[str, dict] = {}
JOBS_LOCK = Lock()


def utc_now_iso() -> str:
    return utcnow().isoformat() + "Z"


def create_job(job_type: str) -> str:
    job_id = f"job_{uuid.uuid4().hex[:12]}"
    with JOBS_LOCK:
        JOBS[job_id] = {
            "id": job_id,
            "type": job_type,
            "status": "queued",
            "progress": 0,
            "result": None,
            "error": None,
            "started_at": None,
            "finished_at": None,
            "created_at": utc_now_iso(),
        }
    return job_id


def update_job(job_id: str, **fields) -> None:
    with JOBS_LOCK:
        job = JOBS.get(job_id)
        if not job:
            return
        job.update(fields)


def get_job(job_id: str) -> dict | None:
    with JOBS_LOCK:
        job = JOBS.get(job_id)
        return dict(job) if job else None


def list_jobs() -> list[dict]:
    with JOBS_LOCK:
        return [dict(j) for j in JOBS.values()]
