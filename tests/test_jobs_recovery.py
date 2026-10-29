"""Durable job registry: submit, recover, and duplicate-claim protection."""

from __future__ import annotations

import time

import pytest

from backend import jobs


@pytest.fixture(autouse=True)
def isolated_jobs(tmp_path, monkeypatch):
    monkeypatch.setattr(jobs, "JOBS_FILE", str(tmp_path / "jobs.json"))
    jobs.register_handler("unit-double", lambda payload, job_id: int(payload["x"]) * 2)
    yield


def _wait(job_id: str, timeout: float = 5.0) -> dict:
    deadline = time.time() + timeout
    while time.time() < deadline:
        job = jobs.get_job(job_id)
        if job and job.get("status") in {"done", "failed"}:
            return job
        time.sleep(0.02)
    raise AssertionError(f"job did not finish: {jobs.get_job(job_id)}")


def test_submit_job_runs_registered_handler():
    job_id = jobs.submit_job("unit-double", {"x": 21})
    job = _wait(job_id)
    assert job["status"] == "done", job
    assert job["result"] == 42
    assert job["attempts"] == 1
    assert job["finished_at"]


def test_queued_job_is_recovered_after_restart():
    job_id = jobs.create_job("unit-double", {"x": 7})
    assert jobs.get_job(job_id)["status"] == "queued"

    recovered = jobs.recover_jobs()
    assert recovered >= 1
    job = _wait(job_id)
    assert job["status"] == "done", job
    assert job["result"] == 14


def test_unknown_handler_fails_the_job():
    job_id = jobs.submit_job("not-registered", {})
    job = _wait(job_id)
    assert job["status"] == "failed"
    assert "no handler" in job["error"]


def test_fresh_running_job_is_not_stolen():
    job_id = jobs.create_job("unit-double", {"x": 1})
    jobs.update_job(job_id, status="running", worker_id="other-worker", started_at=jobs.utc_now_iso())

    jobs.JOB_EXECUTOR.submit(jobs._execute, job_id)
    time.sleep(0.2)
    job = jobs.get_job(job_id)
    assert job["status"] == "running"
    assert job["worker_id"] == "other-worker"
