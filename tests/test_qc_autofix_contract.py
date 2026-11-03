"""QC autofix behavior contracts at the API seam.

Known nulls suggest interpolation. Known negatives suggest clipping.
Faults lower the score. A clean well scores 100 with no issues.
"""

from __future__ import annotations

import numpy as np
from fastapi.testclient import TestClient

from backend.main import app

client = TestClient(app)
HEADERS = {"X-User-Role": "interpreter"}


def _curves_with_faults():
    gr = np.array([50.0, 51.0, np.nan, np.nan, np.nan, 55.0, 56.0, 57.0,
                   58.0, 59.0, 60.0, 61.0, 62.0, 63.0, 64.0, 65.0, 66.0,
                   67.0, 68.0, 69.0, 70.0, -5.0, 72.0, 73.0, 74.0])
    return {
        "DEPT": np.arange(1000.0, 1000.0 + len(gr) * 0.5, 0.5),
        "GR": gr,
        "RT": np.full(len(gr), 20.0),
        "NPHI": np.full(len(gr), 0.21),
        "RHOB": np.full(len(gr), 2.30),
    }


def _clean_curves():
    n = 25
    return {
        "DEPT": np.arange(1000.0, 1000.0 + n * 0.5, 0.5),
        "GR": np.linspace(40.0, 60.0, n),
        "RT": np.linspace(15.0, 25.0, n),
        "NPHI": np.linspace(0.18, 0.24, n),
        "RHOB": np.linspace(2.28, 2.32, n),
    }


def _run_qc(wid: int) -> dict:
    r = client.post(f"/api/wells/{wid}/qc-autofix", json={}, headers=HEADERS)
    assert r.status_code == 200, r.text
    return r.json()


def test_qc_autofix_suggests_interpolate_only_above_half_null(make_well):
    sparse = make_well("qc-sparse", _curves_with_faults())
    sparse_fixes = [f for f in _run_qc(sparse)["fixes"] if f["curve"] == "GR"]
    assert not any(f["action"] == "interpolate" for f in sparse_fixes)
    heavy = dict(_curves_with_faults())
    heavy["GR"] = np.array([np.nan] * 13 + [50.0] * 12)
    heavy_wid = make_well("qc-heavy", heavy)
    heavy_body = _run_qc(heavy_wid)
    heavy_issues = [i for i in heavy_body["issues"] if i["curve"] == "GR"]
    assert any(i["type"] == "high_nulls" for i in heavy_issues)
    heavy_fixes = [f for f in heavy_body["fixes"] if f["curve"] == "GR"]
    assert any(f["action"] == "interpolate" for f in heavy_fixes)


def test_qc_autofix_suggests_clip_for_negatives(make_well):
    wid = make_well("qc-neg", _curves_with_faults())
    body = _run_qc(wid)
    gr_issues = [i for i in body["issues"] if i["curve"] == "GR"]
    assert any(i["type"] == "negative" for i in gr_issues)
    gr_fixes = [f for f in body["fixes"] if f["curve"] == "GR"]
    assert any(f["action"] == "clip_negative" for f in gr_fixes)


def test_qc_autofix_faults_lower_score(make_well):
    faulty = make_well("qc-faulty", _curves_with_faults())
    clean = make_well("qc-clean", _clean_curves())
    faulty_score = _run_qc(faulty)["score"]
    clean_body = _run_qc(clean)
    assert faulty_score < clean_body["score"]
    assert clean_body["score"] == 100
    assert clean_body["issues"] == []
