"""Cutoff sensitivity for NMR vendor-bin interpretation.

Raising cutoff_ms must move porosity from FFI into BVI while NMRP stays
constant. This pins the physical meaning of the cutoff at the API seam.
"""

from __future__ import annotations

import numpy as np
from fastapi.testclient import TestClient

from backend.main import app

client = TestClient(app)
HEADERS = {"X-User-Role": "interpreter"}

BINS = {
    "DEPT": np.array([1000.0, 1001.0]),
    "T2B1": np.array([0.01, 0.01]),
    "T2B2": np.array([0.02, 0.02]),
    "T2B3": np.array([0.03, 0.03]),
    "T2B4": np.array([0.01, 0.01]),
    "T2B5": np.array([0.05, 0.05]),
}
BIN_TIMES = [1.0, 10.0, 100.0, 1000.0, 33.0]


def _interpret(wid: int, cutoff: float) -> dict:
    r = client.post(
        f"/api/wells/{wid}/nmr/interpret",
        headers=HEADERS,
        json={
            "bin_mnemonics": ["T2B1", "T2B2", "T2B3", "T2B4", "T2B5"],
            "t2_bins_ms": BIN_TIMES,
            "cutoff_ms": cutoff,
            "save": False,
            "save_curves": False,
        },
    )
    assert r.status_code == 200, r.text
    return r.json()["curves"]


def test_nmr_cutoff_moves_porosity_from_ffi_to_bvi(make_well):
    wid = make_well("NMR-CUTOFF", BINS)
    # cutoff 33ms: bins at 1,10,33ms are bound (boundary bin inclusive);
    # 100,1000ms are free
    low = _interpret(wid, 33.0)
    # cutoff 500ms: 100ms bin joins the bound volume
    high = _interpret(wid, 500.0)
    assert np.allclose(low["NMRP"], high["NMRP"])
    assert np.allclose(low["NMRP"], [0.12, 0.12])
    assert np.allclose(low["BVI"], [0.08, 0.08])
    assert np.allclose(low["FFI"], [0.04, 0.04])
    assert np.allclose(high["BVI"], [0.11, 0.11])
    assert np.allclose(high["FFI"], [0.01, 0.01])


def test_nmr_cutoff_sensitivity_without_save_leaves_no_rows(make_well):
    from backend.main import SessionLocal
    from backend.models import CurveData, LogRun

    wid = make_well("NMR-NOSAVE", BINS)
    db = SessionLocal()
    try:
        lr_ids = [r.id for r in db.query(LogRun).filter(LogRun.well_id == wid).all()]
        before = db.query(CurveData).filter(CurveData.log_run_id.in_(lr_ids)).count()
    finally:
        db.close()
    _interpret(wid, 33.0)
    db = SessionLocal()
    try:
        lr_ids = [r.id for r in db.query(LogRun).filter(LogRun.well_id == wid).all()]
        after = db.query(CurveData).filter(CurveData.log_run_id.in_(lr_ids)).count()
    finally:
        db.close()
    assert after == before
