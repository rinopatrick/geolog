"""Geomechanics screening API."""

from __future__ import annotations

import csv
import io
import json

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from sqlalchemy.orm import Session

try:
    from database import get_db
    import geomechanics as geo
    from models import GeomechanicsModel, GeomechanicsRun, LogRun, Well
    from semantics import apply_run_semantics
except ImportError:
    from backend.database import get_db
    from backend import geomechanics as geo
    from backend.models import GeomechanicsModel, GeomechanicsRun, LogRun, Well
    from backend.semantics import apply_run_semantics

router = APIRouter(prefix="/api/wells/{wid}/geomechanics", tags=["geomechanics"])

def _well(db: Session, wid: int) -> Well:
    well = db.query(Well).filter(Well.id == wid).first()
    if not well:
        raise HTTPException(404, "Well not found")
    return well

def _model(db: Session, wid: int, model_id: int) -> GeomechanicsModel:
    row = db.query(GeomechanicsModel).filter(
        GeomechanicsModel.id == model_id, GeomechanicsModel.well_id == wid
    ).first()
    if not row:
        raise HTTPException(404, "Geomechanics model not found")
    return row

def _params(row: GeomechanicsModel) -> dict:
    try:
        return json.loads(row.params_json or "{}")
    except json.JSONDecodeError:
        return {}

def _calibration(row: GeomechanicsModel) -> dict:
    try:
        return json.loads(row.calibration_json or "{}")
    except json.JSONDecodeError:
        return {}

def _new_model(wid: int, data: dict, db: Session) -> GeomechanicsModel:
    latest = db.query(GeomechanicsModel).filter(
        GeomechanicsModel.well_id == wid
    ).order_by(GeomechanicsModel.version.desc()).first()
    params = data.get("params") or {}
    calibration = data.get("calibration") or {}
    row = GeomechanicsModel(
        well_id=wid,
        zone_id=data.get("zone_id"),
        version=(latest.version + 1) if latest else 1,
        status="draft",
        model_type=str(data.get("model_type") or "screening"),
        params_json=json.dumps(params, sort_keys=True),
        calibration_json=json.dumps(calibration, sort_keys=True),
        input_hash=geo._hash_payload({"params": params, "calibration": calibration}),
        created_by=str(data.get("created_by") or "api"),
    )
    db.add(row)
    db.flush()
    return row

@router.get("/models")
def list_models(wid: int, db: Session = Depends(get_db)):
    _well(db, wid)
    rows = db.query(GeomechanicsModel).filter(
        GeomechanicsModel.well_id == wid
    ).order_by(GeomechanicsModel.version.desc()).all()
    return [
        {"id": r.id, "version": r.version, "zone_id": r.zone_id, "status": r.status,
         "model_type": r.model_type, "input_hash": r.input_hash,
         "params": _params(r), "calibration": _calibration(r),
         "created_at": r.created_at.isoformat() if r.created_at else "",
         "approved_at": r.approved_at.isoformat() if r.approved_at else ""}
        for r in rows
    ]

@router.post("/models", status_code=201)
def create_model(wid: int, data: dict, db: Session = Depends(get_db)):
    _well(db, wid)
    row = _new_model(wid, data, db)
    db.commit()
    db.refresh(row)
    return {"id": row.id, "version": row.version, "status": row.status,
            "params": _params(row), "calibration": _calibration(row)}

@router.get("/models/{model_id}")
def get_model(wid: int, model_id: int, db: Session = Depends(get_db)):
    _well(db, wid)
    row = _model(db, wid, model_id)
    return {"id": row.id, "version": row.version, "zone_id": row.zone_id, "status": row.status,
            "model_type": row.model_type, "input_hash": row.input_hash,
            "params": _params(row), "calibration": _calibration(row)}

@router.put("/models/{model_id}")
def update_model(wid: int, model_id: int, data: dict, db: Session = Depends(get_db)):
    _well(db, wid)
    row = _model(db, wid, model_id)
    if row.status != "draft":
        raise HTTPException(423, "Approved geomechanics models are immutable")
    if "params" in data:
        row.params_json = json.dumps(data.get("params") or {}, sort_keys=True)
    if "calibration" in data:
        row.calibration_json = json.dumps(data.get("calibration") or {}, sort_keys=True)
    if "zone_id" in data:
        row.zone_id = data.get("zone_id")
    row.input_hash = geo._hash_payload({"params": _params(row), "calibration": _calibration(row)})
    db.commit()
    return {"id": row.id, "version": row.version, "status": row.status,
            "params": _params(row), "calibration": _calibration(row)}

@router.post("/models/{model_id}/approve")
def approve_model(wid: int, model_id: int, db: Session = Depends(get_db)):
    _well(db, wid)
    row = _model(db, wid, model_id)
    row.status = "approved"
    db.commit()
    return {"status": "ok", "id": row.id, "version": row.version}

