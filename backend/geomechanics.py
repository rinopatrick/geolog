"""Screening geomechanics: elastic moduli, pore pressure, stresses, failures.

The calculations are deterministic and vectorized. Absolute SHmax/Shmin and pore
pressure values are labelled ``calibrated`` only when calibration points are
supplied; otherwise they are correlations/assumptions. The deviated-well stress
path is a generalized-Kirsch screening approximation, not a full 3D FE model.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any

import numpy as np

PSI_PER_FT_PER_GCC = 0.4335
FT_PER_M = 3.280839895
PSI_PER_PA = 0.0001450377377

DEFAULT_PARAMS: dict[str, Any] = {
    "pore_pressure_method": "eaton",
    "eaton_n": 3.0,
    "bowers_a": 20000.0,
    "bowers_b": 0.7,
    "bowers_v0": 5000.0,
    "water_gradient": 0.433,
    "overburden_gradient": 0.4335,
    "shmin_gradient": 0.70,
    "shmax_gradient": 1.20,
    "shmax_azimuth": 0.0,
    "inclination": 0.0,
    "azimuth": 0.0,
    "biot": 0.9,
    "ucs": 1500.0,
    "friction_angle": 30.0,
    "tensile_strength": 100.0,
    "cohesion": 500.0,
    "hoek_brown_mb": 1.0,
    "hoek_brown_s": 0.004,
    "hoek_brown_a": 0.5,
    "mud_weight": 9.0,
    "fracture_mu": 0.6,
    "fracture_cohesion": 0.0,
    "dts_castagna": True,
}

def _curve(sem: dict, names: tuple[str, ...]) -> tuple[np.ndarray | None, str]:
    wanted = {n.upper() for n in names}
    for meta in sem["metadata"]["aliases"]:
        if str(meta["name"]).upper() in wanted or str(meta["raw"]).upper() in wanted:
            arr = sem["curves"].get(meta["name"])
            if arr is not None:
                return np.asarray(arr, dtype=np.float64), str(meta["name"])
    return None, ""

def _fill(arr: np.ndarray, fallback: float) -> np.ndarray:
    out = np.asarray(arr, dtype=np.float64).copy()
    good = np.isfinite(out)
    if not np.any(good):
        return np.full_like(out, fallback)
    idx = np.arange(len(out))
    out[~good] = np.interp(idx[~good], idx[good], out[good])
    return out

def _hash_payload(payload: dict) -> str:
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()

def _normal_trend(depth: np.ndarray, dt: np.ndarray, gr: np.ndarray | None) -> np.ndarray:
    good = np.isfinite(depth) & np.isfinite(dt) & (dt > 0)
    if gr is not None and np.any(np.isfinite(gr)):
        cutoff = np.nanpercentile(gr[np.isfinite(gr)], 60)
        shale = good & (gr >= cutoff)
        if np.count_nonzero(shale) >= 8:
            good = shale
    if np.count_nonzero(good) >= 8 and np.ptp(depth[good]) > 0:
        slope, intercept = np.polyfit(depth[good], np.log(dt[good]), 1)
        trend = np.exp(intercept + slope * depth)
        if np.all(np.isfinite(trend)) and np.all(trend > 20) and np.all(trend < 400):
            return trend
    # Fallback normal compaction trend (us/ft); deterministic and conservative.
    return 100.0 - 0.012 * depth

def _interp_points(points: Any, depth: np.ndarray) -> np.ndarray | None:
    if not isinstance(points, list) or len(points) < 2:
        return None
    xs, ys = [], []
    for point in points:
        if isinstance(point, dict):
            x, y = point.get("depth"), point.get("value", point.get("pressure"))
        elif isinstance(point, (list, tuple)) and len(point) >= 2:
            x, y = point[0], point[1]
        else:
            continue
        try:
            xs.append(float(x))
            ys.append(float(y))
        except (TypeError, ValueError):
            continue
    if len(xs) < 2:
        return None
    order = np.argsort(xs)
    return np.interp(depth, np.array(xs)[order], np.array(ys)[order])

def _elastic(vp: np.ndarray, vs: np.ndarray, rhob: np.ndarray) -> dict[str, np.ndarray]:
    # VP/VS arrive in m/s (304800/DT); density in g/cc. No further conversion.
    rho = rhob * 1000.0
    vp_m = np.asarray(vp, dtype=np.float64)
    vs_m = np.asarray(vs, dtype=np.float64)
    mu = rho * vs_m ** 2
    lam = rho * vp_m ** 2 - 2.0 * mu
    nu = (vp ** 2 - 2.0 * vs ** 2) / (2.0 * (vp ** 2 - vs ** 2))
    e = 2.0 * mu * (1.0 + nu)
    return {
        "G": mu / 1e9,
        "K": (lam + 2.0 * mu / 3.0) / 1e9,
        "E": e / 1e9,
        "NU": nu,
    }

def _far_field_tensor(shmax: np.ndarray, shmin: np.ndarray, sv: np.ndarray, azimuth_deg: float) -> np.ndarray:
    """ENU tensor with SHmax azimuth measured clockwise from north."""
    a = np.deg2rad(azimuth_deg)
    ex = np.array([np.sin(a), np.cos(a), 0.0])
    ey = np.array([np.cos(a), -np.sin(a), 0.0])
    ez = np.array([0.0, 0.0, 1.0])
    out = np.zeros((len(sv), 3, 3))
    out += shmax[:, None, None] * np.outer(ex, ex)
    out += shmin[:, None, None] * np.outer(ey, ey)
    out += sv[:, None, None] * np.outer(ez, ez)
    return out

def _borehole_hoop(tensor: np.ndarray, inclination: float, azimuth: float) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    inc = np.deg2rad(inclination)
    azi = np.deg2rad(azimuth)
    b = np.array([np.sin(inc) * np.sin(azi), np.sin(inc) * np.cos(azi), np.cos(inc)])
    helper = np.array([0.0, 0.0, 1.0]) if abs(b[2]) < 0.9 else np.array([1.0, 0.0, 0.0])
    e1 = np.cross(b, helper)
    e1 /= np.linalg.norm(e1)
    e2 = np.cross(b, e1)
    e2 /= np.linalg.norm(e2)
    rot = np.stack([e1, e2, b])
    transformed = np.einsum("ij,njk,lk->nil", rot, tensor, rot)
    s11, s22, s12 = transformed[:, 0, 0], transformed[:, 1, 1], transformed[:, 0, 1]
    amplitude = 4.0 * np.sqrt(((s11 - s22) / 2.0) ** 2 + s12 ** 2)
    base_max = s11 + s22 + amplitude
    base_min = s11 + s22 - amplitude
    return base_max, base_min, s11 + s22

def _plane_slip(tensor: np.ndarray, planes: Any, pp: np.ndarray, mu: float, cohesion: float) -> np.ndarray | None:
    if not isinstance(planes, list) or not planes:
        return None
    out = np.zeros(len(pp), dtype=bool)
    for plane in planes:
        try:
            strike = np.deg2rad(float(plane.get("strike", 0.0)))
            dip = np.deg2rad(float(plane.get("dip", 0.0)))
        except (AttributeError, TypeError, ValueError):
            continue
        n = np.array([np.sin(strike) * np.sin(dip), np.cos(strike) * np.sin(dip), np.cos(dip)])
        normal = np.einsum("nij,i,j->n", tensor, n, n)
        shear_vec = np.einsum("nij,j->ni", tensor, n) - normal[:, None] * n
        tau = np.linalg.norm(shear_vec, axis=1)
        out |= tau > (mu * np.maximum(normal - pp, 0.0) + cohesion)
    return out

def compute(
    sem: dict,
    params: dict | None = None,
    calibration: dict | None = None,
) -> dict[str, Any]:
    p = dict(DEFAULT_PARAMS)
    p.update(params or {})
    cal = calibration or {}
    unit_system = (sem.get("metadata", {}).get("unit_system") or "field").lower()
    depth = np.asarray(sem["depth"], dtype=np.float64)
    tvd = np.asarray(sem.get("tvd", depth), dtype=np.float64)
    if unit_system == "si":
        depth_ft = depth * FT_PER_M
        tvd_ft = tvd * FT_PER_M
    else:
        depth_ft = depth
        tvd_ft = tvd

    rhob, _ = _curve(sem, ("RHOB", "RHOZ", "DEN", "ZDEN"))
    dt, _ = _curve(sem, ("DT", "DTC", "AC"))
    dts, _ = _curve(sem, ("DTS", "DTSM"))
    gr, _ = _curve(sem, ("GR", "GAMMA"))
    if rhob is None or dt is None:
        raise ValueError("RHOB and DT curves are required")
    warnings: list[str] = []
    rhob = _fill(rhob, 2.4)
    dt = _fill(dt, 80.0)
    if unit_system == "si":
        rhob = rhob / 1000.0
        dt = dt * 0.3048
        if dts is not None:
            dts = dts * 0.3048
    dt = np.clip(dt, 20.0, 400.0)
    if dts is not None:
        dts = np.asarray(dts, dtype=np.float64)
        dts = np.where(np.isfinite(dts), np.clip(dts, 20.0, 600.0), np.nan)
    vp = 304800.0 / dt
    # VP/VS curves are m/s (304800/DT(us/ft) = 1 ft/us in m/s). Castagna's
    # mudrock line is SI, so it applies directly. Below the line's range it
    # goes unphysical, so fall back to Vp/Vs = 2.0 (Poisson ~0.33).
    vs_mps = (vp - 1360.0) / 1.16
    slow = ~np.isfinite(vs_mps) | (vs_mps <= 0.0)
    vs_mps = np.where(slow, vp / 2.0, vs_mps)
    castagna_dts = 304800.0 / np.maximum(vs_mps, 1.0)
    if dts is None or not np.any(np.isfinite(dts)):
        dts = castagna_dts
        warnings.append("DTS missing; Vs estimated with Castagna")
    else:
        missing = ~np.isfinite(dts)
        dts = np.where(missing, castagna_dts, dts)
        if np.any(missing):
            warnings.append("DTS gaps filled with Castagna")
    vs = 304800.0 / dts

    # Overburden from density integration (psi).
    dz = np.diff(np.concatenate([[0.0], tvd_ft]))
    dz = np.clip(dz, 0.0, None)
    sv = np.cumsum(rhob * p["overburden_gradient"] * dz)
    sv = np.maximum(sv, 0.0)

    phyd = p["water_gradient"] * tvd_ft
    pp_cal = _interp_points(cal.get("pp"), tvd_ft)
    if pp_cal is not None:
        pp = pp_cal
        pp_source = "calibrated"
    else:
        pp_source = "correlation"
        method = str(p.get("pore_pressure_method") or "eaton").lower()
        if method == "bowers":
            v0 = float(p["bowers_v0"])
            a = max(float(p["bowers_a"]), 1e-9)
            b = max(float(p["bowers_b"]), 1e-6)
            pp = np.power(np.maximum(vp - v0, 0.0) / a, 1.0 / b)
            pp = np.where(np.isfinite(pp), pp, phyd)
        elif method == "hydrostatic":
            pp = phyd
        else:
            trend = _normal_trend(depth_ft, dt, gr)
            n = float(p.get("eaton_n") or 3.0)
            ratio = np.clip(trend / dt, 1e-6, None)
            pp = sv - (sv - phyd) * np.power(ratio, n)
            pp = np.where(np.isfinite(pp), pp, phyd)
    pp = np.clip(pp, phyd * 0.8, sv * 0.98)
    if pp_cal is None:
        warnings.append("pore pressure is a correlation (no pp calibration)")

    shmin_cal = _interp_points(cal.get("shmin"), tvd_ft)
    shmax_cal = _interp_points(cal.get("shmax"), tvd_ft)
    if shmin_cal is not None:
        shmin = shmin_cal
        shmin_source = "calibrated"
    else:
        shmin = float(p["shmin_gradient"]) * tvd_ft
        shmin_source = "assumption"
    if shmax_cal is not None:
        shmax = shmax_cal
        shmax_source = "calibrated"
    else:
        shmax = float(p["shmax_gradient"]) * tvd_ft
        shmax_source = "assumption"
        warnings.append("SHmax is an assumption; supply LOT/XLOT/DFIT/breakout calibration")
    shmax_azi = float(cal.get("shmax_azimuth", p.get("shmax_azimuth", 0.0)) or 0.0)
    shmin = np.clip(shmin, pp, sv)
    shmax = np.clip(shmax, shmin, sv * 1.5)

    el = _elastic(vp, vs, rhob)
    alpha = float(p["biot"])
    ucs = float(p["ucs"])
    phi = np.deg2rad(float(p["friction_angle"]))
    tensile = float(p["tensile_strength"])
    tensor = _far_field_tensor(shmax, shmin, sv, shmax_azi)
    base_max, base_min, _ = _borehole_hoop(tensor, float(p.get("inclination", 0.0)), float(p.get("azimuth", 0.0)))
    pw_min_psi = np.maximum((base_max - alpha * pp - ucs) / 2.0, 0.0)
    pw_max_psi = (base_min - alpha * pp + tensile) / 2.0
    mw_min = pw_min_psi / np.maximum(0.052 * tvd_ft, 1e-9)
    mw_max = pw_max_psi / np.maximum(0.052 * tvd_ft, 1e-9)
    mw_min = np.clip(mw_min, 0.0, 25.0)
    mw_max = np.where(np.isfinite(mw_max), mw_max, np.nan)
    mw_max = np.maximum(mw_max, mw_min)
    mw_current = float(p.get("mud_weight") or 9.0)

    # Effective principal stresses from the full tensor (ascending order).
    eff = tensor - alpha * pp[:, None, None] * np.eye(3)
    princ = np.linalg.eigvalsh(eff)
    s3, s2, s1 = princ[:, 0], princ[:, 1], princ[:, 2]
    mc_term = np.tan(np.pi / 4.0 + phi / 2.0) ** 2
    cohesion = float(p.get("cohesion") or ucs / (2.0 * np.tan(np.pi / 4.0 + phi / 2.0)))
    mc_fail = s1 - s3 * mc_term - 2.0 * cohesion * np.sqrt(mc_term) > 0.0

    mb = float(p.get("hoek_brown_mb") or 1.0)
    hs = float(p.get("hoek_brown_s") or 0.004)
    ha = float(p.get("hoek_brown_a") or 0.5)
    hb_strength = s3 + ucs * np.power(np.maximum(mb * s3 / max(ucs, 1e-9) + hs, 0.0), ha)
    hb_fail = s1 > hb_strength

    p_eff = (s1 + s2 + s3) / 3.0
    j2 = ((s1 - s2) ** 2 + (s2 - s3) ** 2 + (s3 - s1) ** 2) / 6.0
    dp_m = 6.0 * np.sin(phi) / (np.sqrt(3.0) * (3.0 - np.sin(phi)))
    dp_q = 6.0 * cohesion * np.cos(phi) / (np.sqrt(3.0) * (3.0 - np.sin(phi)))
    dp_fail = np.sqrt(np.maximum(j2, 0.0)) > (dp_q + dp_m * p_eff)

    # Critical drawdown for sanding: reservoir pressure minus the critical
    # flowing bottomhole pressure. Pw_crit comes from the same vertical-well
    # shear criterion as MW_MIN: Pw = (3*SHmax - SHmin - alpha*Pp - UCS)/2.
    # Zero means no drawdown capacity before shear failure at the sandface.
    pw_crit = (3.0 * shmax - shmin - alpha * pp - ucs) / 2.0
    cdp = np.maximum(pp - pw_crit, 0.0)
    planes = cal.get("fracture_planes")
    slip = _plane_slip(tensor, planes, pp, float(p.get("fracture_mu") or 0.6), float(p.get("fracture_cohesion") or 0.0))
    if planes and slip is None:
        warnings.append("fracture planes supplied but could not be parsed")

    def arr(x: np.ndarray, nd: int = 6) -> list[float | None]:
        return [None if not np.isfinite(v) else round(float(v), nd) for v in np.asarray(x)]

    curves = {
        "DEPTH": arr(depth, 4),
        "TVD": arr(tvd, 4),
        "RHOB": arr(rhob), "DT": arr(dt), "DTS": arr(dts),
        "VP": arr(vp, 2), "VS": arr(vs, 2),
        "E": arr(el["E"], 3), "NU": arr(el["NU"], 4), "G": arr(el["G"], 3), "K": arr(el["K"], 3),
        "SV": arr(sv, 2), "PP": arr(pp, 2),
        "SHMIN": arr(shmin, 2), "SHMAX": arr(shmax, 2),
        "SIGV_EFF": arr(s1, 2), "SIGHMIN_EFF": arr(s3, 2), "SIGHMAX_EFF": arr(s2, 2),
        "MW_MIN": arr(mw_min, 3), "MW_MAX": arr(mw_max, 3), "MW": [round(mw_current, 3)] * len(depth),
        "BO": [bool(np.isfinite(a) and mw_current < a) for a in mw_min],
        "MC_FAIL": [bool(v) for v in mc_fail],
        "HB_FAIL": [bool(v) for v in hb_fail],
        "DP_FAIL": [bool(v) for v in dp_fail],
        "SAND_CDP": arr(cdp, 2),
        "FRAC_SLIP": None if slip is None else [bool(v) for v in slip],
        "SHMAX_AZI": [round(shmax_azi, 3)] * len(depth),
    }
    provenance = {
        "RHOB": "measured", "DT": "measured", "DTS": "measured" if "DTS" not in str(warnings) else "correlation",
        "PP": pp_source, "SHMIN": shmin_source, "SHMAX": shmax_source, "SHMAX_AZI": "calibrated" if "shmax_azimuth" in cal else "assumption",
        "SV": "measured", "E": "correlation", "NU": "correlation", "MW_MIN": "correlation", "MW_MAX": "correlation",
        "BO": "correlation", "MC_FAIL": "correlation", "HB_FAIL": "correlation", "DP_FAIL": "correlation",
        "SAND_CDP": "correlation", "FRAC_SLIP": "correlation" if slip is not None else "not_available",
    }
    summary = {
        "points": int(len(depth)),
        "depth_top": curves["DEPTH"][0] if len(depth) else None,
        "depth_bottom": curves["DEPTH"][-1] if len(depth) else None,
        "mw_min": round(float(np.nanmin(mw_min)), 3) if len(mw_min) else None,
        "mw_max": round(float(np.nanmax(mw_max)), 3) if len(mw_max) and np.any(np.isfinite(mw_max)) else None,
        "pp_min": round(float(np.nanmin(pp)), 2) if len(pp) else None,
        "pp_max": round(float(np.nanmax(pp)), 2) if len(pp) else None,
        "sv_min": round(float(np.nanmin(sv)), 2) if len(sv) else None,
        "sv_max": round(float(np.nanmax(sv)), 2) if len(sv) else None,
        "breakout_count": int(sum(curves["BO"])),
        "mc_fail_count": int(sum(curves["MC_FAIL"])),
        "input_hash": _hash_payload({"params": p, "calibration": cal, "semantics": sem.get("metadata", {}).get("input_hash", "")}),
    }
    return {"curves": curves, "summary": summary, "warnings": warnings, "provenance": provenance}
