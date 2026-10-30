"""Regression: GRV cell-area contract, kriging exactness, Kirchhoff fold, SEG-Y signed headers."""

from __future__ import annotations

import numpy as np
import pytest

from backend.geostat import krige_grid
from backend.migration3d import _decimate, kirchhoff_migrate
from backend.seismic import index_segy, parse_segy
from backend.volumetrics import grv_from_depth_grid


def _segy_bytes(inlines=(100, 101, 102), crosslines=(200, 201, 202)) -> bytes:
    textual = b" " * 3200
    binary = bytearray(400)
    binary[16:18] = (2000).to_bytes(2, "big")
    binary[20:22] = (6).to_bytes(2, "big")
    binary[24:26] = (5).to_bytes(2, "big")
    traces = []
    for inline, crossline in zip(inlines, crosslines):
        header = bytearray(240)
        header[114:116] = (6).to_bytes(2, "big")
        header[188:192] = int(inline).to_bytes(4, "big", signed=True)
        header[192:196] = int(crossline).to_bytes(4, "big", signed=True)
        traces.append(bytes(header) + np.asarray([1.0] * 6, dtype=">f4").tobytes())
    return textual + bytes(binary) + b"".join(traces)


def test_grv_meter_coordinates_do_not_double_count_spacing():
    top = [[2000.0, 2000.0], [2000.0, 2000.0]]
    result = grv_from_depth_grid(top, 2100, 25, 25, [0, 25], [0, 25])
    assert result["cell_area_m2"] == pytest.approx(25.0 * 25.0)
    assert result["grv_m3"] == pytest.approx(100.0 * 4 * 25.0 * 25.0)


def test_grv_index_labels_do_not_multiply_by_position():
    top = [[2000.0, 2000.0], [2000.0, 2000.0]]
    base = [[2050.0, 2050.0], [2050.0, 2050.0]]
    result = grv_from_depth_grid(top, 2100, 25, 25, [100, 101], [200, 201], base_depth_grid=base)
    assert result["cell_area_m2"] == pytest.approx(25.0 * 25.0)
    assert result["grv_m3"] == pytest.approx(50.0 * 4 * 25.0 * 25.0)


def test_kriging_honors_sample_at_exact_location():
    pts = np.array(
        [
            [0.0, 0.0, 100.0],
            [10.0, 0.0, 110.0],
            [0.0, 10.0, 105.0],
            [10.0, 10.0, 115.0],
            [5.0, 5.0, 108.0],
        ]
    )
    grid, _ = krige_grid(pts, [0.0], [0.0], nugget=0.0)
    assert grid[0][0] == pytest.approx(100.0, abs=1.0)


def test_kirchhoff_fold_normalization_is_per_voxel():
    ni = nx = 9
    nt = 80
    cube = np.zeros((ni, nx, nt), dtype=np.float32)
    cube[:, :, 20] = 1.0
    full = kirchhoff_migrate(cube, list(range(ni)), list(range(nx)), 2.0, 2000.0, 25.0, 25.0,
                             max_depth_samples=30)
    half = cube.copy()
    half[:4, :, :] = 0.0
    part = kirchhoff_migrate(half, list(range(ni)), list(range(nx)), 2.0, 2000.0, 25.0, 25.0,
                             max_depth_samples=30)
    # With a global scalar normalization the half-fold case is diluted by dead
    # traces; per-voxel fold keeps amplitudes comparable (within 2x).
    ratio = float(np.max(np.abs(part["cube"])) / max(float(np.max(np.abs(full["cube"]))), 1e-12))
    assert 0.5 <= ratio <= 2.0


def test_kirchhoff_aperture_does_not_dilute_fold():
    ni = nx = 9
    nt = 80
    cube = np.zeros((ni, nx, nt), dtype=np.float32)
    cube[:, :, 20] = 1.0
    wide = kirchhoff_migrate(cube, list(range(ni)), list(range(nx)), 2.0, 2000.0, 25.0, 25.0,
                             max_depth_samples=30, aperture_m=None)
    narrow = kirchhoff_migrate(cube, list(range(ni)), list(range(nx)), 2.0, 2000.0, 25.0, 25.0,
                               max_depth_samples=30, aperture_m=1.0)
    # Traces excluded by the aperture must not count toward fold; otherwise the
    # narrow-aperture image is diluted toward zero by dead contributions.
    assert np.max(np.abs(narrow["cube"])) >= np.max(np.abs(wide["cube"])) * 0.5


def test_segy_signed_inline_header():
    parsed = parse_segy(_segy_bytes(inlines=(-5, -4, -3), crosslines=(200, 201, 202)))
    assert parsed["inline_min"] == -5 and parsed["inline_max"] == -3
    indexed = index_segy(_segy_bytes(inlines=(-5, -4, -3), crosslines=(200, 201, 202)))
    assert indexed["inline_min"] == -5 and indexed["inline_max"] == -3


def test_decimate_helpers_stable():
    assert _decimate([1, 2, 3], 10) == [1, 2, 3]
