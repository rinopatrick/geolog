"""Forecast-vs-actual anomaly detection with CUSUM trend.

Fit the first half of the series with the decline fitter, forecast the
second half, flag points deviating beyond threshold_pct. CUSUM on residuals
determines trend: persistent negative drift = declining faster than model,
persistent positive = growing. Clean exponential decline produces no flags.
"""

from __future__ import annotations

from datetime import date
from typing import Any

import numpy as np

try:
    from decline import fit_best
except ImportError:
    from backend.decline import fit_best


def _rate_at(fit: dict[str, Any], day: float) -> float:
    if fit["model"] == "exponential":
        return float(fit["qi"] * np.exp(-fit["d"] * day))
    b = max(float(fit["b"]), 1e-6)
    return float(fit["qi"] * np.power(1.0 + b * fit["di"] * day, -1.0 / b))


def detect_anomalies(
    dates: list[date],
    rates: list[float],
    threshold_pct: float = 20.0,
    seed: int | None = None,
    train_fraction: float = 0.5,
) -> dict[str, Any]:
    if len(dates) != len(rates):
        raise ValueError("dates and rates length mismatch")
    if len(dates) < 12 or len(rates) < 12:
        raise ValueError("need at least 12 samples")
    threshold = float(threshold_pct)
    if not np.isfinite(threshold) or not 1.0 <= threshold <= 200.0:
        raise ValueError("threshold_pct must be between 1 and 200")
    frac = float(train_fraction)
    if not 0.25 <= frac <= 0.75:
        raise ValueError("train_fraction must be between 0.25 and 0.75")

    n = len(dates)
    rates_arr = np.asarray(rates, dtype=float)
    if np.any(~np.isfinite(rates_arr)) or np.any(rates_arr < 0):
        raise ValueError("rates must be finite non-negative")
    split = max(6, int(n * frac))
    fit = fit_best(list(dates[:split]), list(rates_arr[:split]))
    if fit is None:
        raise ValueError("could not fit decline to training window")

    t0 = dates[0]
    days = np.array([(d - t0).days for d in dates], dtype=float)
    forecast = np.array([_rate_at(fit, t) for t in days])
    denom = np.maximum(np.abs(forecast), 1e-9)
    resid_pct = 100.0 * (rates_arr - forecast) / denom

    anomalies = []
    for i in range(split, n):
        if abs(float(resid_pct[i])) >= threshold:
            kind = "drop" if resid_pct[i] < 0 else "jump"
            anomalies.append({
                "index": int(i),
                "date": dates[i].isoformat(),
                "actual": round(float(rates_arr[i]), 3),
                "forecast": round(float(forecast[i]), 3),
                "residual_pct": round(float(resid_pct[i]), 2),
                "kind": kind,
            })

    # CUSUM on test-window residuals (normalized): drift direction = trend.
    test_resid = resid_pct[split:]
    scale = max(float(np.std(test_resid)), 1e-9)
    cusum_pos = float(np.sum(np.clip(test_resid / scale - 0.5, 0.0, None)))
    cusum_neg = float(np.sum(np.clip(-test_resid / scale - 0.5, 0.0, None)))
    if cusum_neg > cusum_pos + 1.0:
        trend = "declining"
    elif cusum_pos > cusum_neg + 1.0:
        trend = "growing"
    else:
        # No drift: fall back to fitted decline direction.
        d = fit.get("d", fit.get("di", 0.0))
        trend = "declining" if d > 1e-6 else "stable"

    return {
        "anomaly_count": len(anomalies),
        "anomalies": anomalies,
        "trend": trend,
        "cusum_pos": round(cusum_pos, 3),
        "cusum_neg": round(cusum_neg, 3),
        "train_points": split,
        "fit_model": fit["model"],
        "threshold_pct": threshold,
        "seed": seed,
    }
