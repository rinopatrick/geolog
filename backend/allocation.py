"""Rate allocation across compartments by transmissibility (kh).

Steady-state single-phase: flow splits proportional to kh when compartments
share drawdown. Zero-kh compartments take no rate. Residual from rounding is
assigned to the largest-kh compartment with a fixed seed tie-break so results
reproduce exactly.
"""

from __future__ import annotations

from typing import Any

import numpy as np


def allocate_production(
    total_rate_bpd: float,
    compartments: list[dict[str, Any]],
    seed: int | None = None,
) -> dict[str, Any]:
    total = float(total_rate_bpd)
    if not np.isfinite(total) or total < 0:
        raise ValueError("total_rate must be a non-negative finite number")
    if not compartments:
        raise ValueError("compartments must be a non-empty list")
    kh = []
    for comp in compartments:
        try:
            value = float(comp.get("kh_md_m", 0.0))
        except (TypeError, ValueError):
            raise ValueError(f"compartment {comp.get('id')} kh_md_m must be a number")
        if not np.isfinite(value) or value < 0:
            raise ValueError(f"compartment {comp.get('id')} kh_md_m must be non-negative finite")
        kh.append(value)
    kh = np.asarray(kh, dtype=float)
    kh_sum = float(np.sum(kh))
    if kh_sum <= 0:
        raise ValueError("total transmissibility must be positive")
    fractions = kh / kh_sum
    rates = np.round(total * fractions, 6)
    residual = round(total - float(np.sum(rates)), 6)
    if residual != 0.0:
        # Deterministic: largest kh first, lowest id breaks ties.
        order = sorted(
            range(len(compartments)),
            key=lambda i: (-kh[i], int(compartments[i].get("id", i))),
        )
        rates[order[0]] = round(float(rates[order[0]]) + residual, 6)
    allocations = []
    for comp, rate, frac in zip(compartments, rates, fractions):
        allocations.append({
            "id": comp.get("id"),
            "kh_md_m": float(kh[len(allocations)]),
            "grv_m3": comp.get("grv_m3"),
            "fraction": round(float(frac), 6),
            "rate_bpd": round(float(rate), 6),
        })
    return {
        "total_rate_bpd": round(total, 6),
        "allocated_bpd": round(float(np.sum(rates)), 6),
        "allocations": allocations,
        "seed": seed,
        "method": "kh_proportional",
    }
