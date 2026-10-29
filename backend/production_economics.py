"""Probabilistic decline-curve economics.

The deterministic decline fit lives in `decline.py`. This module forecasts
monthly oil, applies a simple net-cash-flow model and runs a Monte Carlo around
the fitted decline parameters. It is deliberately dependency-free apart from
NumPy so the API can run it synchronously for a single well.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np

try:
    from decline import fit_best
except ImportError:
    from backend.decline import fit_best


DAYS_PER_MONTH = 30.4375


@dataclass
class EconomicAssumptions:
    oil_price: float = 70.0
    opex_per_bbl: float = 12.0
    capex: float = 0.0
    discount_rate: float = 0.10
    royalty_rate: float = 0.125
    working_interest: float = 1.0
    tax_rate: float = 0.25
    economic_limit: float = 10.0
    years: int = 20

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "EconomicAssumptions":
        def _num(key: str, default: float, low: float, high: float) -> float:
            try:
                value = float(data.get(key, default))
            except (TypeError, ValueError):
                value = default
            return float(min(high, max(low, value)))

        return cls(
            oil_price=_num("oil_price", 70.0, 0.01, 1000.0),
            opex_per_bbl=_num("opex_per_bbl", 12.0, 0.0, 1000.0),
            capex=_num("capex", 0.0, 0.0, 1e12),
            discount_rate=_num("discount_rate", 0.10, 0.0, 1.0),
            royalty_rate=_num("royalty_rate", 0.125, 0.0, 1.0),
            working_interest=_num("working_interest", 1.0, 0.0, 1.0),
            tax_rate=_num("tax_rate", 0.25, 0.0, 1.0),
            economic_limit=_num("economic_limit", 10.0, 0.01, 1e6),
            years=int(_num("years", 20, 1, 50)),
        )


def _rate_at(fit: dict[str, Any], day: float) -> float:
    if fit["model"] == "exponential":
        return float(fit["qi"] * np.exp(-fit["d"] * day))
    b = max(float(fit["b"]), 1e-6)
    return float(fit["qi"] * np.power(1.0 + b * fit["di"] * day, -1.0 / b))


def monthly_forecast(fit: dict[str, Any], assumptions: EconomicAssumptions) -> list[dict[str, float]]:
    months = assumptions.years * 12
    rows: list[dict[str, float]] = []
    cumulative = 0.0
    for month in range(1, months + 1):
        day = (month - 0.5) * DAYS_PER_MONTH
        rate = _rate_at(fit, day)
        if rate < assumptions.economic_limit:
            break
        oil = rate * DAYS_PER_MONTH
        revenue = oil * assumptions.oil_price * (1.0 - assumptions.royalty_rate) * assumptions.working_interest
        opex = oil * assumptions.opex_per_bbl * assumptions.working_interest
        net = revenue - opex
        if net > 0:
            net *= 1.0 - assumptions.tax_rate
        cumulative += net
        rows.append({"month": month, "oil_bbl": oil, "net_cash": net, "cumulative_cash": cumulative})
    return rows


def npv(rows: list[dict[str, float]], assumptions: EconomicAssumptions) -> float:
    monthly_rate = (1.0 + assumptions.discount_rate) ** (1.0 / 12.0) - 1.0
    value = -assumptions.capex * assumptions.working_interest
    for row in rows:
        value += row["net_cash"] / ((1.0 + monthly_rate) ** row["month"])
    return float(value)


def payback_month(rows: list[dict[str, float]], assumptions: EconomicAssumptions) -> int | None:
    target = assumptions.capex * assumptions.working_interest
    if target <= 0:
        return 1 if rows else None
    for row in rows:
        if row["cumulative_cash"] >= target:
            return int(row["month"])
    return None


def _sample_fit(fit: dict[str, Any], rng: np.random.Generator, data: dict[str, Any]) -> dict[str, Any]:
    qi_pct = min(0.9, max(0.0, float(data.get("qi_uncertainty_pct", 20.0) or 20.0) / 100.0))
    di_pct = min(0.9, max(0.0, float(data.get("di_uncertainty_pct", 20.0) or 20.0) / 100.0))
    b_sigma = min(0.9, max(0.0, float(data.get("b_uncertainty", 0.1) or 0.1)))
    sampled = dict(fit)
    sampled["qi"] = max(1e-6, float(fit["qi"] * max(0.05, 1.0 + rng.normal(0.0, qi_pct))))
    if fit["model"] == "exponential":
        sampled["d"] = max(1e-8, float(fit["d"] * max(0.05, 1.0 + rng.normal(0.0, di_pct))))
    else:
        sampled["di"] = max(1e-8, float(fit["di"] * max(0.05, 1.0 + rng.normal(0.0, di_pct))))
        sampled["b"] = float(min(1.5, max(0.05, fit["b"] + rng.normal(0.0, b_sigma))))
    return sampled


def evaluate(
    dates: list,
    rates: list[float],
    data: dict[str, Any],
) -> dict[str, Any]:
    model = str(data.get("model", "auto") or "auto").lower()
    if model not in {"auto", "exponential", "hyperbolic"}:
        model = "auto"
    fit = fit_best(dates, rates, model)
    if fit is None:
        raise ValueError("could not fit a decline curve")

    assumptions = EconomicAssumptions.from_dict(data)
    base_rows = monthly_forecast(fit, assumptions)
    base_eur = float(sum(row["oil_bbl"] for row in base_rows))
    base_npv = npv(base_rows, assumptions)

    iterations = int(min(5000, max(50, int(data.get("iterations", 500) or 500))))
    seed = int(data.get("seed", 42) or 42)
    rng = np.random.default_rng(seed)
    eur_samples = []
    npv_samples = []
    for _ in range(iterations):
        sample = _sample_fit(fit, rng, data)
        rows = monthly_forecast(sample, assumptions)
        eur_samples.append(sum(row["oil_bbl"] for row in rows))
        npv_samples.append(npv(rows, assumptions))

    def _pct(values: list[float]) -> dict[str, float]:
        arr = np.asarray(values, dtype=float)
        return {
            "p90": float(np.percentile(arr, 10)),
            "p50": float(np.percentile(arr, 50)),
            "p10": float(np.percentile(arr, 90)),
            "mean": float(np.mean(arr)),
        }

    return {
        "model": fit["model"],
        "fit": {
            key: float(fit[key])
            for key in ("qi", "d", "di", "b", "sse")
            if key in fit
        },
        "assumptions": assumptions.__dict__,
        "base": {
            "eur_bbl": base_eur,
            "npv": base_npv,
            "payback_month": payback_month(base_rows, assumptions),
            "forecast_months": len(base_rows),
        },
        "probabilistic": {
            "iterations": iterations,
            "seed": seed,
            "eur_bbl": _pct(eur_samples),
            "npv": _pct(npv_samples),
        },
        "forecast": base_rows,
    }
