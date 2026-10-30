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

router = APIRouter(prefix="/api/wells", tags=["wells"])

# NumPy 2 removed np.trapz; 1.x has only trapz. Use whichever exists.
_trapezoid = getattr(np, "trapezoid", None) or getattr(np, "trapz")

try:
    from decline import (
        compute_eur as _compute_eur,
        fit_exponential as _fit_exponential_decline,
        fit_hyperbolic as _fit_hyperbolic_decline,
    )
except ImportError:
    from backend.decline import (
        compute_eur as _compute_eur,
        fit_exponential as _fit_exponential_decline,
        fit_hyperbolic as _fit_hyperbolic_decline,
    )
_trapezoid = getattr(np, "trapezoid", None) or getattr(np, "trapz")


def _to_float_or_none(value):
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    s = str(value).strip()
    if not s:
        return None
    # Keep numeric content and sign/dot
    cleaned = "".join(ch for ch in s if ch.isdigit() or ch in {".", "-", "+"})
    if cleaned in {"", ".", "-", "+", "-.", "+."}:
        return None
    try:
        return float(cleaned)
    except ValueError:
        return None


def _extract_las_coordinates(las):
    """Extract latitude/longitude from LAS well header/parameters when present."""
    lat = None
    lon = None

    # Try explicit attributes if parser is extended in future
    lat = _to_float_or_none(getattr(las.well, "latitude", None))
    lon = _to_float_or_none(getattr(las.well, "longitude", None))

    # Fallback: parse from location string (e.g. "29.1234, -95.5678")
    if lat is None or lon is None:
        loc = getattr(las.well, "location", "") or ""
        nums = []
        for token in loc.replace(";", " ").replace(",", " ").split():
            v = _to_float_or_none(token)
            if v is not None:
                nums.append(v)
        if len(nums) >= 2:
            if lat is None:
                lat = nums[0]
            if lon is None:
                lon = nums[1]

    # Fallback: parse common parameter mnemonics
    if lat is None or lon is None:
        for p in las.parameters:
            m = (p.mnemonic or "").strip().upper()
            v = _to_float_or_none(p.value)
            if v is None:
                continue
            if lat is None and m in {"LAT", "LATI", "LATITUDE"}:
                lat = v
            if lon is None and m in {"LON", "LONG", "LONGI", "LONGITUDE"}:
                lon = v

    # Basic sanity check
    if lat is not None and not (-90.0 <= lat <= 90.0):
        lat = None
    if lon is not None and not (-180.0 <= lon <= 180.0):
        lon = None

    return lat, lon






def _build_petro_summary(wid: int, params: dict, db: Session):
    well = db.query(Well).filter(Well.id == wid).first()
    latest = db.query(LogRun).filter(LogRun.well_id == wid).order_by(LogRun.id.desc()).first()
    gross = None
    if latest and latest.start_depth is not None and latest.stop_depth is not None:
        gross = float(latest.stop_depth - latest.start_depth)
    return {
        "well_id": wid,
        "well_name": well.name if well else None,
        "log_run_id": latest.id if latest else None,
        "interval": {
            "top": latest.start_depth if latest else None,
            "base": latest.stop_depth if latest else None,
            "gross": gross,
        },
        "petro_params": params,
        "notes": "Template applied and petrophysical defaults updated.",
    }


def _semantic_curves(db: Session, lr: LogRun):
    """Depth plus a raw/canonical name -> corrected array map for one run."""
    semantic = apply_run_semantics(db, lr, as_arrays=True)
    depth = np.asarray(semantic["depth"], dtype=np.float64)
    by_name = {}
    for meta in semantic["metadata"]["aliases"]:
        arr = semantic["curves"].get(meta["name"])
        if arr is not None:
            by_name[str(meta["name"]).upper()] = arr
            by_name[str(meta["raw"]).upper()] = arr
    return depth, by_name

def _first_curve(by_name: dict, names):
    for name in names:
        arr = by_name.get(str(name).upper())
        if arr is not None:
            return arr
    return None

def _aligned(arr, n: int):
    if arr is None:
        return np.full(n, np.nan, dtype=np.float64)
    arr = np.asarray(arr, dtype=np.float64)
    if len(arr) == n:
        return arr
    out = np.full(n, np.nan, dtype=np.float64)
    out[:min(len(arr), n)] = arr[:min(len(arr), n)]
    return out

