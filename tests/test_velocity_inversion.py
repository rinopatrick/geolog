"""Checkshot interval-velocity inversion (TDD Red).

Production-grade bar: inverted layered model must predict held-out
checkshot depths within tolerance; residuals reported, guards fire.
"""

from __future__ import annotations

import pytest


def _checkshot():
    # Synthetic: two layers, v1=2000 to 1000ms, v2=3000 after.
    return [
        {"depth": 0.0, "twt_ms": 0.0},
        {"depth": 500.0, "twt_ms": 500.0},
        {"depth": 1000.0, "twt_ms": 1000.0},
        {"depth": 1750.0, "twt_ms": 1500.0},
        {"depth": 2500.0, "twt_ms": 2000.0},
        {"depth": 3250.0, "twt_ms": 2500.0},
    ]


def test_inversion_recovers_layer_velocities():
    from backend.velocity_inversion import invert_checkshot

    out = invert_checkshot(_checkshot(), n_layers=2)
    assert out["layers"][0]["velocity_m_s"] == pytest.approx(2000.0, rel=0.05)
    assert out["layers"][1]["velocity_m_s"] == pytest.approx(3000.0, rel=0.05)
    assert out["layers"][0]["top_ms"] == 0.0
    assert out["max_residual_m"] < 1.0


def test_holdout_misfit_reported():
    from backend.velocity_inversion import invert_checkshot

    pts = _checkshot()
    out = invert_checkshot(pts[:-1], n_layers=2, holdout=pts[-1:])
    assert out["holdout_rmse_m"] is not None
    assert out["holdout_rmse_m"] < 50.0


def test_inversion_rejects_bad_input():
    from backend.velocity_inversion import invert_checkshot

    with pytest.raises(ValueError, match="at least 3"):
        invert_checkshot([{"depth": 0.0, "twt_ms": 0.0}])
    with pytest.raises(ValueError, match="monotonic|increasing"):
        invert_checkshot([
            {"depth": 0.0, "twt_ms": 0.0},
            {"depth": 100.0, "twt_ms": 0.0},
            {"depth": 200.0, "twt_ms": 50.0},
        ])
    with pytest.raises(ValueError, match="layers"):
        invert_checkshot(_checkshot(), n_layers=1)

def test_invert_checkshot_endpoint():
    from fastapi.testclient import TestClient
    from backend.main import SessionLocal, app
    from backend.models import Project
    tclient = TestClient(app)
    admin = {"X-User-Role": "admin"}
    db = SessionLocal()
    try:
        pid = int(db.query(Project.id).order_by(Project.id.asc()).first()[0])
    finally:
        db.close()
    pts = [
        {"depth": 0.0, "twt_ms": 0.0},
        {"depth": 500.0, "twt_ms": 500.0},
        {"depth": 1000.0, "twt_ms": 1000.0},
        {"depth": 1750.0, "twt_ms": 1500.0},
        {"depth": 2500.0, "twt_ms": 2000.0},
    ]
    r = tclient.post(
        f"/api/projects/{pid}/velocity-models/invert-checkshot",
        json={"checkshot": pts, "n_layers": 2, "save": True, "name": "E2E VEL"},
        headers=admin,
    )
    assert r.status_code == 201, r.text
    data = r.json()
    assert data["saved_model"]["kind"] == "layers"
    assert data["inversion"]["max_residual_m"] < 1.0
    bad = tclient.post(
        f"/api/projects/{pid}/velocity-models/invert-checkshot",
        json={"checkshot": []},
        headers=admin,
    )
    assert bad.status_code == 400
