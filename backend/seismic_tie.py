"""Well-to-seismic tie calculations."""

from __future__ import annotations

from typing import Any

import numpy as np


def validate_checkshot(raw: Any) -> list[dict[str, float]]:
    if raw in (None, []):
        return []
    if not isinstance(raw, list):
        raise ValueError("checkshot must be a list")
    points = []
    for index, point in enumerate(raw):
        if not isinstance(point, dict):
            raise ValueError(f"checkshot[{index}] must be an object")
        try:
            depth = float(point["depth"])
            twt_ms = float(point["twt_ms"])
        except (KeyError, TypeError, ValueError):
            raise ValueError(f"checkshot[{index}] requires depth and twt_ms")
        if not np.isfinite(depth) or not np.isfinite(twt_ms):
            raise ValueError(f"checkshot[{index}] must be finite")
        points.append({"depth": depth, "twt_ms": twt_ms})
    points.sort(key=lambda item: (item["depth"], item["twt_ms"]))
    for previous, current in zip(points, points[1:]):
        if current["depth"] <= previous["depth"]:
            raise ValueError("checkshot depths must be strictly increasing")
        if current["twt_ms"] <= previous["twt_ms"]:
            raise ValueError("checkshot TWT must be strictly increasing")
    return points


def _correlation(a: np.ndarray, b: np.ndarray) -> float:
    a = np.nan_to_num(a, nan=0.0)
    b = np.nan_to_num(b, nan=0.0)
    denominator = float(np.linalg.norm(a) * np.linalg.norm(b))
    if denominator <= 1e-12:
        return 0.0
    return float(np.dot(a, b) / denominator)


def build_tie(
    synthetic: dict[str, Any],
    seismic: np.ndarray,
    sample_interval_ms: float,
    checkshot: list[dict[str, float]],
    max_shift_ms: float = 40.0,
    max_points: int = 2000,
) -> dict[str, Any]:
    checkshot = validate_checkshot(checkshot)
    depths = np.asarray(synthetic.get("depth") or [], dtype=float)
    times = np.asarray(synthetic.get("twt") or [], dtype=float) * 1000.0
    amplitudes = np.asarray(synthetic.get("synthetic") or [], dtype=float)
    if len(depths) < 3 or len(times) != len(amplitudes):
        raise ValueError("synthetic trace has no usable samples")
    if checkshot:
        check_depth = np.asarray([point["depth"] for point in checkshot], dtype=float)
        check_time = np.asarray([point["twt_ms"] for point in checkshot], dtype=float)
        if depths.min() < check_depth.min() - 1e-6 or depths.max() > check_depth.max() + 1e-6:
            raise ValueError("checkshot does not cover the log depth range")
        times = np.interp(depths, check_depth, check_time)
    order = np.argsort(times)
    times = times[order]
    amplitudes = amplitudes[order]
    unique_time, unique_indices = np.unique(times, return_index=True)
    times = unique_time
    amplitudes = amplitudes[unique_indices]
    ns = len(seismic)
    if ns < 3:
        raise ValueError("seismic trace has too few samples")
    seismic_times = np.arange(ns, dtype=float) * float(sample_interval_ms)
    max_lag = int(round(float(max_shift_ms) / max(1e-9, float(sample_interval_ms))))
    best_score = -2.0
    best_lag = 0
    for lag in range(-max_lag, max_lag + 1):
        shifted_times = seismic_times - lag * sample_interval_ms
        overlap = (shifted_times >= times[0]) & (shifted_times <= times[-1])
        if int(overlap.sum()) < max(10, ns // 10):
            continue
        shifted = np.interp(shifted_times, times, amplitudes, left=0.0, right=0.0)
        score = _correlation(seismic[overlap], shifted[overlap])
        if score > best_score:
            best_score = score
            best_lag = lag
    if best_score <= -1.5:
        raise ValueError("synthetic and seismic traces do not overlap")
    shift_ms = best_lag * float(sample_interval_ms)
    shifted = np.interp(seismic_times - shift_ms, times, amplitudes, left=0.0, right=0.0)
    step = max(1, ns // max(1, int(max_points)))
    return {
        "twt_ms": [round(float(value), 4) for value in seismic_times[::step]],
        "seismic": [round(float(value), 6) for value in seismic[::step]],
        "synthetic": [round(float(value), 6) for value in np.interp(seismic_times, times, amplitudes, left=0.0, right=0.0)[::step]],
        "synthetic_shifted": [round(float(value), 6) for value in shifted[::step]],
        "shift_ms": round(float(shift_ms), 4),
        "correlation": round(float(best_score), 4),
        "sample_interval_ms": float(sample_interval_ms),
        "checkshot_used": bool(checkshot),
        "check_samples": len(checkshot),
        "samples": int(ns),
        "search_ms": float(max_shift_ms),
    }
