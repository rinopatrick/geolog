"""NMR T2 inversion and interpretation."""

from __future__ import annotations

import time

import numpy as np
import pytest
from fastapi.testclient import TestClient

from backend.main import SessionLocal, app
from backend.models import CurveData, NmrDistribution, NmrInversion
from backend.nmr import build_kernel, derived_curves, regularized_invert, t2_grid

client = TestClient(app)
INTERPRETER = {"X-User-Role": "interpreter"}

def test_synthetic_inversion_recovers_total_and_peak():
    bins = t2_grid(count=24)
    truth = np.zeros(24)
    truth[8] = 0.12
    truth[14] = 0.06
    te = np.arange(1, 129) * 0.6
    echoes = truth[None, :] @ build_kernel(te, bins).T
    amps = regularized_invert(echoes, te, bins, 0.1)
    assert np.all(amps >= 0)
    assert abs(float(amps.sum()) - 0.18) < 0.03
    assert int(np.argmax(amps[0])) == 8
    derived = derived_curves(amps, bins, cutoff_ms=33)
    assert abs(float(derived["NMRP"][0]) - 0.182) < 0.03
    assert float(derived["BVI"][0]) > float(derived["FFI"][0])
    assert np.isfinite(derived["T2GM"][0])
    assert float(derived["KSDR"][0]) >= 0

def test_vendor_bin_interpretation_and_distribution(make_well):
    wid = make_well("NMR-BINS", {
        "DEPT": np.array([1000.0, 1001.0, 1002.0]),
        "T2B1": np.array([0.01, 0.01, 0.01]),
        "T2B2": np.array([0.02, 0.02, 0.02]),
        "T2B3": np.array([0.03, 0.03, 0.03]),
        "T2B4": np.array([0.01, 0.01, 0.01]),
    })
    r = client.post(
        f"/api/wells/{wid}/nmr/interpret",
        headers=INTERPRETER,
        json={
            "bin_mnemonics": ["T2B1", "T2B2", "T2B3", "T2B4"],
            "t2_bins_ms": [1.0, 10.0, 100.0, 1000.0],
            "cutoff_ms": 33.0,
        },
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["inversion_id"]
    assert np.allclose(data["curves"]["NMRP"], [0.07, 0.07, 0.07])
    assert np.allclose(data["curves"]["BVI"], [0.03, 0.03, 0.03])
    assert np.allclose(data["curves"]["FFI"], [0.04, 0.04, 0.04])
    assert data["semantics"]["version"] == "data-semantics-v1"

    db = SessionLocal()
    try:
        inv = db.query(NmrInversion).filter(NmrInversion.id == data["inversion_id"]).first()
        assert inv is not None
        assert db.query(NmrDistribution).filter(NmrDistribution.inversion_id == inv.id).count() == 1
        for name in ("NMRP", "BVI", "FFI", "T2GM", "KSDR", "KCOATES"):
            assert db.query(CurveData).filter_by(log_run_id=inv.log_run_id, mnemonic=name).first() is not None
    finally:
        db.close()

    r = client.get(f"/api/wells/{wid}/nmr/inversions/{data['inversion_id']}/distribution")
    assert r.status_code == 200, r.text
    dist = r.json()
    assert len(dist["depth"]) == 3
    assert len(dist["amplitudes"]) == 3
    assert len(dist["amplitudes"][0]) == 4

def test_nmr_bad_bins_is_400():
    r = client.post(
        "/api/wells/1/nmr/interpret",
        headers=INTERPRETER,
        json={"bin_mnemonics": ["A", "B"], "t2_bins_ms": [1.0]},
    )
    assert r.status_code == 400

def test_nmr_async_inversion(make_well):
    wid = make_well("NMR-ECHO", {
        "DEPT": np.array([1000.0, 1001.0]),
        "E1": np.array([0.15, 0.14]),
        "E2": np.array([0.12, 0.11]),
        "E3": np.array([0.09, 0.08]),
        "E4": np.array([0.06, 0.05]),
    })
    r = client.post(
        f"/api/wells/{wid}/nmr/invert-async",
        headers=INTERPRETER,
        json={
            "echo_mnemonics": ["E1", "E2", "E3", "E4"],
            "te_ms": [0.6, 1.2, 1.8, 2.4],
            "n_bins": 8,
            "lambda": 0.05,
        },
    )
    assert r.status_code == 202, r.text
    job_id = r.json()["job_id"]
    for _ in range(100):
        job = client.get(f"/api/jobs/{job_id}").json()
        if job.get("status") in {"done", "failed"}:
            break
        time.sleep(0.1)
    assert job.get("status") == "done", job
    assert job.get("result", {}).get("inversion_id")
