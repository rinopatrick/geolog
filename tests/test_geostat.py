"""Ordinary kriging checks."""

from __future__ import annotations

import numpy as np
import pytest

from backend.geostat import krige_grid


def test_kriging_reproduces_constant_surface():
    points = np.asarray([
        [0, 0, 10.0],
        [0, 1, 10.0],
        [1, 0, 10.0],
        [1, 1, 10.0],
    ])
    grid, info = krige_grid(points, [0, 1, 2], [0, 1, 2], variogram_model="spherical")
    assert np.allclose(grid, 10.0, atol=1e-5)
    assert info["reader"] == "ordinary_kriging"
    assert info["variogram_model"] == "spherical"


def test_kriging_anisotropy_and_validation():
    points = np.asarray([
        [0, 0, 100.0],
        [0, 1, 100.0],
        [1, 0, 104.0],
        [1, 1, 104.0],
    ])
    grid, info = krige_grid(
        points,
        [0, 1],
        [0, 1],
        range_m=10,
        sill=4,
        anisotropy_ratio=2,
        azimuth_deg=30,
    )
    assert len(grid) == 2 and len(grid[0]) == 2
    assert info["anisotropy_ratio"] == 2

    with pytest.raises(ValueError, match="variogram"):
        krige_grid(points, [0, 1], [0, 1], variogram_model="unknown")
