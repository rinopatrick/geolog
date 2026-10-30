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


def _validated_matrix(raw: Any, count: int, label: str) -> np.ndarray | None:
    if raw is None:
        return None
    matrix = np.asarray(raw, dtype=float)
    if matrix.shape != (count, count):
        raise ValueError(f"{label} must be a {count}x{count} matrix")
    if not np.allclose(matrix, matrix.T, atol=1e-6):
        raise ValueError(f"{label} must be symmetric")
    if not np.allclose(np.diag(matrix), 1.0, atol=1e-6):
        raise ValueError(f"{label} diagonal must be 1")
    if np.any(np.abs(matrix) > 1.0 + 1e-6):
        raise ValueError(f"{label} values must be between -1 and 1")
    if float(np.min(np.linalg.eigvalsh(matrix))) < -1e-8:
        raise ValueError(f"{label} must be positive semidefinite")
    return matrix


def _correlated_normals(
    matrix: np.ndarray | None,
    scalar: float,
    count: int,
    iterations: int,
    random: np.random.Generator,
    common: np.ndarray,
) -> np.ndarray:
    if matrix is not None:
        try:
            cholesky = np.linalg.cholesky(matrix + np.eye(matrix.shape[0]) * 1e-10)
        except np.linalg.LinAlgError as exc:
            raise ValueError("correlation matrix is not positive definite") from exc
        return cholesky @ random.normal(size=(count, iterations))
    rows = []
    for _ in range(count):
        rows.append(np.sqrt(scalar) * common + np.sqrt(1.0 - scalar) * random.normal(size=iterations))
    return np.vstack(rows)


def build_portfolio(
    prospects: list[dict[str, Any]],
    price_per_boe: float = 60.0,
    opex_per_boe: float = 10.0,
    capex: float = 0.0,
    dry_hole_cost: float = 0.0,
    correlation: float = 0.0,
    risk_correlation: float = 0.0,
    correlation_matrix: Any = None,
    risk_correlation_matrix: Any = None,
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
    count = len(prospects)
    volume_matrix = _validated_matrix(correlation_matrix, count, "correlation_matrix")
    risk_matrix = _validated_matrix(risk_correlation_matrix, count, "risk_correlation_matrix")

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
    ranked = sorted(items, key=lambda item: item["emv"], reverse=True)
    for index, item in enumerate(ranked):
        item["rank"] = index + 1

    rng = np.random.default_rng(seed)
    norm = NormalDist()
    volume_normals = _correlated_normals(
        volume_matrix, correlation, count, iterations, rng, rng.normal(size=iterations)
    )
    risk_normals = _correlated_normals(
        risk_matrix, risk_correlation, count, iterations, rng, rng.normal(size=iterations)
    )
    portfolio_samples = np.zeros(iterations, dtype=float)
    risked_samples = np.zeros(iterations, dtype=float)
    for index, item in enumerate(items):
        volume_u = np.asarray([norm.cdf(float(value)) for value in volume_normals[index]])
        volume = np.interp(
            volume_u,
            [0.1, 0.5, 0.9],
            [item["boe_p90"], item["boe_p50"], item["boe_p10"]],
        )
        risk_u = np.asarray([norm.cdf(float(value)) for value in risk_normals[index]])
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
            "correlation_matrix": volume_matrix.tolist() if volume_matrix is not None else None,
            "risk_correlation_matrix": risk_matrix.tolist() if risk_matrix is not None else None,
            "capex_timing": timing,
            "iterations": iterations,
            "seed": seed,
        },
        "prospects": ranked,
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
