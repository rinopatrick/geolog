"""Post-stack 3D Kirchhoff depth migration (constant velocity)."""

from __future__ import annotations

from typing import Any

import numpy as np

try:
    from seismic import read_indexed_traces
except ImportError:
    from backend.seismic import read_indexed_traces


def _decimate(values: list[int], limit: int) -> list[int]:
    unique = sorted(set(int(value) for value in values))
    if len(unique) <= limit:
        return unique
    positions = np.linspace(0, len(unique) - 1, limit).round().astype(int)
    return [unique[int(position)] for position in sorted(set(positions.tolist()))]


def volume_cube(
    content: bytes,
    index: dict[str, Any],
    max_inlines: int = 32,
    max_crosslines: int = 32,
    max_samples: int = 256,
) -> dict[str, Any]:
    inlines = _decimate(index.get("trace_inlines") or [], max(2, int(max_inlines)))
    crosslines = _decimate(index.get("trace_crosslines") or [], max(2, int(max_crosslines)))
    if len(inlines) < 2 or len(crosslines) < 2:
        raise ValueError("3D migration needs at least two inlines and crosslines")
    ns = min(int(index["samples_per_trace"]), max(1, int(max_samples)))
    cube = np.zeros((len(inlines), len(crosslines), ns), dtype=np.float32)
    inline_positions = index.get("trace_inlines") or []
    crossline_positions = index.get("trace_crosslines") or []
    lookup: dict[tuple[int, int], list[int]] = {}
    for position, (inline, crossline) in enumerate(zip(inline_positions, crossline_positions)):
        key = (int(inline), int(crossline))
        if int(inline) in inlines and int(crossline) in crosslines:
            lookup.setdefault(key, []).append(position)
    for row, inline in enumerate(inlines):
        for column, crossline in enumerate(crosslines):
            positions = lookup.get((inline, crossline))
            if not positions:
                continue
            traces = read_indexed_traces(content, index, positions)
            trace = np.mean(traces, axis=0)[:ns]
            cube[row, column, :len(trace)] = trace
    return {
        "cube": cube,
        "inlines": inlines,
        "crosslines": crosslines,
        "sample_interval_ms": float(index["sample_interval_ms"]),
        "samples": ns,
    }


def kirchhoff_migrate(
    cube: np.ndarray,
    inlines: list[int],
    crosslines: list[int],
    sample_interval_ms: float,
    velocity_m_s: float,
    inline_spacing_m: float,
    crossline_spacing_m: float,
    max_depth_samples: int = 128,
    aperture_m: float | None = None,
) -> dict[str, Any]:
    cube = np.asarray(cube, dtype=np.float32)
    if cube.ndim != 3 or min(cube.shape) < 2:
        raise ValueError("migration cube must be at least 2x2x2")
    velocity = float(velocity_m_s)
    if not 500.0 <= velocity <= 8000.0:
        raise ValueError("velocity_m_s must be between 500 and 8000")
    dt_ms = float(sample_interval_ms)
    if dt_ms <= 0:
        raise ValueError("sample interval must be positive")
    inline_spacing = float(inline_spacing_m)
    crossline_spacing = float(crossline_spacing_m)
    if inline_spacing <= 0 or crossline_spacing <= 0:
        raise ValueError("inline/crossline spacing must be positive")
    ni, nx, nt = cube.shape
    times_ms = np.arange(nt, dtype=float) * dt_ms
    depth_step = velocity * dt_ms / 2000.0
    depth_count = max(2, min(int(max_depth_samples), nt))
    depths = np.arange(depth_count, dtype=float) * depth_step
    x = np.asarray(inlines, dtype=float) * inline_spacing
    y = np.asarray(crosslines, dtype=float) * crossline_spacing
    grid_x, grid_y = np.meshgrid(x, y, indexing="ij")
    grid_x = grid_x - grid_x.mean()
    grid_y = grid_y - grid_y.mean()
    x = x - x.mean()
    y = y - y.mean()
    migrated = np.zeros((ni, nx, depth_count), dtype=np.float32)
    fold = np.zeros((ni, nx, depth_count), dtype=np.float64)
    aperture = float(aperture_m) if aperture_m is not None else None
    for row in range(ni):
        for column in range(nx):
            trace = cube[row, column]
            if not np.any(np.isfinite(trace)) or not np.any(trace != 0):
                continue
            trace = np.nan_to_num(trace, nan=0.0)
            distance_xy = np.sqrt((grid_x - x[row]) ** 2 + (grid_y - y[column]) ** 2)
            inside = np.ones_like(distance_xy, dtype=bool)
            if aperture is not None:
                inside = distance_xy <= aperture
            for depth_index, depth in enumerate(depths):
                distance = np.sqrt(distance_xy ** 2 + depth ** 2)
                travel_ms = 2000.0 * distance / velocity
                sample = np.interp(travel_ms, times_ms, trace, left=0.0, right=0.0)
                weight = depth / np.maximum(distance, 1e-6)
                contribution = (sample * weight).astype(np.float64)
                contribution[~inside] = 0.0
                migrated[:, :, depth_index] += contribution.astype(np.float32)
                fold[:, :, depth_index] += (weight * inside).astype(np.float64)
    nonzero = fold > 1e-12
    migrated[nonzero] = (migrated[nonzero] / fold[nonzero]).astype(np.float32)
    migrated[~nonzero] = 0.0
    return {
        "cube": migrated,
        "inlines": inlines,
        "crosslines": crosslines,
        "depths_m": [round(float(value), 3) for value in depths],
        "depth_step_m": round(float(depth_step), 3),
        "velocity_m_s": velocity,
        "inline_spacing_m": inline_spacing,
        "crossline_spacing_m": crossline_spacing,
        "stats": {
            "inline_count": ni,
            "crossline_count": nx,
            "depth_count": depth_count,
            "max_amplitude": round(float(np.max(np.abs(migrated))), 6),
            "aperture_m": aperture,
        },
    }
