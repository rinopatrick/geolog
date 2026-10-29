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
    from production_economics import evaluate as evaluate_production_economics
    from routers.wells import (
        _to_float_or_none, _extract_las_coordinates, _build_petro_summary,
        _semantic_curves, _first_curve, _aligned, _safe_float,
        _persist_non_las_runs, _parse_iso_date, _fit_exponential_decline,
        _fit_hyperbolic_decline, _compute_eur, _hilbert_transform,
        _require_well_admin,
    )
except ImportError:
    from backend.production_economics import evaluate as evaluate_production_economics
    from backend.routers.wells import (
        _to_float_or_none, _extract_las_coordinates, _build_petro_summary,
        _semantic_curves, _first_curve, _aligned, _safe_float,
        _persist_non_las_runs, _parse_iso_date, _fit_exponential_decline,
        _fit_hyperbolic_decline, _compute_eur, _hilbert_transform,
        _require_well_admin,
    )

router = APIRouter(prefix="/api/wells", tags=["wells"])


@router.get("/{wid}/tops")
def list_tops(wid: int, db: Session = Depends(get_db)):
    tops = db.query(FormationTop).filter(FormationTop.well_id == wid).order_by(FormationTop.depth).all()
    return [{c.name: getattr(t, c.name) for c in FormationTop.__table__.columns} for t in tops]


@router.post("/{wid}/tops", status_code=201)
def create_top(wid: int, data: dict, db: Session = Depends(get_db)):
    # Was FormationTop(well_id=wid, **data), which is mass assignment: a client
    # could set id and created_at, and any unknown key raised TypeError -> 500.
    t = FormationTop(
        well_id=wid,
        formation_name=require_str(data, "formation_name"),
        depth=require_float(data, "depth"),
        top_depth=optional_float(data, "top_depth"),
        base_depth=optional_float(data, "base_depth"),
        depth_unit=optional_str(data, "depth_unit", "FT"),
        color=optional_str(data, "color", "#888888"),
        lithology=optional_str(data, "lithology"),
        notes=optional_str(data, "notes"),
    )
    db.add(t)
    db.commit()
    db.refresh(t)
    return {c.name: getattr(t, c.name) for c in FormationTop.__table__.columns}


@router.get("/{wid}/zones")
def list_zones(wid: int, db: Session = Depends(get_db)):
    zones = db.query(Zone).filter(Zone.well_id == wid).order_by(Zone.sort_order.asc(), Zone.id.asc()).all()
    return [{c.name: getattr(z, c.name) for c in Zone.__table__.columns} for z in zones]


@router.post("/{wid}/zones", status_code=201)
def replace_zones(wid: int, data: dict, db: Session = Depends(get_db)):
    zones = data.get("zones", [])
    db.query(Zone).filter(Zone.well_id == wid).delete()
    if not isinstance(zones, list):
        raise HTTPException(400, "zones must be a list")
    for i, z in enumerate(zones):
        if not isinstance(z, dict):
            raise HTTPException(400, f"zones[{i}] must be an object")
        try:
            top = float(z.get("top", z.get("top_depth", 0)))
            bottom = float(z.get("bottom", z.get("bottom_depth", 0)))
        except (TypeError, ValueError):
            raise HTTPException(400, f"zones[{i}] requires numeric top and bottom")
        if bottom <= top:
            continue
        db.add(Zone(
            well_id=wid,
            name=str(z.get("name", f"Zone-{i+1}")),
            top_depth=top,
            bottom_depth=bottom,
            color=str(z.get("color", "#1f6feb")),
            sort_order=i,
        ))
    db.commit()
    return {"status": "ok"}


@router.get("/{wid}/annotations")
def list_annotations(wid: int, db: Session = Depends(get_db)):
    anns = db.query(Annotation).filter(Annotation.well_id == wid).order_by(Annotation.depth).all()
    return [{c.name: getattr(a, c.name) for c in Annotation.__table__.columns} for a in anns]


@router.post("/{wid}/annotations", status_code=201)
def create_annotation(wid: int, data: dict, db: Session = Depends(get_db)):
    ann = Annotation(
        well_id=wid,
        depth=require_float(data, "depth"),
        text=optional_str(data, "text"),
        annotation_type=optional_str(data, "annotation_type", "note"),
        color=optional_str(data, "color", "#f39c12"),
    )
    db.add(ann)
    db.commit()
    db.refresh(ann)
    return {c.name: getattr(ann, c.name) for c in Annotation.__table__.columns}


