"""Well router for GeoLog.

The largest route group: ingest (LAS/DLIS/LIS/CSV), formation tops, zones, DST and
RFT, completion and production data, petrophysics, curve editing, deviation,
seismic tie, image logs, zonation, snapshots and delivery bundles.

Locks, snapshots and template signatures live in backend/well_state.py because the
RBAC middleware reads the well lock on every write.
"""

from __future__ import annotations

import csv
import datetime
import io
import json
import uuid
import zipfile

import numpy as np
from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile
from sqlalchemy.orm import Session
from starlette.responses import StreamingResponse

try:
    from saturation import saturation
    from timeutils import utcnow
except ImportError:
    from backend.saturation import saturation
    from backend.timeutils import utcnow

try:
    from curve_corrections import (
        DEFAULT_DRHO_LIMIT,
        DEFAULT_WASHOUT_INCHES,
        apply_mask,
        bad_hole_mask,
        density_porosity,
        qc_summary,
    )
    from acl import MEMBER_ROLES, can_access_well, membership_role, request_role, request_subject, well_membership_role
    from audit import log_audit as _log_audit
    from database import SessionLocal, get_db
    from deps import SafeJSONResponse, require_admin, require_interpreter
    from dlis_lis_parser import parse_dlis_content, parse_lis_content
    from jobs import (
        register_handler as _register_handler,
        submit_job as _submit_job,
        update_job as _update_job,
    )
    from las_parser import LASParser
    from semantics import apply_run_semantics
    from uploads import read_upload
    from models import (
        Annotation,
        CompletionData,
        CurveAlias,
        CurveData,
        DeviationSurvey,
        DSTTest,
        FormationTop,
        LogRun,
        PetroParams,
        ProductionData,
        Project,
        RFTPoint,
        Well,
        Zone,
    )
    from well_state import (
        default_template_lock as _default_template_lock,
        delete_well_data as _delete_well_data,
        get_template_lock as _get_template_lock,
        get_well_lock as _get_well_lock,
        load_snapshots as _load_snapshots,
        mutate_snapshots as _mutate_snapshots,
        set_template_lock as _set_template_lock,
        set_well_lock as _set_well_lock,
        snapshot_template_signature as _snapshot_template_signature,
    )
    from validation import (
        optional_float,
        optional_str,
        pick_typed,
        require_float,
        require_int,
        require_str,
    )
except ImportError:
    from backend.curve_corrections import (
        DEFAULT_DRHO_LIMIT,
        DEFAULT_WASHOUT_INCHES,
        apply_mask,
        bad_hole_mask,
        density_porosity,
        qc_summary,
    )
    from backend.acl import MEMBER_ROLES, can_access_well, membership_role, request_role, request_subject, well_membership_role
    from backend.audit import log_audit as _log_audit
    from backend.database import SessionLocal, get_db
    from backend.deps import SafeJSONResponse, require_admin, require_interpreter
    from backend.dlis_lis_parser import parse_dlis_content, parse_lis_content
    from backend.jobs import (
        register_handler as _register_handler,
        submit_job as _submit_job,
        update_job as _update_job,
    )
    from backend.las_parser import LASParser
    from backend.semantics import apply_run_semantics
    from backend.uploads import read_upload
    from backend.models import (
        WellMember,
        Annotation,
        CompletionData,
        CurveAlias,
        CurveData,
        DeviationSurvey,
        DSTTest,
        FormationTop,
        LogRun,
        PetroParams,
        ProductionData,
        Project,
        RFTPoint,
        Well,
        Zone,
    )
    from backend.well_state import (
        default_template_lock as _default_template_lock,
        delete_well_data as _delete_well_data,
        get_template_lock as _get_template_lock,
        get_well_lock as _get_well_lock,
        load_snapshots as _load_snapshots,
        mutate_snapshots as _mutate_snapshots,
        set_template_lock as _set_template_lock,
        set_well_lock as _set_well_lock,
        snapshot_template_signature as _snapshot_template_signature,
    )
    from backend.validation import (
        optional_float,
        optional_str,
        pick_typed,
        require_float,
        require_int,
        require_str,
    )

COMPLETION_COMPONENT_TYPES = [
    "casing", "liner", "tubing", "packer", "perforation", "screen",
    "cement", "plug", "christmas_tree", "other",
]


# NumPy 2 removed np.trapz; 1.x has only trapz. Use whichever exists.
_trapezoid = getattr(np, "trapezoid", None) or getattr(np, "trapz")



try:
    from routers.wells import (
        _to_float_or_none, _extract_las_coordinates, _build_petro_summary,
        _semantic_curves, _first_curve, _aligned, _safe_float,
        _persist_non_las_runs, _parse_iso_date, _fit_exponential_decline,
        _fit_hyperbolic_decline, _compute_eur, _hilbert_transform,
        _require_well_admin, _trapezoid,
    )
except ImportError:
    from backend.routers.wells import (
        _to_float_or_none, _extract_las_coordinates, _build_petro_summary,
        _semantic_curves, _first_curve, _aligned, _safe_float,
        _persist_non_las_runs, _parse_iso_date, _fit_exponential_decline,
        _fit_hyperbolic_decline, _compute_eur, _hilbert_transform,
        _require_well_admin, _trapezoid,
    )




try:
    from routers.wells import (
        _to_float_or_none, _extract_las_coordinates, _build_petro_summary,
        _semantic_curves, _first_curve, _aligned, _safe_float,
        _persist_non_las_runs, _parse_iso_date, _fit_exponential_decline,
        _fit_hyperbolic_decline, _compute_eur, _hilbert_transform,
        _require_well_admin, _trapezoid,
    )
except ImportError:
    from backend.routers.wells import (
        _to_float_or_none, _extract_las_coordinates, _build_petro_summary,
        _semantic_curves, _first_curve, _aligned, _safe_float,
        _persist_non_las_runs, _parse_iso_date, _fit_exponential_decline,
        _fit_hyperbolic_decline, _compute_eur, _hilbert_transform,
        _require_well_admin, _trapezoid,
    )

router = APIRouter(prefix="/api/wells", tags=["wells"])


def _compute_synthetic_seismogram(wid: int, data: dict, db: Session):
    """Generate a synthetic trace on a uniform TWT grid from DT and RHOB."""
    lr_id = data.get("log_run_id")
    lr = db.query(LogRun).filter(LogRun.id == lr_id).first() if lr_id else          db.query(LogRun).filter(LogRun.well_id == wid).order_by(LogRun.num_points.desc()).first()
    if not lr:
        raise HTTPException(404, "No log run")
    well = db.query(Well).filter(Well.id == wid).first()
    if not well:
        raise HTTPException(404, "Well not found")

    dt_cd = db.query(CurveData).filter(CurveData.log_run_id == lr.id, CurveData.mnemonic.in_(["DT", "DTC", "DTCO"])).first()
    rhob_cd = db.query(CurveData).filter(CurveData.log_run_id == lr.id, CurveData.mnemonic.in_(["RHOB", "RHOZ", "DEN"])).first()
    dept_cd = db.query(CurveData).filter(CurveData.log_run_id == lr.id, CurveData.mnemonic.in_(["DEPT", "DEPTH"])).first()
    if not dt_cd or not rhob_cd:
        raise HTTPException(400, "Need DT and RHOB curves for synthetic seismogram")

    dt = np.frombuffer(dt_cd.data_binary, dtype=np.float64).copy()
    rhob = np.frombuffer(rhob_cd.data_binary, dtype=np.float64).copy()
    dept = np.frombuffer(dept_cd.data_binary, dtype=np.float64).copy() if dept_cd else np.arange(len(dt)) * 0.5
    try:
        try:
            from synthetic import compute_synthetic_seismogram as _synth
        except ImportError:
            from backend.synthetic import compute_synthetic_seismogram as _synth
        return _synth(
            dt,
            rhob,
            dept,
            dt_unit=dt_cd.unit or "US/F",
            depth_unit=well.depth_unit or "FT",
            wavelet_freq=float(data.get("wavelet_freq", data.get("frequency", 30))),
            polarity=str(data.get("polarity", "normal")),
            phase=int(float(data.get("phase", 0))),
            max_points=2000,
        )
    except ValueError as exc:
        raise HTTPException(400, str(exc))

