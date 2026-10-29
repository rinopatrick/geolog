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
    from routers.wells import (
        _to_float_or_none, _extract_las_coordinates, _build_petro_summary,
        _semantic_curves, _first_curve, _aligned, _safe_float,
        _persist_non_las_runs, _parse_iso_date, _fit_exponential_decline,
        _fit_hyperbolic_decline, _compute_eur, _hilbert_transform,
        _require_well_admin,
    )
except ImportError:
    from backend.routers.wells import (
        _to_float_or_none, _extract_las_coordinates, _build_petro_summary,
        _semantic_curves, _first_curve, _aligned, _safe_float,
        _persist_non_las_runs, _parse_iso_date, _fit_exponential_decline,
        _fit_hyperbolic_decline, _compute_eur, _hilbert_transform,
        _require_well_admin,
    )

router = APIRouter(prefix="/api/wells", tags=["wells"])


@router.post("/{wid}/upload-las")
async def upload_las(wid: int, file: UploadFile = File(...), db: Session = Depends(get_db)):
    """Upload a LAS file and attach it to a well."""
    well = db.query(Well).filter(Well.id == wid).first()
    if not well:
        raise HTTPException(404, "Well not found")

    content = await read_upload(file)
    if len(content) == 0:
        raise HTTPException(400, "Empty file")

    try:
        text = content.decode('utf-8', errors='replace')
        las = LASParser.parse_string(text)
    except Exception as e:
        raise HTTPException(400, f"Failed to parse LAS file: {str(e)}")

    # Create log run
    curves_def = [
        {"mnemonic": c.mnemonic, "unit": c.unit, "description": c.description}
        for c in las.curves
    ]
    params_def = [
        {"mnemonic": p.mnemonic, "unit": p.unit, "value": p.value}
        for p in las.parameters
    ]

    log_run = LogRun(
        well_id=wid,
        run_number=len(well.log_runs) + 1,
        filename=file.filename or "unknown.las",
        las_version=las.version,
        start_depth=las.well.start,
        stop_depth=las.well.stop,
        step=las.well.step,
        null_value=las.well.null,
        num_points=len(las.depth),
        curves_json=json.dumps(curves_def),
        parameters_json=json.dumps(params_def),
    )
    db.add(log_run)
    db.flush()

    # Store curve data as binary numpy arrays
    for curve in las.curves:
        arr = las.data.get(curve.mnemonic)
        if arr is not None:
            valid = arr[~np.isnan(arr)]
            curve_record = CurveData(
                log_run_id=log_run.id,
                mnemonic=curve.mnemonic,
                unit=curve.unit,
                description=curve.description,
                num_points=len(arr),
                min_value=float(np.min(valid)) if len(valid) > 0 else None,
                max_value=float(np.max(valid)) if len(valid) > 0 else None,
                data_binary=arr.tobytes(),
            )
            db.add(curve_record)

    # Update well info from LAS if not set
    if las.well.well_name and not well.name:
        well.name = las.well.well_name
    if las.well.uwi and not well.uwi:
        well.uwi = las.well.uwi
    if las.well.operator and not well.operator:
        well.operator = las.well.operator
    if las.well.start:
        well.total_depth = las.well.stop

    lat, lon = _extract_las_coordinates(las)
    if lat is not None:
        well.latitude = lat
    if lon is not None:
        well.longitude = lon

    db.commit()

    return {
        "status": "ok",
        "log_run_id": log_run.id,
        "filename": file.filename,
        "curves": [c.mnemonic for c in las.curves],
        "num_points": len(las.depth),
        "start_depth": las.well.start,
        "stop_depth": las.well.stop,
        "step": las.well.step,
    }