def _safe_float(val, default=None):
    """Safely convert value to float, return default on failure."""
    if val is None or val == "":
        return default
    try:
        return float(val)
    except (ValueError, TypeError):
        return default



def _persist_non_las_runs(db: Session, well: Well, filename: str, parsed, source_format: str):
    created_runs = []
    for run in parsed.runs:
        curves_def = [
            {"mnemonic": c.mnemonic, "unit": c.unit, "description": c.description}
            for c in run.curves
        ]

        lr = LogRun(
            well_id=well.id,
            run_number=len(well.log_runs) + len(created_runs) + 1,
            filename=f"{filename}::{run.run_name}" if len(parsed.runs) > 1 else filename,
            las_version=run.version,
            start_depth=run.start_depth,
            stop_depth=run.stop_depth,
            step=run.step,
            null_value=run.null_value,
            num_points=int(len(run.depth)),
            curves_json=json.dumps(curves_def),
            parameters_json=json.dumps(run.parameters or []),
        )
        db.add(lr)
        db.flush()

        for curve in run.curves:
            arr = run.data.get(curve.mnemonic)
            if arr is None:
                continue
            arr = np.asarray(arr, dtype=np.float64)
            valid = arr[~np.isnan(arr)]
            db.add(CurveData(
                log_run_id=lr.id,
                mnemonic=curve.mnemonic,
                unit=curve.unit,
                description=curve.description,
                num_points=len(arr),
                min_value=float(np.min(valid)) if len(valid) else None,
                max_value=float(np.max(valid)) if len(valid) else None,
                data_binary=arr.tobytes(),
            ))

        created_runs.append(lr)

    if parsed.well_name and (not well.name or well.name.startswith("Well")):
        well.name = parsed.well_name
    if parsed.uwi and not well.uwi:
        well.uwi = parsed.uwi
    if created_runs:
        well.total_depth = max((r.stop_depth or 0.0) for r in created_runs)

    return created_runs


COMPLETION_COMPONENT_TYPES = {"casing", "tubing", "packer", "perforation", "screen", "liner", "cement", "pump", "valve"}


def _parse_iso_date(value):
    if value is None:
        return None
    if isinstance(value, datetime.date):
        return value
    try:
        return datetime.datetime.strptime(str(value).strip(), "%Y-%m-%d").date()
    except Exception:
        return None








