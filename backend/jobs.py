"""Durable, multi-worker background job registry.

A job is a JSON-serialisable `(type, payload)` pair persisted in jobs.json.
Handlers register themselves by type at import time. Any worker can claim a
queued job, and startup/reaper recovery requeues jobs orphaned by a crash. The
in-process ThreadPoolExecutor is only the execution vehicle; the durable part is
the file registry.
"""

from __future__ import annotations

import datetime
import json
import os
import threading
import uuid
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Callable

try:
    from filelock import interprocess_lock
except ImportError:
    from backend.filelock import interprocess_lock

try:
    from deps import sanitize_json
    from timeutils import utcnow
except ImportError:
    from backend.deps import sanitize_json
    from backend.timeutils import utcnow

try:
    from well_state import ARTIFACT_DIR
except ImportError:
    from backend.well_state import ARTIFACT_DIR

JOB_EXECUTOR = ThreadPoolExecutor(max_workers=4, thread_name_prefix="geolog-job")
JOBS_FILE = os.path.join(ARTIFACT_DIR, "jobs.json")
JOBS_LOCK = threading.Lock()
JOBS: dict[str, dict] = {}
HANDLERS: dict[str, Callable[[dict[str, Any], str], Any]] = {}
HANDLERS_LOCK = threading.Lock()
WORKER_ID = f"{os.getpid()}:{uuid.uuid4().hex[:8]}"
STALE_SECONDS = int(os.getenv("GEOLOG_JOB_STALE_SECONDS", "900") or 900)


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
        json.dump(sanitize_json(jobs_data), f, indent=2)
    os.replace(tmp_path, JOBS_FILE)


def utc_now_iso() -> str:
    return utcnow().isoformat() + "Z"


def _mutate_jobs(fn):
    with JOBS_LOCK, interprocess_lock(JOBS_FILE):
        jobs = _load_jobs_file()
        result = fn(jobs)
        _save_jobs_file(jobs)
        JOBS.clear()
        JOBS.update(jobs)
        return result


def register_handler(job_type: str, handler: Callable[[dict[str, Any], str], Any]) -> None:
    with HANDLERS_LOCK:
        HANDLERS[job_type] = handler


def create_job(job_type: str, payload: dict[str, Any] | None = None) -> str:
    job_id = f"job_{uuid.uuid4().hex[:12]}"

    def _add(jobs):
        jobs[job_id] = {
            "id": job_id,
            "type": job_type,
            "payload": payload or {},
            "status": "queued",
            "progress": 0,
            "result": None,
            "error": None,
            "attempts": 0,
            "worker_id": None,
            "started_at": None,
            "finished_at": None,
            "created_at": utc_now_iso(),
        }
        return job_id

    return _mutate_jobs(_add)


def update_job(job_id: str, **fields) -> None:
    def _update(jobs):
        job = jobs.get(job_id)
        if not job:
            return None
        job.update(fields)
        return job

    _mutate_jobs(_update)


def get_job(job_id: str) -> dict | None:
    with JOBS_LOCK:
        jobs = _load_jobs_file()
        job = jobs.get(job_id)
        return dict(job) if job else None


def list_jobs() -> list[dict]:
    with JOBS_LOCK:
        jobs = _load_jobs_file()
        return [dict(j) for j in jobs.values()]


def _parse_ts(value: str | None) -> datetime.datetime | None:
    if not value:
        return None
    try:
        return datetime.datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None


def _is_stale(job: dict) -> bool:
    started = _parse_ts(job.get("started_at"))
    if started is None:
        return True
    now = utcnow()
    if started.tzinfo is None:
        started = started.replace(tzinfo=datetime.timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=datetime.timezone.utc)
    return (now - started).total_seconds() > STALE_SECONDS


def _claim(job_id: str) -> dict | None:
    def _apply(jobs):
        job = jobs.get(job_id)
        if not job:
            return None
        status = job.get("status")
        if status == "running" and job.get("worker_id") != WORKER_ID and not _is_stale(job):
            return None
        if status not in {"queued", "running", "retrying"}:
            return None
        job["status"] = "running"
        job["worker_id"] = WORKER_ID
        job["attempts"] = int(job.get("attempts", 0)) + 1
        job["started_at"] = utc_now_iso()
        job["finished_at"] = None
        job["error"] = None
        return dict(job)

    return _mutate_jobs(_apply)


def _execute(job_id: str) -> None:
    job = _claim(job_id)
    if job is None:
        return
    job_type = str(job.get("type") or "")
    with HANDLERS_LOCK:
        handler = HANDLERS.get(job_type)
    if handler is None:
        update_job(job_id, status="failed", error=f"no handler for {job_type}", finished_at=utc_now_iso())
        return
    try:
        result = handler(job.get("payload") or {}, job_id)
    except Exception as exc:
        update_job(job_id, status="failed", progress=100, error=str(exc), finished_at=utc_now_iso())
    else:
        update_job(job_id, status="done", progress=100, result=result, finished_at=utc_now_iso())


def submit_job(job_type: str, payload: dict[str, Any] | None = None) -> str:
    """Persist a job, then hand it to the local executor."""
    job_id = create_job(job_type, payload)
    JOB_EXECUTOR.submit(_execute, job_id)
    return job_id


def _requeue(job_id: str) -> None:
    update_job(job_id, status="queued")
    JOB_EXECUTOR.submit(_execute, job_id)


def recover_jobs() -> int:
    """Requeue jobs orphaned by a crash or left queued at shutdown."""
    recovered = 0
    for job in list_jobs():
        status = job.get("status")
        if status == "queued" or (status == "running" and _is_stale(job)):
            _requeue(job["id"])
            recovered += 1
    return recovered


def _reaper_loop() -> None:
    while True:
        threading.Event().wait(60)
        try:
            recover_jobs()
        except Exception:
            pass


threading.Thread(target=_reaper_loop, name="geolog-job-reaper", daemon=True).start()
