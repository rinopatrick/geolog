"""Tests for multi-process / multi-worker file persistence of jobs and metrics."""

from __future__ import annotations

import pathlib
import pytest

from backend.jobs import create_job, get_job, list_jobs, update_job, JOBS_FILE
from backend.observability import record_request, _load_metrics, METRICS_FILE


def test_job_file_persistence(tmp_path, monkeypatch):
    test_jobs_file = str(tmp_path / "jobs.json")
    monkeypatch.setattr("backend.jobs.JOBS_FILE", test_jobs_file)

    jid = create_job("multi-worker-test")
    assert jid.startswith("job_")

    # Read directly from file to verify persistence
    job = get_job(jid)
    assert job["id"] == jid
    assert job["status"] == "queued"

    # Simulate another worker updating the job
    update_job(jid, status="done", progress=100)
    updated = get_job(jid)
    assert updated["status"] == "done"
    assert updated["progress"] == 100

    all_jobs = list_jobs()
    assert any(j["id"] == jid for j in all_jobs)


def test_metrics_file_persistence(tmp_path, monkeypatch):
    test_metrics_file = str(tmp_path / "metrics.json")
    monkeypatch.setattr("backend.observability.METRICS_FILE", test_metrics_file)

    record_request(method="GET", path="/api/test1", status=200, elapsed_ms=12.5)
    record_request(method="POST", path="/api/test2", status=201, elapsed_ms=30.0)

    # Simulate another worker reading the shared state
    m = _load_metrics()
    assert m["requests_total"] >= 2
    assert m["requests_by_method"]["GET"] >= 1
    assert m["requests_by_method"]["POST"] >= 1
    assert m["requests_by_status"]["200"] >= 1
    assert m["requests_by_status"]["201"] >= 1
    assert len(m["recent_events"]) >= 2
