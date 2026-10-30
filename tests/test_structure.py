"""Compartment and juxtaposition calculations."""

from __future__ import annotations

import pytest

from backend.structure import build_compartments, juxtaposition


def test_compartments_use_base_reservoir():
    top = [[2000.0, 2000.0], [2000.0, 2000.0]]
    base = [[2050.0, 2050.0], [2050.0, 2050.0]]
    faults = [{"id": 1, "points": [{"inline": 0, "crossline": 0.5}, {"inline": 1, "crossline": 0.5}]}]
    result = build_compartments(
        top,
        [0, 1],
        [0, 1],
        2100,
        25,
        25,
        faults,
        base_depth_grid=base,
    )
    assert result["base_used"] is True
    assert result["total_grv_m3"] == 50.0 * 4 * 25 * 25
    assert result["mean_reservoir_thickness_m"] == 50.0
    assert sum(item["grv_m3"] for item in result["compartments"]) == result["total_grv_m3"]


def test_juxtaposition_reservoir_overlap():
    top = [[2000.0, 2000.0, 2000.0] for _ in range(3)]
    base = [[2050.0, 2050.0, 2050.0] for _ in range(3)]
    faults = [{
        "id": 1,
        "points": [
            {"inline": 0, "crossline": 1},
            {"inline": 2, "crossline": 1},
        ],
    }]
    result = juxtaposition(top, base, [0, 1, 2], [0, 1, 2], faults)
    assert result["faults"][0]["reservoir_reservoir"] > 0
    assert result["faults"][0]["mean_overlap_m"] == pytest.approx(50.0)
    assert result["reservoir_reservoir_samples"] > 0


def test_fault_throw_from_horizon_offset():
    from backend.structure import fault_throw_from_surface

    top = [[2000.0, 2010.0, 2020.0] for _ in range(3)]
    points = [
        {"inline": 0, "crossline": 1},
        {"inline": 1, "crossline": 1},
        {"inline": 2, "crossline": 1},
    ]
    result = fault_throw_from_surface(top, [0, 1, 2], [0, 1, 2], points)
    assert result["samples"] == 3
    assert result["throw_median_m"] == pytest.approx(20.0)
    assert result["throw_max_m"] == pytest.approx(20.0)
