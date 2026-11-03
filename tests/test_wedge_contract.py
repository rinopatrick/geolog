"""Wedge forward-model input contract at the API seam.

A valid sweep returns per-frequency curves over the requested thickness
range. Out-of-range physics and oversize grids are 400s, not silent
truncation or server errors.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from backend.main import app

client = TestClient(app)
HEADERS = {"X-User-Role": "interpreter"}

VALID = {
    "ai_top": 6000.0,
    "ai_reservoir": 8000.0,
    "ai_base": 6000.0,
    "velocity_m_s": 3000.0,
    "freqs_hz": [20.0, 30.0],
    "thickness_m": [0.0, 10.0, 20.0, 30.0, 40.0, 50.0],
}


def test_wedge_valid_sweep_shape():
    r = client.post("/api/seismic/wedge-model", json=VALID, headers=HEADERS)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["thickness_m"] == VALID["thickness_m"]
    assert body["freqs_hz"] == [20.0, 30.0]
    assert set(body["curves"].keys()) == {"20.0", "30.0"}
    for freq in ("20.0", "30.0"):
        assert len(body["curves"][freq]["peak_amplitude"]) == 6
    assert set(body["tuning_thickness_per_freq"].keys()) == {"20.0", "30.0"}


def test_wedge_rejects_out_of_range_physics():
    bad = dict(VALID, ai_top=-100.0)
    r = client.post("/api/seismic/wedge-model", json=bad, headers=HEADERS)
    assert r.status_code == 400


def test_wedge_rejects_oversize_thickness_grid():
    bad = dict(VALID, thickness_m=[float(i) for i in range(250)])
    r = client.post("/api/seismic/wedge-model", json=bad, headers=HEADERS)
    assert r.status_code == 400


def test_wedge_rejects_non_object_body():
    r = client.post("/api/seismic/wedge-model", json=[1, 2, 3], headers=HEADERS)
    assert r.status_code in (400, 422)