def _run(db: Session, wid: int, data: dict) -> tuple[GeomechanicsModel, LogRun, dict]:
    if data.get("model_id") is not None:
        model = _model(db, wid, int(data["model_id"]))
    else:
        model = _new_model(wid, data, db)
    q = db.query(LogRun).filter(LogRun.well_id == wid)
    if data.get("log_run_id") is not None:
        q = q.filter(LogRun.id == int(data["log_run_id"]))
    lr = q.order_by(LogRun.num_points.desc()).first()
    if not lr:
        raise HTTPException(404, "No log run for this well")
    sem = apply_run_semantics(
        db, lr,
        start=data.get("start"),
        stop=data.get("stop"),
        step=max(1, int(data.get("step") or 1)),
        as_arrays=True,
    )
    try:
        result = geo.compute(sem, _params(model), _calibration(model))
    except ValueError as exc:
        raise HTTPException(400, str(exc))
    return model, lr, result

@router.post("/compute")
def compute(wid: int, data: dict, db: Session = Depends(get_db)):
    _well(db, wid)
    model, lr, result = _run(db, wid, data)
    run = GeomechanicsRun(
        model_id=model.id, log_run_id=lr.id,
        depth_top=result["summary"].get("depth_top"),
        depth_bottom=result["summary"].get("depth_bottom"),
        summary_json=json.dumps(result["summary"]),
        warnings_json=json.dumps(result["warnings"]),
        provenance_json=json.dumps(result["provenance"]),
    )
    db.add(run)
    db.commit()
    db.refresh(run)
    return {"run_id": run.id, "model_id": model.id, "model_version": model.version,
            "log_run_id": lr.id, **result}

@router.get("/runs")
def list_runs(wid: int, db: Session = Depends(get_db)):
    _well(db, wid)
    rows = (
        db.query(GeomechanicsRun)
        .join(GeomechanicsModel, GeomechanicsRun.model_id == GeomechanicsModel.id)
        .filter(GeomechanicsModel.well_id == wid)
        .order_by(GeomechanicsRun.id.desc())
        .all()
    )
    return [
        {"id": r.id, "model_id": r.model_id, "log_run_id": r.log_run_id,
         "depth_top": r.depth_top, "depth_bottom": r.depth_bottom,
         "summary": json.loads(r.summary_json or "{}"),
         "warnings": json.loads(r.warnings_json or "[]"),
         "provenance": json.loads(r.provenance_json or "{}")}
        for r in rows
    ]

@router.get("/report")
def report(wid: int, model_id: int = None, log_run_id: int = None, format: str = "json",
           start: float = None, stop: float = None, step: int = 1, db: Session = Depends(get_db)):
    _well(db, wid)
    data = {"model_id": model_id, "log_run_id": log_run_id, "start": start, "stop": stop, "step": step}
    model, lr, result = _run(db, wid, data)
    fmt = (format or "json").lower()
    if fmt == "json":
        return {"model_id": model.id, "model_version": model.version, "log_run_id": lr.id, **result}
    if fmt == "csv":
        keys = ["DEPTH", "TVD", "SV", "PP", "SHMIN", "SHMAX", "MW_MIN", "MW_MAX", "BO", "MC_FAIL"]
        buf = io.StringIO()
        writer = csv.writer(buf)
        writer.writerow(keys)
        length = len(result["curves"]["DEPTH"])
        for i in range(length):
            writer.writerow([result["curves"][k][i] for k in keys])
        return Response(buf.getvalue(), media_type="text/csv",
                        headers={"Content-Disposition": f'attachment; filename="geomechanics_{wid}.csv"'})
    if fmt == "pdf":
        try:
            from reportlab.lib.pagesizes import A4
            from reportlab.pdfgen import canvas
        except ImportError:
            raise HTTPException(501, "reportlab is not installed")
        buf = io.BytesIO()
        c = canvas.Canvas(buf, pagesize=A4)
        width, height = A4
        y = height - 40
        c.setFont("Helvetica-Bold", 12)
        c.drawString(40, y, f"Well {wid} geomechanics screening")
        y -= 18
        c.setFont("Helvetica", 8)
        c.drawString(40, y, f"Model {model.id} v{model.version}; points {result['summary']['points']}")
        y -= 12
        c.drawString(40, y, f"MW window {result['summary']['mw_min']} - {result['summary']['mw_max']} ppg")
        y -= 18
        for i in range(0, len(result["curves"]["DEPTH"]), max(1, len(result["curves"]["DEPTH"]) // 50)):
            c.drawString(40, y, f"MD {result['curves']['DEPTH'][i]}  Pp {result['curves']['PP'][i]}  "
                               f"Shmin {result['curves']['SHMIN'][i]}  Shmax {result['curves']['SHMAX'][i]}  "
                               f"MWmin {result['curves']['MW_MIN'][i]}  MWmax {result['curves']['MW_MAX'][i]}")
            y -= 11
            if y < 50:
                c.showPage()
                y = height - 40
                c.setFont("Helvetica", 8)
        c.save()
        return Response(buf.getvalue(), media_type="application/pdf",
                        headers={"Content-Disposition": f'attachment; filename="geomechanics_{wid}.pdf"'})
    raise HTTPException(400, "format must be json, csv or pdf")
