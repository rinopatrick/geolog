"""NMR async inversion lifecycle at the API seam.

Submitting echo inversion queues a job and returns its id. The id is
pollable at /api/jobs/{job_id}. An unknown id is a 404.
"""

from __future__ import annotations

import time

import numpy as np
from fastapi.testclient import TestClient

from backend.main import app

client = TestClient(app)
INTERPRETER = {"X-User-Role": "interpreter"}
VIEWER = {"X-User-Role": "viewer"}


def _submit(make_well) -> str:
    wid = make_well("NMR-ASYNC-LIFE", {
        "DEPT": np.array([1000.0, 1001.0]),
        "E1": np.array([0.15, 0.14]),
        "E2": np.array([0.12, 0.11]),
        "E3": np.array([0.09, 0.08]),
        "E4": np.array([0.06, 0.05]),
    })
    r = client.post(
        f"/api/wells/{wid}/nmr/invert-async",
        headers=INTERPRETER,
        json={
            "echo_mnemonics": ["E1", "E2", "E3", "E4"],
            "te_ms": [0.6, 1.2, 1.8, 2.4],
            "n_bins": 8,
            "lambda": 0.05,
        },
    )
    assert r.status_code == 202, r.text
    assert r.json()["status"] == "queued"
    return r.json()["job_id"]


def test_nmr_async_submit_is_pollable(make_well):
    job_id = _submit(make_well)
    deadline = time.time() + 30
    last = None
    while time.time() < deadline:
        last = client.get(f"/api/jobs/{job_id}", headers=VIEWER)
        assert last.status_code == 200, last.text
        if last.json()["status"] in ("done", "failed"):
            break
        time.sleep(0.5)
    assert last.json()["status"] in ("done", "failed")
    assert last.json()["type"] == "nmr-inversion"


def test_nmr_async_rejects_bad_echoes(make_well):
    wid = make_well("NMR-ASYNC-BAD", {"DEPT": np.array([1000.0])})
    r = client.post(
        f"/api/wells/{wid}/nmr/invert-async",
        headers=INTERPRETER,
        json={"echo_mnemonics": ["E1"], "te_ms": [0.6]},
    )
    assert r.status_code == 400


def test_unknown_job_id_is_404():
    r = client.get("/api/jobs/does-not-exist", headers=VIEWER)
    assert r.status_code == 404
