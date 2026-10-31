"""Pure deterministic petrophysics kernels (VCL, PHIE blend, Sw).

Extracted from the compute_saturation endpoint path so the same math is
testable without a database. Conventions mirror the endpoint defaults:
Larionov tertiary VSH, density-neutron blend with gas crossover, Archie
and shaly-sand Sw shared with backend/saturation.py.
"""

from __future__ import annotations

import numpy as np

try:
    from curve_corrections import density_porosity
    from saturation import saturation
except ImportError:
    from backend.curve_corrections import density_porosity
    from backend.saturation import saturation


def vclay(
    gr: np.ndarray,
    gr_clean: float,
    gr_shale: float,
    method: str = "larionov_tertiary",
) -> np.ndarray:
    gr = np.asarray(gr, dtype=float)
    if not np.isfinite(gr_clean) or not np.isfinite(gr_shale):
        raise ValueError("gr_clean and gr_shale must be finite")
    if gr_shale <= gr_clean:
        raise ValueError(f"gr_shale ({gr_shale}) must exceed gr_clean ({gr_clean})")
    name = str(method or "larionov_tertiary").lower()
    if name not in {"igr", "larionov_tertiary", "larionov_old", "steiber", "clavier"}:
        raise ValueError(f"unknown vsh method: {method}")
    gr_range = max(float(gr_shale) - float(gr_clean), 1e-9)
    igr = np.clip((gr - float(gr_clean)) / gr_range, 0.0, 1.0)
    if name == "igr":
        vsh = igr
    elif name == "steiber":
        vsh = np.where(igr < 1.0, igr / np.maximum(3.0 - 2.0 * igr, 1e-9), 1.0)
    elif name == "clavier":
        vsh = np.where(igr < 1.0, 1.7 - np.sqrt(np.maximum(3.38 - (igr + 0.7) ** 2, 0.0)), 1.0)
    elif name == "larionov_old":
        vsh = np.where(igr < 1.0, 0.33 * (2.0 ** (2.0 * igr) - 1.0), 1.0)
    else:
        vsh = np.where(igr < 1.0, 0.083 * (2.0 ** (3.7 * igr) - 1.0), 1.0)
    return np.clip(vsh, 0.0, 1.0)


def porosity_blend(
    nphi: np.ndarray,
    rhob: np.ndarray,
    vsh: np.ndarray,
    rho_ma: float = 2.65,
    rho_f: float = 1.0,
    phi_sh: float = 0.30,
) -> np.ndarray:
    nphi = np.asarray(nphi, dtype=float)
    rhob = np.asarray(rhob, dtype=float)
    vsh = np.asarray(vsh, dtype=float)
    if not (len(nphi) == len(rhob) == len(vsh)):
        raise ValueError("nphi/rhob/vsh length mismatch")
    if not 0.0 <= float(phi_sh) <= 0.6:
        raise ValueError("phi_sh must be between 0 and 0.6")
    phi = np.full(len(nphi), np.nan)
    for i in range(len(nphi)):
        phi_n = nphi[i] if np.isfinite(nphi[i]) else np.nan
        phi_d = np.nan
        if np.isfinite(rhob[i]):
            try:
                phi_d = density_porosity(float(rhob[i]), lo=-0.15, hi=0.60)
            except (TypeError, ValueError):
                phi_d = np.nan
        vv = vsh[i] if np.isfinite(vsh[i]) else 0.0
        if np.isfinite(phi_d) and np.isfinite(phi_n):
            phie_v = phi_d if phi_n < phi_d - 0.03 else (phi_d + phi_n) / 2.0
        elif np.isfinite(phi_d):
            phie_v = phi_d
        elif np.isfinite(phi_n):
            phie_v = phi_n * (1.0 - vv)
        else:
            continue
        phi[i] = max(0.0, min(0.60, phie_v - vv * float(phi_sh)))
    return phi


def water_saturation(
    model: str,
    rt: np.ndarray,
    phi: np.ndarray,
    vsh: np.ndarray,
    a: float = 1.0,
    m: float = 2.0,
    n: float = 2.0,
    rw: float = 0.1,
    rsh: float = 4.0,
) -> np.ndarray:
    name = str(model or "").lower()
    if name not in {"archie", "simandoux", "indonesian"}:
        raise ValueError(f"unknown saturation model: {model}")
    rt = np.asarray(rt, dtype=float)
    phi = np.asarray(phi, dtype=float)
    vsh = np.asarray(vsh, dtype=float)
    if not (len(rt) == len(phi) == len(vsh)):
        raise ValueError("rt/phi/vsh length mismatch")
    out = np.full(len(rt), np.nan)
    for i in range(len(rt)):
        if not np.isfinite(rt[i]) or rt[i] <= 0:
            continue
        if not np.isfinite(phi[i]) or phi[i] < 0.01:
            continue
        vv = vsh[i] if np.isfinite(vsh[i]) else 0.0
        try:
            out[i] = float(saturation(name, rt[i], max(float(phi[i]), 0.01), vv, a=a, m=m, n=n, rw=rw, rsh=rsh))
        except (TypeError, ValueError):
            continue
    return out
