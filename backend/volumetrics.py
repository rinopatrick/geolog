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


def _cell_area_m2(
    inline_spacing_m: float,
    crossline_spacing_m: float,
) -> float:
    """Cell area from survey bin spacing only.

    ``inlines``/``crosslines`` carry trace labels (numbers that may start at an
    arbitrary offset such as 100 or be real coordinates in metres); they must
    never scale the area. Grid nodes are adjacent cells, so one node covers
    exactly ``inline_spacing_m * crossline_spacing_m``.
    """
    if not inline_spacing_m or not crossline_spacing_m:
        raise ValueError("surface needs inline_spacing_m and crossline_spacing_m")
    return float(inline_spacing_m) * float(crossline_spacing_m)

def grv_from_depth_grid(
    depth_grid: list[list[float]],
    contact_depth_m: float,
    inline_spacing_m: float,
    crossline_spacing_m: float,
    inlines: list[float],
    crosslines: list[float],
    base_depth_grid: list[list[float]] | None = None,
) -> dict[str, float]:
    grid = np.asarray(depth_grid, dtype=float)
    if grid.ndim != 2 or grid.size == 0 or not np.any(np.isfinite(grid)):
        raise ValueError("surface has no depth grid")
    cell_area = _cell_area_m2(inline_spacing_m, crossline_spacing_m)
    base = None
    if base_depth_grid is not None:
        base = np.asarray(base_depth_grid, dtype=float)
        if base.shape != grid.shape:
            raise ValueError("base surface grid must match the top surface grid")
    bottom = np.minimum(base, float(contact_depth_m)) if base is not None else np.full_like(grid, float(contact_depth_m))
    columns = np.clip(bottom - grid, 0.0, None)
    columns = np.nan_to_num(columns, nan=0.0)
    grv = float(np.sum(columns) * cell_area)
    area = float(np.count_nonzero(columns > 0) * cell_area)
    if grv <= 0:
        raise ValueError("contact is above the entire surface; no hydrocarbon column")
    thickness = np.nan_to_num(np.clip(base - grid, 0.0, None), nan=0.0) if base is not None else None
    return {
        "grv_m3": round(grv, 3),
        "area_m2": round(area, 3),
        "cell_area_m2": round(cell_area, 3),
        "mean_column_m": round(float(np.mean(columns[columns > 0])), 3),
        "max_column_m": round(float(np.max(columns)), 3),
        "base_used": base is not None,
        "mean_reservoir_thickness_m": round(float(np.mean(thickness[thickness > 0])), 3) if thickness is not None and np.any(thickness > 0) else None,
    }


def barrel_percentiles(values: np.ndarray) -> dict[str, float]:
    p90, p50, p10 = np.percentile(values, [10, 50, 90])
    return {
        "p90_bbl": round(float(p90), 3),
        "p50_bbl": round(float(p50), 3),
        "p10_bbl": round(float(p10), 3),
        "mean_bbl": round(float(np.mean(values)), 3),
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
    base_depth_grid: list[list[float]] | None = None,
    iterations: int = 1000,
    seed: int | None = None,
    fluid_type: str = "oil",
    bg: float = 0.005,
    condensate_yield: float = 30.0,
) -> dict[str, Any]:
    grv = grv_from_depth_grid(
        depth_grid,
        contact_depth_m,
        inline_spacing_m,
        crossline_spacing_m,
        inlines,
        crosslines,
        base_depth_grid=base_depth_grid,
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

    fluid = str(fluid_type or "oil").lower()
    if fluid not in {"oil", "gas", "condensate"}:
        raise ValueError("fluid_type must be oil, gas or condensate")
    bg_value = min(0.1, max(0.0001, _number(bg, 0.005)))
    yield_value = min(500.0, max(0.0, _number(condensate_yield, 30.0)))

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
    pore_volume = grv["grv_m3"] * ntg_samples * porosity_samples * (1.0 - sw_samples)
    risk_summary = {
        "probability": round(risk_probability, 4),
        "components": components,
    }
    ranges = {
        "porosity": list(porosity_range),
        "water_saturation": list(sw_range),
        "recovery_factor": list(rf_range),
        "net_to_gross": list(ntg_range),
    }
    if fluid == "oil":
        stoiip = pore_volume / bo_value
        recoverable = stoiip * rf_samples
        stoiip_stats = percentiles(stoiip)
        recovery_stats = percentiles(recoverable)
        risked = {key: round(value * risk_probability, 3) for key, value in stoiip_stats.items()}
        return {
            "fluid_type": "oil",
            "grv": grv,
            "ranges": ranges,
            "bo": bo_value,
            "risk": risk_summary,
            "iterations": iterations,
            "seed": seed,
            "stoiip": stoiip_stats,
            "recoverable": recovery_stats,
            "recoverable_boe": barrel_percentiles(recoverable),
            "risked_stoiip": risked,
        }

    giip = pore_volume / bg_value
    recoverable_gas = giip * rf_samples
    condensate = giip * 35.3147 / 1e6 * yield_value
    gas_boe = giip * 35.3147 / 5800.0
    boe = gas_boe + condensate
    giip_stats = percentiles(giip)
    gas_recovery_stats = percentiles(recoverable_gas)
    condensate_stats = percentiles(condensate)
    boe_stats = barrel_percentiles(boe)
    recoverable_boe = barrel_percentiles(
        recoverable_gas * 35.3147 / 5800.0 + recoverable_gas * 35.3147 / 1e6 * yield_value
    )
    return {
        "fluid_type": "condensate" if fluid == "condensate" or yield_value > 0 else "gas",
        "grv": grv,
        "ranges": ranges,
        "bg": bg_value,
        "condensate_yield_bbl_per_mmscf": yield_value,
        "risk": risk_summary,
        "iterations": iterations,
        "seed": seed,
        "giip": giip_stats,
        "recoverable_gas": gas_recovery_stats,
        "condensate": condensate_stats,
        "boe": boe_stats,
        "recoverable_boe": recoverable_boe,
        "risked_giip": {key: round(value * risk_probability, 3) for key, value in giip_stats.items()},
        "risked_boe": {
            key: round(value * risk_probability, 3)
            for key, value in boe_stats.items()
        },
    }
