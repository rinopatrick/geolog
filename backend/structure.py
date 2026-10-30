"""Fault surfaces and compartment segmentation."""

from __future__ import annotations

from typing import Any

import numpy as np

try:
    from velocity import time_to_depth_ms
except ImportError:
    from backend.velocity import time_to_depth_ms

try:
    from geostat import krige_grid
except ImportError:
    from backend.geostat import krige_grid


def _axis(values: list[float], limit: int) -> list[float]:
    if len(values) <= limit:
        return values
    positions = np.linspace(0, len(values) - 1, limit).round().astype(int)
    return [values[int(position)] for position in sorted(set(positions.tolist()))]


def build_fault_surface(
    points: list[dict[str, float]],
    sample_interval_ms: float,
    max_grid: int = 64,
    velocity_m_s: float | None = None,
    layers: list[dict[str, float]] | None = None,
    method: str = "idw",
    variogram: dict[str, Any] | None = None,
    anisotropy_ratio: float = 1.0,
    azimuth_deg: float = 0.0,
) -> dict[str, Any]:
    if len(points) < 2:
        raise ValueError("fault surface needs at least two picks")
    values = np.asarray(
        [[float(point["inline"]), float(point["crossline"]), float(point["sample"])] for point in points],
        dtype=float,
    )
    if len(values) > 4000:
        positions = np.linspace(0, len(values) - 1, 4000).round().astype(int).tolist()
        values = values[positions]
    inlines = _axis(sorted(set(float(value) for value in values[:, 0])), max(2, int(max_grid)))
    crosslines = _axis(sorted(set(float(value) for value in values[:, 1])), max(2, int(max_grid)))
    interpolation = str(method or "idw").lower()
    variogram = variogram or {}
    kriging_info: dict[str, Any] = {}
    if interpolation == "kriging":
        grid, kriging_info = krige_grid(
            values,
            inlines,
            crosslines,
            variogram_model=str(variogram.get("model", "spherical")),
            range_m=variogram.get("range"),
            sill=variogram.get("sill"),
            nugget=float(variogram.get("nugget", 0.0) or 0.0),
            anisotropy_ratio=float(anisotropy_ratio or 1.0),
            azimuth_deg=float(azimuth_deg or 0.0),
            max_neighbors=int(variogram.get("max_neighbors", 16) or 16),
        )
        time_grid = np.asarray(grid, dtype=float) * float(sample_interval_ms)
    elif interpolation == "idw":
        grid = []
        for inline in inlines:
            distance = ((inline - values[:, 0]) ** 2)[:, None] + (np.asarray(crosslines)[None, :] - values[:, 1][:, None]) ** 2
            weights = 1.0 / (distance + 1e-9)
            samples = (weights * values[:, 2][None, :]).sum(axis=1) / weights.sum(axis=1)
            grid.append(samples)
        time_grid = np.asarray(grid, dtype=float) * float(sample_interval_ms)
    else:
        raise ValueError("fault surface method must be idw or kriging")
    domain = "time"
    if velocity_m_s is not None:
        time_grid = time_to_depth_ms(time_grid, "constant", velocity_m_s, [])
        domain = "depth"
    elif layers:
        time_grid = time_to_depth_ms(time_grid, "layers", None, layers)
        domain = "depth"
    return {
        "grid": [[round(float(value), 3) for value in row] for row in time_grid],
        "inlines": [int(value) for value in inlines],
        "crosslines": [int(value) for value in crosslines],
        "domain": domain,
        "stats": {
            "point_count": len(points),
            "inline_count": len(inlines),
            "crossline_count": len(crosslines),
            "min": round(float(np.min(time_grid)), 3),
            "max": round(float(np.max(time_grid)), 3),
            "mean": round(float(np.mean(time_grid)), 3),
            "method": interpolation,
            "anisotropy_ratio": float(anisotropy_ratio or 1.0),
            "azimuth_deg": float(azimuth_deg or 0.0),
            **({"kriging": kriging_info} if kriging_info else {}),
        },
    }


def _fault_side(point: tuple[float, float], polyline: list[dict[str, float]]) -> int:
    if len(polyline) < 2:
        return 0
    ordered = sorted(polyline, key=lambda item: (float(item["inline"]), float(item["crossline"])))
    px, py = point
    best_distance = float("inf")
    side = 0
    for first, second in zip(ordered, ordered[1:]):
        ax, ay = float(first["inline"]), float(first["crossline"])
        bx, by = float(second["inline"]), float(second["crossline"])
        dx, dy = bx - ax, by - ay
        length_sq = dx * dx + dy * dy
        if length_sq <= 1e-12:
            continue
        t = max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / length_sq))
        nx, ny = ax + t * dx, ay + t * dy
        distance = (px - nx) ** 2 + (py - ny) ** 2
        if distance < best_distance:
            best_distance = distance
            side = 1 if (dx * (py - ay) - dy * (px - ax)) >= 0 else -1
    return side


def build_compartments(
    depth_grid: list[list[float]],
    inlines: list[float],
    crosslines: list[float],
    contact_depth_m: float,
    inline_spacing_m: float,
    crossline_spacing_m: float,
    faults: list[dict[str, Any]],
) -> dict[str, Any]:
    grid = np.asarray(depth_grid, dtype=float)
    if grid.ndim != 2 or grid.size == 0:
        raise ValueError("surface has no depth grid")
    if not inline_spacing_m or not crossline_spacing_m:
        raise ValueError("surface needs inline/crossline spacing")
    inline_step = float(np.median(np.diff(np.asarray(inlines, dtype=float)))) if len(inlines) > 1 else 1.0
    crossline_step = float(np.median(np.diff(np.asarray(crosslines, dtype=float)))) if len(crosslines) > 1 else 1.0
    cell_area = float(inline_spacing_m) * float(crossline_spacing_m) * max(1.0, inline_step) * max(1.0, crossline_step)
    columns = np.nan_to_num(np.clip(float(contact_depth_m) - grid, 0.0, None), nan=0.0)
    groups: dict[str, dict[str, float]] = {}
    for row, inline in enumerate(inlines):
        for column, crossline in enumerate(crosslines):
            bits = tuple(str(_fault_side((float(inline), float(crossline)), fault.get("points") or [])) for fault in faults)
            key = "-".join(bits) if bits else "0"
            group = groups.setdefault(key, {"cells": 0.0, "area_m2": 0.0, "grv_m3": 0.0, "column_sum": 0.0})
            group["cells"] += 1
            group["column_sum"] += float(columns[row][column])
            group["area_m2"] += cell_area if columns[row][column] > 0 else 0.0
            group["grv_m3"] += float(columns[row][column]) * cell_area
    compartments = []
    for index, (key, group) in enumerate(groups.items()):
        compartments.append({
            "id": index + 1,
            "key": key,
            "cells": int(group["cells"]),
            "area_m2": round(group["area_m2"], 3),
            "grv_m3": round(group["grv_m3"], 3),
            "mean_column_m": round(group["column_sum"] / max(1.0, group["cells"]), 3),
        })
    compartments.sort(key=lambda item: item["grv_m3"], reverse=True)
    for index, item in enumerate(compartments):
        item["id"] = index + 1
    return {
        "cell_area_m2": round(cell_area, 3),
        "fault_count": len(faults),
        "compartments": compartments,
        "total_grv_m3": round(sum(item["grv_m3"] for item in compartments), 3),
    }
