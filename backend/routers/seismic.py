"""SEG-Y upload, section preview and horizon picks."""

from __future__ import annotations

import json
import os
import uuid

import numpy as np

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from sqlalchemy.orm import Session

try:
    from acl import require_project_access
    from database import get_db
    from models import Project, SeismicFault, SeismicFaultLink, SeismicHorizon, SeismicLine
    from seismic import (
        auto_track,
        detect_faults,
        index_segy,
        link_faults_3d,
        parse_segy,
        section_payload,
        volume_index,
        volume_section,
    )
    from uploads import read_upload
    from well_state import ARTIFACT_DIR
except ImportError:
    from backend.acl import require_project_access
    from backend.database import get_db
    from backend.models import Project, SeismicFault, SeismicFaultLink, SeismicHorizon, SeismicLine
    from backend.seismic import (
        auto_track,
        detect_faults,
        index_segy,
        link_faults_3d,
        parse_segy,
        section_payload,
        volume_index,
        volume_section,
    )
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


def _fault(row: SeismicFault) -> dict:
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
        "score": row.score,
        "created_at": row.created_at.isoformat() if row.created_at else "",
    }


def _section_from_line(row: SeismicLine) -> dict:
    with open(row.file_path, "rb") as handle:
        parsed = parse_segy(handle.read())
    return section_payload(parsed, max_traces=600, max_samples=600)

def _seismic_index(row: SeismicLine) -> dict:
    if row.trace_headers_path and os.path.exists(row.trace_headers_path):
        try:
            with open(row.trace_headers_path, encoding="utf-8") as handle:
                return json.load(handle)
        except (OSError, json.JSONDecodeError):
            pass
    with open(row.file_path, "rb") as handle:
        return index_segy(handle.read())