@router.post("/{wid}/upload-dlis")
async def upload_dlis(wid: int, file: UploadFile = File(...), db: Session = Depends(get_db)):
    """Upload DLIS file and attach one/many frame-runs to a well."""
    well = db.query(Well).filter(Well.id == wid).first()
    if not well:
        raise HTTPException(404, "Well not found")

    content = await read_upload(file)
    if len(content) == 0:
        raise HTTPException(400, "Empty file")

    try:
        parsed = parse_dlis_content(content, file.filename or "upload.dlis")
    except Exception as e:
        raise HTTPException(400, f"Failed to parse DLIS file: {str(e)}")

    created = _persist_non_las_runs(db, well, file.filename or "unknown.dlis", parsed, "DLIS")
    if not created:
        raise HTTPException(400, "No frame data found in DLIS")
    db.commit()

    primary = parsed.runs[0]
    return {
        "status": "ok",
        "source_format": "DLIS",
        "log_run_id": created[0].id,
        "log_run_ids": [r.id for r in created],
        "filename": file.filename,
        "runs_created": len(created),
        "curves": [c.mnemonic for c in primary.curves],
        "num_points": int(primary.depth.size),
        "start_depth": primary.start_depth,
        "stop_depth": primary.stop_depth,
        "step": primary.step,
        "version": primary.version,
        "warnings": list(getattr(parsed, "warnings", [])),
    }


@router.post("/{wid}/upload-lis")
async def upload_lis(wid: int, file: UploadFile = File(...), db: Session = Depends(get_db)):
    """Upload LIS file and attach log sets as runs to a well."""
    well = db.query(Well).filter(Well.id == wid).first()
    if not well:
        raise HTTPException(404, "Well not found")

    content = await read_upload(file)
    if len(content) == 0:
        raise HTTPException(400, "Empty file")

    try:
        parsed = parse_lis_content(content, file.filename or "upload.lis")
    except Exception as e:
        raise HTTPException(400, f"Failed to parse LIS file: {str(e)}")

    created = _persist_non_las_runs(db, well, file.filename or "unknown.lis", parsed, "LIS")
    if not created:
        raise HTTPException(400, "No data records found in LIS")
    db.commit()

    primary = parsed.runs[0]
    return {
        "status": "ok",
        "source_format": "LIS",
        "log_run_id": created[0].id,
        "log_run_ids": [r.id for r in created],
        "filename": file.filename,
        "runs_created": len(created),
        "curves": [c.mnemonic for c in primary.curves],
        "num_points": int(primary.depth.size),
        "start_depth": primary.start_depth,
        "stop_depth": primary.stop_depth,
        "step": primary.step,
        "version": primary.version,
        "warnings": list(getattr(parsed, "warnings", [])),
    }


@router.post("/{wid}/bulk-upload")
async def bulk_upload_las(wid: int, files: list[UploadFile] = File(...), db: Session = Depends(get_db)):
    """Upload multiple LAS files to a well."""
    well = db.query(Well).filter(Well.id == wid).first()
    if not well:
        raise HTTPException(404, "Well not found")
    results = []
    next_run = len(well.log_runs) + 1
    for file in files:
        try:
            content = await read_upload(file)
            if len(content) == 0:
                results.append({"filename": file.filename, "status": "skipped", "reason": "size"})
                continue
            text = content.decode("utf-8", errors="replace")
            las = LASParser.parse_string(text)
            curves_def = [{"mnemonic": c.mnemonic, "unit": c.unit, "description": c.description} for c in las.curves]
            lr = LogRun(
                well_id=wid, run_number=next_run,
                filename=file.filename or "unknown.las", las_version=las.version,
                start_depth=las.well.start, stop_depth=las.well.stop,
                step=las.well.step, null_value=las.well.null, num_points=len(las.depth),
                curves_json=json.dumps(curves_def),
            )
            db.add(lr)
            db.flush()
            for curve in las.curves:
                arr = las.data.get(curve.mnemonic)
                if arr is not None:
                    valid = arr[~np.isnan(arr)]
                    db.add(CurveData(
                        log_run_id=lr.id, mnemonic=curve.mnemonic,
                        unit=curve.unit, description=curve.description,
                        num_points=len(arr),
                        min_value=float(np.min(valid)) if len(valid) else None,
                        max_value=float(np.max(valid)) if len(valid) else None,
                        data_binary=arr.tobytes(),
                    ))
            db.flush()
            db.commit()
            next_run += 1
            results.append({"filename": file.filename, "status": "ok", "log_run_id": lr.id, "curves": len(las.curves), "points": len(las.depth)})
        except Exception as e:
            db.rollback()
            results.append({"filename": file.filename, "status": "error", "reason": type(e).__name__})
    return {"uploaded": len([r for r in results if r["status"] == "ok"]), "results": results}


