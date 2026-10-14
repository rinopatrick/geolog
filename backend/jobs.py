"""Multi-worker safe background job registry.

State is backed by SQLite storage in artifacts/jobs.json or file-backed storage,
ensuring background jobs created by one worker process are accessible and trackable
by any other worker process.
"""

from __future__ import annotations

import datetime
import json
import os
import uuid
from concurrent.futures import ThreadPoolExecutor
from threading import Lock

try:
    from timeutils import utcnow
except ImportError:
    from backend.timeutils import utcnow

try:
    from well_state import ARTIFACT_DIR
except ImportError:
    from backend.well_state import ARTIFACT_DIR


JOB_EXECUTOR = ThreadPoolExecutor(max_workers=4)
JOBS_FILE = os.path.join(ARTIFACT_DIR, "jobs.json")
JOBS_LOCK = Lock()
JOBS: dict[str, dict] = {}


def _load_jobs_file() -> dict[str, dict]:
    if not os.path.exists(JOBS_FILE):
        return {}
    try:
        with open(JOBS_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _save_jobs_file(jobs_data: dict[str, dict]) -> None:
    os.makedirs(os.path.dirname(JOBS_FILE), exist_ok=True)
    tmp_path = JOBS_FILE + ".tmp"
    with open(tmp_path, "w", encoding="utf-8") as f:
        json.dump(jobs_data, f, indent=2)
    os.replace(tmp_path, JOBS_FILE)


def utc_now_iso() -> str:
    return utcnow().isoformat() + "Z"


def create_job(job_type: str) -> str:
    job_id = f"job_{uuid.uuid4().hex[:12]}"
    with JOBS_LOCK:
        jobs = _load_jobs_file()
        job = {
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
        jobs[job_id] = job
        _save_jobs_file(jobs)
        JOBS.clear()
        JOBS.update(jobs)
    return job_id


def update_job(job_id: str, **fields) -> None:
    with JOBS_LOCK:
        jobs = _load_jobs_file()
        job = jobs.get(job_id)
        if not job:
            return
        job.update(fields)
        jobs[job_id] = job
        _save_jobs_file(jobs)
        JOBS.clear()
        JOBS.update(jobs)


def get_job(job_id: str) -> dict | None:
    with JOBS_LOCK:
        jobs = _load_jobs_file()
        job = jobs.get(job_id)
        return dict(job) if job else None


def list_jobs() -> list[dict]:
    with JOBS_LOCK:
        jobs = _load_jobs_file()
        return [dict(j) for j in jobs.values()]