def _hilbert_transform(x: np.ndarray) -> np.ndarray:
    """Compute Hilbert transform using FFT (SciPy-free)."""
    n = len(x)
    Xf = np.fft.fft(x)
    h = np.zeros(n)
    if n % 2 == 0:
        h[0] = 1
        h[n // 2] = 1
        h[1:n // 2] = 2
    else:
        h[0] = 1
        h[1:(n + 1) // 2] = 2
    analytic = np.fft.ifft(Xf * h)
    return np.imag(analytic)




@router.get("/")
def list_wells(request: Request, project_id: int = None, db: Session = Depends(get_db)):
    q = db.query(Well)
    if project_id:
        q = q.filter(Well.project_id == project_id)
    wells = q.all()
    subject = request_subject(request)
    role = request_role(request)
    wells = [w for w in wells if can_access_well(db, w.id, subject, role)]
    result = []
    for w in wells:
        d = {c.name: getattr(w, c.name) for c in Well.__table__.columns}
        d["log_run_count"] = len(w.log_runs)
        d["formation_top_count"] = len(w.formation_tops)
        result.append(d)
    return result


@router.post("/", status_code=201)
def create_well(data: dict, db: Session = Depends(get_db)):
    # Was Well(**data), which let a client choose the primary key and write any
    # column. Only these fields are part of the request contract.
    project_id = require_int(data, "project_id")
    if not db.query(Project.id).filter(Project.id == project_id).first():
        raise HTTPException(400, "project_id does not exist")
    w = Well(
        project_id=project_id,
        name=require_str(data, "name"),
        uwi=optional_str(data, "uwi"),
        api_number=optional_str(data, "api_number"),
        latitude=optional_float(data, "latitude"),
        longitude=optional_float(data, "longitude"),
        elevation=optional_float(data, "elevation"),
        total_depth=optional_float(data, "total_depth"),
        depth_unit=optional_str(data, "depth_unit", "FT"),
        unit_system=optional_str(data, "unit_system", "field").lower(),
        operator=optional_str(data, "operator"),
        field_name=optional_str(data, "field_name"),
        spud_date=optional_str(data, "spud_date"),
    )
    if w.unit_system not in {"field", "si"}:
        raise HTTPException(400, "unit_system must be 'field' or 'si'")
    db.add(w)
    db.commit()
    db.refresh(w)
    return {c.name: getattr(w, c.name) for c in Well.__table__.columns}


@router.get("/{wid}")
def get_well(wid: int, db: Session = Depends(get_db)):
    w = db.query(Well).filter(Well.id == wid).first()
    if not w:
        raise HTTPException(404, "Well not found")
    d = {c.name: getattr(w, c.name) for c in Well.__table__.columns}
    d["log_runs"] = [{c.name: getattr(lr, c.name) for c in LogRun.__table__.columns} for lr in w.log_runs]
    d["formation_tops"] = [{c.name: getattr(ft, c.name) for c in FormationTop.__table__.columns} for ft in w.formation_tops]
    return d


@router.delete("/{wid}", status_code=204)
def delete_well(wid: int, db: Session = Depends(get_db)):
    w = db.query(Well).filter(Well.id == wid).first()
    if not w:
        raise HTTPException(404, "Well not found")
    _delete_well_data(db, wid)
    db.delete(w)
    db.commit()


@router.put("/{wid}")
def update_well(wid: int, data: dict, db: Session = Depends(get_db)):
    w = db.query(Well).filter(Well.id == wid).first()
    if not w:
        raise HTTPException(404, "Well not found")
    # Was a bare setattr loop: {"name": null} hit the NOT NULL constraint and
    # surfaced as a 500.
    for field, value in pick_typed(
        data,
        strings=("name", "uwi", "api_number", "operator", "field_name",
                 "depth_unit", "spud_date", "unit_system"),
        floats=("latitude", "longitude", "elevation", "total_depth"),
        nullable=("latitude", "longitude", "elevation", "total_depth"),
    ).items():
        setattr(w, field, value)
    if (w.unit_system or "field").lower() not in {"field", "si"}:
        raise HTTPException(400, "unit_system must be 'field' or 'si'")
    w.unit_system = (w.unit_system or "field").lower()
    db.commit()
    db.refresh(w)
    return {c.name: getattr(w, c.name) for c in Well.__table__.columns}
















def _require_well_admin(db: Session, wid: int, request: Request) -> None:
    if request_role(request) == "admin":
        return
    subject = request_subject(request)
    row = db.query(Well.project_id).filter(Well.id == wid).first()
    if row is not None and membership_role(db, int(row[0]), subject) == "admin":
        return
    if well_membership_role(db, wid, subject) == "admin":
        return
    raise HTTPException(403, "well or project admin role required")


@router.get("/{wid}/members")
def list_well_members(wid: int, db: Session = Depends(get_db)):
    if not db.query(Well.id).filter(Well.id == wid).first():
        raise HTTPException(404, "Well not found")
    rows = (
        db.query(WellMember)
        .filter(WellMember.well_id == wid)
        .order_by(WellMember.id.asc())
        .all()
    )
    return [
        {
            "id": row.id,
            "well_id": row.well_id,
            "subject": row.subject,
            "role": row.role,
            "created_at": row.created_at.isoformat() if row.created_at else "",
        }
        for row in rows
    ]


@router.post("/{wid}/members", status_code=201)
def add_well_member(
    wid: int,
    data: dict,
    request: Request,
    db: Session = Depends(get_db),
    _role: str = Depends(require_interpreter),
):
    if not db.query(Well.id).filter(Well.id == wid).first():
        raise HTTPException(404, "Well not found")
    _require_well_admin(db, wid, request)
    subject = str(data.get("subject") or "").strip()
    if not subject:
        raise HTTPException(400, "subject is required")
    role = str(data.get("role") or "viewer").strip().lower()
    if role not in MEMBER_ROLES:
        raise HTTPException(400, "role must be viewer, interpreter or admin")
    existing = (
        db.query(WellMember)
        .filter(WellMember.well_id == wid, WellMember.subject == subject)
        .first()
    )
    if existing:
        existing.role = role
        db.commit()
        return {"id": existing.id, "well_id": wid, "subject": subject, "role": role}
    row = WellMember(well_id=wid, subject=subject, role=role)
    db.add(row)
    db.commit()
    db.refresh(row)
    return {"id": row.id, "well_id": wid, "subject": subject, "role": row.role}


@router.delete("/{wid}/members/{subject}", status_code=204)
def remove_well_member(
    wid: int,
    subject: str,
    request: Request,
    force: bool = False,
    db: Session = Depends(get_db),
    _role: str = Depends(require_interpreter),
):
    _require_well_admin(db, wid, request)
    row = (
        db.query(WellMember)
        .filter(WellMember.well_id == wid, WellMember.subject == subject)
        .first()
    )
    if not row:
        raise HTTPException(404, "Member not found")
    remaining = (
        db.query(WellMember)
        .filter(WellMember.well_id == wid, WellMember.id != row.id)
        .count()
    )
    if remaining == 0 and not force:
        raise HTTPException(
            400,
            "cannot remove the last well member; pass force=true to inherit the project again",
        )
    db.delete(row)
    db.commit()




@router.post("/{wid}/snapshots", status_code=201)
def create_snapshot(wid: int, data: dict = None, db: Session = Depends(get_db)):
    well = db.query(Well).filter(Well.id == wid).first()
    if not well:
        raise HTTPException(404, "Well not found")
    snap_id = str(uuid.uuid4())

    tops = [{c.name: getattr(t, c.name) for c in FormationTop.__table__.columns}
            for t in db.query(FormationTop).filter(FormationTop.well_id == wid).order_by(FormationTop.depth).all()]
    zones = [{c.name: getattr(z, c.name) for c in Zone.__table__.columns}
             for z in db.query(Zone).filter(Zone.well_id == wid).order_by(Zone.sort_order.asc()).all()]
    params = db.query(PetroParams).filter(PetroParams.well_id == wid).first()
    params_dict = {c.name: getattr(params, c.name) for c in PetroParams.__table__.columns} if params else {}

    def _append(snapshots):
        payload = {
            "snapshot_id": snap_id,
            "well_id": wid,
            "well_name": well.name,
            "created_at": utcnow().isoformat() + "Z",
            "label": (data or {}).get("label", f"snapshot-{len(snapshots)+1}"),
            "snapshot_version": 1,
            "approved": False,
            "approved_by": None,
            "approved_at": None,
            "approval_status": "pending",
            "approval_history": [],
            "tops": tops,
            "zones": zones,
            "petro_params": params_dict,
        }
        snapshots.append(payload)
        return payload

    return _mutate_snapshots(wid, _append)

@router.get("/{wid}/snapshots")
def list_snapshots(wid: int):
    snaps = _load_snapshots(wid)
    return {"count": len(snaps), "snapshots": snaps}


@router.get("/{wid}/lock-status")
def lock_status(wid: int):
    return _get_well_lock(wid)


@router.get("/{wid}/template-lock-status")
def template_lock_status(wid: int, db: Session = Depends(get_db)):
    payload, signature = _snapshot_template_signature(db, wid)
    lock = _get_template_lock(wid)
    return {
        **lock,
        "well_id": wid,
        "current_signature": signature,
        "signature_matches": (lock.get("signature") == signature) if lock.get("locked") else None,
        "current_template": payload.get("template", "custom"),
    }


@router.post("/{wid}/template-lock")
def lock_template(wid: int, data: dict = None, db: Session = Depends(get_db), _role: str = Depends(require_interpreter)):
    actor = (data or {}).get("actor", _role)
    reason = (data or {}).get("reason", "Template QA signed")
    payload, signature = _snapshot_template_signature(db, wid)

    lock = {
        "locked": True,
        "locked_by": actor,
        "locked_at": utcnow().isoformat() + "Z",
        "reason": reason,
        "signature": signature,
        "signed_template": payload.get("template", "custom"),
        "signed_params": payload,
    }
    _set_template_lock(wid, lock)
    _log_audit(db, "template_lock", "well", entity_id=wid, well_id=wid,
               details=f"locked_by={actor};template={payload.get('template','custom')};sig={signature[:12]}")
    return {**lock, "well_id": wid}


@router.post("/{wid}/template-unlock")
def unlock_template(wid: int, data: dict = None, db: Session = Depends(get_db), _role: str = Depends(require_admin)):
    actor = (data or {}).get("actor", _role)
    cleared = _default_template_lock()
    _set_template_lock(wid, cleared)
    _log_audit(db, "template_unlock", "well", entity_id=wid, well_id=wid, details=f"unlocked_by={actor}")
    return {**cleared, "well_id": wid, "unlocked_by": actor}


@router.post("/{wid}/unlock")
def unlock_well(wid: int, data: dict = None, _role: str = Depends(require_admin)):
    actor = (data or {}).get("actor", _role)
    _set_well_lock(wid, False, actor=actor, snapshot_id=None)
    return _get_well_lock(wid)


@router.get("/{wid}/snapshots/{snapshot_id}")
def get_snapshot(wid: int, snapshot_id: str):
    snaps = _load_snapshots(wid)
    for s in snaps:
        if s.get("snapshot_id") == snapshot_id:
            return s
    raise HTTPException(404, "Snapshot not found")


@router.post("/{wid}/snapshots/{snapshot_id}/approve")
def approve_snapshot(
    wid: int,
    snapshot_id: str,
    data: dict = None,
    _role: str = Depends(require_interpreter),
):
    actor = (data or {}).get("approved_by", _role)
    expected_version = (data or {}).get("expected_version")

    def _approve(snaps):
        for s in snaps:
            if s.get("snapshot_id") != snapshot_id:
                continue
            current_version = int(s.get("snapshot_version") or 1)
            if expected_version is not None and int(expected_version) != current_version:
                raise HTTPException(
                    status_code=409,
                    detail={
                        "error": "snapshot version conflict",
                        "expected_version": int(expected_version),
                        "current_version": current_version,
                        "snapshot_id": snapshot_id,
                    },
                )

            approved_at = utcnow().isoformat() + "Z"
            s["approved"] = True
            s["approved_by"] = actor
            s["approved_at"] = approved_at
            s["approval_status"] = "approved"
            s["snapshot_version"] = current_version + 1
            history = s.get("approval_history") if isinstance(s.get("approval_history"), list) else []
            history.append(
                {
                    "action": "approve",
                    "actor": actor,
                    "at": approved_at,
                    "from_version": current_version,
                    "to_version": current_version + 1,
                }
            )
            s["approval_history"] = history
            return s
        return None

    result = _mutate_snapshots(wid, _approve)
    if result is None:
        raise HTTPException(404, "Snapshot not found")
    _set_well_lock(wid, True, actor=actor, snapshot_id=snapshot_id)
    return result

@router.get("/{wid}/snapshots/{base_id}/diff/{target_id}")
def diff_snapshot(wid: int, base_id: str, target_id: str):
    snaps = _load_snapshots(wid)
    base = next((s for s in snaps if s.get("snapshot_id") == base_id), None)
    target = next((s for s in snaps if s.get("snapshot_id") == target_id), None)
    if not base or not target:
        raise HTTPException(404, "Snapshot not found")

    def key_tops(items):
        return {(i.get("formation_name"), round(float(i.get("depth", 0)), 3)): i for i in items}

    btops = key_tops(base.get("tops", []))
    ttops = key_tops(target.get("tops", []))
    added_tops = [v for k, v in ttops.items() if k not in btops]
    removed_tops = [v for k, v in btops.items() if k not in ttops]

    bz = {(z.get("name"), z.get("top_depth"), z.get("base_depth")) for z in base.get("zones", [])}
    tz = {(z.get("name"), z.get("top_depth"), z.get("base_depth")) for z in target.get("zones", [])}

    changed_params = {}
    bp = base.get("petro_params", {})
    tp = target.get("petro_params", {})
    for k in sorted(set(bp.keys()) | set(tp.keys())):
        if bp.get(k) != tp.get(k):
            changed_params[k] = {"from": bp.get(k), "to": tp.get(k)}

    return {
        "base": base_id,
        "target": target_id,
        "added_tops": added_tops,
        "removed_tops": removed_tops,
        "added_zones": list(tz - bz),
        "removed_zones": list(bz - tz),
        "changed_petro_params": changed_params,
    }






@router.get("/{wid}/petro-params")
def get_petro_params(wid: int, db: Session = Depends(get_db)):
    pp = db.query(PetroParams).filter(PetroParams.well_id == wid).first()
    lock = _get_template_lock(wid)
    if not pp:
        base = {"well_id": wid, "saturation_model": "archie", "a": 1.0, "m": 2.0, "n": 2.0, "rw": 0.1,
                "vsh_cutoff": 0.35, "phie_cutoff": 0.10, "sw_cutoff": 0.60, "template": "custom"}
        base["template_lock"] = lock
        return base
    out = {c.name: getattr(pp, c.name) for c in PetroParams.__table__.columns}
    out["template_lock"] = lock
    return out


@router.post("/{wid}/petro-params")
def save_petro_params(wid: int, data: dict, db: Session = Depends(get_db)):
    tlock = _get_template_lock(wid)
    if tlock.get("locked"):
        raise HTTPException(423, "Template is locked; unlock required before edits")

    existing = db.query(PetroParams).filter(PetroParams.well_id == wid).first()
    values = pick_typed(
        data,
        strings=("saturation_model", "template"),
        floats=("a", "m", "n", "rw", "vsh_cutoff", "phie_cutoff", "sw_cutoff",
                "gr_clean", "gr_shale", "phi_sh"),
    )
    if existing:
        for field, value in values.items():
            setattr(existing, field, value)
    else:
        db.add(PetroParams(well_id=wid, **values))
    db.commit()
    _, signature_after = _snapshot_template_signature(db, wid)
    _log_audit(db, "save_petro_params", "well", entity_id=wid, well_id=wid,
               details=f"template={data.get('template','custom')};sig={signature_after[:12]}")
    return {"status": "ok", "signature": signature_after}

@router.post("/{wid}/petro-calibration")
def calibrate_petro_params(wid: int, data: dict, db: Session = Depends(get_db)):
    """Fit gr_clean/gr_shale/phi_sh against reference curves.

    Body: {gr: [...], vsh_ref: [...], phi_raw: [...], phi_ref: [...], save: bool}.
    phi_raw is the interpreter's density-neutron blend before shale correction;
    see backend/petro_calibration.py. Returns fitted params + MAE vs defaults.
    """
    import numpy as _np
    try:
        from petro_calibration import calibrate_phi_sh, calibrate_vsh
    except ImportError:
        from backend.petro_calibration import calibrate_phi_sh, calibrate_vsh
    tlock = _get_template_lock(wid)
    if tlock.get("locked"):
        raise HTTPException(423, "Template is locked; unlock required before edits")
    if not db.query(Well.id).filter(Well.id == wid).first():
        raise HTTPException(404, "Well not found")
    try:
        gr = _np.asarray(data.get("gr", []), dtype=float)
        vsh_ref = _np.asarray(data.get("vsh_ref", []), dtype=float)
        phi_raw = _np.asarray(data.get("phi_raw", []), dtype=float)
        phi_ref = _np.asarray(data.get("phi_ref", []), dtype=float)
    except (TypeError, ValueError):
        raise HTTPException(400, "gr/vsh_ref/phi_raw/phi_ref must be numeric arrays")
    try:
        vsh_fit = calibrate_vsh(gr, vsh_ref)
        phi_fit = calibrate_phi_sh(phi_raw, vsh_ref, phi_ref)
    except ValueError as exc:
        raise HTTPException(400, str(exc))
    saved = False
    if bool(data.get("save")):
        existing = db.query(PetroParams).filter(PetroParams.well_id == wid).first()
        values = {
            "gr_clean": vsh_fit["gr_clean"],
            "gr_shale": vsh_fit["gr_shale"],
            "phi_sh": phi_fit["phi_sh"],
        }
        if existing:
            for field, value in values.items():
                setattr(existing, field, value)
        else:
            db.add(PetroParams(well_id=wid, **values))
        db.commit()
        saved = True
        _, signature_after = _snapshot_template_signature(db, wid)
        _log_audit(db, "calibrate_petro_params", "well", entity_id=wid, well_id=wid,
                   details=f"gr_clean={values['gr_clean']};gr_shale={values['gr_shale']};phi_sh={values['phi_sh']}")
    return {"vsh": vsh_fit, "phi_sh": phi_fit, "saved": saved}
















































































































@router.post("/{wid}/image-log")
def image_log(wid: int, data: dict, db: Session = Depends(get_db)):
    """Generate a resistivity image log display from available curves.
    Maps curve values to a color scale for image-like visualization.
    Uses RT/RESD curve values mapped to a blue-white-red color scale.
    """
    lr_id = data.get("log_run_id")
    lr = db.query(LogRun).filter(LogRun.id == lr_id).first() if lr_id else \
         db.query(LogRun).filter(LogRun.well_id == wid).order_by(LogRun.num_points.desc()).first()
    if not lr:
        raise HTTPException(404, "No log run")

    curve_name = data.get("curve", "RT")
    n_bins = max(4, min(int(data.get("n_bins", 72)), 360))  # angular bins around borehole

    cd = db.query(CurveData).filter(CurveData.log_run_id == lr.id, CurveData.mnemonic == curve_name).first()
    if not cd:
        # Try alternatives
        cd = db.query(CurveData).filter(CurveData.log_run_id == lr.id, CurveData.mnemonic.in_(["RT", "RESD", "RILD", "ILD"])).first()
    if not cd:
        raise HTTPException(400, "No resistivity curve found")

    dept_cd = db.query(CurveData).filter(CurveData.log_run_id == lr.id, CurveData.mnemonic.in_(["DEPT", "DEPTH"])).first()
    arr = np.frombuffer(cd.data_binary, dtype=np.float64).copy()
    dept = np.frombuffer(dept_cd.data_binary, dtype=np.float64).copy() if dept_cd else np.arange(len(arr)) * 0.5

    # Log-scale the resistivity for better dynamic range
    arr_log = np.where(arr > 0, np.log10(arr), np.nan)

    valid = arr_log[~np.isnan(arr_log)]
    if len(valid) == 0:
        raise HTTPException(400, "No valid data in curve")

    v_min = float(np.percentile(valid, 5))
    v_max = float(np.percentile(valid, 95))

    # Normalize to 0-1
    normalized = (arr_log - v_min) / (v_max - v_min) if v_max > v_min else np.zeros_like(arr_log)
    normalized = np.clip(normalized, 0, 1)

    # Generate image data: each depth sample → n_bins angular values
    # Simulate borehole image by adding some angular variation
    step = max(1, len(dept) // 1000)
    image_data = []
    depths_out = []

    for i in range(0, len(dept), step):
        if np.isnan(normalized[i]):
            continue
        base_val = normalized[i]
        # Create angular variation (simulate borehole breakout/tool eccentricity)
        row = []
        for b in range(n_bins):
            # Add sinusoidal variation + noise
            angle = (b / n_bins) * 2 * np.pi
            variation = 0.1 * np.sin(angle + i * 0.01) + np.random.normal(0, 0.03)
            val = np.clip(base_val + variation, 0, 1)
            # Map to RGB: blue(0) → white(0.5) → red(1)
            if val < 0.5:
                r = int(val * 2 * 255)
                g = int(val * 2 * 255)
                b_c = 255
            else:
                r = 255
                g = int((1 - val) * 2 * 255)
                b_c = int((1 - val) * 2 * 255)
            row.append([r, g, b_c])
        image_data.append(row)
        depths_out.append(round(float(dept[i]), 1))

    return {
        "depth": depths_out,
        "image": image_data,
        "n_bins": n_bins,
        "params": {"curve": cd.mnemonic, "v_min": round(10**v_min, 2), "v_max": round(10**v_max, 2)},
        "color_scale": "blue-white-red (log resistivity)",
    }


@router.post("/{wid}/seismic-tie")
def seismic_tie(wid: int, payload: dict, db: Session = Depends(get_db)):
    lr = db.query(LogRun).filter(LogRun.well_id == wid).order_by(LogRun.num_points.desc()).first()
    if not lr:
        raise HTTPException(404, "No log run")
    cds = db.query(CurveData).filter(CurveData.log_run_id == lr.id).all()
    cmap = {c.mnemonic: c for c in cds}
    rhob_cd = cmap.get("RHOB")
    dt_cd = cmap.get("DT")
    dept_cd = cmap.get("DEPT") or cmap.get("DEPTH")
    if not rhob_cd or not dt_cd:
        raise HTTPException(400, "RHOB and DT curves are required")

    rhob = np.frombuffer(rhob_cd.data_binary, dtype=np.float64).copy()
    dt = np.frombuffer(dt_cd.data_binary, dtype=np.float64).copy()
    n = int(min(len(rhob), len(dt)))
    if dept_cd:
        depth = np.frombuffer(dept_cd.data_binary, dtype=np.float64).copy()[:n]
    else:
        depth = np.linspace(float(lr.start_depth or 0.0), float(lr.stop_depth or 0.0), n)
    rhob, dt = rhob[:n], dt[:n]

    vel = np.where(dt > 0, 1e6 / dt, np.nan)
    ai = rhob * vel
    ai = np.where(np.isfinite(ai), ai, np.nan)

    rc = np.zeros(n)
    for i in range(1, n):
        a0, a1 = ai[i - 1], ai[i]
        if np.isfinite(a0) and np.isfinite(a1) and abs(a1 + a0) > 1e-12:
            rc[i] = (a1 - a0) / (a1 + a0)
        else:
            rc[i] = 0.0

    freq = float(payload.get("frequency_hz", 30.0) or 30.0)
    freq = max(20.0, min(60.0, freq))
    dt_s = 0.001
    t = np.arange(-0.064, 0.064 + dt_s, dt_s)
    pf = np.pi * freq * t
    wavelet = (1.0 - 2.0 * (pf ** 2)) * np.exp(-(pf ** 2))
    synthetic = np.convolve(rc, wavelet, mode="same")

    step = max(1, int(n / 1200))
    return {
        "depth": np.where(np.isnan(depth[::step]), None, depth[::step]).tolist(),
        "ai": np.where(np.isnan(ai[::step]), None, ai[::step]).tolist(),
        "rc": rc[::step].tolist(),
        "synthetic": synthetic[::step].tolist(),
        "frequency_hz": freq,
        "wavelet": {
            "time": t.tolist(),
            "amplitude": wavelet.tolist(),
        },
    }


@router.get("/{wid}/image-log")
def image_log_get(wid: int, db: Session = Depends(get_db)):
    lr = db.query(LogRun).filter(LogRun.well_id == wid).order_by(LogRun.num_points.desc()).first()
    if not lr:
        raise HTTPException(404, "No log run")
    cds = db.query(CurveData).filter(CurveData.log_run_id == lr.id).all()
    cmap = {c.mnemonic: c for c in cds}
    dept_cd = cmap.get("DEPT") or cmap.get("DEPTH")
    amp_cd = cmap.get("FMI") or cmap.get("OBI") or cmap.get("RT") or cmap.get("RESD") or cmap.get("GR")
    if not amp_cd:
        raise HTTPException(400, "No usable curve for image generation")

    amp = np.frombuffer(amp_cd.data_binary, dtype=np.float64).copy()
    depth = np.frombuffer(dept_cd.data_binary, dtype=np.float64).copy() if dept_cd else np.arange(len(amp), dtype=float)
    n = min(len(amp), len(depth))
    amp, depth = amp[:n], depth[:n]

    if amp_cd.mnemonic == "GR":
        valid_gr = amp[np.isfinite(amp)]
        med = float(np.nanmedian(valid_gr)) if len(valid_gr) else 80.0
        amp = np.where(np.isfinite(amp), amp, med)
        amp = (amp - np.nanmin(amp)) / max(np.nanmax(amp) - np.nanmin(amp), 1e-9)
        amp = 1.0 - amp

    valid = amp[np.isfinite(amp)]
    if len(valid) == 0:
        raise HTTPException(400, "No valid samples for image log")
    lo, hi = np.percentile(valid, [5, 95])
    norm = np.clip((amp - lo) / max(hi - lo, 1e-9), 0.0, 1.0)

    n_bins = 72
    step = max(1, int(n / 1200))
    image = []
    depths = []
    for i in range(0, n, step):
        if not np.isfinite(norm[i]):
            continue
        base = float(norm[i])
        row = []
        for b in range(n_bins):
            ang = (2.0 * np.pi * b) / n_bins
            val = np.clip(base + 0.14 * np.sin(ang + i * 0.02) + 0.05 * np.cos(2 * ang), 0.0, 1.0)
            row.append(val)
        image.append(row)
        depths.append(float(depth[i]))

    return {
        "depth": depths,
        "image": image,
        "n_bins": n_bins,
        "curve_used": amp_cd.mnemonic,
        "synthetic": amp_cd.mnemonic == "GR",
    }










