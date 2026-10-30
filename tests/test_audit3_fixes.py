"""Regression: geomechanics API-scale consistency (psi vs ppg)."""

from __future__ import annotations

import numpy as np
import pytest

from backend.geomechanics import compute as geomech_compute
from tests.test_audit2_fixes import _sem


def _realistic(n: int = 50):
    return _sem(depth_ft=5000.0, dt_us_ft=90.0, n=n)


def test_cdp_is_drawdown_capacity_not_absolute_stress():
    out = geomech_compute(_realistic(), {"ucs": 3000.0}, None)
    cdp = np.array([v for v in out["curves"]["SAND_CDP"] if v is not None], dtype=float)
    pp = np.array([v for v in out["curves"]["PP"] if v is not None], dtype=float)
    shmax = np.array([v for v in out["curves"]["SHMAX"] if v is not None], dtype=float)
    shmin = np.array([v for v in out["curves"]["SHMIN"] if v is not None], dtype=float)
    alpha, ucs = 0.9, 3000.0
    pw_crit = (3.0 * shmax - shmin - alpha * pp - ucs) / 2.0
    assert np.allclose(cdp, np.maximum(pp - pw_crit, 0.0), rtol=1e-6)
    # Drawdown capacity is bounded by reservoir pressure; the old absolute
    # formula returned multi-thousand psi above Pp.
    assert np.all(cdp <= pp + 1e-6)


def test_provenance_labels_dynamic_moduli_as_correlation():
    out = geomech_compute(_realistic(11), {}, None)
    assert out["provenance"]["E"] == "correlation"


def test_mw_window_scales_with_depth_and_is_ordered():
    out = geomech_compute(_realistic(), {"ucs": 3000.0, "mud_weight": 12.0}, None)
    mw_min = np.array(out["curves"]["MW_MIN"], dtype=float)
    mw_max = np.array(out["curves"]["MW_MAX"], dtype=float)
    assert np.all(np.isfinite(mw_min)) and np.all(np.isfinite(mw_max))
    assert np.all(mw_max >= mw_min)
    # TvD is ~constant here; mud window must be roughly flat, not exploding.
    assert float(np.ptp(mw_min)) < 2.0


def test_breakout_endpoint_recovers_known_shmax(make_well):
    """End-to-end: synthetic breakout from the forward hoop inverts to SHmax."""
    import math

    from fastapi.testclient import TestClient

    from backend.main import app

    client = TestClient(app)
    head = {"X-User-Role": "admin"}
    wid = make_well(
        "BO-TEST",
        {
            "DEPT": np.arange(5000.0, 5011.0, 1.0),
            "GR": np.full(11, 80.0),
            "RHOB": np.full(11, 2.35),
            "DT": np.full(11, 90.0),
            "DTS": np.full(11, 170.0),
        },
    )
    # Physically consistent normal-faulting regime: Shmin < Sv(~5093 psi).
    shmax_true, shmin_true, ucs, alpha = 5500.0, 4000.0, 2500.0, 0.9
    pid = client.get("/api/projects/", headers=head).json()[0]["id"]
    create = client.post(
        f"/api/wells/{wid}/geomechanics/models",
        headers=head,
        json={
            "params": {"ucs": ucs, "biot": alpha, "mud_weight": 12.0},
            "calibration": {
                "pp": [[5000, 4500], [5010, 4545]],
                "shmin": [[5000, shmin_true], [5010, shmin_true + 40]],
            },
        },
    )
    assert create.status_code == 201, create.text
    mid = create.json()["id"]
    # Forward hoop at mid depth with the TRUE shmax, then width at UCS edge.
    from backend.geomechanics import _borehole_hoop, _far_field_tensor

    tensor = _far_field_tensor(
        np.array([shmax_true]), np.array([shmin_true]), np.array([9500.0]), 0.0
    )
    base_max, _, _ = _borehole_hoop(tensor, 0.0, 0.0)
    pp, pw = 4522.0, 12.0 * 0.052 * 5005.0
    edge = ucs + pw + alpha * pp
    cos2t = (shmax_true + shmin_true - edge) / (2.0 * (shmax_true - shmin_true))
    assert -1.0 <= cos2t <= 1.0
    width_deg = math.degrees(2.0 * (math.pi / 2.0 - 0.5 * math.acos(cos2t)))
    assert 0 < width_deg < 120
    cal = client.post(
        f"/api/wells/{wid}/geomechanics/breakout-calibration",
        headers=head,
        json={"model_id": mid, "breakouts": [{"depth": 5005.0, "width_deg": width_deg, "mud_weight": 12.0}]},
    )
    assert cal.status_code == 200, cal.text
    recovered = cal.json()["points"][0]["value"]
    assert recovered == pytest.approx(shmax_true, rel=0.10)
