"""Source-rock TOC/kerogen screening endpoints."""

from __future__ import annotations

import numpy as np
from fastapi.testclient import TestClient

from backend.main import SessionLocal, app
from backend.models import CurveData

client = TestClient(app)
INTERPRETER = {"X-User-Role": "interpreter"}


def _source_well(make_well, name="SOURCE-ROCK"):
    depth = np.arange(1000.0, 1050.0, 1.0)
    n = len(depth)
    return make_well(
        name,
        {
            "DEPT": depth,
            "RT": np.linspace(2.0, 30.0, n),
            "DT": np.linspace(100.0, 60.0, n),
            "RHOB": np.linspace(2.55, 2.30, n),
        },
    )


def test_passey_toc_and_kerogen_curves(make_well):
    wid = _source_well(make_well, "SOURCE-PASSEY")
    r = client.post(
        f"/api/wells/{wid}/source-rock",
        json={"method": "passey", "porosity_mode": "sonic", "lom": 10},
        headers=INTERPRETER,
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["method"] == "passey"
    assert body["stats"]["toc"]["count"] > 0
    assert body["stats"]["toc"]["max"] >= 0
    assert body["curves"] == {"toc": "TOC", "vker": "VKER"}
    assert body["analysis_id"] > 0

    analyses = client.get(f"/api/wells/{wid}/source-rock/analyses", headers=INTERPRETER)
    assert analyses.status_code == 200, analyses.text
    latest = analyses.json()[0]
    assert latest["method"] == "passey"
    assert latest["porosity_mode"] == "sonic"
    assert latest["lom"] == 10.0
    assert latest["toc_curve"] == "TOC"

    db = SessionLocal()
    try:
        lr_id = body["log_run_id"]
        toc = db.query(CurveData).filter_by(log_run_id=lr_id, mnemonic="TOC").first()
        vker = db.query(CurveData).filter_by(log_run_id=lr_id, mnemonic="VKER").first()
        assert toc is not None and vker is not None
        assert toc.num_points == vker.num_points
        assert toc.max_value is not None
    finally:
        db.close()


def test_schmoker_toc(make_well):
    wid = _source_well(make_well, "SOURCE-SCHMOKER")
    r = client.post(
        f"/api/wells/{wid}/source-rock",
        json={"method": "schmoker"},
        headers=INTERPRETER,
    )
    assert r.status_code == 200, r.text
    assert r.json()["method"] == "schmoker"
    assert r.json()["stats"]["toc"]["count"] > 0


def test_source_rock_rejects_missing_resistivity(make_well):
    depth = np.arange(1000.0, 1010.0, 1.0)
    wid = make_well("SOURCE-NORT", {"DEPT": depth, "DT": np.full(len(depth), 80.0)})
    r = client.post(f"/api/wells/{wid}/source-rock", json={"method": "passey"}, headers=INTERPRETER)
    assert r.status_code == 400
    assert "resistivity" in r.text.lower()
