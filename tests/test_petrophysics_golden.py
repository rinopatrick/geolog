"""Numeric verification of the petrophysics compute path.

The parser bug this suite was written alongside was silent numeric corruption on
the way in. This is the same class of check on the way out: `compute-sw` returns
200 whether or not the arithmetic is right, and nothing previously asserted the
numbers.

Two kinds of assertion, deliberately:

- **Golden values** hand-computed from the published equations (Archie 1942,
  Larionov 1969, Clavier 1971, Stieber 1970). These are pinned as literals so a
  change in the implementation shows up as a diff rather than silently tracking it.
- **Physical invariants** that hold for any correct implementation: Sw is a
  fraction, resistivity up means Sw down, porosity up means Sw down.

Inputs are synthetic and exact, so the expected output is derivable by hand.
"""

from __future__ import annotations

import numpy as np
import pytest
from fastapi.testclient import TestClient

from backend.main import SessionLocal, app
from backend.models import CurveData, LogRun, Project, Well

client = TestClient(app)
HEADERS = {"X-User-Role": "interpreter"}


# ─── Helpers ────────────────────────────────────────────────────


def _make_well(name: str, curves: dict[str, list[float]]) -> int:
    """Create a well whose curves are exactly the supplied values."""
    db = SessionLocal()
    try:
        project = db.query(Project).order_by(Project.id.asc()).first()
        assert project is not None, "conftest should have seeded a project"

        well = Well(project_id=project.id, name=name, depth_unit="FT")
        db.add(well)
        db.flush()

        lengths = {len(v) for v in curves.values()}
        assert len(lengths) == 1, f"all curves must be the same length, got {lengths}"
        n = lengths.pop()

        run = LogRun(
            well_id=well.id, run_number=1, filename=f"{name}.las",
            start_depth=1000.0, stop_depth=1000.0 + n, step=1.0,
            null_value=-999.25, num_points=n,
        )
        db.add(run)
        db.flush()

        for mnemonic, values in curves.items():
            arr = np.asarray(values, dtype=np.float64)
            valid = arr[~np.isnan(arr)]
            db.add(CurveData(
                log_run_id=run.id, mnemonic=mnemonic, unit="",
                num_points=n,
                min_value=float(np.min(valid)) if len(valid) else None,
                max_value=float(np.max(valid)) if len(valid) else None,
                data_binary=arr.tobytes(),
            ))
        db.commit()
        return well.id
    finally:
        db.close()


def _compute_sw(wid: int, **params) -> dict:
    payload = {"model": "archie", "a": 1.0, "m": 2.0, "n": 2.0, "rw": 0.1}
    payload.update(params)
    r = client.post(f"/api/wells/{wid}/compute-sw", json=payload, headers=HEADERS)
    assert r.status_code == 200, r.text
    return r.json()


# ─── Golden values: Archie, clean sand ──────────────────────────
#
# GR 20, gr_clean 20, gr_shale 120  -> IGR 0 -> Vcl(larionov_tertiary) = 0
# RHOB 2.30 -> phi_d = (2.65-2.30)/1.65        = 0.2121212
# NPHI 0.30; 0.30 >= phi_d-0.03, so no gas effect -> phie_v = mean = 0.2560606
# phie = 0.2560606 - 0*0.30                    = 0.2560606
# Sw   = (1*0.1 / (0.2560606^2 * 10))^(1/2)    = 0.3905325


def test_archie_clean_sand_matches_hand_calculation():
    wid = _make_well("golden-clean", {
        "DEPT": [1000.0], "GR": [20.0], "RHOB": [2.30], "NPHI": [0.30], "RT": [10.0],
    })
    out = _compute_sw(wid, gr_clean=20.0, gr_shale=120.0)

    assert out["vsh"][0] == pytest.approx(0.0, abs=1e-6)
    assert out["phie"][0] == pytest.approx(0.2561, abs=1e-4)
    assert out["sw"][0] == pytest.approx(0.3905, abs=1e-4)


# ─── Golden values: shaly sand (Vclay + clay-corrected porosity) ─
#
# GR 70 -> IGR 0.5 -> Vcl = 0.083*(2^1.85 - 1)  = 0.2162152
# RHOB 2.35 -> phi_d = 0.1818182 ; NPHI 0.32 -> phie_v = 0.2509091
# phie = 0.2509091 - 0.2162152*0.30            = 0.1860445
# Sw   = (0.1 / (0.1860445^2 * 5))^(1/2)       = 0.7601478


def test_archie_shaly_sand_matches_hand_calculation():
    wid = _make_well("golden-shaly", {
        "DEPT": [1000.0], "GR": [70.0], "RHOB": [2.35], "NPHI": [0.32], "RT": [5.0],
    })
    out = _compute_sw(wid, gr_clean=20.0, gr_shale=120.0)

    assert out["vsh"][0] == pytest.approx(0.2162, abs=1e-4)
    assert out["phie"][0] == pytest.approx(0.1860, abs=1e-4)
    assert out["sw"][0] == pytest.approx(0.7601, abs=1e-4)


