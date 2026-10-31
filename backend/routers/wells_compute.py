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
    from timeutils import utcnow
except ImportError:
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
    from saturation import saturation
    from petro_deterministic import vclay as _vclay, porosity_blend as _porosity_blend
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
    from backend.saturation import saturation
    from backend.petro_deterministic import vclay as _vclay, porosity_blend as _porosity_blend
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

router = APIRouter(prefix="/api/wells", tags=["wells"])










@router.post("/{wid}/depth-match")
def auto_depth_match(wid: int, data: dict, db: Session = Depends(get_db)):
    """Compute optimal depth shift between two runs of same curve via cross-correlation."""
    run_a_raw = data.get("run_a")
    run_b_raw = data.get("run_b")
    if run_a_raw is None or run_b_raw is None:
        raise HTTPException(400, "run_a and run_b are required")
    run_a = int(run_a_raw)
    run_b = int(run_b_raw)
    mnemonic = data.get("mnemonic", "GR")
    max_shift = float(data.get("max_shift", 50))

    cd_a = db.query(CurveData).filter(CurveData.log_run_id == run_a, CurveData.mnemonic == mnemonic).first()
    cd_b = db.query(CurveData).filter(CurveData.log_run_id == run_b, CurveData.mnemonic == mnemonic).first()
    if not cd_a or not cd_b:
        raise HTTPException(404, f"Curve {mnemonic} not found in both runs")

    dept_a_cd = db.query(CurveData).filter(CurveData.log_run_id == run_a, CurveData.mnemonic.in_(["DEPT", "DEPTH"])).first()
    dept_b_cd = db.query(CurveData).filter(CurveData.log_run_id == run_b, CurveData.mnemonic.in_(["DEPT", "DEPTH"])).first()
    if not dept_a_cd or not dept_b_cd:
        raise HTTPException(404, "Depth curve not found")

    a_vals = np.frombuffer(cd_a.data_binary, dtype=np.float64).copy()
    b_vals = np.frombuffer(cd_b.data_binary, dtype=np.float64).copy()
    a_dept = np.frombuffer(dept_a_cd.data_binary, dtype=np.float64).copy()
    b_dept = np.frombuffer(dept_b_cd.data_binary, dtype=np.float64).copy()

    # Interpolate both onto common grid
    step = float(db.query(LogRun).filter(LogRun.id == run_a).first().step or 0.5)
    d_min = max(a_dept[0], b_dept[0])
    d_max = min(a_dept[-1], b_dept[-1])
    if d_max <= d_min:
        raise HTTPException(400, "No overlapping depth range")

    common = np.arange(d_min, d_max, step)
    a_interp = np.interp(common, a_dept, a_vals)
    b_interp = np.interp(common, b_dept, b_vals)

    # Remove NaNs
    valid = ~(np.isnan(a_interp) | np.isnan(b_interp))
    a_v = a_interp[valid]
    b_v = b_interp[valid]
    if len(a_v) < 50:
        raise HTTPException(400, "Not enough overlapping valid data")

    # Cross-correlation with shifts
    max_samples = int(max_shift / step)
    best_corr = -2
    best_shift = 0
    correlations = []
    for shift in range(-max_samples, max_samples + 1):
        if shift >= 0:
            aa = a_v[shift:]
            bb = b_v[:len(aa)]
        else:
            bb = b_v[-shift:]
            aa = a_v[:len(bb)]
        if len(aa) < 30:
            continue
        corr = np.corrcoef(aa, bb)[0, 1]
        correlations.append({"shift_ft": round(shift * step, 2), "correlation": round(float(corr), 4)})
        if corr > best_corr:
            best_corr = corr
            best_shift = shift * step

    return {
        "optimal_shift_ft": round(float(best_shift), 2),
        "correlation": round(float(best_corr), 4),
        "common_depth_range": [round(float(d_min), 1), round(float(d_max), 1)],
        "step": step,
        "correlations": correlations,
    }


@router.post("/{wid}/auto-pick-tops")
def auto_pick_tops(wid: int, data: dict, db: Session = Depends(get_db), _role: str = Depends(require_interpreter)):
    """Auto-detect formation boundaries from GR or RT curve breaks."""
    curve = data.get("curve", "GR")
    threshold = float(data.get("threshold", 1.5))  # z-score threshold for boundary detection
    min_gap = float(data.get("min_gap", 20))  # minimum depth gap between picks (ft)

    lr_id = data.get("log_run_id")
    lr = db.query(LogRun).filter(LogRun.id == lr_id).first() if lr_id else db.query(LogRun).filter(LogRun.well_id == wid).order_by(LogRun.num_points.desc()).first()
    if not lr:
        raise HTTPException(404, "No log run found")

    cd = db.query(CurveData).filter(CurveData.log_run_id == lr.id, CurveData.mnemonic == curve).first()
    dept_cd = db.query(CurveData).filter(CurveData.log_run_id == lr.id, CurveData.mnemonic.in_(["DEPT", "DEPTH"])).first()
    if not cd or not dept_cd:
        raise HTTPException(404, f"Curve {curve} not found")

    values = np.frombuffer(cd.data_binary, dtype=np.float64).copy()
    depth = np.frombuffer(dept_cd.data_binary, dtype=np.float64)

    # Compute first derivative (gradient)
    grad = np.diff(values)
    valid = ~np.isnan(grad)
    grad_valid = grad[valid]
    if len(grad_valid) < 10:
        raise HTTPException(400, "Not enough valid data")

    std_g = np.std(np.abs(grad_valid))
    if std_g == 0:
        raise HTTPException(400, "Curve has no variation")

    # Find peaks in absolute gradient (curve breaks)
    picks = []
    for i in range(1, len(grad) - 1):
        if np.isnan(grad[i]):
            continue
        z = abs(grad[i]) / (std_g if std_g > 0 else 1)
        if z > threshold:
            d = float(depth[i])
            if not picks or (d - picks[-1]["depth"]) > min_gap:
                picks.append({"depth": round(d, 1), "z_score": round(float(z), 2), "curve": curve})

    # Assign tentative formation names
    for i, p in enumerate(picks):
        p["formation_name"] = f"Auto_Top_{i + 1}"
        p["color"] = ["#e74c3c", "#3498db", "#2ecc71", "#f39c12", "#9b59b6", "#1abc9c", "#e67e22", "#34495e"][i % 8]

    return {"picks": picks, "threshold": threshold, "min_gap": min_gap, "curve": curve}


@router.post("/{wid}/save-picks")
def save_picks(wid: int, data: dict, db: Session = Depends(get_db)):
    """Save auto-picked or edited tops to database."""
    picks = data.get("picks", [])
    if not isinstance(picks, list):
        raise HTTPException(400, "picks must be a list")
    count = 0
    for i, p in enumerate(picks):
        if not isinstance(p, dict):
            raise HTTPException(400, f"picks[{i}] must be an object")
        name = optional_str(p, "formation_name")
        depth = optional_float(p, "depth", 0)
        if not name or depth <= 0:
            continue
        db.add(FormationTop(
            well_id=wid, formation_name=name, depth=depth,
            color=optional_str(p, "color", "#888888"),
            lithology=optional_str(p, "lithology"),
        ))
        count += 1
    db.commit()
    return {"status": "ok", "saved": count}


