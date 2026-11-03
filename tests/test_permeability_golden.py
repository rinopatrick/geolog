"""Golden-value coverage for the single-model permeability endpoint.

Coates and Timur values are hand-computed from the published formulas so the
test pins the arithmetic, not a re-run of the code:
  Coates: k = C * phi^4 / Swir^2
  Timur:  k = a * phi^4.4 / Swir^2
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from backend.main import app

client = TestClient(app)
HEADERS = {"X-User-Role": "interpreter"}


def _clean_sand():
    return {
        "DEPT": [1000.0, 1000.5],
        "GR": [15.0, 16.0],
        "RT": [20.0, 19.0],
        "NPHI": [0.21, 0.20],
        "RHOB": [2.30, 2.31],
        "PHIE": [0.21, 0.20],
        "SW": [0.35, 0.36],
    }


def test_permeability_coates_matches_hand_calculation(make_well):
    wid = make_well("perm-coates", _clean_sand())
    r = client.post(f"/api/wells/{wid}/permeability",
                    json={"model": "coates", "coates_c": 10000.0},
                    headers=HEADERS)
    assert r.status_code == 200, r.text
    k = r.json()["k_values"]["coates"]
    # k = 10000 * 0.21^4 / 0.35^2
    assert k[0] == pytest.approx(10000.0 * 0.21**4 / 0.35**2, rel=1e-3)
    assert k[1] == pytest.approx(10000.0 * 0.20**4 / 0.36**2, rel=1e-3)


def test_permeability_timur_matches_hand_calculation(make_well):
    wid = make_well("perm-timur", _clean_sand())
    r = client.post(f"/api/wells/{wid}/permeability",
                    json={"model": "timur", "timur_a": 0.136},
                    headers=HEADERS)
    assert r.status_code == 200, r.text
    k = r.json()["k_values"]["timur"]
    # k = 0.136 * phi^4.4 / Swir^2
    assert k[0] == pytest.approx(0.136 * 0.21**4.4 / 0.35**2, rel=1e-3)


def test_permeability_rejects_unknown_model(make_well):
    wid = make_well("perm-badmodel", _clean_sand())
    r = client.post(f"/api/wells/{wid}/permeability",
                    json={"model": "kozeny"}, headers=HEADERS)
    assert r.status_code == 400


def test_permeability_sdr_needs_t2gm(make_well):
    wid = make_well("perm-nosdr", _clean_sand())
    r = client.post(f"/api/wells/{wid}/permeability",
                    json={"model": "sdr"}, headers=HEADERS)
    assert r.status_code == 400
    assert "T2gm" in r.json()["detail"]
