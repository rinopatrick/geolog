"""Prospect GRV and Monte Carlo STOIIP calculations."""

from __future__ import annotations

from typing import Any

import numpy as np

BBL_PER_M3 = 6.2898


def _number(value: Any, fallback: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return float(fallback)


def normalize_range(
    data: Any,
    label: str,
    default: float,
    minimum: float = 0.0,
    maximum: float = 1.0,
) -> tuple[float, float, float]:
    if isinstance(data, dict):
        low = _number(data.get("low", data.get("p10")), default)
        mode = _number(data.get("mode", data.get("p50")), default)
        high = _number(data.get("high", data.get("p90")), default)
    else:
        low = mode = high = _number(data, default)
    values = sorted([low, mode, high])
    low, mode, high = values
    if not minimum <= low <= maximum or not minimum <= high <= maximum:
        raise ValueError(f"{label} must be between {minimum} and {maximum}")
    return low, mode, high


def grv_from_depth_grid(
    depth_grid: list[list[float]],
    contact_depth_m: float,
    inline_spacing_m: float,
    crossline_spacing_m: float,
    inlines: list[float],
    crosslines: list[float],
) -> dict[str, float]:
    grid = np.asarray(depth_grid, dtype=float)
    if grid.ndim != 2 or grid.size == 0 or not np.any(np.isfinite(grid)):
        raise ValueError("surface has no depth grid")
    if not inline_spacing_m or not crossline_spacing_m:
        raise ValueError("surface needs inline_spacing_m and crossline_spacing_m")
    inline_step = float(np.median(np.diff(np.asarray(inlines, dtype=float)))) if len(inlines) > 1 else 1.0
    crossline_step = float(np.median(np.diff(np.asarray(crosslines, dtype=float)))) if len(crosslines) > 1 else 1.0
    cell_area = float(inline_spacing_m) * float(crossline_spacing_m) * max(1.0, inline_step) * max(1.0, crossline_step)
    columns = np.clip(float(contact_depth_m) - grid, 0.0, None)
    columns = np.nan_to_num(columns, nan=0.0)
    grv = float(np.sum(columns) * cell_area)
    area = float(np.count_nonzero(columns > 0) * cell_area)
    if grv <= 0:
        raise ValueError("contact is above the entire surface; no hydrocarbon column")
    return {
        "grv_m3": round(grv, 3),
        "area_m2": round(area, 3),
        "cell_area_m2": round(cell_area, 3),
        "mean_column_m": round(float(np.mean(columns[columns > 0])), 3),
        "max_column_m": round(float(np.max(columns)), 3),
    }


def percentiles(values: np.ndarray) -> dict[str, float]:
    p90, p50, p10 = np.percentile(values, [10, 50, 90])
    return {
        "p90_m3": round(float(p90), 3),
        "p50_m3": round(float(p50), 3),
        "p10_m3": round(float(p10), 3),
        "mean_m3": round(float(np.mean(values)), 3),
        "p90_bbl": round(float(p90) * BBL_PER_M3, 3),
        "p50_bbl": round(float(p50) * BBL_PER_M3, 3),
        "p10_bbl": round(float(p10) * BBL_PER_M3, 3),
        "mean_bbl": round(float(np.mean(values)) * BBL_PER_M3, 3),
    }


def calculate_prospect(
    depth_grid: list[list[float]],
    contact_depth_m: float,
    inline_spacing_m: float,
    crossline_spacing_m: float,
    inlines: list[float],
    crosslines: list[float],
    porosity: Any,
    water_saturation: Any,
    recovery_factor: Any,
    net_to_gross: Any = 1.0,
    bo: float = 1.2,
    risk: float = 1.0,
    risks: dict[str, float] | None = None,
    iterations: int = 1000,
    seed: int | None = None,
) -> dict[str, Any]:
    grv = grv_from_depth_grid(
        depth_grid,
        contact_depth_m,
        inline_spacing_m,
        crossline_spacing_m,
        inlines,
        crosslines,
    )
    porosity_range = normalize_range(porosity, "porosity", 0.2, 0.001, 0.6)
    sw_range = normalize_range(water_saturation, "water_saturation", 0.3)
    rf_range = normalize_range(recovery_factor, "recovery_factor", 0.35)
    ntg_range = normalize_range(net_to_gross, "net_to_gross", 1.0)
    bo_value = min(3.0, max(0.8, _number(bo, 1.2)))
    iterations = max(100, min(int(iterations), 20000))
    if risks:
        components = {key: min(1.0, max(0.0, _number(value, 1.0))) for key, value in risks.items()}
        risk_probability = float(np.prod(list(components.values()))) if components else 1.0
    else:
        components = {}
        risk_probability = min(1.0, max(0.0, _number(risk, 1.0)))

    rng = np.random.default_rng(seed)

    def sample(values: tuple[float, float, float]) -> np.ndarray:
        low, mode, high = values
        if high - low <= 1e-12:
            return np.full(iterations, low, dtype=float)
        return rng.triangular(low, mode, high, size=iterations)

    porosity_samples = sample(porosity_range)
    sw_samples = sample(sw_range)
    rf_samples = sample(rf_range)
    ntg_samples = sample(ntg_range)
    stoiip = grv["grv_m3"] * ntg_samples * porosity_samples * (1.0 - sw_samples) / bo_value
    recoverable = stoiip * rf_samples
    stoiip_stats = percentiles(stoiip)
    recovery_stats = percentiles(recoverable)
    risked = {key: round(value * risk_probability, 3) for key, value in stoiip_stats.items()}
    return {
        "grv": grv,
        "ranges": {
            "porosity": list(porosity_range),
            "water_saturation": list(sw_range),
            "recovery_factor": list(rf_range),
            "net_to_gross": list(ntg_range),
        },
        "bo": bo_value,
        "risk": {
            "probability": round(risk_probability, 4),
            "components": components,
        },
        "iterations": iterations,
        "seed": seed,
        "stoiip": stoiip_stats,
        "recoverable": recovery_stats,
        "risked_stoiip": risked,
    }
