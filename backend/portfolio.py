"""Prospect portfolio economics and correlated volume sampling."""

from __future__ import annotations

from statistics import NormalDist
from typing import Any

import numpy as np


def _boe_stats(prospect: dict[str, Any]) -> tuple[float, float, float]:
    result = prospect.get("result") or {}
    boe = result.get("recoverable_boe") or {}
    if boe:
        return float(boe.get("p90_bbl") or 0), float(boe.get("p50_bbl") or 0), float(boe.get("p10_bbl") or 0)
    recoverable = result.get("recoverable") or {}
    if recoverable:
        return float(recoverable.get("p90_bbl") or 0), float(recoverable.get("p50_bbl") or 0), float(recoverable.get("p10_bbl") or 0)
    return 0.0, 0.0, 0.0


def build_portfolio(
    prospects: list[dict[str, Any]],
    price_per_boe: float = 60.0,
    opex_per_boe: float = 10.0,
    capex: float = 0.0,
    dry_hole_cost: float = 0.0,
    correlation: float = 0.0,
    iterations: int = 2000,
    seed: int | None = None,
) -> dict[str, Any]:
    if not prospects:
        raise ValueError("portfolio needs at least one prospect")
    iterations = max(100, min(int(iterations), 20000))
    correlation = max(0.0, min(1.0, float(correlation)))
    items = []
    for prospect in prospects:
        p90, p50, p10 = _boe_stats(prospect)
        result = prospect.get("result") or {}
        chance = float((result.get("risk") or {}).get("probability", 1.0))
        net = (float(price_per_boe) - float(opex_per_boe)) * p50 - float(capex)
        emv = chance * net - (1.0 - chance) * float(dry_hole_cost)
        items.append({
            "id": prospect.get("id"),
            "name": prospect.get("name") or "Prospect",
            "fluid_type": prospect.get("fluid_type") or result.get("fluid_type") or "oil",
            "chance": round(chance, 4),
            "boe_p90": round(p90, 3),
            "boe_p50": round(p50, 3),
            "boe_p10": round(p10, 3),
            "net_revenue": round(net, 3),
            "emv": round(emv, 3),
        })
    items.sort(key=lambda item: item["emv"], reverse=True)
    for index, item in enumerate(items):
        item["rank"] = index + 1

    rng = np.random.default_rng(seed)
    norm = NormalDist()
    common = rng.normal(size=iterations)
    portfolio_samples = np.zeros(iterations, dtype=float)
    for item in items:
        idiosyncratic = rng.normal(size=iterations)
        z = np.sqrt(correlation) * common + np.sqrt(1.0 - correlation) * idiosyncratic
        u = np.asarray([norm.cdf(float(value)) for value in z])
        portfolio_samples += np.interp(
            u,
            [0.1, 0.5, 0.9],
            [item["boe_p90"], item["boe_p50"], item["boe_p10"]],
        )
    p90, p50, p10 = np.percentile(portfolio_samples, [10, 50, 90])
    return {
        "inputs": {
            "price_per_boe": float(price_per_boe),
            "opex_per_boe": float(opex_per_boe),
            "capex": float(capex),
            "dry_hole_cost": float(dry_hole_cost),
            "correlation": correlation,
            "iterations": iterations,
            "seed": seed,
        },
        "prospects": items,
        "portfolio": {
            "total_emv": round(float(sum(item["emv"] for item in items)), 3),
            "total_boe_p90": round(float(p90), 3),
            "total_boe_p50": round(float(p50), 3),
            "total_boe_p10": round(float(p10), 3),
            "mean_boe": round(float(np.mean(portfolio_samples)), 3),
            "prospect_count": len(items),
        },
    }
