"""Golden + invariant coverage for dual-water, vcl-enhanced, lithology, curve-calc.

Dual-water must converge to Archie in clean sand (Vsh -> 0): same Sw within
tolerance on identical inputs. vcl-enhanced returns all requested methods.
Lithology classifies clean sand vs shale. curve-calc evaluates expressions.
"""

from __future__ import annotations

import numpy as np
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
    }


def test_dual_water_converges_to_archie_in_clean_sand(make_well):
    wid = make_well("dw-clean", _clean_sand())
    params = {"a": 1.0, "m": 2.0, "n": 2.0, "rw": 0.1}
    archie = client.post(f"/api/wells/{wid}/compute-sw",
                         json=params, headers=HEADERS)
    dw = client.post(f"/api/wells/{wid}/dual-water",
                     json=params, headers=HEADERS)
    assert archie.status_code == 200
    assert dw.status_code == 200
    a_sw = archie.json()["sw"]
    d_sw = dw.json()["sw"]
    assert len(a_sw) == len(d_sw) > 0
    # On points Archie deems valid, dual-water agrees closely and stays physical.
    # Invalid points may be handled differently per model (None vs clamped 0).
    compared = 0
    for a, d in zip(a_sw, d_sw):
        if a is None:
            continue
        assert d is not None and 0.0 < d <= 1.0
        assert d == pytest.approx(a, rel=0.25)
        compared += 1
    assert compared > 0


def test_dual_water_needs_rt_nphi(make_well):
    wid = make_well("dw-nocurve", {"DEPT": [1000.0], "GR": [50.0]})
    r = client.post(f"/api/wells/{wid}/dual-water", json={}, headers=HEADERS)
    assert r.status_code == 400


def test_vcl_enhanced_returns_all_methods(make_well):
    wid = make_well("vcl-e", _clean_sand())
    r = client.post(f"/api/wells/{wid}/vcl-enhanced", json={}, headers=HEADERS)
    assert r.status_code == 200
    body = r.json()
    for method in ("igr", "larionov_tertiary", "larionov_old",
                   "steiber", "clavier"):
        assert method in body, method
        assert len(body[method]) == 2


def test_lithology_clean_sand_vs_shale(make_well):
    sand = make_well("lith-sand", _clean_sand())
    shale = make_well("lith-shale", {
        "DEPT": [1000.0], "GR": [150.0], "RT": [2.0],
        "NPHI": [0.45], "RHOB": [2.45],
    })
    rs = client.post(f"/api/wells/{sand}/lithology", json={},
                     headers=HEADERS)
    rh = client.post(f"/api/wells/{shale}/lithology", json={},
                     headers=HEADERS)
    assert rs.status_code == 200 and rh.status_code == 200
    assert rs.json()["lith_code"] != rh.json()["lith_code"]


def test_curve_calc_evaluates_expression(make_well):
    wid = make_well("calc", _clean_sand())
    r = client.post(f"/api/wells/{wid}/curve-calc",
                    json={"output_name": "GR2X", "expression": "GR * 2"},
                    headers=HEADERS)
    assert r.status_code == 200
    body = r.json()
    assert body["curve_name"] == "GR2X"
    assert body["points"] == 2
    assert body["min"] == pytest.approx(30.0)
    assert body["max"] == pytest.approx(32.0)
