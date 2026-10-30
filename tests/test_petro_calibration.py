"""Volve F-1 calibration harness (TDD Red).

Production-grade bar: calibration must beat defaults on the reference
fixture by a stated margin, and guard rails must fire on bad config.
"""

from __future__ import annotations

import pytest


def _load():
    import csv

    inp = list(csv.DictReader(open("test_data/volve_f1/input.csv")))
    ref = list(csv.DictReader(open("test_data/volve_f1/reference_output.csv")))
    return inp, ref


def test_calibrated_vsh_beats_minmax_default():
    from backend.petro_calibration import calibrate_vsh

    inp, ref = _load()
    import numpy as np

    gr = np.array([float(r["GR"]) for r in inp])
    vsh_ref = np.array([float(r["VSH"]) for r in ref])
    default = (gr - gr.min()) / (gr.max() - gr.min())
    default_mae = float(np.mean(np.abs(default - vsh_ref)))
    cal = calibrate_vsh(gr, vsh_ref)
    assert cal["mae"] < default_mae * 0.5
    assert 0.0 <= cal["gr_clean"] < cal["gr_shale"] <= 300.0


def test_calibrated_phi_sh_beats_default():
    from backend.petro_calibration import calibrate_phi_sh

    inp, ref = _load()
    import numpy as np

    nphi = np.array([float(r["NPHI"]) for r in inp])
    rhob = np.array([float(r["RHOB"]) for r in inp])
    vsh = np.array([float(r["VSH"]) for r in ref])
    phif = np.array([float(r["PHIF"]) for r in ref])
    phi_d = (2.65 - rhob) / 1.65
    phi_raw = np.where(nphi < phi_d - 0.03, phi_d, (phi_d + nphi) / 2)
    default = np.maximum(0.0, phi_raw - vsh * 0.30)
    default_mae = float(np.mean(np.abs(default - phif)))
    cal = calibrate_phi_sh(phi_raw, vsh, phif)
    assert cal["mae"] < default_mae * 0.5
    assert 0.0 <= cal["phi_sh"] <= 0.6


def test_calibration_rejects_bad_reference():
    from backend.petro_calibration import calibrate_phi_sh, calibrate_vsh
    import numpy as np

    with pytest.raises(ValueError, match="length"):
        calibrate_vsh(np.array([1.0, 2.0]), np.array([1.0]))
    with pytest.raises(ValueError, match="finite"):
        calibrate_vsh(np.array([np.nan, np.nan]), np.array([0.1, 0.2]))
    with pytest.raises(ValueError, match="length"):
        calibrate_phi_sh(np.array([0.1]), np.array([0.1]), np.array([0.1, 0.2]))

def test_calibration_endpoint_fits_and_saves(make_well):
    from fastapi.testclient import TestClient
    from backend.main import SessionLocal, app
    import csv
    import numpy as np
    tclient = TestClient(app)
    admin = {"X-User-Role": "admin"}
    wid = make_well("CAL-01", {"DEPT": [1000.0, 1001.0], "GR": [80.0, 82.0]})
    inp = list(csv.DictReader(open("test_data/volve_f1/input.csv")))
    ref = list(csv.DictReader(open("test_data/volve_f1/reference_output.csv")))
    gr = [float(r["GR"]) for r in inp]
    vsh = [float(r["VSH"]) for r in ref]
    nphi = np.array([float(r["NPHI"]) for r in inp])
    rhob = np.array([float(r["RHOB"]) for r in inp])
    phi_d = (2.65 - rhob) / 1.65
    phi_raw = np.where(nphi < phi_d - 0.03, phi_d, (phi_d + nphi) / 2).tolist()
    phif = [float(r["PHIF"]) for r in ref]
    r = tclient.post(
        f"/api/wells/{wid}/petro-calibration",
        json={"gr": gr, "vsh_ref": vsh, "phi_raw": phi_raw, "phi_ref": phif, "save": True},
        headers=admin,
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["saved"] is True
    assert data["vsh"]["mae"] < 0.1
    assert data["phi_sh"]["mae"] < 0.02
    params = tclient.get(f"/api/wells/{wid}/petro-params", headers=admin).json()
    assert params["phi_sh"] == data["phi_sh"]["phi_sh"]
    bad = tclient.post(
        f"/api/wells/{wid}/petro-calibration", json={"gr": [1.0], "vsh_ref": []}, headers=admin
    )
    assert bad.status_code == 400