@router.post("/{wid}/completion/upload-csv")
async def upload_completion_csv(wid: int, file: UploadFile = File(...), db: Session = Depends(get_db)):
    content = await read_upload(file)
    text_data = content.decode("utf-8", errors="replace")
    reader = csv.DictReader(io.StringIO(text_data))
    inserted = 0

    for rec in reader:
        if not rec:
            continue
        ctype = str(rec.get("component_type") or rec.get("ComponentType") or rec.get("type") or "").strip().lower()
        if ctype not in COMPLETION_COMPONENT_TYPES:
            continue
        top_raw = rec.get("depth_top") or rec.get("DepthTop") or rec.get("top")
        base_raw = rec.get("depth_base") or rec.get("DepthBase") or rec.get("base")
        if top_raw in (None, "") or base_raw in (None, ""):
            continue
        try:
            top = float(str(top_raw).strip())
            base = float(str(base_raw).strip())
        except Exception:
            continue
        if base < top:
            top, base = base, top

        row = CompletionData(
            well_id=wid,
            depth_top=top,
            depth_base=base,
            component_type=ctype,
            size=str(rec.get("size") or rec.get("Size") or ""),
            description=str(rec.get("description") or rec.get("Description") or ""),
            notes=str(rec.get("notes") or rec.get("Notes") or ""),
        )
        db.add(row)
        inserted += 1

    db.commit()
    return {"status": "ok", "inserted": inserted}


@router.post("/{wid}/rft/upload-csv")
async def upload_rft_csv(wid: int, file: UploadFile = File(...), db: Session = Depends(get_db)):
    content = await read_upload(file)
    text_data = content.decode("utf-8", errors="replace")
    reader = csv.DictReader(io.StringIO(text_data))
    inserted = 0
    for rec in reader:
        if not rec:
            continue
        depth_raw = rec.get("depth") or rec.get("Depth") or rec.get("DEPTH")
        press_raw = rec.get("pressure") or rec.get("Pressure") or rec.get("PRESSURE")
        if depth_raw is None or press_raw is None:
            continue
        try:
            depth = float(str(depth_raw).strip())
            pressure = float(str(press_raw).strip())
        except Exception:
            continue
        row = RFTPoint(
            well_id=wid,
            depth=depth,
            pressure=pressure,
            mobility=_safe_float(rec.get("mobility")),
            fluid_type=str(rec.get("fluid_type") or rec.get("FluidType") or rec.get("fluid") or "unknown").lower(),
            sample_recovered=str(rec.get("sample_recovered") or rec.get("sample") or ""),
            notes=str(rec.get("notes") or ""),
        )
        db.add(row)
        inserted += 1
    db.commit()
    return {"status": "ok", "inserted": inserted}


@router.post("/{wid}/production/upload-csv")
async def upload_production_csv(wid: int, file: UploadFile = File(...), db: Session = Depends(get_db)):
    content = await read_upload(file)
    text_data = content.decode("utf-8", errors="replace")
    reader = csv.DictReader(io.StringIO(text_data))
    inserted = 0
    for rec in reader:
        if not rec:
            continue
        date_val = rec.get("date") or rec.get("Date") or rec.get("DATE")
        d = _parse_iso_date(date_val)
        if not d:
            continue

        def f(*keys):
            for k in keys:
                v = rec.get(k)
                if v not in (None, ""):
                    try:
                        return float(str(v).strip())
                    except Exception:
                        return None
            return None

        row = ProductionData(
            well_id=wid,
            date=d,
            oil_rate=f("oil_rate", "OilRate", "oil"),
            gas_rate=f("gas_rate", "GasRate", "gas"),
            water_rate=f("water_rate", "WaterRate", "water"),
            water_cut=f("water_cut", "WaterCut"),
            gor=f("gor", "GOR"),
            bhp=f("bhp", "BHP"),
            whp=f("whp", "WHP"),
            choke_size=f("choke_size", "ChokeSize"),
            cumulative_oil=f("cumulative_oil", "CumOil"),
            cumulative_gas=f("cumulative_gas", "CumGas"),
            cumulative_water=f("cumulative_water", "CumWater"),
            notes=str(rec.get("notes") or rec.get("Notes") or ""),
        )
        db.add(row)
        inserted += 1
    db.commit()
    return {"status": "ok", "inserted": inserted}