@router.post("/{wid}/strat-normalize")
def strat_normalize(wid: int, data: dict, db: Session = Depends(get_db)):
    """Normalize depths relative to a reference formation top for structural cross-sections."""
    ref_formation = data.get("reference_formation", "")
    lr_id = data.get("log_run_id")
    mnemonic = data.get("curve", "GR")

    if not ref_formation:
        raise HTTPException(400, "Specify reference_formation")

    # Find the reference top for this well
    top = db.query(FormationTop).filter(
        FormationTop.well_id == wid, FormationTop.formation_name == ref_formation
    ).first()
    if not top:
        raise HTTPException(404, f"Formation '{ref_formation}' not found in this well")

    ref_depth = top.depth

    # Get curve data
    lr = db.query(LogRun).filter(LogRun.id == lr_id).first() if lr_id else db.query(LogRun).filter(LogRun.well_id == wid).order_by(LogRun.id.desc()).first()
    if not lr:
        raise HTTPException(404, "No log run")

    cd = db.query(CurveData).filter(CurveData.log_run_id == lr.id, CurveData.mnemonic == mnemonic).first()
    dept_cd = db.query(CurveData).filter(CurveData.log_run_id == lr.id, CurveData.mnemonic.in_(["DEPT", "DEPTH"])).first()
    if not cd or not dept_cd:
        raise HTTPException(404, f"Curve {mnemonic} not found")

    depth = np.frombuffer(dept_cd.data_binary, dtype=np.float64)
    values = np.frombuffer(cd.data_binary, dtype=np.float64)

    # Normalize: positive = above reference (shallower), negative = below (deeper)
    normalized_depth = ref_depth - depth

    # Subsample
    step = max(1, len(depth) // 500)
    idx = list(range(0, len(depth), step))

    return {
        "well_id": wid, "reference_formation": ref_formation, "reference_depth": ref_depth,
        "normalized_depth": [round(float(normalized_depth[i]), 1) for i in idx],
        "values": [round(float(values[i]), 3) if not np.isnan(values[i]) else None for i in idx],
        "md_range": [round(float(depth[0]), 1), round(float(depth[-1]), 1)],
    }


@router.post("/{wid}/permeability")
def compute_permeability(wid: int, data: dict, db: Session = Depends(get_db)):
    """Compute permeability (mD) via Coates, Timur, SDR, with crossplot + FZI diagnostics."""
    well = db.query(Well).filter(Well.id == wid).first()
    if not well:
        raise HTTPException(404, "Well not found")

    lr = db.query(LogRun).filter(LogRun.well_id == wid).order_by(LogRun.id.desc()).first()
    if not lr:
        raise HTTPException(404, "No log run")

    model = str(data.get("model", data.get("method", "timur"))).strip().lower()
    if model not in {"coates", "timur", "sdr", "all"}:
        raise HTTPException(400, "model must be one of: coates, timur, sdr, all")

    phie_curve = data.get("phie_curve", "PHIE")
    sw_curve = data.get("sw_curve", "SW")
    rhob_curve = data.get("rhob_curve", "RHOB")
    grain_density = float(data.get("grain_density", 2.65))
    water_cut = float(data.get("water_cut", 0.0) or 0.0)
    water_cut = max(0.0, min(1.0, water_cut))

    # Model constants (industry-typical defaults)
    coates_c = float(data.get("coates_c", 1e4))
    timur_a = float(data.get("timur_a", 0.136))
    sdr_a = float(data.get("sdr_a", 4.0))

    depth, by_name = _semantic_curves(db, lr)
    if depth.size == 0:
        raise HTTPException(404, "Depth curve not found")
    n = len(depth)
    phie = by_name.get(str(phie_curve).upper())
    sw = by_name.get(str(sw_curve).upper())

    # PHIE fallback from RHOB if needed
    if phie is None:
        rho_arr = by_name.get(str(rhob_curve).upper())
        if rho_arr is None:
            raise HTTPException(404, f"Curve {phie_curve} not found and no {rhob_curve} for fallback")
        rho_arr = _aligned(rho_arr, n)
        phie = density_porosity(rho_arr, grain_density, 1.0, lo=0.0, hi=0.6)
        phie[np.isnan(rho_arr)] = np.nan
    else:
        phie = _aligned(phie, n)

    # Sw / Swir handling
    sw = _aligned(sw, n) if sw is not None else np.full(n, np.nan)

    # User Swir takes priority. Else estimate Swir = Sw * (1 - water_cut)
    user_swir = data.get("swir")
    if user_swir is not None and str(user_swir).strip() != "":
        swir = np.full_like(phie, float(user_swir), dtype=np.float64)
    else:
        swir = sw * (1.0 - water_cut)

    # If Sw missing, fall back to PetroParams sw_cutoff (legacy behavior)
    pp = db.query(PetroParams).filter(PetroParams.well_id == wid).first()
    sw_fallback = float(pp.sw_cutoff) if pp and pp.sw_cutoff is not None else 0.2
    swir[np.isnan(swir)] = sw_fallback

    # Sanitize
    phie_clip = np.clip(phie, 0.0, 0.6)
    swir_clip = np.clip(swir, 1e-4, 1.0)

    def _stats(arr: np.ndarray):
        v = arr[np.isfinite(arr) & (arr > 0)]
        if len(v) == 0:
            return {"count": 0, "min": None, "max": None, "mean": None, "median": None}
        return {
            "count": int(len(v)),
            "min": round(float(np.min(v)), 4),
            "max": round(float(np.max(v)), 4),
            "mean": round(float(np.mean(v)), 4),
            "median": round(float(np.median(v)), 4),
        }

    def _crossplot(phi_arr: np.ndarray, k_arr: np.ndarray):
        mask = np.isfinite(phi_arr) & np.isfinite(k_arr) & (phi_arr > 0) & (k_arr > 0)
        if np.sum(mask) < 3:
            return {
                "A": None, "B": None, "r2": None, "n_points": int(np.sum(mask)),
                "equation": "insufficient data",
                "phi": [], "k": [], "k_fit": []
            }
        x = phi_arr[mask]
        y = np.log10(k_arr[mask])
        A, B = np.polyfit(x, y, 1)
        yhat = A * x + B
        ss_res = float(np.sum((y - yhat) ** 2))
        ss_tot = float(np.sum((y - np.mean(y)) ** 2))
        r2 = (1.0 - ss_res / ss_tot) if ss_tot > 0 else 0.0
        return {
            "A": round(float(A), 6),
            "B": round(float(B), 6),
            "r2": round(float(r2), 6),
            "n_points": int(len(x)),
            "equation": f"log10(k) = {A:.4f} * phi + {B:.4f}",
            "phi": [round(float(v), 6) for v in x],
            "k": [round(float(v), 6) for v in k_arr[mask]],
            "k_fit": [round(float(10 ** v), 6) for v in yhat],
        }

    def _fzi(k_arr: np.ndarray, phi_arr: np.ndarray):
        # RQI = 0.0314 * sqrt(k/phi), phi_z = phi/(1-phi), FZI = RQI/phi_z
        valid = np.isfinite(k_arr) & np.isfinite(phi_arr) & (k_arr > 0) & (phi_arr > 0) & (phi_arr < 1)
        if np.sum(valid) == 0:
            return {"values": [], "histogram": [], "hfu": []}

        phi_v = phi_arr[valid]
        k_v = k_arr[valid]
        rqi = 0.0314 * np.sqrt(k_v / np.clip(phi_v, 1e-9, None))
        phi_z = phi_v / np.clip(1.0 - phi_v, 1e-9, None)
        fzi = rqi / np.clip(phi_z, 1e-9, None)

        fzi = fzi[np.isfinite(fzi) & (fzi > 0)]
        if len(fzi) == 0:
            return {"values": [], "histogram": [], "hfu": []}

        # HFU grouping by FZI terciles
        q1, q2 = np.percentile(fzi, [33.33, 66.67])
        hfu = []
        for v in fzi:
            if v <= q1:
                hfu.append("HFU-1")
            elif v <= q2:
                hfu.append("HFU-2")
            else:
                hfu.append("HFU-3")

        hist_counts, hist_edges = np.histogram(fzi, bins=10)
        histogram = []
        for i in range(len(hist_counts)):
            histogram.append({
                "from": round(float(hist_edges[i]), 6),
                "to": round(float(hist_edges[i + 1]), 6),
                "count": int(hist_counts[i]),
            })

        return {
            "values": [round(float(v), 6) for v in fzi],
            "histogram": histogram,
            "hfu": hfu,
            "stats": _stats(fzi),
        }

    # Load optional NMR T2 geometric mean curve
    t2_cd = None
    for t2_mn in [data.get("t2gm_curve", "T2GM"), "T2LM", "T2_LOG_MEAN", "T2GEOM"]:
        if not t2_mn:
            continue
        t2_cd = db.query(CurveData).filter(CurveData.log_run_id == lr.id, CurveData.mnemonic == t2_mn).first()
        if t2_cd:
            break
    t2gm = np.frombuffer(t2_cd.data_binary, dtype=np.float64).copy() if t2_cd else None

    available = {}

    def _add_model(name: str, arr: np.ndarray):
        arr = np.where(np.isfinite(arr) & (arr > 0), arr, np.nan)
        available[name] = {
            "k_md": arr,
            "stats": _stats(arr),
            "crossplot": _crossplot(phie_clip, arr),
            "fzi": _fzi(arr, phie_clip),
        }

    # Coates: k = ((phi^4)/(Swir^2))*C
    k_coates = ((phie_clip ** 4) / (swir_clip ** 2)) * coates_c
    _add_model("coates", k_coates)

    # Timur: k = a*(phi^4.4)/(Swir^2)
    k_timur = timur_a * (phie_clip ** 4.4) / (swir_clip ** 2)
    _add_model("timur", k_timur)

    # SDR (requires NMR T2gm): k = a * phi^4 * T2gm^2
    if t2gm is not None:
        t2_clip = np.where(np.isfinite(t2gm) & (t2gm > 0), t2gm, np.nan)
        k_sdr = sdr_a * (phie_clip ** 4) * (t2_clip ** 2)
        _add_model("sdr", k_sdr)

    selected_models = list(available.keys()) if model == "all" else [model]
    selected_models = [m for m in selected_models if m in available]
    if not selected_models:
        raise HTTPException(400, "Requested model unavailable (SDR requires NMR T2gm data)")

    step = max(1, len(depth) // 800)
    idx = list(range(0, len(depth), step))

    k_values = {}
    summary = {}
    crossplot = {}
    fzi = {}

    for m in selected_models:
        k_arr = available[m]["k_md"]
        k_values[m] = [round(float(k_arr[i]), 6) if np.isfinite(k_arr[i]) else None for i in idx]
        summary[m] = available[m]["stats"]
        crossplot[m] = available[m]["crossplot"]
        fzi[m] = available[m]["fzi"]

    primary = selected_models[0]
    primary_valid = available[primary]["k_md"][np.isfinite(available[primary]["k_md"]) & (available[primary]["k_md"] > 0)]

    return {
        "well_id": wid,
        "log_run_id": lr.id,
        "model": model,
        "models_computed": selected_models,
        "units": "md",
        "curve_name": "PERM",
        "depth": [round(float(depth[i]), 3) for i in idx],
        "phi": [round(float(phie_clip[i]), 6) if np.isfinite(phie_clip[i]) else None for i in idx],
        "swir": [round(float(swir_clip[i]), 6) if np.isfinite(swir_clip[i]) else None for i in idx],
        "k_values": k_values,
        "summary": summary,
        "crossplot": crossplot,
        "fzi": fzi,
        "points": int(len(primary_valid)),
        "stats": summary[primary],
        "constants": {
            "coates_c": coates_c,
            "timur_a": timur_a,
            "sdr_a": sdr_a,
            "water_cut": water_cut,
        },
        "availability": {
            "sdr_available": t2gm is not None,
            "nmr_t2_curve": t2_cd.mnemonic if t2_cd else None,
        },
    }












@router.post("/{wid}/curve-calc")
def curve_calc(wid: int, data: dict, db: Session = Depends(get_db)):
    well = db.query(Well).filter(Well.id == wid).first()
    if not well:
        raise HTTPException(404, "Well not found")

    expression = str(data.get("expression", "")).strip()
    output_name = str(data.get("output_name", "")).strip().upper()
    if not expression or not output_name:
        raise HTTPException(400, "expression and output_name are required")

    lr = db.query(LogRun).filter(LogRun.well_id == wid).order_by(LogRun.id.desc()).first()
    if not lr:
        raise HTTPException(404, "No log run")

    all_curves = db.query(CurveData).filter(CurveData.log_run_id == lr.id).all()
    if not all_curves:
        raise HTTPException(404, "No curves found")

    # Whitelist expression safety checks
    import re
    import ast as _ast
    allowed_funcs = {
        "sqrt", "log", "log10", "abs", "clip", "where",
        "sin", "cos", "tan", "arcsin", "arccos", "arctan",
        "exp", "power", "minimum", "maximum", "np"
    }
    tokens = re.findall(r"[A-Za-z_][A-Za-z0-9_]*", expression)

    safe_ns = {
        "np": np,
        "sqrt": np.sqrt,
        "log": np.log,
        "log10": np.log10,
        "abs": np.abs,
        "clip": np.clip,
        "where": np.where,
        "sin": np.sin,
        "cos": np.cos,
        "tan": np.tan,
        "arcsin": np.arcsin,
        "arccos": np.arccos,
        "arctan": np.arctan,
        "exp": np.exp,
        "power": np.power,
        "minimum": np.minimum,
        "maximum": np.maximum,
    }

    curve_arrays = {}
    for cd in all_curves:
        arr = np.frombuffer(cd.data_binary, dtype=np.float64).copy()
        safe_ns[cd.mnemonic] = arr
        curve_arrays[cd.mnemonic] = arr

    curve_names = set(curve_arrays.keys())
    for t in tokens:
        if t in allowed_funcs:
            continue
        if t in curve_names:
            continue
        raise HTTPException(400, f"Unsupported token in expression: {t}")

    def _safe_eval(expr: str):
        """Evaluate arithmetic, curve names and the allow-listed numpy calls."""
        tree = _ast.parse(expr, mode="eval")
        binops = {
            _ast.Add: lambda a, b: a + b,
            _ast.Sub: lambda a, b: a - b,
            _ast.Mult: lambda a, b: a * b,
            _ast.Div: lambda a, b: a / b,
            _ast.Pow: lambda a, b: a ** b,
            _ast.Mod: lambda a, b: a % b,
        }

        def ev(node):
            if isinstance(node, _ast.Expression):
                return ev(node.body)
            if isinstance(node, _ast.Constant) and isinstance(node.value, (int, float)):
                return node.value
            if isinstance(node, _ast.Name):
                if node.id in safe_ns:
                    return safe_ns[node.id]
                raise ValueError(f"unsupported name: {node.id}")
            if isinstance(node, _ast.BinOp) and type(node.op) in binops:
                return binops[type(node.op)](ev(node.left), ev(node.right))
            if isinstance(node, _ast.UnaryOp) and isinstance(node.op, _ast.USub):
                return -ev(node.operand)
            if isinstance(node, _ast.UnaryOp) and isinstance(node.op, _ast.UAdd):
                return +ev(node.operand)
            if isinstance(node, _ast.Attribute):
                owner = ev(node.value)
                if owner is np and node.attr in allowed_funcs:
                    return getattr(owner, node.attr)
                raise ValueError(f"unsupported attribute: {node.attr}")
            if isinstance(node, _ast.Call):
                fn = ev(node.func)
                if not callable(fn):
                    raise ValueError("expression calls a non-function")
                return fn(*[ev(arg) for arg in node.args])
            raise ValueError(f"unsupported expression: {type(node).__name__}")

        return ev(tree)

    try:
        result = _safe_eval(expression)
    except Exception as e:
        raise HTTPException(400, f"Expression evaluation error: {str(e)[:200]}")

    if np.isscalar(result):
        # broadcast scalar across longest curve length
        max_len = max(len(a) for a in curve_arrays.values())
        result_arr = np.full(max_len, float(result), dtype=np.float64)
    else:
        result_arr = np.asarray(result, dtype=np.float64)

    valid = result_arr[~np.isnan(result_arr)]

    existing = db.query(CurveData).filter(CurveData.log_run_id == lr.id, CurveData.mnemonic == output_name).first()
    if existing:
        existing.data_binary = result_arr.tobytes()
        existing.num_points = len(result_arr)
        existing.min_value = float(np.min(valid)) if len(valid) else None
        existing.max_value = float(np.max(valid)) if len(valid) else None
        existing.description = f"Calculated curve: {expression}"
        curve_name = existing.mnemonic
    else:
        new_cd = CurveData(
            log_run_id=lr.id,
            mnemonic=output_name,
            unit="",
            description=f"Calculated curve: {expression}",
            num_points=len(result_arr),
            min_value=float(np.min(valid)) if len(valid) else None,
            max_value=float(np.max(valid)) if len(valid) else None,
            data_binary=result_arr.tobytes(),
        )
        db.add(new_cd)
        curve_name = output_name

    db.commit()

    return {
        "status": "ok",
        "curve_name": curve_name,
        "points": int(len(result_arr)),
        "min": round(float(np.min(valid)), 6) if len(valid) else None,
        "max": round(float(np.max(valid)), 6) if len(valid) else None,
        "mean": round(float(np.mean(valid)), 6) if len(valid) else None,
    }


@router.post("/{wid}/dual-water")
def compute_dual_water(wid: int, data: dict, db: Session = Depends(get_db)):
    """Compute Sw using Dual-Water model (Clavier et al. 1977).
    Sw = sqrt( (a * Rw) / (phi^m * Rt) * (1 - (Rw/Rwb) * (Vsh * phi_sh / phi)) )
    Simplified: Sw_dw = Sw_archie * correction_factor
    """
    lr_id = data.get("log_run_id")
    lr = db.query(LogRun).filter(LogRun.id == lr_id).first() if lr_id else \
         db.query(LogRun).filter(LogRun.well_id == wid).order_by(LogRun.num_points.desc()).first()
    if not lr:
        raise HTTPException(404, "No log run")

    dept, by_name = _semantic_curves(db, lr)
    n = len(dept)
    if n == 0:
        raise HTTPException(400, "Log run has no depth samples")
    rt = _first_curve(by_name, ["RT", "RESD", "RILD", "ILD"])
    nphi = _first_curve(by_name, ["NPHI", "NPHI_LS"])
    gr = _first_curve(by_name, ["GR", "SGR", "CGR"])
    if rt is None or nphi is None:
        raise HTTPException(400, "Need RT and NPHI curves")
    rt = _aligned(rt, n)
    nphi = _aligned(nphi, n)
    gr = _aligned(gr, n)

    a_v = float(data.get("a", 1.0))
    m_v = float(data.get("m", 2.0))
    n_v = float(data.get("n", 2.0))
    rw = float(data.get("rw", 0.1))
    rwb = float(data.get("rwb", 0.03))  # bound water resistivity
    phi_sh = float(data.get("phi_sh", 0.30))  # shale porosity

    # Vsh from GR
    gr_valid = gr[~np.isnan(gr) & (gr > 0)]
    gr_min = float(np.min(gr_valid)) if len(gr_valid) else 0
    gr_max = float(np.max(gr_valid)) if len(gr_valid) else 150
    if gr_max == gr_min:
        gr_max = gr_min + 1

    sw = np.full(n, np.nan)
    vsh_arr = np.full(n, np.nan)
    phie_arr = np.full(n, np.nan)
    bvw_arr = np.full(n, np.nan)

    for i in range(n):
        if np.isnan(rt[i]) or np.isnan(nphi[i]) or rt[i] <= 0 or nphi[i] < 0:
            continue
        igr = (gr[i] - gr_min) / (gr_max - gr_min) if gr_max > gr_min else 0
        vsh_v = max(0, min(1, igr))
        vsh_arr[i] = vsh_v

        phi_t = max(0.01, nphi[i])
        # Dual-water: effective porosity = total - bound water
        phi_e = phi_t * (1 - vsh_v * (1 - phi_sh / max(phi_t, 0.01)))
        phi_e = max(0.01, phi_e)
        phie_arr[i] = phi_e

        # Sw calculation with bound water correction
        sw_archie = (a_v * rw / (phi_e ** m_v * rt[i])) ** (1.0 / n_v)
        # Bound water volume
        vwb = vsh_v * phi_sh
        # Dual-water correction
        if phi_e > 0:
            correction = 1 - (rw / rwb) * (vwb / phi_e)
            sw_v = sw_archie * max(0, correction)
        else:
            sw_v = 1.0
        sw[i] = max(0, min(1, sw_v))
        bvw_arr[i] = sw[i] * phi_e  # bulk volume water

    valid_sw = sw[~np.isnan(sw)]
    valid_phie = phie_arr[~np.isnan(phie_arr)]
    valid_bvw = bvw_arr[~np.isnan(bvw_arr)]

    return {
        "depth": dept.tolist(),
        "sw": sw.tolist(),
        "vsh": vsh_arr.tolist(),
        "phie": phie_arr.tolist(),
        "bvw": bvw_arr.tolist(),
        "stats": {
            "sw_mean": round(float(np.mean(valid_sw)), 4) if len(valid_sw) else None,
            "sw_median": round(float(np.median(valid_sw)), 4) if len(valid_sw) else None,
            "phie_mean": round(float(np.mean(valid_phie)), 4) if len(valid_phie) else None,
            "bvw_mean": round(float(np.mean(valid_bvw)), 4) if len(valid_bvw) else None,
            "model": "dual_water",
            "rwb": rwb,
            "phi_sh": phi_sh,
        }
    }


@router.post("/{wid}/vcl-models")
def compute_vcl_models(wid: int, data: dict, db: Session = Depends(get_db)):
    """Compute Vclay using multiple models for comparison.
    Models: larionov_tertiary, larionov_old, clavier, steiber, linear_igr
    """
    lr_id = data.get("log_run_id")
    lr = db.query(LogRun).filter(LogRun.id == lr_id).first() if lr_id else \
         db.query(LogRun).filter(LogRun.well_id == wid).order_by(LogRun.num_points.desc()).first()
    if not lr:
        raise HTTPException(404, "No log run")

    dept, by_name = _semantic_curves(db, lr)
    gr = _first_curve(by_name, ["GR", "SGR", "CGR"])
    if gr is None:
        raise HTTPException(400, "GR curve required")
    n = len(dept)
    if n == 0:
        raise HTTPException(400, "Log run has no depth samples")
    gr = _aligned(gr, n)

    gr_clean = float(data.get("gr_clean", 20))  # GR in clean sand
    gr_shale = float(data.get("gr_shale", 120))  # GR in shale

    results = {
        "depth": dept.tolist(),
        "igr": np.full(n, np.nan).tolist(),
        "larionov_tertiary": np.full(n, np.nan).tolist(),
        "larionov_old": np.full(n, np.nan).tolist(),
        "clavier": np.full(n, np.nan).tolist(),
        "steiber": np.full(n, np.nan).tolist(),
    }

    for i in range(n):
        if np.isnan(gr[i]) or gr[i] < 0:
            continue
        # IGR (Linear Gamma Ray Index)
        igr = (gr[i] - gr_clean) / (gr_shale - gr_clean) if gr_shale > gr_clean else 0
        igr = max(0, min(1, igr))
        results["igr"][i] = round(igr, 4)

        # Larionov (Tertiary rocks): Vcl = 0.083 * (2^(3.7*IGR) - 1)
        vcl_lt = 0.083 * (2 ** (3.7 * igr) - 1)
        results["larionov_tertiary"][i] = round(max(0, min(1, vcl_lt)), 4)

        # Larionov (Older rocks): Vcl = 0.33 * (2^(2*IGR) - 1)
        vcl_lo = 0.33 * (2 ** (2 * igr) - 1)
        results["larionov_old"][i] = round(max(0, min(1, vcl_lo)), 4)

        # Clavier et al.: Vcl = 1.7 - sqrt(3.38 - (IGR + 0.7)^2)
        vcl_c = 1.7 - np.sqrt(max(0, 3.38 - (igr + 0.7) ** 2))
        results["clavier"][i] = round(max(0, min(1, vcl_c)), 4)

        # Steiber: Vcl = IGR / (3 - 2*IGR)
        vcl_s = igr / (3 - 2 * igr) if (3 - 2 * igr) > 0 else 1.0
        results["steiber"][i] = round(max(0, min(1, vcl_s)), 4)

    # Summary stats
    summary = {}
    for model in ["igr", "larionov_tertiary", "larionov_old", "clavier", "steiber"]:
        vals = [v for v in results[model] if v is not None and not np.isnan(v)]
        summary[model] = {
            "mean": round(float(np.mean(vals)), 4) if vals else None,
            "median": round(float(np.median(vals)), 4) if vals else None,
            "min": round(float(np.min(vals)), 4) if vals else None,
            "max": round(float(np.max(vals)), 4) if vals else None,
        }

    return {"results": results, "summary": summary, "params": {"gr_clean": gr_clean, "gr_shale": gr_shale}}


@router.post("/{wid}/lithology")
def classify_lithology(wid: int, data: dict, db: Session = Depends(get_db)):
    """Automated lithology classification from GR with optional RHOB/NPHI crossplot criteria."""
    lr_id = data.get("log_run_id")
    lr = db.query(LogRun).filter(LogRun.id == lr_id).first() if lr_id else \
         db.query(LogRun).filter(LogRun.well_id == wid).order_by(LogRun.num_points.desc()).first()
    if not lr:
        raise HTTPException(404, "No log run")

    method = str(data.get("method", "gr_rhob_nphi")).strip().lower()
    if method not in {"gr_only", "gr_rhob_nphi", "crossplot"}:
        raise HTTPException(400, "method must be one of: gr_only, gr_rhob_nphi, crossplot")

    gr_min = float(data.get("gr_min", 0.0))
    gr_max = float(data.get("gr_max", 150.0))
    if gr_max <= gr_min:
        raise HTTPException(400, "gr_max must be greater than gr_min")

    gr_cd = db.query(CurveData).filter(CurveData.log_run_id == lr.id, CurveData.mnemonic.in_(["GR", "SGR", "CGR"])).first()
    if not gr_cd:
        raise HTTPException(400, "GR curve required")

    rhob_cd = db.query(CurveData).filter(CurveData.log_run_id == lr.id, CurveData.mnemonic.in_(["RHOB", "RHOZ", "DEN"])) .first()
    nphi_cd = db.query(CurveData).filter(CurveData.log_run_id == lr.id, CurveData.mnemonic.in_(["NPHI", "NPHI_LS"])) .first()
    dept_cd = db.query(CurveData).filter(CurveData.log_run_id == lr.id, CurveData.mnemonic.in_(["DEPT", "DEPTH", "MD", "TVD"])) .first()

    gr = np.frombuffer(gr_cd.data_binary, dtype=np.float64).copy()
    n = len(gr)
    rhob = np.frombuffer(rhob_cd.data_binary, dtype=np.float64).copy() if rhob_cd else np.full(n, np.nan)
    nphi = np.frombuffer(nphi_cd.data_binary, dtype=np.float64).copy() if nphi_cd else np.full(n, np.nan)
    dept = np.frombuffer(dept_cd.data_binary, dtype=np.float64).copy() if dept_cd else np.arange(n, dtype=np.float64)

    lith_code = np.zeros(n, dtype=np.int32)
    vcl_array = np.full(n, np.nan)

    for i in range(n):
        gv = gr[i]
        if np.isnan(gv):
            continue

        igr = (gv - gr_min) / (gr_max - gr_min)
        igr = max(0.0, min(1.0, float(igr)))

        # Vcl models from GR (Larionov tertiary default)
        vcl_larionov_tertiary = 0.083 * (2 ** (3.7 * igr) - 1)
        vcl = max(0.0, min(1.0, float(vcl_larionov_tertiary)))
        vcl_array[i] = vcl

        rv = rhob[i] if i < len(rhob) else np.nan
        nv = nphi[i] if i < len(nphi) else np.nan
        has_rhob_nphi = (not np.isnan(rv)) and (not np.isnan(nv))

        if method == "gr_only" or ((method in {"gr_rhob_nphi", "crossplot"}) and not has_rhob_nphi):
            if vcl < 0.3:
                lith_code[i] = 1
            elif vcl < 0.5:
                lith_code[i] = 2
            else:
                lith_code[i] = 3
            continue

        if rv < 2.0 and nv > 0.4:
            lith_code[i] = 8
        elif 2.0 < rv < 2.1 and nv < 0.05:
            lith_code[i] = 7
        elif rv > 2.85 and nv < 0.05:
            lith_code[i] = 6
        elif vcl < 0.2 and 2.7 < rv < 2.9 and -0.05 < nv < 0.1:
            lith_code[i] = 5
        elif vcl < 0.2 and 2.6 < rv < 2.75 and -0.05 < nv < 0.15:
            lith_code[i] = 4
        elif vcl >= 0.5 and rv > 2.2:
            lith_code[i] = 3
        elif 0.3 <= vcl < 0.5 and 2.0 < rv < 2.75:
            lith_code[i] = 2
        elif vcl < 0.3 and 2.0 < rv < 2.65 and nv < 0.35:
            lith_code[i] = 1

    labels = {
        1: "sand",
        2: "shaly_sand",
        3: "shale",
        4: "limestone",
        5: "dolomite",
        6: "anhydrite",
        7: "salt",
        8: "coal",
    }
    total_valid = int(np.sum(lith_code > 0))
    summary = {}
    for code, label in labels.items():
        count = int(np.sum(lith_code == code))
        if count > 0:
            summary[label] = round((count / max(1, total_valid)) * 100.0, 2)

    # Replace NaN with None for JSON compliance
    vcl_clean = [None if np.isnan(v) else round(float(v), 4) for v in vcl_array]
    dept_clean = [None if np.isnan(d) else round(float(d), 4) for d in dept]
    
    return {
        "depth": dept_clean,
        "lith_code": lith_code.astype(int).tolist(),
        "vcl_array": vcl_clean,
        "summary": summary,
    }


@router.post("/{wid}/compute-sw")
def compute_saturation(wid: int, data: dict, db: Session = Depends(get_db)):
    """Unified saturation computation with multiple models.
    
    Supported models: archie, simandoux, indonesian, waxman_smits, dual_water
    
    Params:
        model: str - saturation model name
        a, m, n: float - Archie parameters
        rw: float - formation water resistivity
        rwb: float - bound water resistivity (for dual-water/waxman-smits)
        qv: float - cation exchange capacity per unit pore volume (for waxman-smits)
        phi_sh: float - shale porosity (for dual-water)
        vsh_method: str - Vclay method (larionov, steiber, clavier, igr)
        gr_clean, gr_shale: float - GR endpoints for Vclay
    """
    lr = db.query(LogRun).filter(LogRun.well_id == wid).order_by(LogRun.num_points.desc()).first()
    if not lr:
        raise HTTPException(404, "No log run")

    # Load curves through the shared semantics layer.
    semantic = apply_run_semantics(db, lr, as_arrays=True)
    by_name = {}
    for meta in semantic["metadata"]["aliases"]:
        arr = semantic["curves"].get(meta["name"])
        if arr is not None:
            by_name[str(meta["name"]).upper()] = arr
            by_name[str(meta["raw"]).upper()] = arr

    def _get_curve(names):
        for name in names:
            arr = by_name.get(name.upper())
            if arr is not None:
                return arr
        return None

    dept = np.asarray(semantic["depth"], dtype=np.float64)
    if dept.size == 0:
        raise HTTPException(400, "Log run has no depth samples")
    rt = _get_curve(["RT", "RESD", "RILD", "ILD"])
    gr = _get_curve(["GR", "SGR", "CGR"])
    nphi = _get_curve(["NPHI", "NPHI_LS"])
    rhob = _get_curve(["RHOB", "RHOZ", "DEN"])
    drho = _get_curve(["DRHO", "DCOR", "HDRA"])
    cali = _get_curve(["CAL", "CALI", "HCAL", "DCAL"])
    bit_size = _get_curve(["BS", "BIT", "BIT_SIZE"])

    if rt is None:
        raise HTTPException(400, "RT curve required")
    if gr is None:
        raise HTTPException(400, "GR curve required for Vclay")

    n = len(dept)
    def _fit(arr):
        if arr is None:
            return np.full(n, np.nan)
        arr = np.asarray(arr, dtype=np.float64)
        if len(arr) == n:
            return arr
        out = np.full(n, np.nan)
        out[:min(len(arr), n)] = arr[:min(len(arr), n)]
        return out

    rt = _fit(rt)
    gr = _fit(gr)
    nphi = _fit(nphi)
    rhob = _fit(rhob)
    drho = _fit(drho) if drho is not None else None
    cali = _fit(cali) if cali is not None else None
    bit_size = _fit(bit_size) if bit_size is not None else None

    # Parameters
    model = str(data.get("model", "archie")).lower()
    a_v = float(data.get("a", 1.0))
    m_v = float(data.get("m", 2.0))
    n_v = float(data.get("n", 2.0))
    rw = float(data.get("rw", 0.1))
    rwb = float(data.get("rwb", 0.03))
    qv = float(data.get("qv", 0.0))  # meq/mL for waxman-smits
    phi_sh = float(data.get("phi_sh", 0.30))
    vsh_method = str(data.get("vsh_method", "larionov_tertiary")).lower()
    gr_clean = float(data.get("gr_clean", np.nanmin(gr[~np.isnan(gr)]))) if not np.all(np.isnan(gr)) else 20
    gr_shale = float(data.get("gr_shale", np.nanmax(gr[~np.isnan(gr)]))) if not np.all(np.isnan(gr)) else 120

    n = len(rt)
    sw = np.full(n, np.nan)
    vsh_arr = np.full(n, np.nan)
    phie_arr = np.full(n, np.nan)

    # --- Density quality control ---
    # A rugose or washed-out hole lets the density pad lift off the formation and
    # the tool applies a large correction to compensate. Those samples must not
    # be read as porosity. Default is to flag and report only: nulling samples is
    # a data change, so it is opt-in.
    drho_limit = float(data.get("drho_limit", DEFAULT_DRHO_LIMIT))
    washout_inches = float(data.get("washout_inches", DEFAULT_WASHOUT_INCHES))
    apply_filter = bool(data.get("apply_bad_hole_filter", False))
    bad_mask, bad_reasons = bad_hole_mask(
        n, drho=drho, cali=cali, bit_size=bit_size,
        drho_limit=drho_limit, washout_inches=washout_inches,
    )

    # --- Vclay computation (shared kernel in backend/petro_deterministic.py) ---
    vsh_arr = _vclay(gr, gr_clean, gr_shale, method=vsh_method)
    vsh_arr[np.isnan(gr)] = np.nan

    # --- Porosity computation (shared kernel) ---
    phie_arr = _porosity_blend(nphi, rhob, np.nan_to_num(vsh_arr, nan=0.0), rho_ma=2.65, rho_f=1.0, phi_sh=phi_sh)

    # Apply the bad-hole filter after the porosity loop, not by blanking RHOB:
    # a NaN RHOB would fall through to the neutron fallback branch above and
    # quietly substitute a different measurement for a sample the caller asked
    # to exclude. VSH stays, since it comes from GR and not from the density.
    if apply_filter and bad_mask.any():
        phie_arr = apply_mask(phie_arr, bad_mask)

    # --- Saturation computation ---
    for i in range(n):
        if np.isnan(rt[i]) or np.isnan(phie_arr[i]) or rt[i] <= 0 or phie_arr[i] < 0.01:
            continue
        phi = max(phie_arr[i], 0.01)
        vsh_v = vsh_arr[i] if not np.isnan(vsh_arr[i]) else 0

        if model in {"simandoux", "indonesian"}:
            rsh = float(data.get("rsh", 4.0))
            sw_v = saturation(
                model,
                rt[i],
                phi,
                vsh_v,
                a=a_v,
                m=m_v,
                n=n_v,
                rw=rw,
                rsh=rsh,
            )

        elif model == "waxman_smits":
            # Waxman-Smits (1968): Sw^-n = (a*Rw / (phi^m * Rt)) * (1 + Rw*B*Qv/Sw)
            # B = 3.83 * (1 - 0.83 * exp(-0.5 / Rw)) at 25°C
            B = 3.83 * (1 - 0.83 * np.exp(-0.5 / max(rw, 0.001)))
            sw_v = 1.0
            for _ in range(30):
                cex = B * qv / max(sw_v, 0.01)
                inner = a_v * rw * (1 + cex) / (phi ** m_v * rt[i])
                sw_new = max(0, min(1, inner ** (1.0 / n_v)))
                if abs(sw_new - sw_v) < 0.001:
                    break
                sw_v = sw_new

        elif model == "dual_water":
            # Dual-Water (Clavier 1977):
            # Sw^(-n) = a*Rw / (phi^m * Rt) * (1 + (Rw/Rwb - 1) * (Vsh*phi_sh / phi))
            correction = (rw / rwb - 1) * (vsh_v * phi_sh / phi) if rwb > 0 else 0
            inner = a_v * rw / (phi ** m_v * rt[i]) * (1 + correction)
            sw_v = max(0, min(1, inner ** (1.0 / n_v)))

        else:  # archie (default)
            sw_v = max(0, min(1, (a_v * rw / (phi ** m_v * rt[i])) ** (1.0 / n_v)))

        sw[i] = np.clip(sw_v, 0, 1)

    # Stats
    valid_sw = sw[~np.isnan(sw)]
    valid_phie = phie_arr[~np.isnan(phie_arr)]
    valid_vsh = vsh_arr[~np.isnan(vsh_arr)]

    return {
        "depth": dept.tolist(),
        "sw": [None if np.isnan(v) else round(float(v), 4) for v in sw],
        "vsh": [None if np.isnan(v) else round(float(v), 4) for v in vsh_arr],
        "phie": [None if np.isnan(v) else round(float(v), 4) for v in phie_arr],
        "bad_hole": bad_mask.astype(bool).tolist(),
        "model": model,
        "params": {"a": a_v, "m": m_v, "n": n_v, "rw": rw, "rwb": rwb, "qv": qv,
                   "vsh_method": vsh_method, "gr_clean": gr_clean, "gr_shale": gr_shale,
                   "drho_limit": drho_limit, "washout_inches": washout_inches,
                   "apply_bad_hole_filter": apply_filter},
        "qc": qc_summary(bad_mask, bad_reasons),
        "stats": {
            "sw_mean": round(float(np.nanmean(valid_sw)), 4) if len(valid_sw) else None,
            "sw_min": round(float(np.nanmin(valid_sw)), 4) if len(valid_sw) else None,
            "sw_max": round(float(np.nanmax(valid_sw)), 4) if len(valid_sw) else None,
            "phie_mean": round(float(np.nanmean(valid_phie)), 4) if len(valid_phie) else None,
            "vsh_mean": round(float(np.nanmean(valid_vsh)), 4) if len(valid_vsh) else None,
            "n_points": len(valid_sw),
        }
    }


@router.post("/{wid}/multimineral")
def multimineral_solver(wid: int, data: dict, db: Session = Depends(get_db)):
    """Multimineral solver — estimate mineral volumes from log responses.

    Solves for: V_quartz, V_calcite, V_dolomite, V_clay, phi_e
    Using: GR, RHOB, NPHI, DT (minimum 3 curves needed)

    Based on deterministic linear inversion of response equations.
    """
    lr = db.query(LogRun).filter(LogRun.well_id == wid).order_by(LogRun.num_points.desc()).first()
    if not lr:
        raise HTTPException(404, "No log run")

    dept, by_name = _semantic_curves(db, lr)
    n_pts = len(dept)
    if n_pts == 0:
        raise HTTPException(400, "Log run has no depth samples")
    rhob = _first_curve(by_name, ["RHOB", "RHOZ", "DEN"])
    nphi = _first_curve(by_name, ["NPHI", "NPHI_LS"])
    dt_arr = _first_curve(by_name, ["DT", "DTC", "DTCO"])
    gr = _first_curve(by_name, ["GR", "SGR", "CGR"])

    if rhob is None or nphi is None:
        raise HTTPException(400, "Need RHOB and NPHI at minimum")
    rhob = _aligned(rhob, n_pts)
    nphi = _aligned(nphi, n_pts)
    dt_arr = _aligned(dt_arr, n_pts) if dt_arr is not None else None
    gr = _aligned(gr, n_pts) if gr is not None else None

    # Endmember values (can be overridden via data)
    endmembers = {
        "quartz":   {"rhob": 2.65, "nphi": -0.02, "dt": 55.5, "gr": 10},
        "calcite":  {"rhob": 2.71, "nphi": 0.00,  "dt": 47.6, "gr": 10},
        "dolomite": {"rhob": 2.87, "nphi": 0.02,  "dt": 43.5, "gr": 10},
        "clay":     {"rhob": float(data.get("rho_clay", 2.45)),
                     "nphi": float(data.get("nphi_clay", 0.40)),
                     "dt": float(data.get("dt_clay", 100)),
                     "gr": float(data.get("gr_clay", 150))},
        "water":    {"rhob": 1.00, "nphi": 1.00,  "dt": 189,  "gr": 0},
    }

    # Use 3 or 4 minerals depending on available curves
    use_dt = dt_arr is not None

    gr_max = float(np.nanmax(gr)) if gr is not None and not np.all(np.isnan(gr)) else 150
    gr_min = float(np.nanmin(gr)) if gr is not None and not np.all(np.isnan(gr)) else 10
    gr_range = max(gr_max - gr_min, 1)

    result = {
        "v_quartz": np.full(n_pts, np.nan),
        "v_calcite": np.full(n_pts, np.nan),
        "v_dolomite": np.full(n_pts, np.nan),
        "v_clay": np.full(n_pts, np.nan),
        "phi_e": np.full(n_pts, np.nan),
    }

    for i in range(n_pts):
        if np.isnan(rhob[i]) or np.isnan(nphi[i]):
            continue

        # Estimate Vclay from GR
        if gr is not None and not np.isnan(gr[i]):
            igr = np.clip((gr[i] - gr_min) / gr_range, 0, 1)
            vsh_est = 0.083 * (2 ** (3.7 * igr) - 1) if igr < 1 else 1.0
        else:
            vsh_est = 0

        # Simplified deterministic: use RHOB-NPHI crossplot
        # phi from density
        phi_d = density_porosity(rhob[i], lo=-np.inf, hi=np.inf)
        phi_n = nphi[i]

        # Clay volume from neutron-density spread
        if phi_n > phi_d:
            # Clay effect
            vclay_den = max(0, min(1, (phi_n - phi_d) / (endmembers["clay"]["nphi"] - (2.65 - endmembers["clay"]["rhob"]) / 1.65)))
        else:
            vclay_den = vsh_est

        # Porosity
        phi_e_v = max(0, min(0.5, phi_d - vclay_den * (2.65 - endmembers["clay"]["rhob"]) / 1.65))

        # Remaining mineral fraction (quartz/calcite/dolomite mix)
        v_minerals = max(0, 1 - vclay_den - phi_e_v)

        # Distribute minerals: use DT if available
        if use_dt and not np.isnan(dt_arr[i]):
            # Use DT to distinguish quartz from carbonate
            dt_ma = 55.5  # quartz transit time
            dt_ca = 47.6  # calcite transit time
            # Fraction of quartz vs carbonate
            if dt_ma != dt_ca:
                frac_quartz = np.clip((dt_arr[i] - dt_ca - phi_e_v * 189) / (dt_ma - dt_ca), 0, 1)
            else:
                frac_quartz = 0.5
            v_quartz = v_minerals * frac_quartz
            v_dolo = v_minerals * (1 - frac_quartz) * 0.3
            v_calcite = v_minerals - v_quartz - v_dolo
        else:
            # Default: mostly quartz
            v_quartz = v_minerals * 0.6
            v_calcite = v_minerals * 0.3
            v_dolo = v_minerals * 0.1

        result["v_quartz"][i] = max(0, v_quartz)
        result["v_calcite"][i] = max(0, v_calcite)
        result["v_dolomite"][i] = max(0, v_dolo)
        result["v_clay"][i] = max(0, vclay_den)
        result["phi_e"][i] = max(0, phi_e_v)

    def _to_list(arr):
        return [None if np.isnan(v) else round(float(v), 4) for v in arr]

    return {
        "depth": dept.tolist(),
        "v_quartz": _to_list(result["v_quartz"]),
        "v_calcite": _to_list(result["v_calcite"]),
        "v_dolomite": _to_list(result["v_dolomite"]),
        "v_clay": _to_list(result["v_clay"]),
        "phi_e": _to_list(result["phi_e"]),
        "endmembers": endmembers,
        "stats": {
            "quartz_mean": round(float(np.nanmean(result["v_quartz"])), 4),
            "calcite_mean": round(float(np.nanmean(result["v_calcite"])), 4),
            "dolomite_mean": round(float(np.nanmean(result["v_dolomite"])), 4),
            "clay_mean": round(float(np.nanmean(result["v_clay"])), 4),
            "phi_mean": round(float(np.nanmean(result["phi_e"])), 4),
        }
    }


@router.post("/{wid}/permeability-multi")
def compute_permeability_multi(wid: int, data: dict, db: Session = Depends(get_db)):
    """Compute permeability using multiple models and compare.

    Models:
    - coates: K = ((phi^2 * (1-Swirr)) / Swirr)^2 * C
    - timur: K = a * phi^b * Swirr^c
    - sdr: K = (phi^4 / Swirr)^2 * C  (for NMR)
    - fzi: K = phi^3 / ((1-phi)^2) * FZI^2  (Flow Zone Indicator)
    """
    lr = db.query(LogRun).filter(LogRun.well_id == wid).order_by(LogRun.num_points.desc()).first()
    if not lr:
        raise HTTPException(404, "No log run")

    dept, by_name = _semantic_curves(db, lr)
    n_pts = len(dept)
    if n_pts == 0:
        raise HTTPException(400, "Log run has no depth samples")
    nphi = _first_curve(by_name, ["NPHI", "NPHI_LS"])
    rhob = _first_curve(by_name, ["RHOB", "RHOZ", "DEN"])
    gr = _first_curve(by_name, ["GR", "SGR", "CGR"])
    if nphi is None:
        raise HTTPException(400, "NPHI curve required")
    nphi = _aligned(nphi, n_pts)
    rhob = _aligned(rhob, n_pts) if rhob is not None else np.full(n_pts, np.nan)
    gr = _aligned(gr, n_pts) if gr is not None else np.full(n_pts, np.nan)

    # Porosity
    phi = np.where(np.isnan(rhob), nphi, density_porosity(rhob, lo=-0.15, hi=0.60))
    phi = np.clip(phi, 0.001, 0.60)

    # Vclay from GR
    gr_valid = gr[~np.isnan(gr) & (gr > 0)]
    gr_min = float(np.min(gr_valid)) if len(gr_valid) else 15
    gr_max = float(np.max(gr_valid)) if len(gr_valid) else 120
    gr_range = max(gr_max - gr_min, 1)
    igr = np.clip((gr - gr_min) / gr_range, 0, 1)
    vsh = np.where(igr < 1, 0.083 * (2 ** (3.7 * igr) - 1), 1.0)

    # Effective porosity
    phie = np.clip(phi - vsh * 0.10, 0.001, 0.60)

    # Swirr estimation (irreducible water saturation)
    # Use simple relationship: Swirr ≈ Vsh * phi_sh / phi + 0.04
    swirr = np.clip(vsh * 0.30 / np.maximum(phie, 0.01) + 0.04, 0.04, 0.95)

    C_coates = float(data.get("c_coates", 10000))
    a_timur = float(data.get("a_timur", 31.6))
    b_timur = float(data.get("b_timur", 4.4))
    c_timur = float(data.get("c_timur", 2.0))
    fzi_default = float(data.get("fzi", 10.0))

    k_coates = np.where(phie > 0.01,
                        C_coates * (phie ** 4) * ((1 - swirr) ** 2) / (swirr ** 2), np.nan)
    k_timur = a_timur * (phie ** b_timur) / (swirr ** c_timur)
    k_sdr = np.where(phie > 0.01, 10000 * (phie ** 4) / (swirr ** 2), np.nan)
    k_fzi = np.where(phie > 0.01, (phie ** 3) / ((1 - phie) ** 2) * fzi_default ** 2, np.nan)

    # Log10 permeability for stats
    def _stats(k_arr):
        valid = k_arr[~np.isnan(k_arr) & (k_arr > 0)]
        if len(valid) == 0:
            return {"mean": None, "min": None, "max": None, "median": None}
        return {
            "mean": round(float(np.mean(valid)), 2),
            "min": round(float(np.min(valid)), 2),
            "max": round(float(np.max(valid)), 2),
            "median": round(float(np.median(valid)), 2),
        }

    def _to_list(arr):
        return [None if (np.isnan(v) or v <= 0) else round(float(v), 2) for v in arr]

    return {
        "depth": dept.tolist(),
        "k_coates": _to_list(k_coates),
        "k_timur": _to_list(k_timur),
        "k_sdr": _to_list(k_sdr),
        "k_fzi": _to_list(k_fzi),
        "phie": [round(float(v), 4) for v in phie],
        "swirr": [round(float(v), 4) for v in swirr],
        "stats": {
            "coates": _stats(k_coates),
            "timur": _stats(k_timur),
            "sdr": _stats(k_sdr),
            "fzi": _stats(k_fzi),
        }
    }


@router.post("/{wid}/vcl-enhanced")
def compute_vcl_enhanced(wid: int, data: dict, db: Session = Depends(get_db)):
    """Enhanced Vclay computation with all methods side-by-side.

    Methods: larionov_tertiary, larionov_old, steiber, clavier, linear_igr
    Returns all 5 for comparison.
    """
    lr = db.query(LogRun).filter(LogRun.well_id == wid).order_by(LogRun.num_points.desc()).first()
    if not lr:
        raise HTTPException(404, "No log run")

    gr_cd = db.query(CurveData).filter(CurveData.log_run_id == lr.id, CurveData.mnemonic.in_(["GR", "SGR", "CGR"])).first()
    dept_cd = db.query(CurveData).filter(CurveData.log_run_id == lr.id, CurveData.mnemonic.in_(["DEPT", "DEPTH"])).first()

    if not gr_cd:
        raise HTTPException(400, "GR curve required")

    gr = np.frombuffer(gr_cd.data_binary, dtype=np.float64).copy()
    dept = np.frombuffer(dept_cd.data_binary, dtype=np.float64).copy() if dept_cd else np.arange(len(gr))

    gr_clean = float(data.get("gr_clean", np.nanmin(gr[~np.isnan(gr)])))
    gr_shale = float(data.get("gr_shale", np.nanmax(gr[~np.isnan(gr)])))
    gr_range = max(gr_shale - gr_clean, 1.0)

    n = len(gr)
    methods = {
        "igr": np.full(n, np.nan),
        "larionov_tertiary": np.full(n, np.nan),
        "larionov_old": np.full(n, np.nan),
        "steiber": np.full(n, np.nan),
        "clavier": np.full(n, np.nan),
    }

    for i in range(n):
        if np.isnan(gr[i]):
            continue
        igr = np.clip((gr[i] - gr_clean) / gr_range, 0, 1)
        methods["igr"][i] = igr
        methods["larionov_tertiary"][i] = 0.083 * (2 ** (3.7 * igr) - 1) if igr < 1 else 1.0
        methods["larionov_old"][i] = 0.33 * (2 ** (2 * igr) - 1) if igr < 1 else 1.0
        methods["steiber"][i] = igr / (3 - 2 * igr) if igr < 1 else 1.0
        methods["clavier"][i] = 1.7 - np.sqrt(3.38 - (igr + 0.7) ** 2) if igr < 0.95 else 1.0

    def _to_list(arr):
        return [None if np.isnan(v) else round(float(v), 4) for v in arr]

    result = {"depth": dept.tolist(), "gr": [round(float(v), 2) if not np.isnan(v) else None for v in gr]}
    for name, arr in methods.items():
        result[name] = _to_list(arr)
        valid = arr[~np.isnan(arr)]
        result[f"{name}_mean"] = round(float(np.mean(valid)), 4) if len(valid) else None

    result["params"] = {"gr_clean": gr_clean, "gr_shale": gr_shale}
    return result




@router.post("/{wid}/core-calibration")
def core_calibration(wid: int, data: dict, db: Session = Depends(get_db)):
    """Calibrate log-derived porosity/permeability against core data.
    Accepts core_depth, core_phi, core_k arrays. Returns regression stats.
    """
    core_depth = data.get("core_depth", [])
    core_phi = data.get("core_phi", [])
    core_k = data.get("core_k", [])
    log_curve = data.get("log_curve", "NPHI")  # curve to calibrate against

    if not core_depth or not core_phi:
        raise HTTPException(400, "core_depth and core_phi required")

    lr_id = data.get("log_run_id")
    lr = db.query(LogRun).filter(LogRun.id == lr_id).first() if lr_id else \
         db.query(LogRun).filter(LogRun.well_id == wid).order_by(LogRun.num_points.desc()).first()
    if not lr:
        raise HTTPException(404, "No log run")

    log_cd = db.query(CurveData).filter(CurveData.log_run_id == lr.id, CurveData.mnemonic == log_curve).first()
    dept_cd = db.query(CurveData).filter(CurveData.log_run_id == lr.id, CurveData.mnemonic.in_(["DEPT", "DEPTH"])).first()
    if not log_cd or not dept_cd:
        raise HTTPException(400, f"Curve {log_curve} or DEPTH not found")

    log_arr = np.frombuffer(log_cd.data_binary, dtype=np.float64).copy()
    dept_arr = np.frombuffer(dept_cd.data_binary, dtype=np.float64).copy()

    # Match core depths to nearest log values
    matched_log = []
    matched_core = []
    matched_depth = []
    for d, phi in zip(core_depth, core_phi):
        try:
            core_d = float(d)
            core_phi_v = float(phi)
        except (TypeError, ValueError):
            continue
        idx = np.argmin(np.abs(dept_arr - core_d))
        if abs(dept_arr[idx] - core_d) < 2.0:  # within 2 ft tolerance
            if not np.isnan(log_arr[idx]):
                matched_log.append(float(log_arr[idx]))
                matched_core.append(core_phi_v)
                matched_depth.append(core_d)

    if len(matched_log) < 3:
        raise HTTPException(400, f"Only {len(matched_log)} core points matched to log (need ≥3)")

    # Linear regression: core_phi = a + b * log_value
    x = np.array(matched_log)
    y = np.array(matched_core)
    n = len(x)
    sx = np.sum(x)
    sy = np.sum(y)
    sxx = np.sum(x * x)
    sxy = np.sum(x * y)
    denom = n * sxx - sx * sx
    if denom == 0:
        raise HTTPException(400, "Degenerate data — cannot fit")

    slope = (n * sxy - sx * sy) / denom
    intercept = (sy - slope * sx) / n

    # R²
    y_pred = intercept + slope * x
    ss_res = np.sum((y - y_pred) ** 2)
    ss_tot = np.sum((y - np.mean(y)) ** 2)
    r_squared = 1 - ss_res / ss_tot if ss_tot > 0 else 0

    # RMSE
    rmse = np.sqrt(np.mean((y - y_pred) ** 2))

    # Permeability transform (if core_k provided)
    perm_stats = None
    if core_k and len(core_k) == len(core_phi):
        # Timur-type: k = a * phi^b / Sw^c (simplified: k = a * phi^b)
        k_arr = np.array([float(k) for k in core_k])
        phi_arr = np.array([float(p) for p in core_phi])
        # Log-log regression: log(k) = log(a) + b * log(phi)
        valid = (k_arr > 0) & (phi_arr > 0)
        if valid.sum() >= 3:
            log_k = np.log10(k_arr[valid])
            log_phi = np.log10(phi_arr[valid])
            nk = len(log_k)
            skx = np.sum(log_phi)
            sky = np.sum(log_k)
            skxx = np.sum(log_phi * log_phi)
            skxy = np.sum(log_phi * log_k)
            dk = nk * skxx - skx * skx
            if dk != 0:
                b_perm = (nk * skxy - skx * sky) / dk
                a_perm = 10 ** ((sky - b_perm * skx) / nk)
                k_pred = a_perm * phi_arr[valid] ** b_perm
                ss_r = np.sum((k_arr[valid] - k_pred) ** 2)
                ss_t = np.sum((k_arr[valid] - np.mean(k_arr[valid])) ** 2)
                r2_perm = 1 - ss_r / ss_t if ss_t > 0 else 0
                perm_stats = {
                    "a_perm": round(float(a_perm), 6),
                    "b_perm": round(float(b_perm), 4),
                    "r_squared": round(float(r2_perm), 4),
                    "equation": f"k = {a_perm:.4f} × φ^{b_perm:.2f}",
                    "n_points": int(valid.sum()),
                }

    return {
        "n_matched": len(matched_log),
        "slope": round(float(slope), 6),
        "intercept": round(float(intercept), 6),
        "r_squared": round(float(r_squared), 4),
        "rmse": round(float(rmse), 6),
        "equation": f"{log_curve}_core = {intercept:.4f} + {slope:.4f} × {log_curve}_log",
        "matched_depth": matched_depth,
        "matched_core": matched_core,
        "matched_log": matched_log,
        "predicted": [round(float(v), 4) for v in y_pred.tolist()],
        "permeability": perm_stats,
    }














