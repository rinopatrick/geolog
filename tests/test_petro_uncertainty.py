"""Per-depth petrophysics uncertainty bands."""

from __future__ import annotations

import numpy as np
from fastapi.testclient import TestClient

from backend.main import app

client = TestClient(app)
ADMIN = {"X-User-Role": "admin"}


def _curves(length: int = 140) -> dict:
    depth = np.arange(1000.0, 1000.0 + length)
    gr = 30.0 + 40.0 * np.sin(np.arange(length) / 9.0)
    nphi = 0.18 + 0.06 * np.cos(np.arange(length) / 11.0)
    rt = 5.0 + 12.0 * (1.0 + np.sin(np.arange(length) / 13.0))
    return {"DEPT": depth, "GR": gr, "NPHI": nphi, "RT": rt}


def test_petro_uncertainty_bands(make_well):
    wid = make_well("Uncertainty-01", _curves())
    response = client.post(
        f"/api/wells/{wid}/petro-uncertainty",
        json={
            "iterations": 50,
            "variation_pct": 20,
            "a": 1.0,
            "m": 2.0,
            "n": 2.0,
            "rw": 0.1,
            "saturation_model": "archie",
            "seed": 4,
            "start_depth": 1005,
            "stop_depth": 1100,
        },
        headers=ADMIN,
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["iterations"] == 50
    assert body["saturation_model"] == "archie"
    assert len(body["depth"]) == len(body["sw"]["p50"])
    assert len(body["depth"]) == len(body["phie"]["p50"]) == len(body["vsh"]["p50"])
    for key in ("sw", "phie", "vsh"):
        band = body[key]
        assert all(low <= mid <= high for low, mid, high in zip(band["p90"], band["p50"], band["p10"]))
    assert body["summary"]["sw_p50_mean"] > 0
    assert body["summary"]["phie_p50_mean"] > 0


def test_petro_uncertainty_validation(make_well):
    wid = make_well("Uncertainty-02", _curves())
    bad_model = client.post(
        f"/api/wells/{wid}/petro-uncertainty",
        json={"iterations": 20, "saturation_model": "unknown"},
        headers=ADMIN,
    )
    assert bad_model.status_code == 400

    empty = client.post(
        f"/api/wells/{wid}/petro-uncertainty",
        json={"iterations": 20, "start_depth": 5000, "stop_depth": 5001},
        headers=ADMIN,
    )
    assert empty.status_code == 400


def test_uncertainty_uses_density_neutron_when_rhob_available(make_well):
    length = 120
    depth = np.arange(1000.0, 1000.0 + length)
    curves = {
        "DEPT": depth,
        "GR": 30.0 + 20.0 * np.sin(np.arange(length) / 9.0),
        "NPHI": np.full(length, 0.25),
        "RHOB": np.full(length, 2.50),
        "RT": 8.0 + 6.0 * (1.0 + np.sin(np.arange(length) / 13.0)),
    }
    wid = make_well("Uncertainty-RHOB", curves)
    response = client.post(
        f"/api/wells/{wid}/petro-uncertainty",
        json={"iterations": 20, "variation_pct": 0, "seed": 1},
        headers=ADMIN,
    )
    assert response.status_code == 200, response.text
    body = response.json()
    # Density porosity is ~0.09; average with 0.25 is ~0.17 before clay correction.
    assert 0.02 < body["summary"]["phie_p50_mean"] < 0.22
    assert len(body["phie"]["p50"]) == len(body["depth"])