# ─── Golden values: gas effect switches to density-only porosity ─
#
# RHOB 2.20 -> phi_d = 0.2727273 ; NPHI 0.15 < phi_d-0.03 = 0.2427273
# -> gas crossover, phie_v = phi_d (NOT the average)
# phie = 0.2727273 ; Sw = (0.1/(0.2727273^2*20))^(1/2) = 0.2592725


def test_gas_effect_uses_density_only_porosity():
    wid = _make_well("golden-gas", {
        "DEPT": [1000.0], "GR": [20.0], "RHOB": [2.20], "NPHI": [0.15], "RT": [20.0],
    })
    out = _compute_sw(wid, gr_clean=20.0, gr_shale=120.0)

    assert out["phie"][0] == pytest.approx(0.2727, abs=1e-4), "gas branch must not average"
    assert out["sw"][0] == pytest.approx(0.2593, abs=1e-4)


# ─── Golden values: the four published Vclay equations ───────────
#
# At IGR = 0.5 (GR 70, endpoints 20/120):
#   larionov_tertiary  0.083*(2^1.85 - 1)                = 0.2162152
#   larionov_old       0.33*(2^1 - 1)                    = 0.33
#   steiber            IGR/(3 - 2*IGR)                   = 0.25
#   clavier            1.7 - sqrt(3.38 - 1.2^2)          = 0.3071612


@pytest.mark.parametrize("method,expected", [
    ("larionov_tertiary", 0.2162),
    ("larionov_old", 0.3300),
    ("steiber", 0.2500),
    ("clavier", 0.3072),
])
def test_vcl_methods_match_published_equations(method, expected):
    wid = _make_well(f"golden-vcl-{method}", {
        "DEPT": [1000.0], "GR": [70.0], "RHOB": [2.35], "NPHI": [0.32], "RT": [5.0],
    })
    out = _compute_sw(wid, gr_clean=20.0, gr_shale=120.0, vsh_method=method)
    assert out["vsh"][0] == pytest.approx(expected, abs=1e-4)


@pytest.mark.parametrize("method", ["larionov_tertiary", "larionov_old", "steiber", "clavier"])
def test_vcl_is_one_at_or_above_shale_endpoint(method):
    """Every method is defined to saturate at Vcl = 1 at IGR >= 1."""
    wid = _make_well(f"golden-vcl1-{method}", {
        "DEPT": [1000.0], "GR": [200.0], "RHOB": [2.35], "NPHI": [0.32], "RT": [5.0],
    })
    out = _compute_sw(wid, gr_clean=20.0, gr_shale=120.0, vsh_method=method)
    assert out["vsh"][0] == pytest.approx(1.0, abs=1e-6)


# ─── Physical invariants ────────────────────────────────────────


def test_sw_is_always_a_fraction():
    """Sw outside [0,1] is unphysical; the endpoint must clip."""
    wid = _make_well("inv-range", {
        "DEPT": [1000.0 + i for i in range(6)],
        "GR": [20.0, 40.0, 70.0, 100.0, 120.0, 200.0],
        "RHOB": [2.05, 2.20, 2.40, 2.60, 2.75, 2.90],
        "NPHI": [0.40, 0.35, 0.30, 0.20, 0.10, 0.05],
        # includes an extremely conductive and an extremely resistive sample
        "RT": [0.05, 0.5, 5.0, 50.0, 5000.0, 50000.0],
    })
    out = _compute_sw(wid, gr_clean=20.0, gr_shale=120.0)
    for value in out["sw"]:
        if value is None:
            continue
        assert 0.0 <= value <= 1.0, f"Sw out of range: {value}"
    for value in out["phie"]:
        if value is None:
            continue
        assert 0.0 <= value <= 0.60, f"PHIE out of range: {value}"
    for value in out["vsh"]:
        if value is None:
            continue
        assert 0.0 <= value <= 1.0, f"VSH out of range: {value}"


def test_sw_decreases_as_resistivity_increases():
    """Archie: for fixed porosity and Rw, more resistivity means less water."""
    rts = [1.0, 5.0, 10.0, 50.0, 100.0]
    wid = _make_well("inv-rt", {
        "DEPT": [1000.0 + i for i in range(len(rts))],
        "GR": [20.0] * len(rts),
        "RHOB": [2.30] * len(rts),
        "NPHI": [0.30] * len(rts),
        "RT": rts,
    })
    out = _compute_sw(wid, gr_clean=20.0, gr_shale=120.0)
    sw = out["sw"]
    assert all(sw[i] >= sw[i + 1] for i in range(len(sw) - 1)), f"not monotonic: {sw}"


