"""DRHO and bad-hole handling in the density-to-porosity path.

DRHO was parsed, stored and plotted but never consulted by any compute path, and
six endpoints each had their own copy of the density-porosity formula fed raw
RHOB. A washed-out or rugose interval therefore produced porosity that looked
like real rock.

Defaults are checked here too: the QC rule reports, and only nulls samples when
asked, because silently dropping data is a data change.
"""

from __future__ import annotations

import numpy as np
import pytest
from fastapi.testclient import TestClient

from backend.curve_corrections import (
    DEFAULT_DRHO_LIMIT,
    DEFAULT_FLUID_DENSITY,
    DEFAULT_MATRIX_DENSITY,
    DEFAULT_WASHOUT_INCHES,
    apply_mask,
    bad_hole_mask,
    density_porosity,
    qc_summary,
)
from backend.las_parser import LASParser
from backend.main import app

client = TestClient(app)
HEADERS = {"X-User-Role": "interpreter"}


def _compute_sw(wid: int, **params) -> dict:
    payload = {"model": "archie", "a": 1.0, "m": 2.0, "n": 2.0, "rw": 0.1,
               "gr_clean": 20.0, "gr_shale": 120.0}
    payload.update(params)
    r = client.post(f"/api/wells/{wid}/compute-sw", json=payload, headers=HEADERS)
    assert r.status_code == 200, r.text
    return r.json()


# ─── density_porosity ───────────────────────────────────────────


def test_density_porosity_matches_the_equation():
    """phi_D = (rho_ma - RHOB) / (rho_ma - rho_f) with the standard constants."""
    # (2.65 - 2.30) / (2.65 - 1.00) = 0.35 / 1.65
    assert density_porosity(np.array([2.30]))[0] == pytest.approx(0.2121212, abs=1e-6)


def test_density_porosity_uses_the_supplied_matrix_and_fluid():
    # limestone matrix 2.71, fluid 1.0 -> (2.71-2.30)/1.71
    got = density_porosity(np.array([2.30]), rho_ma=2.71, rho_f=1.0)[0]
    assert got == pytest.approx(0.2397661, abs=1e-6)


def test_density_porosity_respects_clip_bounds():
    # RHOB 2.0 is above the default matrix density's reach once clipped
    assert density_porosity(np.array([1.50]), lo=0.0, hi=0.60)[0] == pytest.approx(0.60)
    assert density_porosity(np.array([3.00]), lo=-0.15, hi=0.60)[0] == pytest.approx(-0.15)


def test_density_porosity_does_not_divide_by_zero():
    """Matrix and fluid density equal must not produce inf or nan."""
    out = density_porosity(np.array([2.30]), rho_ma=1.0, rho_f=1.0, lo=0.0, hi=0.60)
    assert np.isfinite(out[0])


def test_defaults_are_the_standard_ones():
    assert DEFAULT_MATRIX_DENSITY == 2.65
    assert DEFAULT_FLUID_DENSITY == 1.0


# ─── bad_hole_mask ──────────────────────────────────────────────


def test_flags_drho_above_the_limit():
    drho = np.array([0.01, -0.02, 0.06, -0.09, 0.05])
    mask, reasons = bad_hole_mask(5, drho=drho)
    # strictly greater than the limit, so exactly 0.05 is not flagged
    assert mask.tolist() == [False, False, True, True, False]
    assert reasons["drho"] == 2


def test_nan_drho_is_not_flagged():
    """A missing correction is not a large correction."""
    mask, reasons = bad_hole_mask(3, drho=np.array([np.nan, 0.01, np.nan]))
    assert mask.tolist() == [False, False, False]
    assert reasons["drho"] == 0


def test_drho_limit_is_configurable():
    drho = np.array([0.03])
    assert bad_hole_mask(1, drho=drho)[0].tolist() == [False]
    assert bad_hole_mask(1, drho=drho, drho_limit=0.02)[0].tolist() == [True]


def test_flags_caliper_washout_over_bit_size():
    cali = np.array([8.0, 10.0, 12.5])
    bs = 8.0
    mask, reasons = bad_hole_mask(3, cali=cali, bit_size=bs)
    # 8.0 -> in gauge, 10.0 -> exactly +2in, 12.5 -> washout
    assert mask.tolist() == [False, False, True]
    assert reasons["washout"] == 1


def test_washout_threshold_is_configurable():
    cali = np.array([10.0])
    assert bad_hole_mask(1, cali=cali, bit_size=8.0)[0].tolist() == [False]
    assert bad_hole_mask(1, cali=cali, bit_size=8.0, washout_inches=1.0)[0].tolist() == [True]


def test_no_inputs_flags_nothing():
    """Existing behaviour is unchanged for wells without DRHO or caliper."""
    mask, reasons = bad_hole_mask(5)
    assert not mask.any()
    assert reasons == {"drho": 0, "washout": 0}


def test_caliper_without_bit_size_flags_nothing():
    mask, _ = bad_hole_mask(2, cali=np.array([20.0, 20.0]))
    assert not mask.any()


