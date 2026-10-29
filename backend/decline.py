"""Decline-curve fitting shared by the API and economics workflows."""

from __future__ import annotations

import numpy as np

_trapezoid = getattr(np, "trapezoid", None) or getattr(np, "trapz")


def fit_exponential(t, q):
    """ln(q) = ln(qi) - d*t."""
    if len(t) < 2:
        return None
    y = np.log(np.clip(q, 1e-9, None))
    m, c = np.polyfit(t, y, 1)
    d = max(0.0, -float(m))
    qi = float(np.exp(c))
    qhat = qi * np.exp(-d * t)
    sse = float(np.sum((q - qhat) ** 2))
    return {"model": "exponential", "qi": qi, "d": d, "qhat": qhat, "sse": sse}


def fit_hyperbolic(t, q):
    """q = qi / (1 + b*di*t)^(1/b)."""
    if len(t) < 2:
        return None
    qi0 = float(np.max(q))
    best = None
    b_grid = np.linspace(0.1, 1.5, 57)
    di_grid = np.linspace(1e-4, 2.0, 200)
    for b in b_grid:
        denom = 1.0 + (b * di_grid[:, None] * t[None, :])
        model_unit = np.power(np.clip(denom, 1e-9, None), -1.0 / b)
        num = np.sum(model_unit * q[None, :], axis=1)
        den = np.sum(model_unit * model_unit, axis=1)
        qi_vals = np.where(den > 0, num / den, qi0)
        qhat_all = qi_vals[:, None] * model_unit
        sse_all = np.sum((qhat_all - q[None, :]) ** 2, axis=1)
        idx = int(np.argmin(sse_all))
        sse = float(sse_all[idx])
        qi = float(max(qi_vals[idx], 1e-9))
        di = float(di_grid[idx])
        qhat = qi * np.power(np.clip(1.0 + b * di * t, 1e-9, None), -1.0 / b)
        candidate = {"model": "hyperbolic", "qi": qi, "di": di, "b": float(b), "qhat": qhat, "sse": sse}
        if best is None or sse < best["sse"]:
            best = candidate
    return best


def compute_eur(best_fit, days_to_limit=3650.0, q_limit=1.0):
    if not best_fit:
        return None
    t = np.linspace(0, days_to_limit, 2500)
    if best_fit["model"] == "exponential":
        q = best_fit["qi"] * np.exp(-best_fit["d"] * t)
    else:
        q = best_fit["qi"] * np.power(
            np.clip(1.0 + best_fit["b"] * best_fit["di"] * t, 1e-9, None),
            -1.0 / max(best_fit["b"], 1e-6),
        )
    q = np.clip(q, 0.0, None)
    mask = q >= q_limit
    if np.any(mask):
        t = t[mask]
        q = q[mask]
    return float(_trapezoid(q, t))


def fit_best(dates, rates, model: str = "auto"):
    """Fit both models and return the lowest-SSE candidate (or the requested one)."""
    t0 = dates[0]
    t = np.array([(d - t0).days for d in dates], dtype=float)
    q = np.array(rates, dtype=float)
    fits = []
    if model in {"auto", "exponential"}:
        exp_fit = fit_exponential(t, q)
        if exp_fit:
            fits.append(exp_fit)
    if model in {"auto", "hyperbolic"}:
        hyp_fit = fit_hyperbolic(t, q)
        if hyp_fit:
            fits.append(hyp_fit)
    if not fits:
        return None
    return min(fits, key=lambda f: f["sse"])
