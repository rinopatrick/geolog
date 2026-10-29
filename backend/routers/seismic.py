"""SEG-Y upload, section preview and horizon picks."""

from __future__ import annotations

import json
import os
import uuid

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from sqlalchemy.orm import Session

try:
    from acl import require_project_access
    from database import get_db
    from models import Project, SeismicHorizon, SeismicLine
    from seismic import parse_segy, section_payload
    from uploads import read_upload
    from well_state import ARTIFACT_DIR
except ImportError:
    from backend.acl import require_project_access
    from backend.database import get_db
    from backend.models import Project, SeismicHorizon, SeismicLine
    from backend.seismic import parse_segy, section_payload
    from backend.uploads import read_upload
    from backend.well_state import ARTIFACT_DIR

router = APIRouter(prefix="/api", tags=["seismic"])
SEISMIC_DIR = os.path.join(ARTIFACT_DIR, "seismic")
MAX_SEGY_UPLOAD = 512 * 1024 * 1024


def _line(db: Session, line_id: int) -> SeismicLine:
    row = db.query(SeismicLine).filter(SeismicLine.id == line_id).first()
    if not row:
        raise HTTPException(404, "Seismic line not found")
    return row


def _meta(row: SeismicLine) -> dict:
    return {
        "id": row.id,
        "project_id": row.project_id,
        "name": row.name,
        "filename": row.filename,
        "format_code": row.format_code,
        "sample_interval_ms": row.sample_interval_ms,
        "samples_per_trace": row.samples_per_trace,
        "trace_count": row.trace_count,
        "inline_min": row.inline_min,
        "inline_max": row.inline_max,
        "crossline_min": row.crossline_min,
        "crossline_max": row.crossline_max,
        "amplitude_min": row.amplitude_min,
        "amplitude_max": row.amplitude_max,
        "created_at": row.created_at.isoformat() if row.created_at else "",
    }


def _horizon(row: SeismicHorizon) -> dict:
    try:
        picks = json.loads(row.picks_json or "[]")
    except json.JSONDecodeError:
        picks = []
    return {
        "id": row.id,
        "line_id": row.line_id,
        "name": row.name,
        "color": row.color,
        "picks": picks,
        "created_at": row.created_at.isoformat() if row.created_at else "",
    }


@router.post("/projects/{pid}/seismic", status_code=201)
async def upload_seismic(
    pid: int,
    request: Request,
    file: UploadFile = File(...),
    name: str = Form(""),
    db: Session = Depends(get_db),
):
    if not db.query(Project.id).filter(Project.id == pid).first():
        raise HTTPException(404, "Project not found")
    require_project_access(db, request, pid, write=True)
    content = await read_upload(file, MAX_SEGY_UPLOAD)
    try:
        parsed = parse_segy(content)
    except ValueError as exc:
        raise HTTPException(400, str(exc))
    os.makedirs(SEISMIC_DIR, exist_ok=True)
    path = os.path.join(SEISMIC_DIR, f"{uuid.uuid4().hex}.sgy")
    with open(path, "wb") as handle:
        handle.write(content)
    row = SeismicLine(
        project_id=pid,
        name=(name or os.path.splitext(file.filename or "SEG-Y line")[0]).strip(),
        filename=file.filename or "",
        file_path=path,
        format_code=parsed["format_code"],
        sample_interval_ms=parsed["sample_interval_ms"],
        samples_per_trace=parsed["samples_per_trace"],
        trace_count=parsed["trace_count"],
        inline_min=parsed["inline_min"],
        inline_max=parsed["inline_max"],
        crossline_min=parsed["crossline_min"],
        crossline_max=parsed["crossline_max"],
        amplitude_min=parsed["amplitude_min"],
        amplitude_max=parsed["amplitude_max"],
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return _meta(row)


@router.get("/projects/{pid}/seismic")
def list_seismic(pid: int, request: Request, db: Session = Depends(get_db)):
    require_project_access(db, request, pid)
    rows = db.query(SeismicLine).filter(SeismicLine.project_id == pid).order_by(SeismicLine.id.desc()).all()
    return [_meta(row) for row in rows]


@router.get("/seismic/{line_id}")
def get_seismic(line_id: int, request: Request, db: Session = Depends(get_db)):
    row = _line(db, line_id)
    require_project_access(db, request, row.project_id)
    return _meta(row)


@router.get("/seismic/{line_id}/section")
def get_seismic_section(
    line_id: int,
    request: Request,
    max_traces: int = 500,
    max_samples: int = 500,
    db: Session = Depends(get_db),
):
    row = _line(db, line_id)
    require_project_access(db, request, row.project_id)
    try:
        with open(row.file_path, "rb") as handle:
            parsed = parse_segy(handle.read())
    except (OSError, ValueError) as exc:
        raise HTTPException(500, f"could not read SEG-Y: {exc}")
    section = section_payload(
        parsed,
        max_traces=max(50, min(int(max_traces), 1500)),
        max_samples=max(50, min(int(max_samples), 1500)),
    )
    return {"line": _meta(row), "section": section}


@router.get("/seismic/{line_id}/horizons")
def list_seismic_horizons(line_id: int, request: Request, db: Session = Depends(get_db)):
    row = _line(db, line_id)
    require_project_access(db, request, row.project_id)
    rows = db.query(SeismicHorizon).filter(SeismicHorizon.line_id == line_id).order_by(SeismicHorizon.id.asc()).all()
    return [_horizon(item) for item in rows]


@router.post("/seismic/{line_id}/horizons", status_code=201)
def create_seismic_horizon(line_id: int, data: dict, request: Request, db: Session = Depends(get_db)):
    row = _line(db, line_id)
    require_project_access(db, request, row.project_id, write=True)
    name = str(data.get("name") or "").strip()
    if not name:
        raise HTTPException(400, "name is required")
    picks = data.get("picks") or []
    if not isinstance(picks, list) or len(picks) > 5000:
        raise HTTPException(400, "picks must be a list of at most 5000 points")
    prepared = []
    for index, pick in enumerate(picks):
        if not isinstance(pick, dict):
            raise HTTPException(400, f"picks[{index}] must be an object")
        try:
            prepared.append({"trace": int(pick["trace"]), "sample": int(pick["sample"])})
        except (KeyError, TypeError, ValueError):
            raise HTTPException(400, f"picks[{index}] requires integer trace and sample")
    item = SeismicHorizon(
        line_id=line_id,
        name=name,
        color=str(data.get("color") or "#f0883e"),
        picks_json=json.dumps(prepared),
    )
    db.add(item)
    db.commit()
    db.refresh(item)
    return _horizon(item)


@router.delete("/seismic/{line_id}/horizons/{horizon_id}", status_code=204)
def delete_seismic_horizon(line_id: int, horizon_id: int, request: Request, db: Session = Depends(get_db)):
    row = _line(db, line_id)
    require_project_access(db, request, row.project_id, write=True)
    item = db.query(SeismicHorizon).filter(SeismicHorizon.id == horizon_id, SeismicHorizon.line_id == line_id).first()
    if not item:
        raise HTTPException(404, "Horizon not found")
    db.delete(item)
    db.commit()
