"""Per-cell posterior maps: P10/P50/P90 hydrocarbon column + probability.

Each grid cell gets an independent Monte Carlo over the same triangular
inputs as `calculate_prospect` (porosity, Sw, NTG), applied to that cell's
deterministic gross column `max(0, min(base, contact) - top)`. Output maps
quantify sub-prospect spatial uncertainty; prospect totals stay in
`calculate_prospect`.
"""

from __future__ import annotations

from typing import Any

import numpy as np

try:
    from volumetrics import _cell_area_m2, normalize_range
    from spatial import simulate_gaussian_field
except ImportError:
    from backend.volumetrics import _cell_area_m2, normalize_range
    from backend.spatial import simulate_gaussian_field


def cell_posterior_maps(
    depth_grid: list[list[float]],
    contact_depth_m: float,
    inline_spacing_m: float,
    crossline_spacing_m: float,
    porosity: Any,
    water_saturation: Any,
    net_to_gross: Any = 1.0,
    base_depth_grid: list[list[float]] | None = None,
    iterations: int = 1000,
    seed: int | None = None,
    correlation: str = "none",
    correlation_range_cells: float = 8.0,
) -> dict[str, Any]:
    grid = np.asarray(depth_grid, dtype=float)
    if grid.ndim != 2 or grid.size == 0 or not np.any(np.isfinite(grid)):
        raise ValueError("surface has no depth grid")
    contact = float(contact_depth_m)
    if not np.isfinite(contact):
        raise ValueError("contact_depth_m must be finite")
    cell_area = _cell_area_m2(inline_spacing_m, crossline_spacing_m)
    iterations = int(iterations)
    if not 100 <= iterations <= 20000:
        raise ValueError("iterations must be between 100 and 20000")

    mode = str(correlation or "none").lower()
    if mode not in ("none", "lateral"):
        raise ValueError("correlation must be 'none' or 'lateral'")
    corr_range = float(correlation_range_cells)
    if mode == "lateral" and (not np.isfinite(corr_range) or corr_range <= 0):
        raise ValueError("correlation_range_cells must be positive for lateral mode")

    porosity_range = normalize_range(porosity, "porosity", 0.2, 0.001, 0.6)
    sw_range = normalize_range(water_saturation, "water_saturation", 0.3)
    ntg_range = normalize_range(net_to_gross, "net_to_gross", 1.0)

    # SLO guard: cells x iterations bounded so the endpoint answers in
    # seconds, not minutes. Measured: 50x50x5000 ~0.5s; 200x200x20000 ~60s.
    # Cap at 2M draws (~1-2s worst case); larger jobs must downsample first.
    workload = int(grid.shape[0]) * int(grid.shape[1]) * iterations
    if workload > 2_000_000:
        raise ValueError(
            f"workload too large: {workload:,} cell-draws exceeds 2,000,000; "
            "reduce grid resolution or iterations"
        )

    base = None
    if base_depth_grid is not None:
        base = np.asarray(base_depth_grid, dtype=float)
        if base.shape != grid.shape:
            raise ValueError("base surface grid must match the top surface grid")
    bottom = np.minimum(base, contact) if base is not None else contact
    gross = np.clip(np.nan_to_num(bottom - grid, nan=0.0), 0.0, None)

    rng = np.random.default_rng(seed)

    def sample(values: tuple[float, float, float]) -> np.ndarray:
        low, mode, high = values
        if high - low <= 1e-12:
            return np.full(iterations, low, dtype=float)
        return rng.triangular(low, mode, high, size=iterations)

    # Broadcasting: (iterations, 1, 1) x (rows, cols) -> (iterations, rows, cols)
    poro = sample(porosity_range)[:, None, None]
    sw = sample(sw_range)[:, None, None]
    ntg = sample(ntg_range)[:, None, None]
    if mode == "lateral":
        # One correlated NTG multiplier field per iteration: neighbouring
        # cells move together (shared geology), mean-preserving (mean 1).
        rows, cols = int(grid.shape[0]), int(grid.shape[1])
        fields = np.stack([
            simulate_gaussian_field(rows, cols, mean=0.0, std=0.25,
                                    range_cells=corr_range, seed=None if seed is None else seed + k)
            for k in range(iterations)
        ])
        ntg = np.clip(ntg * (1.0 + fields), 0.0, 1.0)
    pay = gross[None, :, :] * ntg * poro * (1.0 - sw)

    p10 = np.percentile(pay, 10, axis=0)
    p50 = np.percentile(pay, 50, axis=0)
    p90 = np.percentile(pay, 90, axis=0)
    prob = np.mean(pay > 0, axis=0)
    mean = np.mean(pay, axis=0)
    return {
        "p10_column_m": np.round(p10, 4).tolist(),
        "p50_column_m": np.round(p50, 4).tolist(),
        "p90_column_m": np.round(p90, 4).tolist(),
        "mean_column_m": np.round(mean, 4).tolist(),
        "hydrocarbon_probability": np.round(prob, 4).tolist(),
        "cell_area_m2": round(cell_area, 3),
        "rows": int(grid.shape[0]),
        "cols": int(grid.shape[1]),
        "iterations": iterations,
        "seed": seed,
        "inputs": {
            "contact_depth_m": contact,
            "porosity": list(porosity_range),
            "water_saturation": list(sw_range),
            "net_to_gross": list(ntg_range),
            "base_used": base is not None,
            "correlation": mode,
            "correlation_range_cells": corr_range if mode == "lateral" else None,
        },
    }
