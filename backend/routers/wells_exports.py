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


@router.get("/{wid}/export-package")
def export_package(wid: int, db: Session = Depends(get_db)):
    well = db.query(Well).filter(Well.id == wid).first()
    if not well:
        raise HTTPException(404, "Well not found")
    well_dict = {c.name: getattr(well, c.name) for c in Well.__table__.columns}
    tops = [{c.name: getattr(t, c.name) for c in FormationTop.__table__.columns}
            for t in db.query(FormationTop).filter(FormationTop.well_id == wid).order_by(FormationTop.depth).all()]
    zones = [{c.name: getattr(z, c.name) for c in Zone.__table__.columns}
             for z in db.query(Zone).filter(Zone.well_id == wid).order_by(Zone.sort_order.asc()).all()]
    runs = [{c.name: getattr(lr, c.name) for c in LogRun.__table__.columns}
            for lr in db.query(LogRun).filter(LogRun.well_id == wid).all()]
    return {"well": well_dict, "formation_tops": tops, "zones": zones, "log_runs": runs}


@router.get("/{wid}/delivery-bundle")
def delivery_bundle(wid: int, db: Session = Depends(get_db)):
    well = db.query(Well).filter(Well.id == wid).first()
    if not well:
        raise HTTPException(404, "Well not found")

    package = export_package(wid, db)
    snaps = _load_snapshots(wid)
    manifest = {
        "well_id": wid,
        "well_name": well.name,
        "generated_at": utcnow().isoformat() + "Z",
        "files": [
            "well.json",
            "tops.json",
            "zones.json",
            "log_runs.json",
            "snapshots.json",
            "manifest.json",
        ],
    }

    mem = io.BytesIO()
    with zipfile.ZipFile(mem, mode="w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("well.json", json.dumps(package.get("well", {}), indent=2, default=str))
        zf.writestr("tops.json", json.dumps(package.get("formation_tops", []), indent=2, default=str))
        zf.writestr("zones.json", json.dumps(package.get("zones", []), indent=2, default=str))
        zf.writestr("log_runs.json", json.dumps(package.get("log_runs", []), indent=2, default=str))
        zf.writestr("snapshots.json", json.dumps(snaps, indent=2, default=str))
        zf.writestr("manifest.json", json.dumps(manifest, indent=2, default=str))

    mem.seek(0)
    return StreamingResponse(
        mem,
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{well.name}_delivery_bundle.zip"'},
    )


@router.get("/{wid}/report")
def generate_report(wid: int, db: Session = Depends(get_db)):
    """Generate structured data for print report."""
    well = db.query(Well).filter(Well.id == wid).first()
    if not well:
        raise HTTPException(404, "Well not found")
    tops = [{c.name: getattr(t, c.name) for c in FormationTop.__table__.columns}
            for t in db.query(FormationTop).filter(FormationTop.well_id == wid).order_by(FormationTop.depth).all()]
    zones = [{c.name: getattr(z, c.name) for c in Zone.__table__.columns}
             for z in db.query(Zone).filter(Zone.well_id == wid).order_by(Zone.sort_order).all()]
    runs = db.query(LogRun).filter(LogRun.well_id == wid).order_by(LogRun.run_number).all()
    curve_summary = []
    for lr in runs:
        cds = db.query(CurveData).filter(CurveData.log_run_id == lr.id).all()
        for cd in cds:
            arr = np.frombuffer(cd.data_binary, dtype=np.float64)
            valid = arr[~np.isnan(arr)]
            curve_summary.append({
                "run": lr.run_number, "mnemonic": cd.mnemonic, "unit": cd.unit,
                "count": int(len(valid)),
                "min": round(float(np.min(valid)), 4) if len(valid) else None,
                "max": round(float(np.max(valid)), 4) if len(valid) else None,
                "mean": round(float(np.mean(valid)), 4) if len(valid) else None,
            })
    pp = db.query(PetroParams).filter(PetroParams.well_id == wid).first()
    petro = {c.name: getattr(pp, c.name) for c in PetroParams.__table__.columns} if pp else None
    return {
        "well": {c.name: getattr(well, c.name) for c in Well.__table__.columns},
        "formation_tops": tops, "zones": zones,
        "curve_summary": curve_summary, "petro_params": petro,
        "generated_at": utcnow().isoformat(),
    }


@router.get("/{wid}/tops-petrel")
def export_tops_petrel(wid: int, db: Session = Depends(get_db)):
    """Export well tops in Petrel-compatible CSV format."""
    well = db.query(Well).filter(Well.id == wid).first()
    if not well:
        raise HTTPException(404, "Well not found")

    tops = (
        db.query(FormationTop)
        .filter(FormationTop.well_id == wid)
        .order_by(FormationTop.depth.asc(), FormationTop.id.asc())
        .all()
    )

    out = io.StringIO()
    writer = csv.writer(out)
    writer.writerow([
        "WELL", "UWI", "HORIZON", "MD", "TVD", "X_OFFSET", "Y_OFFSET", "LATITUDE", "LONGITUDE", "COMMENTS"
    ])

    for t in tops:
        depth_val = t.depth if t.depth is not None else t.top_depth
        writer.writerow([
            well.name or "",
            well.uwi or "",
            t.formation_name or "",
            depth_val if depth_val is not None else "",
            depth_val if depth_val is not None else "",
            "",
            "",
            well.latitude if well.latitude is not None else "",
            well.longitude if well.longitude is not None else "",
            t.notes or "",
        ])

    csv_text = out.getvalue()
    out.close()
    headers = {"Content-Disposition": f'attachment; filename="well_{wid}_tops_petrel.csv"'}
    return StreamingResponse(iter([csv_text]), media_type="text/csv", headers=headers)


@router.get("/{wid}/export-las")
def export_las(wid: int, db: Session = Depends(get_db)):
    """Export well data as LAS 2.0 format string."""
    well = db.query(Well).filter(Well.id == wid).first()
    if not well:
        raise HTTPException(404, "Well not found")

    lr = db.query(LogRun).filter(LogRun.well_id == wid).order_by(LogRun.num_points.desc()).first()
    if not lr:
        raise HTTPException(404, "No log run")

    curves = db.query(CurveData).filter(CurveData.log_run_id == lr.id).order_by(CurveData.id).all()

    # Build LAS header
    las = "~Version Information\n"
    las += "VERS.                  2.0:   CWLS Log ASCII Standard - VERSION 2.0\n"
    las += "WRAP.                  NO:    One line per depth step\n"
    las += "~Well Information\n"
    las += "#MNEM.UNIT       DATA                   DESCRIPTION\n"
    las += "#----.----      -----                   -----------\n"
    las += f"WELL.                 {well.name}:    Well Name\n"
    las += f"UWI.                  {well.uwi or 'N/A'}:    Unique Well Identifier\n"
    las += f"COMP.                 {well.operator or 'N/A'}:    Company\n"
    las += f"FLD.                  {well.field_name or 'N/A'}:    Field\n"
    las += "SRVC.                 GeoLog:    Service Company\n"
    las += f"DATE.                 {datetime.datetime.now().strftime('%Y-%m-%d')}:    Date\n"
    las += f"STRT.{well.depth_unit or 'FT'}         {lr.start_depth or 0:.4f}                  START DEPTH\n"
    las += f"STOP.{well.depth_unit or 'FT'}         {lr.stop_depth or 0:.4f}                  STOP DEPTH\n"
    las += f"STEP.{well.depth_unit or 'FT'}         {lr.step or 0.5:.4f}                  STEP\n"
    las += f"NULL.                {lr.null_value or -999.25:.2f}                 NULL VALUE\n"

    las += "~Curve Information\n"
    mnemonics = []
    for c in curves:
        las += f"{c.mnemonic:8s}.{c.unit or '':6s} {c.description or ''}\n"
        mnemonics.append(c.mnemonic)

    las += "~Ascii\n"

    # Build data matrix
    n = curves[0].num_points if curves else 0
    arrays = []
    for c in curves:
        arr = np.frombuffer(c.data_binary, dtype=np.float64)
        if len(arr) == n:
            arrays.append(arr)
        else:
            arrays.append(np.full(n, lr.null_value or -999.25))

    for i in range(n):
        row = []
        for arr in arrays:
            v = arr[i]
            if np.isnan(v):
                row.append(f"{lr.null_value or -999.25:12.4f}")
            else:
                row.append(f"{v:12.4f}")
        las += "  ".join(row) + "\n"

    headers = {"Content-Disposition": f'attachment; filename="{well.name}.las"'}
    return StreamingResponse(iter([las]), media_type="text/plain", headers=headers)


@router.get("/{wid}/export-bundle")
def export_client_bundle(wid: int, db: Session = Depends(get_db)):
    """Export a ZIP bundle with LAS, tops, zones, params, and summary report."""
    import zipfile
    import io
    well = db.query(Well).filter(Well.id == wid).first()
    if not well:
        raise HTTPException(404, "Well not found")

    lr = db.query(LogRun).filter(LogRun.well_id == wid).order_by(LogRun.num_points.desc()).first()
    tops = db.query(FormationTop).filter(FormationTop.well_id == wid).order_by(FormationTop.depth).all()
    zones = db.query(Zone).filter(Zone.well_id == wid).order_by(Zone.top_depth).all()
    params = db.query(PetroParams).filter(PetroParams.well_id == wid).first()

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, 'w', zipfile.ZIP_DEFLATED) as zf:
        # 1. LAS file
        if lr:
            cds = db.query(CurveData).filter(CurveData.log_run_id == lr.id).all()
            las_lines = [
                "~Version Information",
                "VERS.                  2.0:   CWLS Log ASCII Standard - VERSION 2.0",
                "WRAP.                  NO:   One line per depth step",
                "~Well Information",
                f"WELL.                  {well.name}:   Well Name",
                f"STRT. {float(lr.start_depth or 0):>10.2f} {getattr(lr, 'depth_unit', 'FT')}:   Start Depth",
                f"STOP. {float(lr.stop_depth or 0):>10.2f} {getattr(lr, 'depth_unit', 'FT')}:   Stop Depth",
                f"STEP. {float(lr.step or 1):>10.4f} {getattr(lr, 'depth_unit', 'FT')}:   Step",
                "NULL.              -999.25:   Null Value",
                "COMP.                  GeoLog:   Company",
                f"DATE.          {__import__('datetime').date.today()}:   Date",
                "~Curve Information",
            ]
            for c in cds:
                las_lines.append(f"{c.mnemonic:>8}.{c.unit:>4}:   {c.description or c.mnemonic}")
            las_lines.append("~Ascii")
            depth_arr = None
            curve_arrays = {}
            for c in cds:
                arr = np.frombuffer(c.data_binary, dtype=np.float64)
                if c.mnemonic in ('DEPT', 'DEPTH'):
                    depth_arr = arr
                else:
                    curve_arrays[c.mnemonic] = arr
            if depth_arr is not None:
                for i in range(len(depth_arr)):
                    vals = [f"{depth_arr[i]:>10.2f}"]
                    for c in cds:
                        if c.mnemonic not in ('DEPT', 'DEPTH'):
                            v = curve_arrays.get(c.mnemonic, [])
                            vals.append(f"{v[i]:>10.4f}" if i < len(v) else "   -999.25")
                    las_lines.append(" ".join(vals))
            zf.writestr(f"{well.name}.las", "\n".join(las_lines))

        # 2. Tops CSV
        if tops:
            # Header and values must match the model: FormationTop has
            # formation_name (no 'name'), and the old header repeated the same
            # value in two columns.
            tops_csv = "depth,formation_name,color,lithology\n"
            for t in tops:
                tops_csv += f"{t.depth},{t.formation_name or ''},{t.color or ''},{t.lithology or ''}\n"
            zf.writestr("tops.csv", tops_csv)

        # 3. Zones CSV
        if zones:
            # Zone stores name/top/bottom/color only. The previous header declared
            # sw_avg, vsh_avg, phie_avg and ntg, which are not columns — they are
            # computed from the curves, and /zonation-report already exports them.
            zones_csv = "name,top_depth,bottom_depth,color\n"
            for z in zones:
                zones_csv += f"{z.name or ''},{z.top_depth},{z.bottom_depth},{z.color or ''}\n"
            zf.writestr("zones.csv", zones_csv)

        # 4. Petro params JSON
        if params:
            import json
            p = {k: getattr(params, k) for k in ['saturation_model', 'a', 'm', 'n', 'rw', 'vsh_cutoff', 'phie_cutoff', 'sw_cutoff', 'template'] if hasattr(params, k)}
            zf.writestr("petro_params.json", json.dumps(p, indent=2))

        # 5. Summary report
        report = f"# GeoLog Export Report\nWell: {well.name}\nDate: {__import__('datetime').datetime.now().isoformat()}\n\n"
        report += f"## Log Runs\n- Depth range: {lr.start_depth} - {lr.stop_depth} ft\n- Points: {lr.num_points}\n\n" if lr else ""
        report += f"## Formation Tops ({len(tops)} entries)\n"
        for t in tops:
            report += f"- {t.depth:.1f} ft: {t.formation_name or ''}\n"
        report += f"\n## Zones ({len(zones)} entries)\n"
        for z in zones:
            report += f"- {z.name or ''}: {z.top_depth:.1f} - {z.bottom_depth:.1f} ft\n"
        zf.writestr("report.md", report)

    buf.seek(0)
    return StreamingResponse(buf, media_type="application/zip", headers={
        "Content-Disposition": f"attachment; filename={well.name}_bundle.zip"
    })
