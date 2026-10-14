"""Golden-value tests for multimineral and multi-model permeability endpoints."""

from __future__ import annotations

import numpy as np
import pytest
from fastapi.testclient import TestClient

from backend.main import app

client = TestClient(app)
HEADERS = {"X-User-Role": "interpreter"}


def test_multimineral_solver_golden_values(make_well):
    """Test deterministic mineral solver outputs against expected physical ranges and formulas."""
    wid = make_well("mm-clean-sand", {
        "DEPT": [1000.0],
        "GR": [10.0],
        "RHOB": [2.65],
        "NPHI": [-0.02],
        "DT": [55.5],
    })

    r = client.post(f"/api/wells/{wid}/multimineral", json={}, headers=HEADERS)
    assert r.status_code == 200
    res = r.json()
    assert "v_quartz" in res
    assert "v_clay" in res
    assert "phi_e" in res

    # In clean sand, Vclay should be ~ 0
    assert res["v_clay"][0] == pytest.approx(0.0, abs=1e-3)
    # Porosity should be close to 0 with grain density 2.65 and bulk density 2.65
    assert res["phi_e"][0] == pytest.approx(0.0, abs=1e-2)
    # Mineral fractions + porosity must sum to roughly 1.0 (volumetric conservation)
    total_vol = (res["v_quartz"][0] or 0) + (res["v_calcite"][0] or 0) + (res["v_dolomite"][0] or 0) + (res["v_clay"][0] or 0) + (res["phi_e"][0] or 0)
    assert total_vol == pytest.approx(1.0, abs=0.05)


def test_permeability_multi_models_golden_values(make_well):
    """Test Coates, Timur, SDR, and FZI permeability outputs."""
    wid = make_well("perm-clean-sand", {
        "DEPT": [2000.0],
        "GR": [15.0],
        "RHOB": [2.30],
        "NPHI": [0.21],
    })

    r = client.post(f"/api/wells/{wid}/permeability-multi", json={"c_coates": 10000.0, "fzi": 10.0}, headers=HEADERS)
    assert r.status_code == 200
    res = r.json()

    assert "k_coates" in res
    assert "k_timur" in res
    assert "k_sdr" in res
    assert "k_fzi" in res

    k_coates = res["k_coates"][0]
    k_timur = res["k_timur"][0]
    k_fzi = res["k_fzi"][0]

    assert k_coates > 10.0, f"Expected good permeability for 21% porosity sand, got {k_coates}"
    assert k_timur > 10.0
    assert k_fzi > 1.0

    stats = res.get("stats", {})
    assert "coates" in stats
