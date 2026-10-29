"""Database-backed shared state for multi-instance deployments."""

from __future__ import annotations

import time

import pytest

from backend import jobs, observability, ratelimit, state_backend, well_state


@pytest.fixture(autouse=True)
def database_state(monkeypatch):
    monkeypatch.setenv("GEOLOG_STATE_BACKEND", "database")
    state_backend.reset_rate_limits()
    state_backend.reset_metrics()
    state_backend.reset_jobs()
    state_backend.reset_well_state()
    yield
    state_backend.reset_rate_limits()
    state_backend.reset_metrics()
    state_backend.reset_jobs()
    state_backend.reset_well_state()


def _wait(job_id: str, timeout: float = 5.0) -> dict:
    deadline = time.time() + timeout
    while time.time() < deadline:
        job = jobs.get_job(job_id)
        if job and job.get("status") in {"done", "failed"}:
            return job
        time.sleep(0.02)
    raise AssertionError(f"job did not finish: {jobs.get_job(job_id)}")


def test_rate_limit_counters_are_shared(monkeypatch):
    monkeypatch.setenv("GEOLOG_AUTH_IP_LIMIT", "2")
    assert ratelimit.hit("shared:ip", 2, 60) == 0
    assert ratelimit.hit("shared:ip", 2, 60) == 0
    assert ratelimit.hit("shared:ip", 2, 60) > 0

    assert ratelimit.record_failure("shared:user", 2, 60, 30) == 0
    assert ratelimit.record_failure("shared:user", 2, 60, 30) == 30
    assert ratelimit.locked_for("shared:user") > 0
    ratelimit.clear_failures("shared:user")
    assert ratelimit.locked_for("shared:user") == 0


def test_metrics_are_aggregated_from_database():
    observability.record_request("GET", "/api/one", 200, 1.0)
    observability.record_request("POST", "/api/two", 201, 2.0)
    data = observability._load_metrics()
    assert data["requests_total"] >= 2
    assert data["requests_by_method"]["GET"] >= 1
    assert data["requests_by_method"]["POST"] >= 1
    assert data["requests_by_status"]["200"] >= 1


def test_jobs_persist_and_run_from_database():
    jobs.register_handler("db-double", lambda payload, job_id: int(payload["x"]) * 2)
    job_id = jobs.submit_job("db-double", {"x": 21})
    job = _wait(job_id)
    assert job["status"] == "done", job
    assert job["result"] == 42
    assert job["attempts"] == 1


def test_queued_database_job_is_recovered():
    jobs.register_handler("db-double", lambda payload, job_id: int(payload["x"]) * 2)
    job_id = jobs.create_job("db-double", {"x": 7})
    assert jobs.get_job(job_id)["status"] == "queued"
    assert jobs.recover_jobs() >= 1
    job = _wait(job_id)
    assert job["status"] == "done", job
    assert job["result"] == 14


def test_claim_is_atomic_and_duplicate_claim_loses():
    jobs.register_handler("db-double", lambda payload, job_id: 1)
    job_id = jobs.create_job("db-double", {"x": 1})
    first = state_backend.claim_job(job_id, "worker-a", 900)
    assert first is not None
    assert first["status"] == "running"
    second = state_backend.claim_job(job_id, "worker-b", 900)
    assert second is None


def test_well_locks_and_templates_are_shared():
    well_state.set_well_lock(1, True, actor="tester", snapshot_id="snap-1")
    lock = well_state.get_well_lock(1)
    assert lock["locked"] is True
    assert lock["actor"] == "tester"

    well_state.set_template_lock(1, {"locked": True, "locked_by": "tester"})
    assert well_state.get_template_lock(1)["locked"] is True


def test_well_snapshots_are_shared_and_atomic():
    well_state.save_snapshots(1, [{"id": "snap-1"}])
    assert well_state.load_snapshots(1) == [{"id": "snap-1"}]

    def _add(snapshots):
        snapshots.append({"id": "snap-2"})
        return len(snapshots)

    assert well_state.mutate_snapshots(1, _add) == 2
    assert [s["id"] for s in well_state.load_snapshots(1)] == ["snap-1", "snap-2"]

    well_state.delete_well_state(1)
    assert well_state.get_well_lock(1)["locked"] is False
    assert well_state.load_snapshots(1) == []
