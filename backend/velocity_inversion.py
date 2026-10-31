"""Interval-velocity inversion from checkshot time-depth pairs.

Piecewise-linear least squares: split the TWT axis into n_layers segments
at quantile boundaries, fit depth = a + b*t within each segment, velocity
is 2000*b (two-way). Validated by holdout RMSE when holdout points are
supplied.
"""

from __future__ import annotations

from typing import Any

import numpy as np


def _validate(points: list[dict[str, Any]]) -> tuple[np.ndarray, np.ndarray]:
    if len(points) < 3:
        raise ValueError("need at least 3 checkshot points")
    twt, depth = [], []
    for i, p in enumerate(points):
        try:
            t, d = float(p["twt_ms"]), float(p["depth"])
        except (KeyError, TypeError, ValueError):
            raise ValueError(f"checkshot[{i}] requires numeric twt_ms and depth")
        if not np.isfinite(t) or not np.isfinite(d):
            raise ValueError(f"checkshot[{i}] must be finite")
        if t < 0 or d < 0:
            raise ValueError(f"checkshot[{i}] must be non-negative")
        twt.append(t)
        depth.append(d)
    twt = np.asarray(twt)
    depth = np.asarray(depth)
    if np.any(np.diff(twt) <= 0) or np.any(np.diff(depth) <= 0):
        raise ValueError("checkshot twt_ms and depth must be strictly increasing (monotonic)")
    return twt, depth


def invert_checkshot(
    points: list[dict[str, Any]],
    n_layers: int = 2,
    holdout: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    if not isinstance(n_layers, int) or isinstance(n_layers, bool) or n_layers < 2:
        raise ValueError("n_layers must be an integer >= 2")
    twt, depth = _validate(points)
    if n_layers >= len(points):
        raise ValueError("n_layers must be fewer than checkshot points")
    bounds = np.quantile(twt, np.linspace(0, 1, n_layers + 1))
    layers = []
    pred = np.zeros_like(depth)
    for i in range(n_layers):
        lo, hi = bounds[i], bounds[i + 1]
        if i == n_layers - 1:
            mask = (twt >= lo) & (twt <= hi)
        else:
            mask = (twt >= lo) & (twt < hi)
        if int(mask.sum()) < 2:
            # Widen to neighbours so every layer has a slope.
            idx = np.argsort(np.abs(twt - (lo + hi) / 2.0))[:2]
            mask = np.zeros(len(twt), dtype=bool)
            mask[idx] = True
        x, y = twt[mask], depth[mask]
        slope, intercept = np.polyfit(x, y, 1)
        velocity = 2000.0 * float(slope)
        if not 200.0 <= velocity <= 12000.0:
            raise ValueError(f"layer {i}: inverted velocity {velocity:.0f} m/s outside physical range")
        layers.append({
            "top_ms": round(float(lo), 3),
            "velocity_m_s": round(velocity, 2),
        })
        pred[mask] = slope * x + intercept
    resid = depth - pred
    # Enforce strictly increasing tops for downstream normalize_model.
    tops = [l["top_ms"] for l in layers]
    for i in range(1, len(tops)):
        if tops[i] <= tops[i - 1]:
            tops[i] = round(tops[i - 1] + 1e-3, 3)
            layers[i]["top_ms"] = tops[i]
    out: dict[str, Any] = {
        "layers": layers,
        "n_layers": n_layers,
        "n_points": len(points),
        "max_residual_m": round(float(np.max(np.abs(resid))), 3),
        "rmse_m": round(float(np.sqrt(np.mean(resid ** 2))), 3),
        "holdout_rmse_m": None,
    }
    if holdout:
        ht, hd = [], []
        for i, p in enumerate(holdout):
            try:
                t, d = float(p["twt_ms"]), float(p["depth"])
            except (KeyError, TypeError, ValueError):
                raise ValueError(f"holdout[{i}] requires numeric twt_ms and depth")
            if not np.isfinite(t) or not np.isfinite(d) or t < 0 or d < 0:
                raise ValueError(f"holdout[{i}] must be finite non-negative")
            ht.append(t)
            hd.append(d)
        if not ht:
            raise ValueError("holdout must not be empty")
        errs = [float(d) - float(_depth_at(t, layers)) for t, d in zip(ht, hd)]
        out["holdout_rmse_m"] = round(float(np.sqrt(np.mean(np.square(errs)))), 3)
    return out


def _depth_at(t_ms: float, layers: list[dict[str, Any]]) -> float:
    depth = 0.0
    for i, layer in enumerate(layers):
        top = float(layer["top_ms"])
        nxt = float(layers[i + 1]["top_ms"]) if i + 1 < len(layers) else float("inf")
        interval = min(max(float(t_ms) - top, 0.0), nxt - top if nxt < float("inf") else max(float(t_ms) - top, 0.0))
        depth += float(layer["velocity_m_s"]) * interval / 2000.0
    return depth
