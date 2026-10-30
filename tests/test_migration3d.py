"""Post-stack 3D Kirchhoff migration checks."""

from __future__ import annotations

import numpy as np
import pytest

from backend.migration3d import kirchhoff_migrate


def test_kirchhoff_focuses_point_diffractor():
    ni = nx = 11
    nt = 120
    dt_ms = 2.0
    velocity = 2000.0
    spacing = 25.0
    target_depth = 100.0
    cube = np.zeros((ni, nx, nt), dtype=np.float32)
    inline_coords = np.arange(ni) * spacing
    crossline_coords = np.arange(nx) * spacing
    for row in range(ni):
        for column in range(nx):
            distance = np.sqrt(
                (inline_coords[row] - inline_coords[ni // 2]) ** 2
                + (crossline_coords[column] - crossline_coords[nx // 2]) ** 2
                + target_depth ** 2
            )
            sample = int(round(2.0 * distance / velocity * 1000.0 / dt_ms))
            if 0 <= sample < nt:
                cube[row, column, sample] = 1.0
    result = kirchhoff_migrate(
        cube,
        list(range(ni)),
        list(range(nx)),
        dt_ms,
        velocity,
        spacing,
        spacing,
        max_depth_samples=100,
    )
    amplitude = np.abs(result["cube"])
    peak = np.unravel_index(np.argmax(amplitude), amplitude.shape)
    assert peak[0] == ni // 2 and peak[1] == nx // 2
    assert result["depths_m"][peak[2]] == pytest.approx(target_depth, abs=2.0)


def test_migration_rejects_bad_velocity():
    cube = np.ones((3, 3, 8), dtype=np.float32)
    with pytest.raises(ValueError, match="velocity"):
        kirchhoff_migrate(cube, [0, 1, 2], [0, 1, 2], 2.0, 100.0, 25, 25)