@router.post("/{wid}/dst", status_code=201)
def create_dst(wid: int, data: dict, db: Session = Depends(get_db)):
    row = DSTTest(
        well_id=wid,
        test_number=str(data.get("test_number", "")),
        top_depth=require_float(data, "top_depth"),
        bottom_depth=require_float(data, "bottom_depth"),
        formation=optional_str(data, "formation"),
        choke_size=optional_str(data, "choke_size"),
        flow_rate=optional_float(data, "flow_rate"),
        shut_in_pressure=optional_float(data, "shut_in_pressure"),
        flowing_pressure=optional_float(data, "flowing_pressure"),
        temperature=optional_float(data, "temperature"),
        permeability=optional_float(data, "permeability"),
        skin=optional_float(data, "skin"),
        result=optional_str(data, "result"),
        notes=optional_str(data, "notes"),
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return {c.name: getattr(row, c.name) for c in DSTTest.__table__.columns}


@router.get("/{wid}/dst")
def list_dst(wid: int, db: Session = Depends(get_db)):
    rows = db.query(DSTTest).filter(DSTTest.well_id == wid).order_by(DSTTest.top_depth.asc(), DSTTest.id.asc()).all()
    return [{c.name: getattr(r, c.name) for c in DSTTest.__table__.columns} for r in rows]


@router.post("/{wid}/rft", status_code=201)
def create_rft(wid: int, data: dict, db: Session = Depends(get_db)):
    row = RFTPoint(
        well_id=wid,
        depth=require_float(data, "depth"),
        pressure=require_float(data, "pressure"),
        mobility=optional_float(data, "mobility"),
        fluid_type=(optional_str(data, "fluid_type", "unknown") or "unknown").lower(),
        sample_recovered=optional_str(data, "sample_recovered"),
        notes=optional_str(data, "notes"),
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return {c.name: getattr(row, c.name) for c in RFTPoint.__table__.columns}


@router.get("/{wid}/rft")
def list_rft(wid: int, db: Session = Depends(get_db)):
    rows = db.query(RFTPoint).filter(RFTPoint.well_id == wid).order_by(RFTPoint.depth.asc(), RFTPoint.id.asc()).all()
    return [{c.name: getattr(r, c.name) for c in RFTPoint.__table__.columns} for r in rows]


@router.post("/{wid}/completion", status_code=201)
def create_completion_component(wid: int, data: dict, db: Session = Depends(get_db)):
    ctype = str(data.get("component_type", "")).strip().lower()
    if ctype not in COMPLETION_COMPONENT_TYPES:
        raise HTTPException(400, f"Invalid component_type. Allowed: {sorted(COMPLETION_COMPONENT_TYPES)}")

    top = require_float(data, "depth_top")
    base = require_float(data, "depth_base")
    if base < top:
        top, base = base, top

    row = CompletionData(
        well_id=wid,
        depth_top=top,
        depth_base=base,
        component_type=ctype,
        size=optional_str(data, "size"),
        description=optional_str(data, "description"),
        notes=optional_str(data, "notes"),
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return {c.name: getattr(row, c.name) for c in CompletionData.__table__.columns}


@router.get("/{wid}/completion")
def list_completion_components(wid: int, db: Session = Depends(get_db)):
    rows = db.query(CompletionData).filter(CompletionData.well_id == wid).order_by(CompletionData.depth_top.asc(), CompletionData.id.asc()).all()
    return [{c.name: getattr(r, c.name) for c in CompletionData.__table__.columns} for r in rows]


@router.get("/{wid}/rft/pressure-gradient")
def rft_pressure_gradient(wid: int, db: Session = Depends(get_db)):
    rows = db.query(RFTPoint).filter(RFTPoint.well_id == wid).order_by(RFTPoint.depth.asc()).all()
    points = [{c.name: getattr(r, c.name) for c in RFTPoint.__table__.columns} for r in rows]
    valid = [{
        "id": r.id,
        "depth": float(r.depth),
        "pressure": float(r.pressure),
        "fluid_type": (r.fluid_type or "unknown").lower(),
    } for r in rows if r.depth is not None and r.pressure is not None]
    if len(valid) < 2:
        return {
            "count": len(valid),
            "points": points,
            "overall": None,
            "by_fluid": [],
            "fluid_segments": [],
            "fluid_contacts": [],
            "gradient_lines": {},
            "pressure_regime_summary": {},
            "formation_pressure": {"points": [], "intervals": []},
        }

    fluid_windows = {
        "gas": (0.05, 0.20),
        "oil": (0.25, 0.35),
        "water": (0.40, 0.50),
    }

    def classify_fluid_by_gradient(grad):
        if grad is None or not np.isfinite(grad):
            return "unknown"
        for name, (lo, hi) in fluid_windows.items():
            if lo <= grad <= hi:
                return name
        return "unknown"

    def classify_pressure_regime(grad):
        if grad is None or not np.isfinite(grad):
            return "unknown"
        if grad < 0.43:
            return "underpressure"
        if grad > 0.47:
            return "overpressure"
        return "normal"

    depths = np.array([v["depth"] for v in valid], dtype=float)
    pressures = np.array([v["pressure"] for v in valid], dtype=float)
    slope, intercept = np.polyfit(depths, pressures, 1)
    overall = {
        "gradient": float(slope),
        "intercept": float(intercept),
        "equation": f"P = {slope:.6f}*Depth + {intercept:.3f}",
        "fluid_guess": classify_fluid_by_gradient(float(slope)),
        "regime": classify_pressure_regime(float(slope)),
    }

    # Segment data by local two-point gradients into contiguous fluid-gradient clusters.
    for i in range(len(valid)):
        if i == 0:
            pair_grad = (valid[i + 1]["pressure"] - valid[i]["pressure"]) / max(valid[i + 1]["depth"] - valid[i]["depth"], 1e-9)
        elif i == len(valid) - 1:
            pair_grad = (valid[i]["pressure"] - valid[i - 1]["pressure"]) / max(valid[i]["depth"] - valid[i - 1]["depth"], 1e-9)
        else:
            pair_grad = (valid[i + 1]["pressure"] - valid[i - 1]["pressure"]) / max(valid[i + 1]["depth"] - valid[i - 1]["depth"], 1e-9)
        valid[i]["pair_gradient"] = float(pair_grad)
        valid[i]["fluid_from_gradient"] = classify_fluid_by_gradient(valid[i]["pair_gradient"])
        valid[i]["pressure_regime"] = classify_pressure_regime(valid[i]["pair_gradient"])

    segments = []
    seg_start = 0
    for i in range(1, len(valid)):
        if valid[i]["fluid_from_gradient"] != valid[i - 1]["fluid_from_gradient"]:
            segments.append((seg_start, i - 1))
            seg_start = i
    segments.append((seg_start, len(valid) - 1))

    fluid_segments = []
    for sidx, (a, b) in enumerate(segments):
        seg_pts = valid[a:b + 1]
        if len(seg_pts) < 2:
            seg_slope = seg_pts[0]["pair_gradient"]
            seg_intercept = seg_pts[0]["pressure"] - seg_slope * seg_pts[0]["depth"]
        else:
            seg_d = np.array([p["depth"] for p in seg_pts], dtype=float)
            seg_p = np.array([p["pressure"] for p in seg_pts], dtype=float)
            seg_slope, seg_intercept = np.polyfit(seg_d, seg_p, 1)
        fluid_guess = classify_fluid_by_gradient(float(seg_slope))
        fluid_segments.append({
            "segment_index": sidx,
            "start_depth": float(seg_pts[0]["depth"]),
            "end_depth": float(seg_pts[-1]["depth"]),
            "count": len(seg_pts),
            "gradient": float(seg_slope),
            "intercept": float(seg_intercept),
            "fluid_type": fluid_guess,
            "equation": f"P = {seg_slope:.6f}*Depth + {seg_intercept:.3f}",
        })

    fluid_contacts = []
    for i in range(1, len(fluid_segments)):
        prev_seg = fluid_segments[i - 1]
        curr_seg = fluid_segments[i]
        if prev_seg["fluid_type"] != curr_seg["fluid_type"]:
            contact_depth = 0.5 * (prev_seg["end_depth"] + curr_seg["start_depth"])
            fluid_contacts.append({
                "depth": float(contact_depth),
                "from_fluid": prev_seg["fluid_type"],
                "to_fluid": curr_seg["fluid_type"],
                "type": f"{prev_seg['fluid_type']}/{curr_seg['fluid_type']}",
            })

    # Legacy by_fluid from stored fluid labels (if present), plus gradient-derived summary.
    by_fluid = []
    for fluid in sorted(set(v["fluid_type"] for v in valid)):
        arr = [(d["depth"], d["pressure"]) for d in valid if d["fluid_type"] == fluid]
        if len(arr) < 2:
            continue
        d = np.array([a[0] for a in arr], dtype=float)
        p = np.array([a[1] for a in arr], dtype=float)
        s, b = np.polyfit(d, p, 1)
        by_fluid.append({
            "fluid_type": fluid,
            "count": len(arr),
            "gradient": float(s),
            "intercept": float(b),
            "equation": f"P = {s:.6f}*Depth + {b:.3f}",
        })

    td = float(np.max(depths))
    d0 = float(np.min(depths))
    # Oilfield gradients in psi/ft.
    hydro_g = 0.433
    litho_g = 1.0
    gradient_lines = {
        "overall": {"gradient": float(slope), "intercept": float(intercept), "label": "RFT Best Fit"},
        "hydrostatic": {"gradient": hydro_g, "intercept": 0.0, "label": "Hydrostatic (0.433 psi/ft)"},
        "lithostatic": {"gradient": litho_g, "intercept": 0.0, "label": "Lithostatic (1.00 psi/ft)"},
        "segments": fluid_segments,
        "plot_depth_min": d0,
        "plot_depth_max": td,
    }

    regime_counts = {"normal": 0, "underpressure": 0, "overpressure": 0, "unknown": 0}
    for p in valid:
        regime_counts[p["pressure_regime"]] = regime_counts.get(p["pressure_regime"], 0) + 1

    # Formation pressure extraction and interval communication diagnostics.
    fp_points = []
    for p in valid:
        fp_points.append({
            "id": p["id"],
            "depth": p["depth"],
            "formation_pressure": p["pressure"],
            "gradient": p["pair_gradient"],
            "fluid_type": p["fluid_from_gradient"],
            "pressure_regime": p["pressure_regime"],
        })

    intervals = []
    for i in range(1, len(valid)):
        p1, p2 = valid[i - 1], valid[i]
        dz = p2["depth"] - p1["depth"]
        if abs(dz) < 1e-9:
            continue
        g = (p2["pressure"] - p1["pressure"]) / dz
        expected = 0.433 * dz
        delta = abs((p2["pressure"] - p1["pressure"]) - expected)
        state = "communicating" if delta <= 75.0 else "sealed"
        intervals.append({
            "top_depth": float(min(p1["depth"], p2["depth"])),
            "bottom_depth": float(max(p1["depth"], p2["depth"])),
            "gradient": float(g),
            "pressure_change": float(p2["pressure"] - p1["pressure"]),
            "expected_hydrostatic_change": float(expected),
            "pressure_deviation": float(delta),
            "communication": state,
        })

    classified_points = []
    for p in valid:
        classified_points.append({
            "id": p["id"],
            "depth": p["depth"],
            "pressure": p["pressure"],
            "fluid_type": p["fluid_type"],
            "fluid_from_gradient": p["fluid_from_gradient"],
            "pair_gradient": p["pair_gradient"],
            "pressure_regime": p["pressure_regime"],
        })

    return {
        "count": len(valid),
        "points": points,
        "classified_points": classified_points,
        "overall": overall,
        "by_fluid": by_fluid,
        "fluid_segments": fluid_segments,
        "fluid_contacts": fluid_contacts,
        "gradient_lines": gradient_lines,
        "pressure_regime_summary": regime_counts,
        "formation_pressure": {"points": fp_points, "intervals": intervals},
    }


@router.post("/{wid}/production", status_code=201)
def create_production_row(wid: int, data: dict, db: Session = Depends(get_db)):
    d = _parse_iso_date(data.get("date"))
    if not d:
        raise HTTPException(400, "date is required in YYYY-MM-DD format")
    row = ProductionData(
        well_id=wid,
        date=d,
        oil_rate=optional_float(data, "oil_rate"),
        gas_rate=optional_float(data, "gas_rate"),
        water_rate=optional_float(data, "water_rate"),
        water_cut=optional_float(data, "water_cut"),
        gor=optional_float(data, "gor"),
        bhp=optional_float(data, "bhp"),
        whp=optional_float(data, "whp"),
        choke_size=optional_float(data, "choke_size"),
        cumulative_oil=optional_float(data, "cumulative_oil"),
        cumulative_gas=optional_float(data, "cumulative_gas"),
        cumulative_water=optional_float(data, "cumulative_water"),
        notes=optional_str(data, "notes"),
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return {c.name: getattr(row, c.name) for c in ProductionData.__table__.columns}


@router.get("/{wid}/production")
def list_production_rows(wid: int, db: Session = Depends(get_db)):
    rows = db.query(ProductionData).filter(ProductionData.well_id == wid).order_by(ProductionData.date.asc(), ProductionData.id.asc()).all()
    result = []
    for r in rows:
        d = {c.name: getattr(r, c.name) for c in ProductionData.__table__.columns}
        if d.get("date") is not None:
            d["date"] = d["date"].isoformat()
        result.append(d)
    return result


@router.get("/{wid}/production/decline-curve")
def production_decline_curve(wid: int, db: Session = Depends(get_db)):
    rows = db.query(ProductionData).filter(ProductionData.well_id == wid).order_by(ProductionData.date.asc(), ProductionData.id.asc()).all()
    valid = [(r.date, float(r.oil_rate)) for r in rows if r.date is not None and r.oil_rate is not None and r.oil_rate > 0]
    if len(valid) < 3:
        return {"count": len(valid), "detail": "Need at least 3 positive oil-rate data points", "best_model": None}

    t0 = valid[0][0]
    t = np.array([(d - t0).days for d, _ in valid], dtype=float)
    q = np.array([v for _, v in valid], dtype=float)

    exp_fit = _fit_exponential_decline(t, q)
    hyp_fit = _fit_hyperbolic_decline(t, q)
    fits = [f for f in [exp_fit, hyp_fit] if f is not None]
    if not fits:
        return {"count": len(valid), "best_model": None}

    best = min(fits, key=lambda f: f["sse"])
    eur = _compute_eur(best)

    fitted_points = []
    qhat = best.get("qhat", np.array([]))
    for i, (d, q_obs) in enumerate(valid):
        fitted_points.append({
            "date": d.isoformat(),
            "t_days": float(t[i]),
            "q_obs": float(q_obs),
            "q_fit": float(qhat[i]) if i < len(qhat) else None,
        })

    payload = {
        "count": len(valid),
        "best_model": best["model"],
        "sse": float(best["sse"]),
        "eur_oil_bbl": eur,
        "fitted_points": fitted_points,
        "models": {
            "exponential": {
                "qi": exp_fit["qi"],
                "d": exp_fit["d"],
                "sse": exp_fit["sse"],
            } if exp_fit else None,
            "hyperbolic": {
                "qi": hyp_fit["qi"],
                "di": hyp_fit["di"],
                "b": hyp_fit["b"],
                "sse": hyp_fit["sse"],
            } if hyp_fit else None,
        },
    }
    return payload


@router.post("/{wid}/production/economics")
def production_economics(wid: int, data: dict, db: Session = Depends(get_db)):
    """Probabilistic decline forecast with NPV and payout assumptions."""
    rows = (
        db.query(ProductionData)
        .filter(ProductionData.well_id == wid)
        .order_by(ProductionData.date.asc(), ProductionData.id.asc())
        .all()
    )
    valid = [
        (r.date, float(r.oil_rate))
        for r in rows
        if r.date is not None and r.oil_rate is not None and r.oil_rate > 0
    ]
    if len(valid) < 3:
        raise HTTPException(400, "Need at least 3 positive oil-rate data points")
    try:
        result = evaluate_production_economics(
            [d for d, _ in valid],
            [q for _, q in valid],
            data or {},
        )
    except ValueError as exc:
        raise HTTPException(400, str(exc))
    return {"well_id": wid, **result}


@router.get("/{wid}/aliases")
def list_aliases(wid: int, db: Session = Depends(get_db)):
    aliases = db.query(CurveAlias).filter(CurveAlias.well_id == wid).all()
    return [{"original": a.original_mnemonic, "alias": a.alias_mnemonic} for a in aliases]


@router.post("/{wid}/aliases")
def save_aliases(wid: int, data: dict, db: Session = Depends(get_db)):
    items = data.get("aliases", [])
    if not isinstance(items, list):
        raise HTTPException(400, "aliases must be a list")
    prepared = []
    for i, item in enumerate(items):
        if not isinstance(item, dict):
            raise HTTPException(400, f"aliases[{i}] must be an object")
        prepared.append((require_str(item, "original"), require_str(item, "alias")))
    db.query(CurveAlias).filter(CurveAlias.well_id == wid).delete()
    for original, alias in prepared:
        db.add(CurveAlias(well_id=wid, original_mnemonic=original, alias_mnemonic=alias))
    db.commit()
    return {"status": "ok", "count": len(prepared)}


@router.post("/{wid}/splice")
def splice_curves(wid: int, data: dict, db: Session = Depends(get_db)):
    """Combine best intervals from multiple runs into a new composite run.
    data: {source_runs: [lr_id1, lr_id2], intervals: [{start, end, source_lr_id}], mnemonic: 'GR'}
    """
    well = db.query(Well).filter(Well.id == wid).first()
    if not well:
        raise HTTPException(404, "Well not found")
    source_runs = data.get("source_runs", [])
    intervals = data.get("intervals", [])
    mnemonic = data.get("mnemonic", "GR")
    if not source_runs or not intervals:
        raise HTTPException(400, "Need source_runs and intervals")

    # Load all source data
    run_data = {}
    for lr_id in source_runs:
        lr = db.query(LogRun).filter(LogRun.id == lr_id).first()
        if not lr:
            continue
        cd = db.query(CurveData).filter(CurveData.log_run_id == lr_id, CurveData.mnemonic == mnemonic).first()
        if cd:
            dept_cd = db.query(CurveData).filter(CurveData.log_run_id == lr_id, CurveData.mnemonic.in_(["DEPT", "DEPTH"])).first()
            if dept_cd:
                depth = np.frombuffer(dept_cd.data_binary, dtype=np.float64)
                values = np.frombuffer(cd.data_binary, dtype=np.float64)
                run_data[lr_id] = {"depth": depth, "values": values, "step": lr.step or 0.5}

    if not run_data:
        raise HTTPException(400, f"No data found for mnemonic {mnemonic}")

    # Build composite: use first run as base, splice intervals from others
    base_id = source_runs[0]
    base = run_data.get(base_id)
    if not base:
        raise HTTPException(400, "Base run not found")

    composite_depth = base["depth"].copy()
    composite_values = base["values"].copy()

    for index, interval in enumerate(intervals):
        src_id = interval.get("source_lr_id")
        try:
            start = float(interval.get("start"))
            end = float(interval.get("end"))
        except (TypeError, ValueError):
            raise HTTPException(
                status_code=400,
                detail=f"intervals[{index}] requires numeric start and end",
            )
        src = run_data.get(src_id)
        if not src:
            continue
        idxs = np.where((composite_depth >= start) & (composite_depth <= end))[0]
        if len(idxs) == 0:
            continue
        source_depth = np.asarray(src["depth"], dtype=np.float64)
        source_values = np.asarray(src["values"], dtype=np.float64)
        order = np.argsort(source_depth)
        source_depth = source_depth[order]
        source_values = source_values[order]
        if len(source_depth) == 0:
            continue
        target_depth = composite_depth[idxs]
        pos = np.clip(np.searchsorted(source_depth, target_depth), 0, len(source_depth) - 1)
        left = np.clip(pos - 1, 0, len(source_depth) - 1)
        right = pos
        choose = np.where(
            np.abs(target_depth - source_depth[left]) <= np.abs(target_depth - source_depth[right]),
            left, right,
        )
        within = np.abs(source_depth[choose] - target_depth) < (src["step"] * 2)
        composite_values[idxs[within]] = source_values[choose[within]]

    # Create new log run
    curves_def = [{"mnemonic": "DEPT", "unit": "FT", "description": "Depth"}, {"mnemonic": mnemonic, "unit": "", "description": f"Spliced {mnemonic}"}]
    lr = LogRun(
        well_id=wid, run_number=len(well.log_runs) + 1,
        filename=f"splice_{mnemonic}.las", las_version="2.0",
        start_depth=float(composite_depth[0]), stop_depth=float(composite_depth[-1]),
        step=float(base["step"]), num_points=len(composite_depth),
        curves_json=json.dumps(curves_def),
    )
    db.add(lr)
    db.flush()

    db.add(CurveData(log_run_id=lr.id, mnemonic="DEPT", unit="FT", num_points=len(composite_depth), data_binary=composite_depth.tobytes()))
    valid = composite_values[~np.isnan(composite_values)]
    db.add(CurveData(log_run_id=lr.id, mnemonic=mnemonic, num_points=len(composite_values), min_value=float(np.min(valid)) if len(valid) else None, max_value=float(np.max(valid)) if len(valid) else None, data_binary=composite_values.tobytes()))
    db.commit()
    return {"status": "ok", "log_run_id": lr.id, "points": len(composite_depth)}


@router.get("/{wid}/log-runs")
def list_log_runs(wid: int, db: Session = Depends(get_db)):
    runs = db.query(LogRun).filter(LogRun.well_id == wid).order_by(LogRun.run_number).all()
    result = []
    for lr in runs:
        curves = db.query(CurveData).filter(CurveData.log_run_id == lr.id).all()
        result.append({
            "id": lr.id, "run_number": lr.run_number, "filename": lr.filename,
            "las_version": lr.las_version, "start_depth": lr.start_depth,
            "stop_depth": lr.stop_depth, "step": lr.step, "num_points": lr.num_points,
            "curves": [c.mnemonic for c in curves],
        })
    return result


@router.get("/{wid}/trajectory")
def get_trajectory(wid: int, db: Session = Depends(get_db)):
    points = db.query(DeviationSurvey).filter(DeviationSurvey.well_id == wid).order_by(DeviationSurvey.md).all()
    if not points:
        return {"points": [], "tvd_computed": False}
    result = [{"md": p.md, "inc": p.inc, "azi": p.azi, "tvd": p.tvd, "northing": p.northing, "easting": p.easting} for p in points]
    return {"points": result, "tvd_computed": any(p.tvd is not None for p in points)}


@router.post("/{wid}/trajectory")
def save_trajectory(wid: int, data: dict, db: Session = Depends(get_db)):
    """Save deviation survey and compute TVD using minimum curvature method."""
    points = data.get("points", [])
    # Also accept flat arrays: {"md":[...], "inc":[...], "azi":[...]}
    if not points and "md" in data and "inc" in data and "azi" in data:
        md_arr = data["md"]
        inc_arr = data["inc"]
        azi_arr = data["azi"]
        try:
            same_length = len(md_arr) == len(inc_arr) == len(azi_arr)
        except TypeError:
            raise HTTPException(400, "md, inc, azi must be arrays")
        if not same_length:
            raise HTTPException(400, "md, inc, azi arrays must have equal length")
        points = [{"md": md_arr[i], "inc": inc_arr[i], "azi": azi_arr[i]} for i in range(len(md_arr))]
    if not points:
        raise HTTPException(400, "No points provided")
    if not isinstance(points, list):
        raise HTTPException(400, "points must be a list")

    # Clear existing
    db.query(DeviationSurvey).filter(DeviationSurvey.well_id == wid).delete()

    # Minimum curvature method
    computed = []
    tvd_total = 0.0
    north_total = 0.0
    east_total = 0.0
    prev_md = 0.0
    prev_inc = 0.0
    prev_azi = 0.0

    for i, p in enumerate(points):
        if not isinstance(p, dict):
            raise HTTPException(400, f"points[{i}] must be an object")
        try:
            md = float(p["md"])
            inc = float(p["inc"])  # degrees
            azi = float(p["azi"])  # degrees
        except (KeyError, TypeError, ValueError):
            raise HTTPException(400, f"points[{i}] requires numeric md, inc and azi")

        if i > 0:
            dmd = md - prev_md
            inc1_rad = np.radians(prev_inc)
            inc2_rad = np.radians(inc)
            azi1_rad = np.radians(prev_azi)
            azi2_rad = np.radians(azi)

            # Dog leg angle
            cos_dog = np.cos(inc2_rad - inc1_rad) - np.sin(inc1_rad) * np.sin(inc2_rad) * (1 - np.cos(azi2_rad - azi1_rad))
            cos_dog = max(-1, min(1, cos_dog))
            dog = np.arccos(cos_dog)

            # RF (ratio factor)
            if dog < 1e-6:
                rf = 1.0
            else:
                rf = 2 / dog * np.tan(dog / 2)

            # TVD increment
            d_tvd = dmd / 2 * (np.cos(inc1_rad) + np.cos(inc2_rad)) * rf
            d_north = dmd / 2 * (np.sin(inc1_rad) * np.cos(azi1_rad) + np.sin(inc2_rad) * np.cos(azi2_rad)) * rf
            d_east = dmd / 2 * (np.sin(inc1_rad) * np.sin(azi1_rad) + np.sin(inc2_rad) * np.sin(azi2_rad)) * rf

            tvd_total += d_tvd
            north_total += d_north
            east_total += d_east

        computed.append({"md": md, "inc": inc, "azi": azi, "tvd": round(tvd_total, 2), "northing": round(north_total, 2), "easting": round(east_total, 2)})
        prev_md, prev_inc, prev_azi = md, inc, azi

    for c in computed:
        db.add(DeviationSurvey(well_id=wid, **c))

    db.commit()
    return {"status": "ok", "points": len(computed), "tvd_range": [computed[0]["tvd"], computed[-1]["tvd"]]}


@router.get("/{wid}/data-table")
def get_data_table(
    wid: int,
    curves: str = "",
    from_depth: float = None,
    to_depth: float = None,
    limit: int = 500,
    db: Session = Depends(get_db),
):
    well = db.query(Well).filter(Well.id == wid).first()
    if not well:
        raise HTTPException(404, "Well not found")

    lr = db.query(LogRun).filter(LogRun.well_id == wid).order_by(LogRun.id.desc()).first()
    if not lr:
        raise HTTPException(404, "No log run")

    selected = [c.strip().upper() for c in str(curves or "").split(",") if c.strip()]
    if not selected:
        selected = ["DEPT"]

    depth_cd = db.query(CurveData).filter(
        CurveData.log_run_id == lr.id,
        CurveData.mnemonic.in_(["DEPT", "DEPTH", "MD", "TVD"]),
    ).first()
    if not depth_cd:
        raise HTTPException(404, "Depth curve not found")

    depth = np.frombuffer(depth_cd.data_binary, dtype=np.float64).copy()
    curve_arrays = {"DEPT": depth}

    for mnem in selected:
        if mnem in ("DEPT", "DEPTH", "MD", "TVD"):
            curve_arrays[mnem] = depth
            continue
        cd = db.query(CurveData).filter(CurveData.log_run_id == lr.id, CurveData.mnemonic == mnem).first()
        if not cd:
            raise HTTPException(404, f"Curve not found: {mnem}")
        curve_arrays[mnem] = np.frombuffer(cd.data_binary, dtype=np.float64).copy()

    columns = selected
    if not any(c in ("DEPT", "DEPTH", "MD", "TVD") for c in columns):
        columns = ["DEPT"] + columns

    min_len = min(len(curve_arrays[c]) for c in columns)
    for c in list(curve_arrays.keys()):
        curve_arrays[c] = curve_arrays[c][:min_len]

    depth_arr = curve_arrays["DEPT"]
    mask = np.ones(min_len, dtype=bool)
    if from_depth is not None:
        mask &= depth_arr >= float(from_depth)
    if to_depth is not None:
        mask &= depth_arr <= float(to_depth)

    idx = np.where(mask)[0]
    total_points = int(len(idx))

    limit = max(1, int(limit or 500))
    if len(idx) > limit:
        step = int(np.ceil(len(idx) / float(limit)))
        idx = idx[::step][:limit]

    def _clean_value(v):
        if np.isnan(v) or float(v) == -999.25:
            return None
        return round(float(v), 3)

    rows = []
    for i in idx:
        rows.append([_clean_value(curve_arrays[c][i]) for c in columns])

    return {
        "columns": columns,
        "rows": rows,
        "total_points": total_points,
        "shown_points": int(len(rows)),
    }


@router.get("/{wid}/formation-tester")
def formation_tester(wid: int, db: Session = Depends(get_db)):
    base = rft_pressure_gradient(wid, db)
    points = base.get("classified_points") or base.get("points") or []
    contacts = []
    for c in (base.get("fluid_contacts") or []):
        f, t = c.get("from_fluid", ""), c.get("to_fluid", "")
        label = "contact"
        if {f, t} == {"oil", "water"}:
            label = "OWC"
        elif {f, t} == {"gas", "oil"}:
            label = "GOC"
        contacts.append({
            "depth": c.get("depth"),
            "label": label,
            "type": c.get("type"),
            "from_fluid": f,
            "to_fluid": t,
        })
    return {
        "count": base.get("count", 0),
        "overall": base.get("overall"),
        "points": points,
        "fluid_segments": base.get("fluid_segments") or [],
        "contacts": contacts,
    }
