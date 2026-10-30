"""Regression: Castagna mudrock units, decline guards, sat-height validation."""

from __future__ import annotations

import numpy as np
import pytest

from backend.decline import compute_eur, fit_best, fit_exponential
from backend.geomechanics import compute as geomech_compute
from backend.saturation_height import apply_model, fit_model
from backend.velocity import time_to_depth_ms


def _sem(depth_ft: float = 1000.0, dt_us_ft: float = 50.0, n: int = 11):
    depth = np.arange(depth_ft, depth_ft + n, 1.0)
    curves = {
        "RHOB": np.full(n, 2.35),
        "DT": np.full(n, dt_us_ft),
        "GR": np.full(n, 80.0),
    }
    return {
        "depth": depth,
        "tvd": depth.copy(),
        "curves": curves,
        "metadata": {
            "unit_system": "field",
            "aliases": [
                {"name": "RHOB", "raw": "RHOB"},
                {"name": "DT", "raw": "DT"},
                {"name": "GR", "raw": "GR"},
            ],
        },
    }


def test_castagna_dts_in_physical_range():
    # DT=50us/ft -> Vp ~6096 m/s; Castagna Vs ~4083 m/s (~0.67 Vp).
    # VP/VS curves are m/s; the elastic moduli must reflect that scale.
    out = geomech_compute(_sem(), {}, None)
    dts = np.array([v for v in out["curves"]["DTS"] if v is not None], dtype=float)
    assert len(dts) == 11
    assert np.all(dts > 10.0) and np.all(dts < 1200.0)
    vs = np.array([v for v in out["curves"]["VS"] if v is not None], dtype=float)
    vp = np.array([v for v in out["curves"]["VP"] if v is not None], dtype=float)
    assert np.all(vs > 1000.0)
    assert np.all(vs < vp)
    e = np.array([v for v in out["curves"]["E"] if v is not None], dtype=float)
    # Dense fast carbonate: E must be tens of GPa, not ~1 GPa from a
    # double ft->m conversion.
    assert np.all(e > 10.0)


def test_exponential_decline_rejects_growing_rates():
    from datetime import date, timedelta

    dates = [date(2020, 1, 1) + timedelta(days=30 * i) for i in range(12)]
    rates = [100.0 + 5.0 * i for i in range(12)]
    assert fit_exponential(np.arange(12) * 30.0, np.array(rates))["d"] == pytest.approx(0.0)
    best = fit_best(dates, rates)
    assert best is not None
    # A growing series is not a decline; the fit must not claim a meaningful
    # positive rate (hyperbolic grid floor is di=1e-4/day, ~3%/month at most).
    assert best.get("d", best.get("di", 0.0)) <= 1e-3


def test_eur_growing_series_stays_bounded():
    from datetime import date, timedelta

    dates = [date(2020, 1, 1) + timedelta(days=30 * i) for i in range(12)]
    rates = [100.0 + 5.0 * i for i in range(12)]
    best = fit_best(dates, rates)
    assert best is not None
    eur = compute_eur(best)
    # Flat clamped fit over 10 years at ~155 bpd stays in a sane band;
    # a runaway exponential would explode into the billions.
    assert eur is not None and eur < 10_000_000


def test_hyperbolic_b_capped_at_unity():
    from datetime import date, timedelta

    dates = [date(2020, 1, 1) + timedelta(days=30 * i) for i in range(24)]
    # Steep transient-style decline: the old 0.1-1.5 grid pinned b at 1.5.
    rates = [1000.0 / (1.0 + 2.0 * 0.05 * (30.0 * i)) ** 0.5 for i in range(24)]
    best = fit_best(dates, rates, model="hyperbolic")
    assert best is not None
    assert 0.0 < best["b"] <= 1.0


def test_brooks_corey_rejects_inverted_data():
    pc = np.array([10.0, 20, 40, 80, 160.0])
    sw_good = np.array([0.9, 0.7, 0.5, 0.35, 0.25])
    good = fit_model("brooks_corey", pc, sw_good)
    assert good["r2"] > 0.9
    with pytest.raises(ValueError, match="monotonic"):
        fit_model("brooks_corey", pc, sw_good[::-1])


def test_time_to_depth_rejects_negative_times():
    with pytest.raises(ValueError, match="non-negative"):
        time_to_depth_ms([-100, 0, 500], "constant", 2000, [])


def test_time_to_depth_rejects_nonfinite_times():
    with pytest.raises(ValueError, match="finite"):
        time_to_depth_ms([0, float("nan"), 500], "constant", 2000, [])
    with pytest.raises(ValueError, match="finite"):
        time_to_depth_ms([0, float("inf"), 500], "constant", 2000, [])
