"""Autotie correlation contract at the API seam.

Same-well and missing ids are 400s. Matching formation names at близки
depths correlate with the shared name. Distant names do not match.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from backend.main import SessionLocal, app
from backend.models import FormationTop, LogRun, Well

client = TestClient(app)
INTERPRETER = {"X-User-Role": "interpreter"}
ADMIN = {"X-User-Role": "admin"}


def _make_well(name: str, tops: list) -> int:
    r = client.post("/api/wells/", json={"project_id": 1, "name": name},
                    headers=ADMIN)
    assert r.status_code == 201, r.text
    wid = r.json()["id"]
    db = SessionLocal()
    try:
        db.add(LogRun(well_id=wid, run_number=1, filename=f"{name}.las",
                      start_depth=1000.0, stop_depth=1100.0, step=1.0,
                      null_value=-999.25, num_points=101))
        for formation_name, depth in tops:
            db.add(FormationTop(well_id=wid, formation_name=formation_name,
                                depth=depth, top_depth=depth))
        db.commit()
        return wid
    finally:
        db.close()


def test_autotie_rejects_same_and_missing_wells():
    r = client.post("/api/correlation/auto-correlate",
                    json={"well_a_id": 1, "well_b_id": 1}, headers=INTERPRETER)
    assert r.status_code == 400
    r = client.post("/api/correlation/auto-correlate",
                    json={"well_a_id": 1}, headers=INTERPRETER)
    assert r.status_code == 400


def test_autotie_matches_shared_formation_names():
    a = _make_well("Tie-A", [("Pay Sand", 1000.0), ("Shale Cap", 1050.0)])
    b = _make_well("Tie-B", [("Pay Sand", 1005.0), ("Shale Cap", 1048.0)])
    r = client.post("/api/correlation/auto-correlate",
                    json={"well_a_id": a, "well_b_id": b,
                          "depth_tolerance": 50.0},
                    headers=INTERPRETER)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["count"] == 2
    assert len(body["matches"]) == 2
    pairs = {(m["formation_a"], m["formation_b"]) for m in body["matches"]}
    assert ("Pay Sand", "Pay Sand") in pairs
    assert ("Shale Cap", "Shale Cap") in pairs
    for m in body["matches"]:
        assert abs(m["depth_delta"]) <= 50.0


def test_autotie_ignores_distant_names(make_well):
    a = _make_well("Tie-Far-A", [("Alpha", 1000.0)])
    b = _make_well("Tie-Far-B", [("Beta", 1400.0)])
    r = client.post("/api/correlation/auto-correlate",
                    json={"well_a_id": a, "well_b_id": b,
                          "depth_tolerance": 50.0},
                    headers=INTERPRETER)
    assert r.status_code == 200, r.text
    assert r.json()["count"] == 0
    assert r.json()["matches"] == []
