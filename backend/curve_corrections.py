"""Shared curve-correction helpers.

Why this exists: DRHO (the density correction the tool computed) and the caliper
were parsed, stored and plotted, but never consulted by any compute path. Six
endpoints each had their own copy of the density-to-porosity formula and fed it
raw RHOB, so a rugose or washed-out interval produced porosity that looked like
real rock. There was also nowhere to put a correction — each site read
``np.frombuffer(...)`` directly — which is why the gap survived.

Two distinct things live here, deliberately kept apart:

1. The formula, so it exists once instead of six times.
2. The QC rule, which decides whether a density reading is trustworthy at all.
   This one is a *judgement call about the tool*, so the thresholds are
   parameters and the default is to report, not to silently drop data.
"""

from __future__ import annotations

from typing import Optional

import numpy as np

# Density readings whose tool correction exceeded this are not reliable. 0.05
# g/cc is the usual rule of thumb for compensated density tools; the exact
# value is tool- and vendor-dependent, hence a parameter.
DEFAULT_DRHO_LIMIT = 0.05

# A caliper reading this far over bit size indicates a washed-out hole, where
# the density pad cannot stay in contact with the formation.
DEFAULT_WASHOUT_INCHES = 2.0

DEFAULT_MATRIX_DENSITY = 2.65
DEFAULT_FLUID_DENSITY = 1.0


def density_porosity(
    rhob: np.ndarray,
    rho_ma: float = DEFAULT_MATRIX_DENSITY,
    rho_f: float = DEFAULT_FLUID_DENSITY,
    lo: float = -0.15,
    hi: float = 0.60,
) -> np.ndarray:
    """Density porosity: phi_D = (rho_ma - RHOB) / (rho_ma - rho_f).

    `lo`/`hi` are the caller's clip bounds; they differ per endpoint (a
    moveable-oil calculation wants [0, 1] where a porosity curve wants a
    slightly negative floor to show the overshoot).
    """
    rhob = np.asarray(rhob, dtype=np.float64)
    # Guard matches the original inline form: a non-positive denominator (matrix
    # and fluid densities equal or inverted) saturates to the clip ceiling
    # rather than producing inf/nan.
    denominator = max(1e-9, rho_ma - rho_f)
    return np.clip((rho_ma - rhob) / denominator, lo, hi)


def bad_hole_mask(
    n: int,
    drho: Optional[np.ndarray] = None,
    cali: Optional[np.ndarray] = None,
    bit_size: Optional[np.ndarray | float] = None,
    drho_limit: float = DEFAULT_DRHO_LIMIT,
    washout_inches: float = DEFAULT_WASHOUT_INCHES,
) -> tuple[np.ndarray, dict]:
    """Flag samples where the density reading should not be trusted.

    Returns ``(mask, reasons)`` where ``mask`` is a boolean array that is True
    for suspect samples. `reasons` counts how many samples each rule caught, so
    a caller can report *why* rather than just how many.

    Both inputs are optional. With neither supplied the mask is all-False and
    every existing behaviour is unchanged.
    """
    mask = np.zeros(n, dtype=bool)
    reasons = {"drho": 0, "washout": 0}

    if drho is not None:
        drho = np.asarray(drho, dtype=np.float64)
        if len(drho) == n:
            # NaN means "no correction recorded", not "large correction".
            flagged = np.isfinite(drho) & (np.abs(drho) > drho_limit)
            reasons["drho"] = int(np.count_nonzero(flagged))
            mask |= flagged

    if cali is not None and bit_size is not None:
        cali = np.asarray(cali, dtype=np.float64)
        bs = np.asarray(bit_size, dtype=np.float64)
        if len(cali) == n:
            bs = np.broadcast_to(bs, (n,)) if bs.ndim == 0 else bs
            if len(bs) == n:
                flagged = np.isfinite(cali) & np.isfinite(bs) & (cali > bs + washout_inches)
                reasons["washout"] = int(np.count_nonzero(flagged))
                mask |= flagged

    return mask, reasons


def apply_mask(arr: np.ndarray, mask: np.ndarray) -> np.ndarray:
    """Return a copy of `arr` with masked samples set to NaN."""
    out = np.array(arr, dtype=np.float64, copy=True)
    out[mask] = np.nan
    return out


def qc_summary(mask: np.ndarray, reasons: dict) -> dict:
    """Shape the mask into something an API response can carry."""
    total = int(len(mask))
    flagged = int(np.count_nonzero(mask))
    return {
        "bad_hole_count": flagged,
        "bad_hole_pct": round(flagged * 100.0 / total, 2) if total else 0.0,
        "total_samples": total,
        "reasons": dict(reasons),
    }