def _fault_link(row: SeismicFaultLink) -> dict:
    try:
        points = json.loads(row.points_json or "[]")
    except json.JSONDecodeError:
        points = []
    return {
        "id": row.id,
        "line_id": row.line_id,
        "name": row.name,
        "color": row.color,
        "points": points,
        "score": row.score,
        "inline_start": row.inline_start,
        "inline_end": row.inline_end,
        "crossline_center": row.crossline_center,
        "sample_center": row.sample_center,
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
        index = index_segy(content)
    except ValueError as exc:
        raise HTTPException(400, str(exc))
    os.makedirs(SEISMIC_DIR, exist_ok=True)
    path = os.path.join(SEISMIC_DIR, f"{uuid.uuid4().hex}.sgy")
    with open(path, "wb") as handle:
        handle.write(content)
    index_path = os.path.join(SEISMIC_DIR, f"{uuid.uuid4().hex}.index.json")
    with open(index_path, "w", encoding="utf-8") as handle:
        json.dump(index, handle, separators=(",", ":"))
    row = SeismicLine(
        project_id=pid,
        name=(name or os.path.splitext(file.filename or "SEG-Y line")[0]).strip(),
        filename=file.filename or "",
        file_path=path,
        format_code=parsed["format_code"],
        sample_interval_ms=parsed["sample_interval_ms"],
        samples_per_trace=parsed["samples_per_trace"],
        trace_count=index["trace_count"],
        trace_headers_path=index_path,
        inline_min=index["inline_min"],
        inline_max=index["inline_max"],
        crossline_min=index["crossline_min"],
        crossline_max=index["crossline_max"],
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

@router.get("/seismic/{line_id}/volume")
def get_seismic_volume(line_id: int, request: Request, db: Session = Depends(get_db)):
    row = _line(db, line_id)
    require_project_access(db, request, row.project_id)
    try:
        index = _seismic_index(row)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        raise HTTPException(500, f"could not index SEG-Y: {exc}")
    return {"line": _meta(row), **volume_index(index)}

@router.get("/seismic/{line_id}/inline/{inline_value}/section")
def get_seismic_inline_section(
    line_id: int,
    inline_value: int,
    request: Request,
    max_traces: int = 500,
    max_samples: int = 500,
    db: Session = Depends(get_db),
):
    row = _line(db, line_id)
    require_project_access(db, request, row.project_id)
    try:
        with open(row.file_path, "rb") as handle:
            content = handle.read()
        section = volume_section(
            content,
            _seismic_index(row),
            "inline",
            inline_value,
            max_traces=max(50, min(int(max_traces), 1500)),
            max_samples=max(50, min(int(max_samples), 1500)),
        )
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        raise HTTPException(400, f"could not read inline section: {exc}")
    return {"line": _meta(row), "section": section}

@router.get("/seismic/{line_id}/crossline/{crossline_value}/section")
def get_seismic_crossline_section(
    line_id: int,
    crossline_value: int,
    request: Request,
    max_traces: int = 500,
    max_samples: int = 500,
    db: Session = Depends(get_db),
):
    row = _line(db, line_id)
    require_project_access(db, request, row.project_id)
    try:
        with open(row.file_path, "rb") as handle:
            content = handle.read()
        section = volume_section(
            content,
            _seismic_index(row),
            "crossline",
            crossline_value,
            max_traces=max(50, min(int(max_traces), 1500)),
            max_samples=max(50, min(int(max_samples), 1500)),
        )
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        raise HTTPException(400, f"could not read crossline section: {exc}")
    return {"line": _meta(row), "section": section}

@router.get("/seismic/{line_id}/fault-links")
def list_seismic_fault_links(line_id: int, request: Request, db: Session = Depends(get_db)):
    row = _line(db, line_id)
    require_project_access(db, request, row.project_id)
    rows = (
        db.query(SeismicFaultLink)
        .filter(SeismicFaultLink.line_id == line_id)
        .order_by(SeismicFaultLink.id.asc())
        .all()
    )
    return [_fault_link(item) for item in rows]

@router.post("/seismic/{line_id}/faults/link-3d", status_code=201)
def link_seismic_faults_3d(line_id: int, data: dict, request: Request, db: Session = Depends(get_db)):
    row = _line(db, line_id)
    require_project_access(db, request, row.project_id, write=True)
    threshold = min(1.0, max(0.01, float(data.get("threshold", 0.35) or 0.35)))
    min_points = max(2, min(int(data.get("min_points", 8) or 8), 500))
    max_faults = max(1, min(int(data.get("max_faults", 20) or 20), 100))
    max_sections = max(2, min(int(data.get("max_sections", 12) or 12), 64))
    crossline_tolerance = max(0.5, min(float(data.get("crossline_tolerance", 3.0) or 3.0), 500.0))
    sample_tolerance = max(1.0, min(float(data.get("sample_tolerance", 16.0) or 16.0), 2000.0))
    try:
        with open(row.file_path, "rb") as handle:
            content = handle.read()
        index = _seismic_index(row)
        links = link_faults_3d(
            content,
            index,
            threshold=threshold,
            min_points=min_points,
            max_faults=max_faults,
            max_sections=max_sections,
            crossline_tolerance=crossline_tolerance,
            sample_tolerance=sample_tolerance,
        )
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        raise HTTPException(400, f"could not link faults: {exc}")
    db.query(SeismicFaultLink).filter(SeismicFaultLink.line_id == line_id).delete()
    created = []
    for link in links:
        item = SeismicFaultLink(
            line_id=line_id,
            name=link["name"],
            color=link["color"],
            points_json=json.dumps(link["points"]),
            score=link["score"],
            inline_start=link["inline_start"],
            inline_end=link["inline_end"],
            crossline_center=link["crossline_center"],
            sample_center=link["sample_center"],
        )
        db.add(item)
        created.append(item)
    db.commit()
    for item in created:
        db.refresh(item)
    return {
        "links": [_fault_link(item) for item in created],
        "scanned_inlines": min(max_sections, len(set(index.get("trace_inlines", [])))),
    }

@router.delete("/seismic/{line_id}/fault-links/{link_id}", status_code=204)
def delete_seismic_fault_link(line_id: int, link_id: int, request: Request, db: Session = Depends(get_db)):
    row = _line(db, line_id)
    require_project_access(db, request, row.project_id, write=True)
    item = (
        db.query(SeismicFaultLink)
        .filter(SeismicFaultLink.id == link_id, SeismicFaultLink.line_id == line_id)
        .first()
    )
    if not item:
        raise HTTPException(404, "Fault link not found")
    db.delete(item)
    db.commit()

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


@router.post("/seismic/{line_id}/horizons/auto-track", status_code=201)
def auto_track_seismic_horizon(line_id: int, data: dict, request: Request, db: Session = Depends(get_db)):
    row = _line(db, line_id)
    require_project_access(db, request, row.project_id, write=True)
    try:
        section = _section_from_line(row)
    except (OSError, ValueError) as exc:
        raise HTTPException(500, f"could not read SEG-Y: {exc}")
    matrix = np.asarray(section["data"], dtype=float)
    horizon = None
    if data.get("horizon_id") is not None:
        horizon = (
            db.query(SeismicHorizon)
            .filter(SeismicHorizon.id == int(data["horizon_id"]), SeismicHorizon.line_id == line_id)
            .first()
        )
    seed_trace = data.get("seed_trace")
    seed_sample = data.get("seed_sample")
    if (seed_trace is None or seed_sample is None) and horizon is not None:
        picks = json.loads(horizon.picks_json or "[]")
        if picks:
            middle = picks[len(picks) // 2]
            seed_trace, seed_sample = middle.get("trace"), middle.get("sample")
    if seed_trace is None or seed_sample is None:
        seed_trace, seed_sample = matrix.shape[0] // 2, matrix.shape[1] // 2
    window = max(2, min(int(data.get("window", 8) or 8), 40))
    search_radius = max(1, min(int(data.get("search_radius", 12) or 12), 80))
    tracked = auto_track(matrix, int(seed_trace), int(seed_sample), window=window, search_radius=search_radius)
    name = str(data.get("name") or "Auto horizon").strip()
    item = SeismicHorizon(
        line_id=line_id,
        name=name,
        color=str(data.get("color") or "#58a6ff"),
        picks_json=json.dumps(tracked["picks"]),
    )
    db.add(item)
    db.commit()
    db.refresh(item)
    return {"horizon": _horizon(item), "confidence": tracked["confidence"], "picks_count": tracked["trace_count"]}


@router.get("/seismic/{line_id}/faults")
def list_seismic_faults(line_id: int, request: Request, db: Session = Depends(get_db)):
    row = _line(db, line_id)
    require_project_access(db, request, row.project_id)
    rows = db.query(SeismicFault).filter(SeismicFault.line_id == line_id).order_by(SeismicFault.id.asc()).all()
    return [_fault(item) for item in rows]


@router.post("/seismic/{line_id}/faults/detect", status_code=201)
def detect_seismic_faults(line_id: int, data: dict, request: Request, db: Session = Depends(get_db)):
    row = _line(db, line_id)
    require_project_access(db, request, row.project_id, write=True)
    try:
        section = _section_from_line(row)
    except (OSError, ValueError) as exc:
        raise HTTPException(500, f"could not read SEG-Y: {exc}")
    matrix = np.asarray(section["data"], dtype=float)
    threshold = min(1.0, max(0.01, float(data.get("threshold", 0.35) or 0.35)))
    min_points = max(2, min(int(data.get("min_points", 8) or 8), 500))
    max_faults = max(1, min(int(data.get("max_faults", 20) or 20), 100))
    detected = detect_faults(matrix, threshold=threshold, min_points=min_points, max_faults=max_faults)
    if not detected:
        return {"faults": [], "detail": "no low-coherence fault candidates found"}
    created = []
    for fault in detected:
        item = SeismicFault(
            line_id=line_id,
            name=fault["name"],
            color=fault["color"],
            picks_json=json.dumps(fault["picks"]),
            score=fault["score"],
        )
        db.add(item)
        created.append(item)
    db.commit()
    for item in created:
        db.refresh(item)
    return {"faults": [_fault(item) for item in created]}


@router.delete("/seismic/{line_id}/faults/{fault_id}", status_code=204)
def delete_seismic_fault(line_id: int, fault_id: int, request: Request, db: Session = Depends(get_db)):
    row = _line(db, line_id)
    require_project_access(db, request, row.project_id, write=True)
    item = db.query(SeismicFault).filter(SeismicFault.id == fault_id, SeismicFault.line_id == line_id).first()
    if not item:
        raise HTTPException(404, "Fault not found")
    db.delete(item)
    db.commit()
