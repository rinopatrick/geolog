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
    from volumetrics import _cell_area_m2
except ImportError:
    from backend.geostat import krige_grid
    from backend.volumetrics import _cell_area_m2


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
    base_depth_grid: list[list[float]] | None = None,
) -> dict[str, Any]:
    grid = np.asarray(depth_grid, dtype=float)
    if grid.ndim != 2 or grid.size == 0:
        raise ValueError("surface has no depth grid")
    cell_area = _cell_area_m2(inline_spacing_m, crossline_spacing_m)
    base = None
    if base_depth_grid is not None:
        base = np.asarray(base_depth_grid, dtype=float)
        if base.shape != grid.shape:
            raise ValueError("base surface grid must match the top surface grid")
    bottom = np.minimum(base, float(contact_depth_m)) if base is not None else np.full_like(grid, float(contact_depth_m))
    columns = np.nan_to_num(np.clip(bottom - grid, 0.0, None), nan=0.0)
    thickness = np.nan_to_num(np.clip(base - grid, 0.0, None), nan=0.0) if base is not None else None
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
        "base_used": base is not None,
        "mean_reservoir_thickness_m": round(float(np.mean(thickness[thickness > 0])), 3)
        if thickness is not None and np.any(thickness > 0)
        else None,
    }


def juxtaposition(
    top_grid: list[list[float]],
    base_grid: list[list[float]],
    inlines: list[float],
    crosslines: list[float],
    faults: list[dict[str, Any]],
) -> dict[str, Any]:
    """Sample top/base intervals on opposite sides of each fault trace."""
    top = np.asarray(top_grid, dtype=float)
    base = np.asarray(base_grid, dtype=float)
    if top.shape != base.shape:
        raise ValueError("top and base grids must match")
    inline_values = np.asarray(inlines, dtype=float)
    crossline_values = np.asarray(crosslines, dtype=float)
    results = []
    for fault in faults:
        points = fault.get("points") or []
        if len(points) < 2:
            continue
        inline_span = max(float(point["inline"]) for point in points) - min(float(point["inline"]) for point in points)
        crossline_span = max(float(point["crossline"]) for point in points) - min(float(point["crossline"]) for point in points)
        along_crossline = crossline_span >= inline_span
        overlaps = []
        reservoir_reservoir = 0
        seal = 0
        for point in points:
            row = int(np.argmin(np.abs(inline_values - float(point["inline"]))))
            column = int(np.argmin(np.abs(crossline_values - float(point["crossline"]))))
            if along_crossline:
                first, second = (row - 1, column), (row + 1, column)
            else:
                first, second = (row, column - 1), (row, column + 1)
            if not ((0 <= first[0] < top.shape[0]) and (0 <= first[1] < top.shape[1])):
                continue
            if not ((0 <= second[0] < top.shape[0]) and (0 <= second[1] < top.shape[1])):
                continue
            top_a, base_a = top[first], base[first]
            top_b, base_b = top[second], base[second]
            if not np.all(np.isfinite([top_a, base_a, top_b, base_b])):
                continue
            overlap = max(0.0, min(base_a, base_b) - max(top_a, top_b))
            overlaps.append(float(overlap))
            if overlap > 0:
                reservoir_reservoir += 1
            else:
                seal += 1
        results.append({
            "id": fault.get("id"),
            "samples": len(overlaps),
            "reservoir_reservoir": reservoir_reservoir,
            "seal": seal,
            "mean_overlap_m": round(float(np.mean(overlaps)), 3) if overlaps else 0.0,
            "max_overlap_m": round(float(np.max(overlaps)), 3) if overlaps else 0.0,
        })
    return {
        "faults": results,
        "reservoir_reservoir_samples": sum(item["reservoir_reservoir"] for item in results),
        "seal_samples": sum(item["seal"] for item in results),
    }


def fault_throw_from_surface(
    top_grid: list[list[float]],
    inlines: list[float],
    crosslines: list[float],
    fault_points: list[dict[str, float]],
) -> dict[str, Any]:
    """Estimate throw from horizon depth offset across a fault trace."""
    top = np.asarray(top_grid, dtype=float)
    inline_values = np.asarray(inlines, dtype=float)
    crossline_values = np.asarray(crosslines, dtype=float)
    if len(fault_points) < 2:
        raise ValueError("fault needs at least two points")
    inline_span = max(float(point["inline"]) for point in fault_points) - min(float(point["inline"]) for point in fault_points)
    crossline_span = max(float(point["crossline"]) for point in fault_points) - min(float(point["crossline"]) for point in fault_points)
    along_crossline = crossline_span >= inline_span
    throws = []
    for point in fault_points:
        row = int(np.argmin(np.abs(inline_values - float(point["inline"]))))
        column = int(np.argmin(np.abs(crossline_values - float(point["crossline"]))))
        if along_crossline:
            first, second = (row - 1, column), (row + 1, column)
        else:
            first, second = (row, column - 1), (row, column + 1)
        if not ((0 <= first[0] < top.shape[0]) and (0 <= first[1] < top.shape[1])):
            continue
        if not ((0 <= second[0] < top.shape[0]) and (0 <= second[1] < top.shape[1])):
            continue
        a, b = top[first], top[second]
        if np.isfinite(a) and np.isfinite(b):
            throws.append(abs(float(a) - float(b)))
    if not throws:
        raise ValueError("no valid horizon cells across the fault")
    return {
        "samples": len(throws),
        "throw_median_m": round(float(np.median(throws)), 3),
        "throw_mean_m": round(float(np.mean(throws)), 3),
        "throw_max_m": round(float(np.max(throws)), 3),
    }
