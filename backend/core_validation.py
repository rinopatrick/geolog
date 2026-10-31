"""Laboratory-plug validation for log-derived transforms.

Fits a log-linear porosity-permeability transform on measured plugs
(log10(k) = intercept + slope * porosity_pct) and reports Sw baselines.
Reference: RealPore NCS fixture (test_data/realpore_ncs/, CC-BY 4.0,
attribution to GeoProvider). Validates against laboratory plugs, not
against another interpretation.
"""

from __future__ import annotations

from typing import Any

import numpy as np


def _columns(rows: list[dict[str, Any]], *names: str) -> dict[str, np.ndarray]:
    if not rows:
        raise ValueError("no rows: empty plug list")
    out = {}
    for name in names:
        values = []
        for row in rows:
            try:
                values.append(float(row[name]))
            except (KeyError, TypeError, ValueError):
                values.append(np.nan)
        arr = np.asarray(values, dtype=float)
        if not np.any(np.isfinite(arr)):
            raise ValueError(f"no finite values for column {name!r}; check column names")
        out[name] = arr
    return out


def fit_poro_perm(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Fit log10(perm_mD) = intercept + slope * porosity_pct on plugs."""
    cols = _columns(rows, "porosity_pct", "perm_klinkenberg_md")
    poro, perm = cols["porosity_pct"], cols["perm_klinkenberg_md"]
    mask = np.isfinite(poro) & np.isfinite(perm) & (poro > 0) & (perm > 0)
    if int(mask.sum()) < 10:
        raise ValueError("need at least 10 valid porosity-permeability pairs")
    poro, perm = poro[mask], perm[mask]
    logk = np.log10(perm)
    slope, intercept = np.polyfit(poro, logk, 1)
    pred = slope * poro + intercept
    ss_res = float(np.sum((logk - pred) ** 2))
    ss_tot = float(np.sum((logk - float(np.mean(logk))) ** 2))
    r2 = 1.0 - ss_res / ss_tot if ss_tot > 0 else 0.0
    return {
        "slope": round(float(slope), 6),
        "intercept": round(float(intercept), 6),
        "r2": round(float(r2), 4),
        "residual_std_log10": round(float(np.std(logk - pred)), 4),
        "n": int(mask.sum()),
        "porosity_range_pct": [round(float(np.min(poro)), 2), round(float(np.max(poro)), 2)],
        "method": "ordinary_least_squares_log10k",
    }


def sw_baseline(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Median laboratory Sw as an interpretation sanity anchor."""
    cols = _columns(rows, "sw_pct")
    sw = cols["sw_pct"]
    sw = sw[np.isfinite(sw)]
    if len(sw) == 0:
        raise ValueError("no finite sw_pct values")
    return {
        "median_sw_pct": round(float(np.median(sw)), 2),
        "mean_sw_pct": round(float(np.mean(sw)), 2),
        "p10_sw_pct": round(float(np.percentile(sw, 10)), 2),
        "p90_sw_pct": round(float(np.percentile(sw, 90)), 2),
        "n": len(sw),
    }


def lot_gradient_band(rows: list[dict[str, Any]], emw_col: str = "wlbLotMudDencity") -> dict[str, Any]:
    """Summarise LOT mud-equivalents as Shmin-gradient band (psi/ft)."""
    vals = []
    for row in rows:
        try:
            v = float(row[emw_col])
        except (KeyError, TypeError, ValueError):
            continue
        if np.isfinite(v) and v > 0:
            vals.append(v * 0.4335)
    arr = np.asarray(vals, dtype=float)
    if len(arr) < 5:
        raise ValueError("need at least 5 valid LOT mud-equivalent values")
    return {
        "n": len(arr),
        "median_psi_ft": round(float(np.median(arr)), 4),
        "p10_psi_ft": round(float(np.percentile(arr, 10)), 4),
        "p90_psi_ft": round(float(np.percentile(arr, 90)), 4),
        "unit": "psi/ft",
    }