def test_mismatched_lengths_are_ignored():
    """A curve of the wrong length must not raise or misalign."""
    mask, reasons = bad_hole_mask(3, drho=np.array([0.9, 0.9]))
    assert not mask.any()
    assert reasons["drho"] == 0


def test_reasons_are_reported_separately():
    drho = np.array([0.9, 0.0])
    cali = np.array([8.0, 20.0])
    mask, reasons = bad_hole_mask(2, drho=drho, cali=cali, bit_size=8.0)
    assert reasons["drho"] == 1
    assert reasons["washout"] == 1
    assert mask.tolist() == [True, True]


def test_apply_mask_nulls_only_the_flagged_samples():
    arr = np.array([1.0, 2.0, 3.0])
    out = apply_mask(arr, np.array([False, True, False]))
    assert out[0] == 1.0
    assert np.isnan(out[1])
    assert out[2] == 3.0
    assert not np.isnan(arr[1]), "input must not be mutated"


def test_qc_summary_shape():
    mask = np.array([True, False, False, False])
    summary = qc_summary(mask, {"drho": 1, "washout": 0})
    assert summary["bad_hole_count"] == 1
    assert summary["bad_hole_pct"] == pytest.approx(25.0)
    assert summary["total_samples"] == 4
    assert summary["reasons"] == {"drho": 1, "washout": 0}


# ─── Integration: compute-sw ────────────────────────────────────


def _bad_hole_well(make_well):
    """Two samples: one clean, one with a large tool correction."""
    return make_well("bh-mixed", {
        "DEPT": [1000.0, 1001.0],
        "GR": [20.0, 20.0],
        "RHOB": [2.30, 2.30],
        "NPHI": [0.30, 0.30],
        "RT": [10.0, 10.0],
        "DRHO": [0.01, 0.20],
    })


def test_compute_sw_reports_bad_hole_without_changing_results(make_well):
    """Default is report-only: identical Sw, plus a QC flag."""
    wid = _bad_hole_well(make_well)
    out = _compute_sw(wid)

    assert out["bad_hole"] == [False, True]
    assert out["qc"]["bad_hole_count"] == 1
    assert out["qc"]["total_samples"] == 2
    assert out["qc"]["reasons"]["drho"] == 1

    # Both samples still computed: nothing was dropped.
    assert out["sw"][0] is not None and out["sw"][1] is not None
    assert out["phie"][0] is not None and out["phie"][1] is not None
    # The clean sample keeps its hand-computed value.
    assert out["phie"][0] == pytest.approx(0.2561, abs=1e-4)
    assert out["sw"][0] == pytest.approx(0.3905, abs=1e-4)


def test_apply_bad_hole_filter_nulls_density_derived_values(make_well):
    """Opting in removes the untrustworthy sample but keeps GR/Rt-derived ones."""
    wid = _bad_hole_well(make_well)
    out = _compute_sw(wid, apply_bad_hole_filter=True)

    assert out["phie"][1] is None, "density-derived porosity must be dropped"
    assert out["sw"][1] is None, "Sw depends on that porosity"
    # VSH comes from GR, which is unaffected by hole condition.
    assert out["vsh"][0] is not None and out["vsh"][1] is not None
    assert out["vsh"][1] == pytest.approx(0.0, abs=1e-6)
    # The clean sample is untouched.
    assert out["phie"][0] == pytest.approx(0.2561, abs=1e-4)


def test_well_without_drho_reports_no_bad_hole(make_well):
    wid = make_well("bh-none", {
        "DEPT": [1000.0], "GR": [20.0], "RHOB": [2.30], "NPHI": [0.30], "RT": [10.0],
    })
    out = _compute_sw(wid)
    assert out["bad_hole"] == [False]
    assert out["qc"]["bad_hole_count"] == 0


def test_drho_limit_is_exposed_in_the_response(make_well):
    wid = _bad_hole_well(make_well)
    out = _compute_sw(wid)
    assert out["params"]["drho_limit"] == DEFAULT_DRHO_LIMIT
    assert out["params"]["washout_inches"] == DEFAULT_WASHOUT_INCHES


# ─── Real data ──────────────────────────────────────────────────


def test_real_fixture_drho_is_mostly_clean():
    """Sanity-check the threshold against a real KGS log, not just synthetics.

    kgs_stephens carries a density correction spanning about -0.25 to 0.27 g/cc,
    of which roughly a fifth of samples exceed the 0.05 limit. If the threshold
    were wrong this would flag everything or nothing.
    """
    las = LASParser.parse_file(
        "test_data/kgs_stephens_trust1_nonstandard_mnemonics.las"
    )
    drho = las.data["DRHO"]
    mask, reasons = bad_hole_mask(len(drho), drho=drho)

    pct = reasons["drho"] * 100.0 / len(drho)
    assert 10.0 < pct < 40.0, f"expected a minority of samples flagged, got {pct:.1f}%"
    assert not mask.all(), "a valid log must not be flagged wholesale"
