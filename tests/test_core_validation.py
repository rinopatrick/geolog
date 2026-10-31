"""RealPore core validation harness (TDD Red).

Production-grade bar: log-linear poro-perm transform fit on laboratory
plugs must show positive slope with R2 above floor, residual spread bounded,
and guards must fire on bad input. This validates transforms against lab
plugs — the missing core-lab leg.
"""

from __future__ import annotations

import pytest


def _load():
    import csv

    with open("test_data/realpore_ncs/core_poroperm.csv") as handle:
        return list(csv.DictReader(handle))


def test_poro_perm_transform_positive_slope_and_r2_floor():
    from backend.core_validation import fit_poro_perm

    rows = _load()
    out = fit_poro_perm(rows)
    assert out["slope"] > 0
    assert out["r2"] >= 0.4
    assert out["n"] == 300
    assert out["residual_std_log10"] < 0.5


def test_poro_perm_transform_is_monotonic():
    from backend.core_validation import fit_poro_perm

    rows = _load()
    out = fit_poro_perm(rows)
    import numpy as np

    grid = np.linspace(5.0, 35.0, 7)
    preds = [out["intercept"] + out["slope"] * p for p in grid]
    assert all(b > a for a, b in zip(preds, preds[1:]))


def test_sw_baseline_median_within_physical_range():
    from backend.core_validation import sw_baseline

    rows = _load()
    out = sw_baseline(rows)
    assert 0.0 <= out["median_sw_pct"] <= 100.0
    assert out["n"] == 300
    assert 40.0 <= out["median_sw_pct"] <= 80.0


def test_core_validation_rejects_bad_input():
    from backend.core_validation import fit_poro_perm, sw_baseline

    with pytest.raises(ValueError, match="empty"):
        fit_poro_perm([])
    with pytest.raises(ValueError, match="empty"):
        sw_baseline([])
    with pytest.raises(ValueError, match="column"):
        fit_poro_perm([{"porosity_pct": "10"}])

def test_core_validation_endpoint(make_well):
    from fastapi.testclient import TestClient
    from backend.main import SessionLocal, app
    import csv
    tclient = TestClient(app)
    admin = {"X-User-Role": "admin"}
    wid = make_well("CORE-01", {"DEPT": [1000.0, 1001.0], "GR": [80.0, 82.0]})
    rows = list(csv.DictReader(open("test_data/realpore_ncs/core_poroperm.csv")))
    r = tclient.post(f"/api/wells/{wid}/plug-transform-check", json={"plugs": rows}, headers=admin)
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["poro_perm_transform"]["r2"] >= 0.4
    assert data["poro_perm_transform"]["slope"] > 0
    assert 40.0 <= data["sw_baseline"]["median_sw_pct"] <= 80.0
    bad = tclient.post(f"/api/wells/{wid}/plug-transform-check", json={"plugs": []}, headers=admin)
    assert bad.status_code == 400
