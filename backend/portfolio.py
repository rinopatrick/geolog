"""Prospect portfolio economics, correlated volumes and correlated risking."""

from __future__ import annotations

from statistics import NormalDist
from typing import Any

import numpy as np


def _boe_stats(prospect: dict[str, Any]) -> tuple[float, float, float, float]:
    result = prospect.get("result") or {}
    boe = result.get("recoverable_boe") or {}
    if not boe:
        boe = result.get("recoverable") or {}
    p90 = float(boe.get("p90_bbl") or 0)
    p50 = float(boe.get("p50_bbl") or 0)
    p10 = float(boe.get("p10_bbl") or 0)
    mean = float(boe.get("mean_bbl") or p50)
    return p90, p50, p10, mean


def _summary(values: np.ndarray) -> dict[str, float]:
    p90, p50, p10 = np.percentile(values, [10, 50, 90])
    return {
        "p90": round(float(p90), 3),
        "p50": round(float(p50), 3),
        "p10": round(float(p10), 3),
        "mean": round(float(np.mean(values)), 3),
    }


def build_portfolio(
    prospects: list[dict[str, Any]],
    price_per_boe: float = 60.0,
    opex_per_boe: float = 10.0,
    capex: float = 0.0,
    dry_hole_cost: float = 0.0,
    correlation: float = 0.0,
    risk_correlation: float = 0.0,
    capex_timing: str = "success",
    iterations: int = 2000,
    seed: int | None = None,
) -> dict[str, Any]:
    if not prospects:
        raise ValueError("portfolio needs at least one prospect")
    iterations = max(100, min(int(iterations), 20000))
    correlation = max(0.0, min(1.0, float(correlation)))
    risk_correlation = max(0.0, min(1.0, float(risk_correlation)))
    timing = str(capex_timing or "success").lower()
    if timing not in {"success", "pre_drill"}:
        raise ValueError("capex_timing must be success or pre_drill")
    price = float(price_per_boe)
    opex = float(opex_per_boe)
    capex_value = float(capex)
    dry_value = float(dry_hole_cost)

    items = []
    for prospect in prospects:
        p90, p50, p10, mean = _boe_stats(prospect)
        result = prospect.get("result") or {}
        chance = min(1.0, max(0.0, float((result.get("risk") or {}).get("probability", 1.0))))
        success_net = (price - opex) * mean - (capex_value if timing == "success" else 0.0)
        dry_net = -(dry_value + (capex_value if timing == "pre_drill" else 0.0))
        emv = chance * success_net + (1.0 - chance) * dry_net
        items.append({
            "id": prospect.get("id"),
            "name": prospect.get("name") or "Prospect",
            "fluid_type": prospect.get("fluid_type") or result.get("fluid_type") or "oil",
            "chance": round(chance, 4),
            "boe_p90": round(p90, 3),
            "boe_p50": round(p50, 3),
            "boe_p10": round(p10, 3),
            "boe_mean": round(mean, 3),
            "success_net": round(success_net, 3),
            "dry_net": round(dry_net, 3),
            "emv": round(emv, 3),
        })
    items.sort(key=lambda item: item["emv"], reverse=True)
    for index, item in enumerate(items):
        item["rank"] = index + 1

    rng = np.random.default_rng(seed)
    norm = NormalDist()
    common_volume = rng.normal(size=iterations)
    common_risk = rng.normal(size=iterations)
    portfolio_samples = np.zeros(iterations, dtype=float)
    risked_samples = np.zeros(iterations, dtype=float)
    for item in items:
        volume_z = (
            np.sqrt(correlation) * common_volume
            + np.sqrt(1.0 - correlation) * rng.normal(size=iterations)
        )
        volume_u = np.asarray([norm.cdf(float(value)) for value in volume_z])
        volume = np.interp(
            volume_u,
            [0.1, 0.5, 0.9],
            [item["boe_p90"], item["boe_p50"], item["boe_p10"]],
        )
        risk_z = (
            np.sqrt(risk_correlation) * common_risk
            + np.sqrt(1.0 - risk_correlation) * rng.normal(size=iterations)
        )
        risk_u = np.asarray([norm.cdf(float(value)) for value in risk_z])
        success = risk_u <= item["chance"]
        portfolio_samples += volume
        risked_samples += volume * success

    unrisked = _summary(portfolio_samples)
    risked = _summary(risked_samples)
    return {
        "inputs": {
            "price_per_boe": price,
            "opex_per_boe": opex,
            "capex": capex_value,
            "dry_hole_cost": dry_value,
            "correlation": correlation,
            "risk_correlation": risk_correlation,
            "capex_timing": timing,
            "iterations": iterations,
            "seed": seed,
        },
        "prospects": items,
        "portfolio": {
            "total_emv": round(float(sum(item["emv"] for item in items)), 3),
            "total_boe_p90": unrisked["p90"],
            "total_boe_p50": unrisked["p50"],
            "total_boe_p10": unrisked["p10"],
            "mean_boe": unrisked["mean"],
            "risked_boe_p90": risked["p90"],
            "risked_boe_p50": risked["p50"],
            "risked_boe_p10": risked["p10"],
            "risked_boe_mean": risked["mean"],
            "prospect_count": len(items),
        },
    }