@router.post("/{wid}/rw-estimation")
def estimate_rw(wid: int, data: dict, db: Session = Depends(get_db)):
    """Estimate formation water resistivity (Rw) using SP, Ro, and Hingle workflows."""
    well = db.query(Well).filter(Well.id == wid).first()
    if not well:
        raise HTTPException(404, "Well not found")

    method = str(data.get("method", "all")).strip().lower()
    if method not in {"sp", "ro", "hingle", "all"}:
        raise HTTPException(400, "method must be one of: sp, ro, hingle, all")

    pp = db.query(PetroParams).filter(PetroParams.well_id == wid).first()
    a_val = float(data.get("a", pp.a if pp and pp.a is not None else 1.0))
    m_default = float(pp.m) if pp and pp.m is not None else 2.0

    results = {
        "method_requested": method,
        "inputs": {},
        "methods": {},
        "catalog": {
            "fresh_water_ohm_m": [0.5, 1.0],
            "saline_water_ohm_m": [0.01, 0.1],
            "typical_gulf_coast_ohm_m": [0.02, 0.05],
            "typical_north_sea_ohm_m": [0.03, 0.08],
        },
    }

    rw_candidates = []
    weights = []

    if method in {"sp", "all"}:
        r = {"rw": None, "rw_77f": None, "confidence": 0.0, "notes": []}
        try:
            rmf = float(data.get("rmf"))
            ssp = float(data.get("ssp"))
            t_val = float(data.get("temperature"))
            t_unit = str(data.get("temperature_unit", "F")).strip().upper()
            if t_unit not in {"F", "C"}:
                raise ValueError("temperature_unit must be F or C")
            t_f = t_val if t_unit == "F" else (t_val * 9.0 / 5.0 + 32.0)
            if rmf <= 0:
                raise ValueError("Rmf must be > 0")
            if t_f <= -459.67:
                raise ValueError("Temperature below absolute zero")

            k = 61.0 + 0.133 * t_f
            denom = k * t_f
            if denom == 0:
                raise ValueError("Invalid temperature produces zero denominator")

            rw = rmf * (10.0 ** (-ssp / denom))
            rw_77 = rw * ((t_f + 6.77) / (77.0 + 6.77))

            r.update({
                "rw": float(rw),
                "rw_77f": float(rw_77),
                "k": float(k),
                "temperature_f": float(t_f),
                "formula": "Rw = Rmf * 10^(-SSP/(K*T)), K=61+0.133*T(F)",
                "confidence": 0.75,
            })
            rw_candidates.append(float(rw_77))
            weights.append(0.75)
            results["inputs"].update({"rmf": rmf, "ssp": ssp, "temperature": t_val, "temperature_unit": t_unit})
        except Exception as e:
            r["notes"].append("calculation failed")
        results["methods"]["sp"] = r

    if method in {"ro", "all"}:
        r = {"rw": None, "a": a_val, "confidence": 0.0, "notes": []}
        try:
            rt_clean = float(data.get("rt_clean"))
            phi_clean = float(data.get("phi_clean"))
            m_val = float(data.get("m", m_default))
            if rt_clean <= 0:
                raise ValueError("Rt_clean must be > 0")
            if phi_clean <= 0 or phi_clean > 1.0:
                raise ValueError("phi_clean must be in (0,1]")
            rw = rt_clean * (phi_clean ** m_val)
            r.update({
                "rw": float(rw),
                "m": float(m_val),
                "formula": "Rw = Rt_clean * phi_clean^m",
                "confidence": 0.80,
            })
            rw_candidates.append(float(rw))
            weights.append(0.80)
            results["inputs"].update({"rt_clean": rt_clean, "phi_clean": phi_clean, "m": m_val})
        except Exception as e:
            r["notes"].append("calculation failed")
        results["methods"]["ro"] = r

    if method in {"hingle", "all"}:
        r = {"rw": None, "r2": None, "a": a_val, "confidence": 0.0, "notes": []}
        try:
            rt_curve = str(data.get("rt_curve", "RT")).upper()
            phi_curve = str(data.get("phi_curve", "NPHI")).upper()
            lr = db.query(LogRun).filter(LogRun.well_id == wid).order_by(LogRun.id.desc()).first()
            if not lr:
                raise ValueError("No log run found")
            rt_cd = db.query(CurveData).filter(CurveData.log_run_id == lr.id, CurveData.mnemonic == rt_curve).first()
            phi_cd = db.query(CurveData).filter(CurveData.log_run_id == lr.id, CurveData.mnemonic == phi_curve).first()
            if not rt_cd or not phi_cd:
                raise ValueError("Required curves not found for Hingle")

            rt = np.frombuffer(rt_cd.data_binary, dtype=np.float64).copy()
            phi = np.frombuffer(phi_cd.data_binary, dtype=np.float64).copy()
            npts = min(len(rt), len(phi))
            rt = rt[:npts]
            phi = phi[:npts]
            with np.errstate(divide="ignore", invalid="ignore"):
                inv_rt = np.where(rt > 0, 1.0 / rt, np.nan)
            valid = (~np.isnan(inv_rt)) & (~np.isnan(phi)) & np.isfinite(inv_rt) & np.isfinite(phi) & (phi >= 0) & (phi <= 1.0)
            if np.sum(valid) < 3:
                raise ValueError("Not enough valid points for Hingle fit")

            x = phi[valid]
            y = inv_rt[valid]
            slope, intercept = np.polyfit(x, y, 1)
            yhat = slope * x + intercept
            ss_res = float(np.sum((y - yhat) ** 2))
            ss_tot = float(np.sum((y - np.mean(y)) ** 2))
            r2 = 1.0 - (ss_res / ss_tot) if ss_tot > 0 else 0.0

            rwa_intercept = float(intercept)
            rw_est = (rwa_intercept / a_val) if (a_val > 0 and rwa_intercept > 0) else None
            conf = max(0.0, min(1.0, r2)) * (1.0 if np.sum(valid) >= 50 else max(0.4, np.sum(valid) / 50.0))

            sample_step = max(1, len(x) // 400)
            x_s = x[::sample_step]
            y_s = y[::sample_step]
            r.update({
                "rw": float(rw_est) if rw_est is not None else None,
                "intercept_rwa": float(rwa_intercept),
                "slope": float(slope),
                "r2": round(float(r2), 6),
                "points": int(np.sum(valid)),
                "formula": "Linear fit on Hingle axes: (1/Rt) vs phi; intercept(phi=0)=Rw*a",
                "confidence": float(conf),
                "crossplot": {
                    "x_phi": [round(float(v), 6) for v in x_s],
                    "y_inv_rt": [round(float(v), 6) for v in y_s],
                },
            })
            if rw_est is not None:
                rw_candidates.append(float(rw_est))
                weights.append(max(0.25, float(conf)))
            results["inputs"].update({"rt_curve": rt_curve, "phi_curve": phi_curve})
        except Exception as e:
            r["notes"].append("calculation failed")
        results["methods"]["hingle"] = r

    if rw_candidates:
        wsum = sum(weights) if sum(weights) > 0 else float(len(rw_candidates))
        recommended = float(sum(v * w for v, w in zip(rw_candidates, weights)) / wsum)
        confidence = min(1.0, max(weights) * (0.6 + 0.4 * min(1.0, len(rw_candidates) / 3.0)))
    else:
        recommended = None
        confidence = 0.0

    results["recommended_rw"] = recommended
    results["confidence_score"] = round(confidence * 100.0, 1)
    return results


@router.post("/{wid}/sensitivity")
def sensitivity_analysis(wid: int, data: dict, db: Session = Depends(get_db)):
    """Monte Carlo uncertainty for net pay with P10/P50/P90 + driver ranking."""
    well = db.query(Well).filter(Well.id == wid).first()
    if not well:
        raise HTTPException(404, "Well not found")
    lr_id = data.get("log_run_id")
    lr = db.query(LogRun).filter(LogRun.id == lr_id).first() if lr_id else db.query(LogRun).filter(LogRun.well_id == wid).order_by(LogRun.num_points.desc()).first()
    if not lr:
        raise HTTPException(404, "No log run")

    rt_cd = db.query(CurveData).filter(CurveData.log_run_id == lr.id, CurveData.mnemonic.in_(["RT", "RESD", "RILD", "ILD"])).first()
    nphi_cd = db.query(CurveData).filter(CurveData.log_run_id == lr.id, CurveData.mnemonic.in_(["NPHI", "NPHI_LS"])).first()
    gr_cd = db.query(CurveData).filter(CurveData.log_run_id == lr.id, CurveData.mnemonic.in_(["GR", "SGR", "CGR"])).first()
    if not rt_cd or not nphi_cd:
        raise HTTPException(400, "Need RT and NPHI curves")

    rt = np.frombuffer(rt_cd.data_binary, dtype=np.float64).copy()
    nphi = np.frombuffer(nphi_cd.data_binary, dtype=np.float64).copy()
    gr = np.frombuffer(gr_cd.data_binary, dtype=np.float64).copy() if gr_cd else np.zeros_like(rt)

    base_a = max(float(data.get("a", 1.0)), 1e-6)
    base_m = max(float(data.get("m", 2.0)), 1e-6)
    base_n = max(float(data.get("n", 2.0)), 1e-6)
    base_rw = max(float(data.get("rw", 0.1)), 1e-6)
    base_rsh = max(float(data.get("rsh", 4.0)), 1e-6)
    base_vsh_cut = float(data.get("vsh_cutoff", 0.35))
    base_phie_cut = float(data.get("phie_cutoff", 0.10))
    base_sw_cut = float(data.get("sw_cutoff", 0.60))

    n_iter = max(50, min(int(data.get("iterations", 500)), 5000))
    pct_common = max(0.0, min(float(data.get("variation_pct", 30)) / 100.0, 0.95))

    rw_pct = max(0.0, min(float(data.get("rw_variation_pct", pct_common * 100.0)) / 100.0, 0.95))
    rsh_pct = max(0.0, min(float(data.get("rsh_variation_pct", pct_common * 100.0)) / 100.0, 0.95))
    m_pct = max(0.0, min(float(data.get("m_variation_pct", pct_common * 100.0)) / 100.0, 0.95))
    n_pct = max(0.0, min(float(data.get("n_variation_pct", pct_common * 100.0)) / 100.0, 0.95))
    vsh_cut_pct = max(0.0, min(float(data.get("vsh_cutoff_variation_pct", pct_common * 100.0)) / 100.0, 0.95))
    phie_cut_pct = max(0.0, min(float(data.get("phie_cutoff_variation_pct", pct_common * 100.0)) / 100.0, 0.95))
    sw_cut_pct = max(0.0, min(float(data.get("sw_cutoff_variation_pct", pct_common * 100.0)) / 100.0, 0.95))

    model = data.get("saturation_model", "archie")
    seed = data.get("seed")
    start_depth = data.get("start_depth")
    stop_depth = data.get("stop_depth")

    gr_valid = gr[~np.isnan(gr) & (gr > 0)]
    gr_min = float(np.min(gr_valid)) if len(gr_valid) else 0.0
    gr_max = float(np.max(gr_valid)) if len(gr_valid) else 150.0
    if gr_max == gr_min:
        gr_max = gr_min + 1.0

    step = float(lr.step) if lr.step else 0.5
    if step == 0:
        step = 0.5

    depth_cd = db.query(CurveData).filter(CurveData.log_run_id == lr.id, CurveData.mnemonic.in_(["DEPT", "DEPTH"])).first()
    depth_arr = np.frombuffer(depth_cd.data_binary, dtype=np.float64).copy() if depth_cd else None
    depth_mask = np.ones(len(rt), dtype=bool)
    if depth_arr is not None and (start_depth is not None or stop_depth is not None):
        if start_depth is not None:
            depth_mask &= (depth_arr >= float(start_depth))
        if stop_depth is not None:
            depth_mask &= (depth_arr <= float(stop_depth))

    vsh = np.clip((gr - gr_min) / (gr_max - gr_min), 0.0, 1.0)
    phi_base = np.maximum(0.0, nphi * (1.0 - vsh))
    valid = depth_mask & np.isfinite(rt) & np.isfinite(phi_base) & (rt > 0) & (phi_base >= 0.01)

    rng = np.random.default_rng(seed if seed is not None else None)

    def _sample(base: float, pct: float, lo: float, hi: float) -> float:
        if pct <= 0:
            return float(np.clip(base, lo, hi))
        return float(np.clip(base * (1.0 + rng.uniform(-pct, pct)), lo, hi))

    param_track = {
        "rw": np.zeros(n_iter, dtype=np.float64),
        "rsh": np.zeros(n_iter, dtype=np.float64),
        "m": np.zeros(n_iter, dtype=np.float64),
        "n": np.zeros(n_iter, dtype=np.float64),
        "vsh_cutoff": np.zeros(n_iter, dtype=np.float64),
        "phie_cutoff": np.zeros(n_iter, dtype=np.float64),
        "sw_cutoff": np.zeros(n_iter, dtype=np.float64),
    }
    net_pays = np.zeros(n_iter, dtype=np.float64)

    for i in range(n_iter):
        a_v = base_a
        m_v = _sample(base_m, m_pct, 0.2, 8.0)
        n_v = _sample(base_n, n_pct, 0.2, 8.0)
        rw_v = _sample(base_rw, rw_pct, 1e-6, 5.0)
        rsh_v = _sample(base_rsh, rsh_pct, 1e-6, 50.0)
        vsh_cut = _sample(base_vsh_cut, vsh_cut_pct, 0.0, 1.0)
        phie_cut = _sample(base_phie_cut, phie_cut_pct, 0.0, 0.6)
        sw_cut = _sample(base_sw_cut, sw_cut_pct, 0.0, 1.0)

        phi = phi_base
        rt_safe = np.maximum(rt, 1e-6)

        sw = saturation(
            model,
            rt_safe,
            phi,
            vsh,
            a=a_v,
            m=m_v,
            n=n_v,
            rw=rw_v,
            rsh=rsh_v,
        )

        pay_mask = valid & (vsh < vsh_cut) & (phi > phie_cut) & (sw < sw_cut)
        net_pays[i] = float(np.sum(pay_mask) * step)

        param_track["rw"][i] = rw_v
        param_track["rsh"][i] = rsh_v
        param_track["m"][i] = m_v
        param_track["n"][i] = n_v
        param_track["vsh_cutoff"][i] = vsh_cut
        param_track["phie_cutoff"][i] = phie_cut
        param_track["sw_cutoff"][i] = sw_cut

    p90 = float(np.percentile(net_pays, 10)) if len(net_pays) else 0.0  # conservative (low)
    p50 = float(np.percentile(net_pays, 50)) if len(net_pays) else 0.0
    p10 = float(np.percentile(net_pays, 90)) if len(net_pays) else 0.0  # optimistic (high)

    drivers = []
    for key, vals in param_track.items():
        if np.std(vals) <= 1e-12 or np.std(net_pays) <= 1e-12:
            corr = 0.0
        else:
            corr = float(np.corrcoef(vals, net_pays)[0, 1])
            if not np.isfinite(corr):
                corr = 0.0
        drivers.append({
            "parameter": key,
            "correlation": round(corr, 4),
            "impact": round(abs(corr), 4),
        })
    drivers.sort(key=lambda x: x["impact"], reverse=True)

    bin_edges = np.histogram_bin_edges(net_pays, bins=20)
    hist_counts = np.histogram(net_pays, bins=bin_edges)[0]

    return {
        "iterations": n_iter,
        "variation_pct": round(pct_common * 100, 1),
        "variation_profile": {
            "rw": round(rw_pct * 100, 1),
            "rsh": round(rsh_pct * 100, 1),
            "m": round(m_pct * 100, 1),
            "n": round(n_pct * 100, 1),
            "vsh_cutoff": round(vsh_cut_pct * 100, 1),
            "phie_cutoff": round(phie_cut_pct * 100, 1),
            "sw_cutoff": round(sw_cut_pct * 100, 1),
        },
        "p10_net_pay": round(p10, 2),
        "p50_net_pay": round(p50, 2),
        "p90_net_pay": round(p90, 2),
        "mean_net_pay": round(float(np.mean(net_pays)), 2) if len(net_pays) else 0,
        "std_net_pay": round(float(np.std(net_pays)), 2) if len(net_pays) else 0,
        "histogram_bins": [round(float(x), 2) for x in bin_edges.tolist()],
        "histogram_counts": hist_counts.tolist(),
        "drivers": drivers,
    }


@router.post("/{wid}/electrofacies")
def compute_electrofacies(wid: int, data: dict, db: Session = Depends(get_db)):
    """K-means clustering on selected curves to classify rock types."""
    lr_id = data.get("log_run_id")
    n_clusters = min(int(data.get("n_clusters", 4)), 8)
    curve_names = data.get("curves", ["GR", "RHOB", "NPHI", "RT"])

    lr = db.query(LogRun).filter(LogRun.id == lr_id).first() if lr_id else db.query(LogRun).filter(LogRun.well_id == wid).order_by(LogRun.id.desc()).first()
    if not lr:
        raise HTTPException(404, "No log run found")

    # Load curves
    curves_data = {}
    dept = None
    for cn in curve_names:
        cd = db.query(CurveData).filter(CurveData.log_run_id == lr.id, CurveData.mnemonic == cn).first()
        if cd:
            curves_data[cn] = np.frombuffer(cd.data_binary, dtype=np.float64).copy()
    dept_cd = db.query(CurveData).filter(CurveData.log_run_id == lr.id, CurveData.mnemonic.in_(["DEPT", "DEPTH"])).first()
    if dept_cd:
        dept = np.frombuffer(dept_cd.data_binary, dtype=np.float64).copy()

    if len(curves_data) < 2 or dept is None:
        raise HTTPException(400, "Need at least 2 curves and depth for clustering")

    # Build feature matrix (filter valid rows)
    n = len(dept)
    keys = list(curves_data.keys())
    valid_mask = np.ones(n, dtype=bool)
    for k in keys:
        arr = curves_data[k]
        valid_mask &= ~np.isnan(arr) & (arr != -999.25)

    # Normalize RT to log scale
    X = np.column_stack([np.log10(curves_data[k]) if k in ("RT", "RESD", "ILD") else curves_data[k] for k in keys])
    X = X[valid_mask]

    if len(X) < n_clusters * 10:
        raise HTTPException(400, f"Not enough valid data ({len(X)} pts) for {n_clusters} clusters")

    # Z-score normalize
    means = X.mean(axis=0)
    stds = X.std(axis=0)
    stds[stds == 0] = 1
    X_norm = (X - means) / stds

    # K-means (simple implementation)
    # Use random seed for non-deterministic clustering (pass seed param for reproducibility if needed)
    centroids = X_norm[np.random.choice(len(X_norm), n_clusters, replace=False)]
    for _ in range(50):
        dists = np.sqrt(((X_norm[:, None] - centroids[None]) ** 2).sum(axis=2))
        labels = dists.argmin(axis=1)
        new_centroids = np.array([X_norm[labels == c].mean(axis=0) if (labels == c).any() else centroids[c] for c in range(n_clusters)])
        if np.allclose(centroids, new_centroids, atol=1e-4):
            break
        centroids = new_centroids

    # Denormalize centroids
    centroids_raw = centroids * stds + means
    facies_names = [f"Facies_{i+1}" for i in range(n_clusters)]

    # Build result: per-point labels for valid data
    full_labels = np.full(n, -1, dtype=int)
    full_labels[valid_mask] = labels

    # Summary per facies
    summary = []
    for c in range(n_clusters):
        mask = labels == c
        count = int(mask.sum())
        pct = round(count / len(labels) * 100, 1) if len(labels) else 0
        center = {}
        for j, k in enumerate(keys):
            raw_val = centroids_raw[c][j]
            if k in ("RT", "RESD", "ILD"):
                raw_val = 10 ** raw_val
            center[k] = round(float(raw_val), 4)
        summary.append({"facies": facies_names[c], "count": count, "pct": pct, "centroid": center})

    return {
        "facies_labels": full_labels.tolist(),
        "depth": dept.tolist(),
        "n_clusters": n_clusters,
        "curves_used": keys,
        "summary": summary,
    }


@router.post("/{wid}/probability-plot")
def probability_plot(wid: int, data: dict, db: Session = Depends(get_db)):
    """Generate cumulative frequency arrays for probability plotting."""
    well = db.query(Well).filter(Well.id == wid).first()
    if not well:
        raise HTTPException(404, "Well not found")

    lr = db.query(LogRun).filter(LogRun.well_id == wid).order_by(LogRun.id.desc()).first()
    if not lr:
        raise HTTPException(404, "No log run")

    mnemonic = data.get("curve", "RT")
    n_bins = max(5, int(data.get("n_bins", 20)))
    start_depth = data.get("start_depth")
    stop_depth = data.get("stop_depth")

    cd = db.query(CurveData).filter(CurveData.log_run_id == lr.id, CurveData.mnemonic == mnemonic).first()
    depth_cd = db.query(CurveData).filter(CurveData.log_run_id == lr.id, CurveData.mnemonic.in_(["DEPT", "DEPTH"])).first()
    if not cd:
        raise HTTPException(404, f"Curve {mnemonic} not found")

    arr = np.frombuffer(cd.data_binary, dtype=np.float64).copy()
    # Apply depth filter if provided
    if depth_cd and (start_depth is not None or stop_depth is not None):
        depth_arr = np.frombuffer(depth_cd.data_binary, dtype=np.float64)
        mask = np.ones(len(arr), dtype=bool)
        if start_depth is not None:
            mask &= (depth_arr >= float(start_depth))
        if stop_depth is not None:
            mask &= (depth_arr <= float(stop_depth))
        arr = arr[mask]
    valid = arr[~np.isnan(arr)]
    valid = valid[valid > 0]
    if len(valid) == 0:
        return {
            "curve": mnemonic,
            "n": 0,
            "sorted_values": [],
            "percentiles": [],
            "p10": None,
            "p50": None,
            "p90": None,
            "mean": None,
            "std": None,
            "skewness": None,
        }

    sorted_vals = np.sort(valid)

    # Return binned/sampled cumulative values using requested bin count
    q = np.linspace(1.0, 99.0, n_bins)
    sampled_vals = np.percentile(sorted_vals, q)

    mean_v = float(np.mean(valid))
    std_v = float(np.std(valid))
    if std_v > 0:
        skew = float(np.mean(((valid - mean_v) / std_v) ** 3))
    else:
        skew = 0.0

    return {
        "curve": mnemonic,
        "n": int(len(valid)),
        "sorted_values": [round(float(v), 3) for v in sampled_vals],
        "percentiles": [round(float(p), 3) for p in q],
        "p10": round(float(np.percentile(valid, 10)), 3),
        "p50": round(float(np.percentile(valid, 50)), 3),
        "p90": round(float(np.percentile(valid, 90)), 3),
        "mean": round(mean_v, 3),
        "std": round(std_v, 3),
        "skewness": round(skew, 3),
    }


@router.post("/{wid}/moveable-oil")
def moveable_oil_index(wid: int, data: dict, db: Session = Depends(get_db)):
    """Compute apparent water resistivity (Rwa), flushed-zone Rwa, and moveable oil index."""
    well = db.query(Well).filter(Well.id == wid).first()
    if not well:
        raise HTTPException(404, "Well not found")

    lr = db.query(LogRun).filter(LogRun.well_id == wid).order_by(LogRun.id.desc()).first()
    if not lr:
        raise HTTPException(404, "No log run")

    rt_curve = data.get("rt_curve", "RT")
    phie_curve = data.get("phie_curve", "PHIE")

    rt_cd = db.query(CurveData).filter(CurveData.log_run_id == lr.id, CurveData.mnemonic == rt_curve).first()
    # RXO fallback: try RXO → RS → RD → RILD → RILM
    rxo_cd = None
    for rxo_name in ["RXO", "RS", "RD", "RILD", "RILM", "RMED"]:
        rxo_cd = db.query(CurveData).filter(CurveData.log_run_id == lr.id, CurveData.mnemonic == rxo_name).first()
        if rxo_cd and rxo_cd != rt_cd:
            break
    phie_cd = db.query(CurveData).filter(CurveData.log_run_id == lr.id, CurveData.mnemonic == phie_curve).first()
    # PHIE fallback: compute from RHOB if not available
    if not phie_cd:
        rhob_cd = db.query(CurveData).filter(CurveData.log_run_id == lr.id, CurveData.mnemonic == "RHOB").first()
        if rhob_cd:
            rhob_arr = np.frombuffer(rhob_cd.data_binary, dtype=np.float64).copy()
            phie_arr = density_porosity(rhob_arr, lo=0.0, hi=1.0)
            phie_arr[rhob_arr <= 0] = np.nan
            phie_cd = rhob_cd  # reuse for length reference
            phie_computed = True
        else:
            phie_computed = False
    else:
        phie_computed = False
    depth_cd = db.query(CurveData).filter(CurveData.log_run_id == lr.id, CurveData.mnemonic.in_(["DEPT", "DEPTH"])).first()
    if not rt_cd or not rxo_cd or not depth_cd:
        raise HTTPException(404, f"Required curves not found (need RT + at least one shallow resistivity + DEPTH). Available: {[c.mnemonic for c in db.query(CurveData).filter(CurveData.log_run_id == lr.id).all()]}")

    rt = np.frombuffer(rt_cd.data_binary, dtype=np.float64).copy()
    rxo = np.frombuffer(rxo_cd.data_binary, dtype=np.float64).copy()
    if phie_computed:
        phie = phie_arr
    else:
        phie = np.frombuffer(phie_cd.data_binary, dtype=np.float64).copy()
    depth = np.frombuffer(depth_cd.data_binary, dtype=np.float64).copy()

    pp = db.query(PetroParams).filter(PetroParams.well_id == wid).first()
    m = float(pp.m) if pp and pp.m is not None else 2.0

    phie_pow = np.power(np.clip(phie, 1e-6, 1.0), m)
    rwa = rt * phie_pow
    rxo_wa = rxo * phie_pow

    with np.errstate(divide="ignore", invalid="ignore"):
        moi = np.where((rwa > 0) & ~np.isnan(rwa) & ~np.isnan(rxo_wa), rxo_wa / rwa, np.nan)

    valid = moi[~np.isnan(moi)]
    step = max(1, len(depth) // 500)
    idx = list(range(0, len(depth), step))

    return {
        "depths": [round(float(depth[i]), 3) for i in idx],
        "rwa": [round(float(rwa[i]), 3) if not np.isnan(rwa[i]) else None for i in idx],
        "rxo_wa": [round(float(rxo_wa[i]), 3) if not np.isnan(rxo_wa[i]) else None for i in idx],
        "moi": [round(float(moi[i]), 3) if not np.isnan(moi[i]) else None for i in idx],
        "stats": {
            "min": round(float(np.min(valid)), 3) if len(valid) else None,
            "max": round(float(np.max(valid)), 3) if len(valid) else None,
            "mean": round(float(np.mean(valid)), 3) if len(valid) else None,
            "median": round(float(np.median(valid)), 3) if len(valid) else None,
        },
    }


@router.post("/{wid}/dip-plot")
def dip_plot(wid: int, data: dict, db: Session = Depends(get_db)):
    """Generate tadpole plot arrays from stored deviation survey."""
    well = db.query(Well).filter(Well.id == wid).first()
    if not well:
        raise HTTPException(404, "Well not found")

    points = db.query(DeviationSurvey).filter(DeviationSurvey.well_id == wid).order_by(DeviationSurvey.md).all()
    if not points:
        # Fallback: generate vertical well from log run depth data
        lr = db.query(LogRun).filter(LogRun.well_id == wid).order_by(LogRun.id.desc()).first()
        if not lr:
            raise HTTPException(404, "No deviation survey or log run data")
        depth_cd = db.query(CurveData).filter(CurveData.log_run_id == lr.id, CurveData.mnemonic.in_(["DEPT", "DEPTH"])).first()
        if not depth_cd:
            depth_cd = db.query(CurveData).filter(CurveData.log_run_id == lr.id).order_by(CurveData.id.asc()).first()
        if not depth_cd or not depth_cd.data_binary:
            raise HTTPException(404, "No deviation survey and no depth data available")
        depths = np.frombuffer(depth_cd.data_binary, dtype=np.float64).copy()
        step = max(1, len(depths) // 200)
        idx = list(range(0, len(depths), step))
        return SafeJSONResponse({
            "md": [float(depths[i]) for i in idx],
            "inc": [0.0] * len(idx),
            "azi": [0.0] * len(idx),
            "dip": [0.0] * len(idx),
            "dip_direction": [0.0] * len(idx),
            "tvd": [float(depths[i]) for i in idx],
            "north": [0.0] * len(idx),
            "east": [0.0] * len(idx),
            "note": "Vertical well assumed (no deviation survey loaded)"
        })

    dip_type = str(data.get("dip_type", "structural")).lower()
    if dip_type not in ("structural", "apparent"):
        dip_type = "structural"

    md = np.array([float(p.md) for p in points], dtype=np.float64)
    inc = np.array([float(p.inc) for p in points], dtype=np.float64)
    azi = np.array([float(p.azi) for p in points], dtype=np.float64)
    tvd = np.array([float(p.tvd) if p.tvd is not None else np.nan for p in points], dtype=np.float64)
    north = np.array([float(p.northing) if p.northing is not None else np.nan for p in points], dtype=np.float64)
    east = np.array([float(p.easting) if p.easting is not None else np.nan for p in points], dtype=np.float64)

    # Structural dip approximation from consecutive survey points
    apparent_dip = np.full_like(md, np.nan)
    for i in range(1, len(md)):
        if np.isnan(tvd[i]) or np.isnan(tvd[i - 1]) or np.isnan(north[i]) or np.isnan(north[i - 1]) or np.isnan(east[i]) or np.isnan(east[i - 1]):
            continue
        dtvd = abs(tvd[i] - tvd[i - 1])
        dh = np.sqrt((north[i] - north[i - 1]) ** 2 + (east[i] - east[i - 1]) ** 2)
        if dh > 1e-6:
            apparent_dip[i] = np.degrees(np.arctan(dtvd / dh))

    step = max(1, len(md) // 500)
    idx = list(range(0, len(md), step))

    notes = "Structural dip approximated from consecutive survey TVD and horizontal displacement."
    if dip_type == "apparent":
        notes = "Apparent dip view uses inclination/azimuth arrays directly with computed TVD context."

    return {
        "md": [round(float(md[i]), 3) for i in idx],
        "inc": [round(float(inc[i]), 3) for i in idx],
        "azi": [round(float(azi[i]), 3) for i in idx],
        "tvd": [round(float(tvd[i]), 3) if not np.isnan(tvd[i]) else None for i in idx],
        "apparent_dip": [round(float(apparent_dip[i]), 3) if not np.isnan(apparent_dip[i]) else None for i in idx],
        "dip_type": dip_type,
        "notes": notes,
    }


@router.post("/{wid}/buckles")
def buckles_plot(wid: int, data: dict, db: Session = Depends(get_db)):
    well = db.query(Well).filter(Well.id == wid).first()
    if not well:
        raise HTTPException(404, "Well not found")

    lr = db.query(LogRun).filter(LogRun.well_id == wid).order_by(LogRun.id.desc()).first()
    if not lr:
        raise HTTPException(404, "No log run")

    phie_curve = str(data.get("phie_curve", "NPHI")).upper()
    sw_curve = str(data.get("sw_curve", "SW")).upper()

    phie_cd = db.query(CurveData).filter(CurveData.log_run_id == lr.id, CurveData.mnemonic == phie_curve).first()
    depth_cd = db.query(CurveData).filter(CurveData.log_run_id == lr.id, CurveData.mnemonic.in_(["DEPT", "DEPTH", "MD", "TVD"])).first()
    if not phie_cd or not depth_cd:
        raise HTTPException(404, f"Required curves not found (need {phie_curve} and depth)")

    sw_cd = db.query(CurveData).filter(CurveData.log_run_id == lr.id, CurveData.mnemonic == sw_curve).first()

    phie = np.frombuffer(phie_cd.data_binary, dtype=np.float64).copy()
    depth = np.frombuffer(depth_cd.data_binary, dtype=np.float64).copy()

    if sw_cd:
        sw = np.frombuffer(sw_cd.data_binary, dtype=np.float64).copy()
    else:
        # Compute Sw via Archie if SW curve missing
        rt_cd = db.query(CurveData).filter(CurveData.log_run_id == lr.id, CurveData.mnemonic.in_(["RT", "RESD", "RILD", "ILD"])).first()
        if not rt_cd:
            raise HTTPException(404, "SW curve not found and no RT curve available for Archie")
        rt = np.frombuffer(rt_cd.data_binary, dtype=np.float64).copy()

        pp = db.query(PetroParams).filter(PetroParams.well_id == wid).first()
        a = float(pp.a) if pp and pp.a is not None else 1.0
        m = float(pp.m) if pp and pp.m is not None else 2.0
        n = float(pp.n) if pp and pp.n is not None else 2.0
        rw = float(pp.rw) if pp and pp.rw is not None else 0.1

        phi_eff = np.clip(phie, 1e-6, 1.0)
        rt_eff = np.clip(rt, 1e-6, None)
        with np.errstate(divide="ignore", invalid="ignore", over="ignore"):
            sw = np.power((a * rw) / (rt_eff * np.power(phi_eff, m)), 1.0 / max(n, 1e-6))
        sw = np.clip(sw, 0.0, 1.0)

    npts = min(len(depth), len(phie), len(sw))
    depth = depth[:npts]
    phie = phie[:npts]
    sw = sw[:npts]

    bvw = phie * sw
    valid = ~np.isnan(depth) & ~np.isnan(phie) & ~np.isnan(sw) & ~np.isnan(bvw)
    valid &= np.isfinite(phie) & np.isfinite(sw) & np.isfinite(bvw)

    if np.any(valid):
        mean_bvw = float(np.mean(bvw[valid]))
        pay_fraction = float(np.mean(bvw[valid] < 0.12))
    else:
        mean_bvw = None
        pay_fraction = 0.0

    step = max(1, len(depth) // 500)
    idx = list(range(0, len(depth), step))

    return {
        "depths": [round(float(depth[i]), 3) if not np.isnan(depth[i]) else None for i in idx],
        "bvw": [round(float(bvw[i]), 5) if not np.isnan(bvw[i]) else None for i in idx],
        "phie": [round(float(phie[i]), 5) if not np.isnan(phie[i]) else None for i in idx],
        "sw": [round(float(sw[i]), 5) if not np.isnan(sw[i]) else None for i in idx],
        "stats": {
            "mean_bvw": round(mean_bvw, 6) if mean_bvw is not None else None,
            "pay_fraction": round(pay_fraction, 6),
        },
        "cutoffs": {"tight": 0.04, "pay": 0.12},
    }


@router.post("/{wid}/hingle")
def hingle_plot(wid: int, data: dict, db: Session = Depends(get_db)):
    well = db.query(Well).filter(Well.id == wid).first()
    if not well:
        raise HTTPException(404, "Well not found")

    lr = db.query(LogRun).filter(LogRun.well_id == wid).order_by(LogRun.id.desc()).first()
    if not lr:
        raise HTTPException(404, "No log run")

    rt_curve = str(data.get("rt_curve", "RT")).upper()
    x_curve = str(data.get("curve", data.get("x_curve", "RHOB"))).upper()
    use_log = bool(data.get("log", False))

    rt_cd = db.query(CurveData).filter(CurveData.log_run_id == lr.id, CurveData.mnemonic == rt_curve).first()
    x_cd = db.query(CurveData).filter(CurveData.log_run_id == lr.id, CurveData.mnemonic == x_curve).first()
    depth_cd = db.query(CurveData).filter(CurveData.log_run_id == lr.id, CurveData.mnemonic.in_(["DEPT", "DEPTH"])).first()
    if not rt_cd or not x_cd or not depth_cd:
        raise HTTPException(404, "Required curves not found")

    rt = np.frombuffer(rt_cd.data_binary, dtype=np.float64).copy()
    x_raw = np.frombuffer(x_cd.data_binary, dtype=np.float64).copy()
    depth = np.frombuffer(depth_cd.data_binary, dtype=np.float64).copy()

    npts = min(len(depth), len(x_raw), len(rt))
    depth = depth[:npts]
    x_raw = x_raw[:npts]
    rt = rt[:npts]

    # Hingle plot: x-axis is the porosity-sensitive curve (RHOB, NPHI, etc.)
    # For RHOB: display as 1/RHOB (density porosity transform)
    # For NPHI: display directly
    x_label = x_curve
    if x_curve in ("RHOB", "RHOZ", "ZDEN", "RHOB_CAL"):
        with np.errstate(divide="ignore", invalid="ignore"):
            x = np.where(x_raw > 0, 1.0 / x_raw, np.nan)
        x_label = f"1/{x_curve}"
    else:
        x = x_raw
    with np.errstate(divide="ignore", invalid="ignore"):
        inv_rt = np.where(rt > 0, 1.0 / rt, np.nan)
        y = np.log(inv_rt) if use_log else inv_rt

    # Water-bearing approximation from high Sw (Sw ≈ 1) via Archie estimate
    pp = db.query(PetroParams).filter(PetroParams.well_id == wid).first()
    a = float(pp.a) if pp and pp.a is not None else 1.0
    m = float(pp.m) if pp and pp.m is not None else 2.0
    n = float(pp.n) if pp and pp.n is not None else 2.0
    rw = float(pp.rw) if pp and pp.rw is not None else 0.1

    # Estimate porosity for Sw calculation from the x-curve
    if x_curve in ("RHOB", "RHOZ", "ZDEN", "RHOB_CAL"):
        rho_ma = 2.65
        rho_f = 1.0
        phi_for_sw = density_porosity(x_raw, rho_ma, rho_f, lo=1e-6, hi=1.0)
    else:
        phi_for_sw = np.clip(x_raw, 1e-6, 1.0)
    phi_eff = np.clip(phi_for_sw, 1e-6, 1.0)
    rt_eff = np.clip(rt, 1e-6, None)
    with np.errstate(divide="ignore", invalid="ignore", over="ignore"):
        sw_est = np.power((a * rw) / (rt_eff * np.power(phi_eff, m)), 1.0 / max(n, 1e-6))
    sw_est = np.clip(sw_est, 0.0, 1.0)

    water_mask = (~np.isnan(x)) & (~np.isnan(y)) & (~np.isnan(sw_est)) & (sw_est >= 0.9)
    if np.sum(water_mask) >= 2:
        slope, intercept = np.polyfit(x[water_mask], y[water_mask], 1)
        slope = float(slope)
        intercept = float(intercept)
    else:
        slope = None
        intercept = None

    valid = (~np.isnan(x)) & (~np.isnan(y))
    step = max(1, len(depth) // 500)
    idx = list(range(0, len(depth), step))

    return {
        "x": [round(float(x[i]), 6) if not np.isnan(x[i]) else None for i in idx],
        "y": [round(float(y[i]), 6) if not np.isnan(y[i]) else None for i in idx],
        "depths": [round(float(depth[i]), 3) if not np.isnan(depth[i]) else None for i in idx],
        "rw_line": {"slope": round(slope, 8) if slope is not None else None, "intercept": round(intercept, 8) if intercept is not None else None},
        "stats": {
            "points": int(np.sum(valid)),
            "water_points": int(np.sum(water_mask)),
            "mean_x": round(float(np.nanmean(x)), 6) if np.any(valid) else None,
            "mean_y": round(float(np.nanmean(y)), 6) if np.any(valid) else None,
            "mode": f"{x_label} vs {'log(1/RT)' if use_log else '1/RT'}",
        },
    }


@router.post("/{wid}/tornado")
def tornado_analysis(wid: int, data: dict, db: Session = Depends(get_db)):
    """Tornado chart: vary each parameter ±X% and measure impact on net_pay.
    Returns sorted impact for each parameter.
    """
    lr_id = data.get("log_run_id")
    lr = db.query(LogRun).filter(LogRun.id == lr_id).first() if lr_id else \
         db.query(LogRun).filter(LogRun.well_id == wid).order_by(LogRun.num_points.desc()).first()
    if not lr:
        raise HTTPException(404, "No log run")

    rt_cd = db.query(CurveData).filter(CurveData.log_run_id == lr.id, CurveData.mnemonic.in_(["RT", "RESD", "RILD", "ILD"])).first()
    nphi_cd = db.query(CurveData).filter(CurveData.log_run_id == lr.id, CurveData.mnemonic.in_(["NPHI", "NPHI_LS"])).first()
    gr_cd = db.query(CurveData).filter(CurveData.log_run_id == lr.id, CurveData.mnemonic.in_(["GR", "SGR", "CGR"])).first()
    if not rt_cd or not nphi_cd:
        raise HTTPException(400, "Need RT and NPHI")

    rt = np.frombuffer(rt_cd.data_binary, dtype=np.float64).copy()
    nphi = np.frombuffer(nphi_cd.data_binary, dtype=np.float64).copy()
    gr = np.frombuffer(gr_cd.data_binary, dtype=np.float64).copy() if gr_cd else np.zeros_like(rt)

    # Base params
    base_params = {
        "a": float(data.get("a", 1.0)),
        "m": float(data.get("m", 2.0)),
        "n": float(data.get("n", 2.0)),
        "rw": float(data.get("rw", 0.1)),
        "vsh_cutoff": float(data.get("vsh_cutoff", 0.35)),
        "phie_cutoff": float(data.get("phie_cutoff", 0.10)),
        "sw_cutoff": float(data.get("sw_cutoff", 0.60)),
    }
    variation = float(data.get("variation_pct", 20)) / 100.0

    gr_valid = gr[~np.isnan(gr) & (gr > 0)]
    gr_min = float(np.min(gr_valid)) if len(gr_valid) else 0
    gr_max = float(np.max(gr_valid)) if len(gr_valid) else 150
    if gr_max == gr_min:
        gr_max = gr_min + 1

    def _count_net_pay(params):
        """Count net pay feet with given params."""
        pay = 0
        step = float(lr.step) if lr.step else 0.5
        for i in range(len(rt)):
            if np.isnan(rt[i]) or np.isnan(nphi[i]) or rt[i] <= 0 or nphi[i] < 0:
                continue
            igr = (gr[i] - gr_min) / (gr_max - gr_min) if gr_max > gr_min else 0
            vsh_v = max(0, min(1, igr))
            phi = max(0, nphi[i] * (1 - vsh_v))
            if phi < 0.01:
                continue
            sw_v = (params["a"] / (phi ** params["m"] * rt[i] / params["rw"])) ** (1.0 / params["n"])
            sw_v = max(0, min(1, sw_v))
            if vsh_v < params["vsh_cutoff"] and phi > params["phie_cutoff"] and sw_v < params["sw_cutoff"]:
                pay += 1
        return pay * step

    # Base net pay
    base_pay = _count_net_pay(base_params)

    # Tornado: vary each param
    tornado_items = []
    for param_name in ["a", "m", "n", "rw", "vsh_cutoff", "phie_cutoff", "sw_cutoff"]:
        low_params = base_params.copy()
        high_params = base_params.copy()
        delta = base_params[param_name] * variation
        low_params[param_name] = max(0.001, base_params[param_name] - delta)
        high_params[param_name] = base_params[param_name] + delta

        pay_low = _count_net_pay(low_params)
        pay_high = _count_net_pay(high_params)

        # Impact = range of net pay variation
        impact = abs(pay_high - pay_low)
        tornado_items.append({
            "parameter": param_name,
            "base_value": base_params[param_name],
            "low_value": round(low_params[param_name], 4),
            "high_value": round(high_params[param_name], 4),
            "pay_low": round(pay_low, 2),
            "pay_high": round(pay_high, 2),
            "base_pay": round(base_pay, 2),
            "impact": round(impact, 2),
            "swing_low": round(pay_low - base_pay, 2),
            "swing_high": round(pay_high - base_pay, 2),
        })

    # Sort by impact (most impactful first)
    tornado_items.sort(key=lambda x: x["impact"], reverse=True)

    return {
        "base_pay": round(base_pay, 2),
        "variation_pct": round(variation * 100, 1),
        "tornado": tornado_items,
    }


@router.post("/{wid}/qc-autofix")
def qc_autofix(wid: int, data: dict, db: Session = Depends(get_db)):
    """Run enhanced QC and suggest auto-fixes.
    Returns issues found + recommended fixes.
    """
    lr_id = data.get("log_run_id")
    lr = db.query(LogRun).filter(LogRun.id == lr_id).first() if lr_id else \
         db.query(LogRun).filter(LogRun.well_id == wid).order_by(LogRun.num_points.desc()).first()
    if not lr:
        raise HTTPException(404, "No log run")

    curves = db.query(CurveData).filter(CurveData.log_run_id == lr.id).all()
    dept_cd = db.query(CurveData).filter(CurveData.log_run_id == lr.id, CurveData.mnemonic.in_(["DEPT", "DEPTH"])).first()
    dept = np.frombuffer(dept_cd.data_binary, dtype=np.float64).copy() if dept_cd else None

    issues = []
    fixes = []

    for cd in curves:
        if cd.mnemonic in ("DEPT", "DEPTH"):
            continue
        arr = np.frombuffer(cd.data_binary, dtype=np.float64).copy()
        n = len(arr)
        valid = arr[~np.isnan(arr)]
        if len(valid) == 0:
            issues.append({"curve": cd.mnemonic, "type": "no_data", "severity": "critical",
                          "detail": f"{cd.mnemonic} has no valid data"})
            continue

        # Check for nulls
        null_count = int(np.sum(np.isnan(arr)))
        null_pct = null_count / n * 100
        if null_pct > 50:
            issues.append({"curve": cd.mnemonic, "type": "high_nulls", "severity": "warning",
                          "detail": f"{cd.mnemonic}: {null_pct:.0f}% null values"})
            fixes.append({"curve": cd.mnemonic, "action": "interpolate", "detail": "Linear interpolation for null gaps"})

        # Check for spikes (>5x std from local mean)
        if len(valid) > 20:
            mean = np.mean(valid)
            std = np.std(valid)
            spike_mask = np.abs(arr - mean) > 5 * std
            spike_count = int(np.sum(spike_mask & ~np.isnan(arr)))
            if spike_count > 0:
                issues.append({"curve": cd.mnemonic, "type": "spikes", "severity": "warning",
                              "detail": f"{cd.mnemonic}: {spike_count} potential spikes (>5σ)"})
                fixes.append({"curve": cd.mnemonic, "action": "despike", "window": 5,
                             "detail": "Apply median filter (window=5)"})

        # Check for constant values (stuck sensor)
        if len(valid) > 10:
            unique_ratio = len(np.unique(np.round(valid, 2))) / len(valid)
            if unique_ratio < 0.01:
                issues.append({"curve": cd.mnemonic, "type": "constant", "severity": "critical",
                              "detail": f"{cd.mnemonic}: appears stuck/constant ({len(np.unique(np.round(valid,2)))} unique values)"})

        # Check depth consistency (gaps)
        if dept is not None and len(dept) > 1:
            step = np.median(np.diff(dept))
            gaps = np.where(np.diff(dept) > step * 3)[0]
            if len(gaps) > 0:
                issues.append({"curve": cd.mnemonic, "type": "depth_gap", "severity": "info",
                              "detail": f"{len(gaps)} depth gaps > {step*3:.1f} ft detected"})

        # Check for negative values in curves that shouldn't have them
        if cd.mnemonic in ("GR", "RT", "RESD", "RHOB", "NPHI"):
            neg_count = int(np.sum(valid < 0))
            if neg_count > 0:
                issues.append({"curve": cd.mnemonic, "type": "negative", "severity": "warning",
                              "detail": f"{cd.mnemonic}: {neg_count} negative values"})
                fixes.append({"curve": cd.mnemonic, "action": "clip_negative",
                             "detail": "Clip negative values to 0"})

    # Score
    critical = sum(1 for i in issues if i["severity"] == "critical")
    warnings = sum(1 for i in issues if i["severity"] == "warning")
    score = max(0, 100 - critical * 20 - warnings * 5)
    grade = "A" if score >= 80 else "B" if score >= 60 else "C"

    return {
        "total_curves": len(curves),
        "issues": issues,
        "fixes": fixes,
        "score": score,
        "grade": grade,
        "critical": critical,
        "warnings": warnings,
    }


@router.post("/{wid}/synthetic-seismogram")
def synthetic_seismogram(wid: int, data: dict, db: Session = Depends(get_db), _role: str = Depends(require_interpreter)):
    """Generate synthetic seismogram from DT+RHOB."""
    return _compute_synthetic_seismogram(wid, data, db)


@router.post("/{wid}/synthetic-seismogram-async", status_code=202)
def synthetic_seismogram_async(wid: int, data: dict, _role: str = Depends(require_interpreter)):
    """Queue synthetic seismogram computation in background job."""
    job_id = _submit_job("synthetic-seismogram", {"wid": wid, "data": data})
    return {"job_id": job_id, "status": "queued"}


@router.post("/{wid}/electrofacies-async", status_code=202)
def electrofacies_async(wid: int, data: dict, _role: str = Depends(require_interpreter)):
    """Queue electrofacies clustering in background job."""
    job_id = _submit_job("electrofacies", {"wid": wid, "data": data})
    return {"job_id": job_id, "status": "queued"}


def _run_synthetic_seismogram_job(payload: dict, job_id: str):
    db = SessionLocal()
    try:
        _update_job(job_id, progress=10)
        return _compute_synthetic_seismogram(int(payload["wid"]), payload.get("data") or {}, db)
    finally:
        db.close()


def _run_electrofacies_job(payload: dict, job_id: str):
    db = SessionLocal()
    try:
        _update_job(job_id, progress=10)
        return compute_electrofacies(int(payload["wid"]), payload.get("data") or {}, db)
    finally:
        db.close()


_register_handler("synthetic-seismogram", _run_synthetic_seismogram_job)
_register_handler("electrofacies", _run_electrofacies_job)