def test_sw_decreases_as_porosity_increases():
    """More pore space at fixed resistivity means a lower water saturation."""
    rhobs = [2.60, 2.45, 2.30, 2.15, 2.05]
    wid = _make_well("inv-phi", {
        "DEPT": [1000.0 + i for i in range(len(rhobs))],
        "GR": [20.0] * len(rhobs),
        "RHOB": rhobs,
        "NPHI": [0.10, 0.18, 0.30, 0.38, 0.42],
        "RT": [10.0] * len(rhobs),
    })
    out = _compute_sw(wid, gr_clean=20.0, gr_shale=120.0)
    sw = out["sw"]
    assert all(sw[i] >= sw[i + 1] for i in range(len(sw) - 1)), f"not monotonic: {sw}"


def test_sw_increases_with_formation_water_resistivity():
    """A more saline Rw means more water saturation at the same Rt."""
    wid = _make_well("inv-rw", {
        "DEPT": [1000.0 + i for i in range(3)],
        "GR": [20.0] * 3, "RHOB": [2.30] * 3, "NPHI": [0.30] * 3,
        "RT": [10.0] * 3,
    })
    low = _compute_sw(wid, gr_clean=20.0, gr_shale=120.0, rw=0.05)["sw"][0]
    high = _compute_sw(wid, gr_clean=20.0, gr_shale=120.0, rw=0.20)["sw"][0]
    assert low < high, f"Rw 0.05 -> {low}, Rw 0.20 -> {high}"


def test_sw_increases_with_exponent_n():
    """Higher n means Sw is more sensitive to resistivity, so Sw rises."""
    wid = _make_well("inv-n", {
        "DEPT": [1000.0 + i for i in range(3)],
        "GR": [20.0] * 3, "RHOB": [2.30] * 3, "NPHI": [0.30] * 3,
        "RT": [10.0] * 3,
    })
    n2 = _compute_sw(wid, gr_clean=20.0, gr_shale=120.0, n=2.0)["sw"][0]
    n3 = _compute_sw(wid, gr_clean=20.0, gr_shale=120.0, n=3.0)["sw"][0]
    assert n2 < n3, f"n=2 -> {n2}, n=3 -> {n3}"


# ─── Missing / unusable data must be reported, not fabricated ────


def test_sw_is_null_where_porosity_is_below_cutoff():
    """The endpoint skips samples with phie < 0.01 rather than inventing a value."""
    wid = _make_well("edge-tight", {
        "DEPT": [1000.0, 1001.0],
        # 2.649 gives phi_d ~ 0.0006, below the 0.01 cutoff
        "GR": [20.0, 20.0], "RHOB": [2.649, 2.30], "NPHI": [0.001, 0.30],
        "RT": [10.0, 10.0],
    })
    out = _compute_sw(wid, gr_clean=20.0, gr_shale=120.0)
    assert out["sw"][0] is None, "tight sample should be null, not a number"
    assert out["sw"][1] is not None


def test_sw_is_null_where_resistivity_is_null():
    wid = _make_well("edge-null-rt", {
        "DEPT": [1000.0, 1001.0],
        "GR": [20.0, 20.0], "RHOB": [2.30, 2.30], "NPHI": [0.30, 0.30],
        "RT": [float("nan"), 10.0],
    })
    out = _compute_sw(wid, gr_clean=20.0, gr_shale=120.0)
    assert out["sw"][0] is None
    assert out["sw"][1] is not None


def test_vsh_is_null_where_gr_is_null():
    wid = _make_well("edge-null-gr", {
        "DEPT": [1000.0, 1001.0],
        "GR": [float("nan"), 20.0], "RHOB": [2.30, 2.30],
        "NPHI": [0.30, 0.30], "RT": [10.0, 10.0],
    })
    out = _compute_sw(wid, gr_clean=20.0, gr_shale=120.0)
    assert out["vsh"][0] is None
    assert out["vsh"][1] is not None


def test_missing_rt_curve_is_rejected():
    wid = _make_well("edge-no-rt", {
        "DEPT": [1000.0], "GR": [20.0], "RHOB": [2.30], "NPHI": [0.30],
    })
    r = client.post(f"/api/wells/{wid}/compute-sw", json={"model": "archie"}, headers=HEADERS)
    assert r.status_code == 400
    assert "RT" in r.json()["detail"]


def test_missing_gr_curve_is_rejected():
    wid = _make_well("edge-no-gr", {
        "DEPT": [1000.0], "RHOB": [2.30], "NPHI": [0.30], "RT": [10.0],
    })
    r = client.post(f"/api/wells/{wid}/compute-sw", json={"model": "archie"}, headers=HEADERS)
    assert r.status_code == 400
    assert "GR" in r.json()["detail"]


def test_unknown_well_is_404():
    r = client.post("/api/wells/999999/compute-sw", json={"model": "archie"}, headers=HEADERS)
    assert r.status_code in (400, 404)