@router.post("/{wid}/upload-csv")
async def upload_csv(wid: int, file: UploadFile = File(...), db: Session = Depends(get_db)):
    """Upload CSV file and convert to log run."""
    well = db.query(Well).filter(Well.id == wid).first()
    if not well:
        raise HTTPException(404, "Well not found")

    content = await read_upload(file)
    if len(content) == 0:
        raise HTTPException(400, "Empty file")

    try:
        text = content.decode("utf-8", errors="replace")
        lines = text.strip().split("\n")
        if len(lines) < 2:
            raise HTTPException(400, "File too short")

        # Parse header
        header = [h.strip().strip('"').upper() for h in lines[0].split(",")]
        n_cols = len(header)

        # Parse data rows
        data_rows = []
        for line in lines[1:]:
            vals = [v.strip() for v in line.split(",")]
            if len(vals) != n_cols:
                continue
            try:
                row = [float(v) if v and v != "" else float("nan") for v in vals]
                data_rows.append(row)
            except ValueError:
                continue

        if not data_rows:
            raise HTTPException(400, "No valid numeric data")

        arr = np.array(data_rows, dtype=np.float64)
        depth_col = None
        for i, h in enumerate(header):
            if h in ("DEPT", "DEPTH", "MD", "TVD"):
                depth_col = i
                break
        if depth_col is None:
            depth_col = 0

        depth = arr[:, depth_col]
        step = abs(float(depth[1] - depth[0])) if len(depth) > 1 else 0.5

        curves_def = [{"mnemonic": h, "unit": "", "description": ""} for h in header]
        lr = LogRun(
            well_id=wid, run_number=len(well.log_runs) + 1,
            filename=file.filename or "data.csv", las_version="CSV",
            start_depth=float(depth[0]), stop_depth=float(depth[-1]),
            step=step, num_points=len(depth),
            curves_json=json.dumps(curves_def),
        )
        db.add(lr)
        db.flush()

        for i, h in enumerate(header):
            col = arr[:, i]
            valid = col[~np.isnan(col)]
            db.add(CurveData(
                log_run_id=lr.id, mnemonic=h, unit="", description="",
                num_points=len(col),
                min_value=float(np.min(valid)) if len(valid) else None,
                max_value=float(np.max(valid)) if len(valid) else None,
                data_binary=col.tobytes(),
            ))
        db.commit()
        return {"status": "ok", "log_run_id": lr.id, "curves": header, "points": len(depth)}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(400, f"CSV parse error: {str(e)[:200]}")


@router.post("/{wid}/tops-import")
def import_tops_csv(wid: int, data: dict, db: Session = Depends(get_db)):
    well = db.query(Well).filter(Well.id == wid).first()
    if not well:
        raise HTTPException(404, "Well not found")

    csv_data = data.get("csv_data")
    if not csv_data:
        raise HTTPException(400, "csv_data is required")

    imported = 0
    skipped = 0
    errors = []

    reader = csv.DictReader(io.StringIO(str(csv_data)))
    for line_no, row in enumerate(reader, start=2):
        try:
            row_well_name = (row.get("well_name") or "").strip()
            row_uwi = (row.get("uwi") or "").strip()
            if row_well_name and row_well_name != (well.name or ""):
                skipped += 1
                errors.append(f"line {line_no}: well_name mismatch ({row_well_name})")
                continue
            if row_uwi and row_uwi != (well.uwi or ""):
                skipped += 1
                errors.append(f"line {line_no}: uwi mismatch ({row_uwi})")
                continue

            formation_name = (row.get("formation_name") or "").strip()
            if not formation_name:
                skipped += 1
                errors.append(f"line {line_no}: formation_name is required")
                continue

            depth_val = row.get("depth")
            if depth_val in (None, ""):
                skipped += 1
                errors.append(f"line {line_no}: depth is required")
                continue

            top = FormationTop(
                well_id=wid,
                formation_name=formation_name,
                depth=float(depth_val),
                top_depth=float(row["top_depth"]) if row.get("top_depth") not in (None, "") else None,
                base_depth=float(row["base_depth"]) if row.get("base_depth") not in (None, "") else None,
                color=(row.get("color") or None),
                lithology=(row.get("lithology") or None),
                notes=(row.get("notes") or None),
            )
            db.add(top)
            imported += 1
        except Exception as e:
            skipped += 1
            errors.append(f"line {line_no}: {type(e).__name__}")

    db.commit()
    return {"imported": imported, "skipped": skipped, "errors": errors}
