"""Source-rock screening: Passey delta-log-R and Schmoker TOC."""

from __future__ import annotations

from typing import Any

import numpy as np


def _finite(arr) -> np.ndarray:
    out = np.asarray(arr, dtype=np.float64).copy()
    out[~np.isfinite(out)] = np.nan
    return out


def passey_toc(
    rt,
    porosity,
    *,
    porosity_mode: str = "sonic",
    rt_base: float | None = None,
    porosity_base: float | None = None,
    lom: float = 10.0,
    toc_base: float = 0.0,
) -> tuple[np.ndarray, dict[str, float]]:
    """Passey et al. (1990) delta-log-R TOC in weight percent.

    Sonic mode uses `log10(Rt/Rt_base) + 0.02*(DT - DT_base)`.
    Density mode uses `log10(Rt/Rt_base) - 2.5*(RHOB - RHOB_base)`.
    Without explicit baselines, shale-side percentiles are used.
    """
    rt = _finite(rt)
    por = _finite(porosity)
    n = min(len(rt), len(por))
    rt, por = rt[:n], por[:n]
    valid = np.isfinite(rt) & (rt > 0) & np.isfinite(por)
    if valid.sum() < 3:
        raise ValueError("need at least three valid resistivity and porosity samples")

    if rt_base is None:
        rt_base = float(np.nanpercentile(rt[valid], 20))
    if porosity_base is None:
        porosity_base = float(np.nanpercentile(por[valid], 80))

    with np.errstate(divide="ignore", invalid="ignore"):
        if porosity_mode == "density":
            delta = np.log10(rt / rt_base) - 2.5 * (por - porosity_base)
        else:
            delta = np.log10(rt / rt_base) + 0.02 * (por - porosity_base)

    delta = np.where(np.isfinite(delta), np.clip(delta, 0.0, None), np.nan)
    toc = delta * (10.0 ** (2.297 - 0.1688 * float(lom))) + float(toc_base)
    toc = np.clip(toc, 0.0, 60.0)
    return toc, {
        "rt_base": float(rt_base),
        "porosity_base": float(porosity_base),
        "lom": float(lom),
        "toc_base": float(toc_base),
        "porosity_mode": porosity_mode,
    }


def schmoker_toc(rhob) -> np.ndarray:
    """Schmoker (1979) density-log TOC approximation in weight percent."""
    rho = _finite(rhob)
    with np.errstate(divide="ignore", invalid="ignore"):
        toc = 154.497 / rho - 57.261
    return np.clip(np.where(np.isfinite(toc), toc, np.nan), 0.0, 60.0)


def kerogen_volume(toc_wt, rhob, rho_kerogen: float = 1.2) -> np.ndarray:
    """Convert TOC weight percent to kerogen bulk-volume fraction."""
    toc = _finite(toc_wt)
    rho = _finite(rhob)
    with np.errstate(divide="ignore", invalid="ignore"):
        vker = (toc / 100.0) * rho / rho_kerogen
    return np.clip(np.where(np.isfinite(vker), vker, np.nan), 0.0, 1.0)


def stats(arr) -> dict[str, Any]:
    values = _finite(arr)
    valid = values[np.isfinite(values)]
    if not len(valid):
        return {"count": 0, "min": None, "max": None, "mean": None}
    return {
        "count": int(len(valid)),
        "min": float(np.min(valid)),
        "max": float(np.max(valid)),
        "mean": float(np.mean(valid)),
    }
