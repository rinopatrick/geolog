"""Analytic and field-fixture physics benchmarks."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from backend.las_parser import LASParser
from backend.seismic import _link_geometry, ibm_to_ieee
from backend.saturation import saturation
from backend.synthetic import _depth_scale, _dt_scale, compute_synthetic_seismogram
from backend.velocity import time_to_depth_ms
from backend.volumetrics import grv_from_depth_grid

ROOT = Path(__file__).resolve().parents[1]


def test_ibm_float_known_words():
    values = ibm_to_ieee(bytes.fromhex("41100000c1100000"))
    assert values[0] == pytest.approx(1.0, rel=1e-7)
    assert values[1] == pytest.approx(-1.0, rel=1e-7)


def test_constant_and_layer_depth_analytic():
    assert time_to_depth_ms([0, 1000, 2000], "constant", 2500, []).tolist() == [0.0, 1250.0, 2500.0]
    layers = [
        {"top_ms": 0, "velocity_m_s": 2000},
        {"top_ms": 1000, "velocity_m_s": 3000},
    ]
    assert time_to_depth_ms([500, 1500], "layers", None, layers).tolist() == [500.0, 1750.0]


def test_fault_geometry_depth_analytic():
    points = [
        {"inline": 0, "crossline": 0, "sample": 100},
        {"inline": 0, "crossline": 1, "sample": 100},
        {"inline": 1, "crossline": 0, "sample": 108},
        {"inline": 1, "crossline": 1, "sample": 108},
    ]
    segments = [{"sample": 100, "throw": {"lag_ms": 8.0, "throw_ms": 8.0}}]
    geometry, _ = _link_geometry(
        points,
        segments,
        sample_interval_ms=2.0,
        inline_spacing_m=25.0,
        crossline_spacing_m=25.0,
        velocity_m_s=2500.0,
    )
    # 100 + 8*inline ms; at 2500 m/s the depth difference is 10 m per line.
    assert geometry["domain"] == "depth"
    assert geometry["throw_m"] == pytest.approx(10.0)
    assert geometry["dip_inline_m_per_line"] == pytest.approx(10.0)
    assert geometry["dip_angle_deg"] == pytest.approx(np.degrees(np.arctan(10.0 / 25.0)), abs=0.001)


def test_grv_base_analytic():
    top = [[2000.0, 2000.0], [2000.0, 2000.0]]
    base = [[2050.0, 2050.0], [2050.0, 2050.0]]
    result = grv_from_depth_grid(
        top,
        2100,
        25,
        25,
        [100, 101],
        [200, 201],
        base_depth_grid=base,
    )
    assert result["grv_m3"] == pytest.approx(50.0 * 4 * 25 * 25)
    assert result["mean_reservoir_thickness_m"] == pytest.approx(50.0)


def test_saturation_clean_sand_equivalence():
    archie = saturation("archie", 10.0, 0.2, 0.0, a=1.0, m=2.0, n=2.0, rw=0.1)
    simandoux = saturation("simandoux", 10.0, 0.2, 0.0, a=1.0, m=2.0, n=2.0, rw=0.1, rsh=4.0)
    indonesian = saturation("indonesian", 10.0, 0.2, 0.0, a=1.0, m=2.0, n=2.0, rw=0.1, rsh=4.0)
    assert simandoux == pytest.approx(archie)
    assert indonesian == pytest.approx(archie)


@pytest.mark.parametrize(
    "path",
    [
        ROOT / "data" / "hawkins_01.las",
        ROOT / "test_data" / "kgs_culwell_unit4_32_density_neutron_resistivity.las",
    ],
)
def test_field_las_twt_and_synthetic_invariants(path):
    las = LASParser.parse_file(str(path))
    depth = np.asarray(las.data["DEPT"], dtype=float)
    dt = np.asarray(las.data["DT"], dtype=float)
    rhob = np.asarray(las.data["RHOB"], dtype=float)
    if not np.any(np.isfinite(dt)):
        pytest.skip(f"{path.name} has no DT")
    result = compute_synthetic_seismogram(
        dt,
        rhob,
        depth,
        dt_unit="US/F",
        depth_unit="FT",
        max_points=5000,
    )
    valid = np.isfinite(dt) & np.isfinite(rhob) & np.isfinite(depth) & (dt > 0) & (rhob > 1.5) & (rhob < 3.5)
    dt_v = dt[valid]
    depth_m = depth[valid] * _depth_scale("FT")
    twt_expected = 2.0 * np.sum(dt_v[:-1] * _dt_scale("US/F") * np.abs(np.diff(depth_m)))
    assert result["stats"]["twt_max_s"] == pytest.approx(twt_expected, abs=1e-4)
    assert np.all(np.diff(result["twt"]) >= 0)
    assert len(result["synthetic"]) == len(result["depth"])
    assert np.all(np.isfinite(result["synthetic"]))
