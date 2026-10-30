"""Synthetic seismogram unit and time-sampling checks."""

from __future__ import annotations

import numpy as np
import pytest

from backend.seismic_tie import build_tie
from backend.synthetic import compute_synthetic_seismogram


def _curves():
    depth = np.arange(1000.0, 1100.0)
    n = len(depth)
    dt = np.full(n, 100.0)
    rhob = 2.4 + 0.1 * np.sin(np.arange(n) / 7.0)
    rhob[: n // 2] = 2.2
    rhob[n // 2:] = 2.7
    return dt, rhob, depth


def test_metric_and_imperial_twt_match():
    dt, rhob, depth = _curves()
    imperial = compute_synthetic_seismogram(dt, rhob, depth, dt_unit="US/F", depth_unit="FT")
    metric = compute_synthetic_seismogram(
        dt / 0.3048,
        rhob,
        depth * 0.3048,
        dt_unit="US/M",
        depth_unit="M",
    )
    assert imperial["stats"]["twt_max_s"] == pytest.approx(0.0198, rel=1e-6)
    assert metric["stats"]["twt_max_s"] == pytest.approx(imperial["stats"]["twt_max_s"], rel=1e-6)
    assert len(imperial["synthetic"]) == len(imperial["depth"])
    assert len(metric["synthetic"]) == len(metric["depth"])
    assert np.all(np.isfinite(imperial["synthetic"]))
    assert imperial["params"]["time_sample_s"] > 0


def test_checkshot_must_cover_log_depths():
    dt, rhob, depth = _curves()
    synthetic = compute_synthetic_seismogram(dt, rhob, depth)
    seismic = np.zeros(100)
    with pytest.raises(ValueError, match="does not cover"):
        build_tie(
            synthetic,
            seismic,
            2.0,
            [{"depth": 5000, "twt_ms": 0}, {"depth": 5100, "twt_ms": 100}],
        )


def test_checkshot_twt_must_increase():
    dt, rhob, depth = _curves()
    synthetic = compute_synthetic_seismogram(dt, rhob, depth)
    seismic = np.zeros(100)
    with pytest.raises(ValueError, match="TWT"):
        build_tie(
            synthetic,
            seismic,
            2.0,
            [{"depth": 1000, "twt_ms": 100}, {"depth": 1100, "twt_ms": 50}],
        )


def test_tie_time_origin_includes_delay_and_datum():
    dt, rhob, depth = _curves()
    synthetic = compute_synthetic_seismogram(dt, rhob, depth)
    seismic = np.zeros(100)
    result = build_tie(
        synthetic,
        seismic,
        0.5,
        checkshot=[],
        max_shift_ms=2,
        time_origin_ms=1.0,
    )
    assert result["twt_ms"][0] == pytest.approx(1.0)
    assert result["time_origin_ms"] == pytest.approx(1.0)
