"""GR-endpoint and shale-porosity calibration against reference interpretation.

VSH uses the linear GR normalisation VSH=(GR-gr_clean)/(gr_shale-gr_clean);
PHIE uses the density-neutron blend minus VSH*phi_sh. Both free parameters
are fit by bounded grid search minimising MAE against reference curves
(e.g. the Volve F-1 professional interpretation fixture).
"""

from __future__ import annotations

import numpy as np


def _check_paired(x: np.ndarray, y: np.ndarray, name: str) -> tuple[np.ndarray, np.ndarray]:
    x = np.asarray(x, dtype=float)
    y = np.asarray(y, dtype=float)
    if len(x) != len(y):
        raise ValueError(f"{name}: length mismatch {len(x)} vs {len(y)}")
    mask = np.isfinite(x) & np.isfinite(y)
    if int(mask.sum()) < 5:
        raise ValueError(f"{name}: not enough finite paired samples")
    return x[mask], y[mask]


def calibrate_vsh(gr: np.ndarray, vsh_ref: np.ndarray) -> dict:
    """Fit gr_clean/gr_shale endpoints by bounded grid search on MAE."""
    gr, ref = _check_paired(gr, vsh_ref, "vsh")
    gmin, gmax = float(np.min(gr)), float(np.max(gr))
    span = max(gmax - gmin, 1.0)
    best = None
    # Search clean in [min-span, p50], shale in [p50, max+span].
    p50 = float(np.median(gr))
    for clean in np.linspace(gmin - 0.5 * span, p50, 25):
        for shale in np.linspace(p50, gmax + 0.5 * span, 25):
            if shale - clean < 1.0:
                continue
            pred = np.clip((gr - clean) / (shale - clean), 0.0, 1.0)
            mae = float(np.mean(np.abs(pred - ref)))
            if best is None or mae < best["mae"]:
                best = {"gr_clean": round(float(clean), 2), "gr_shale": round(float(shale), 2), "mae": mae}
    if best is None:
        raise ValueError("vsh: no valid endpoint pair")
    return best


def calibrate_phi_sh(
    phi_raw: np.ndarray,
    vsh: np.ndarray,
    phi_ref: np.ndarray,
) -> dict:
    """Fit phi_sh in [0, 0.6] minimising MAE of max(0, phi_raw - vsh*phi_sh)."""
    phi_raw = np.asarray(phi_raw, dtype=float)
    vsh = np.asarray(vsh, dtype=float)
    phi_ref = np.asarray(phi_ref, dtype=float)
    if not (len(phi_raw) == len(vsh) == len(phi_ref)):
        raise ValueError("phi_sh: length mismatch")
    mask = np.isfinite(phi_raw) & np.isfinite(vsh) & np.isfinite(phi_ref)
    if int(mask.sum()) < 5:
        raise ValueError("phi_sh: not enough finite paired samples")
    phi_raw, vsh, phi_ref = phi_raw[mask], vsh[mask], phi_ref[mask]
    best = None
    for candidate in np.linspace(0.0, 0.6, 61):
        pred = np.maximum(0.0, phi_raw - vsh * candidate)
        mae = float(np.mean(np.abs(pred - phi_ref)))
        if best is None or mae < best["mae"]:
            best = {"phi_sh": round(float(candidate), 3), "mae": mae}
    return best
