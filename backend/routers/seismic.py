"""SEG-Y upload, section preview and horizon picks."""

from __future__ import annotations

import json
import os
import uuid

import numpy as np

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, Response, UploadFile
from sqlalchemy.orm import Session

try:
    from acl import require_project_access
    from database import get_db
    from models import (
        Project,
        SeismicFault,
        SeismicFaultLink,
        SeismicHorizon,
        SeismicLine,
        SeismicSurface,
        VelocityModel,
    )
    from seismic import (
        auto_track,
        detect_faults,
        index_segy,
        line_section,
        link_faults_3d,
        parse_segy,
        surface_from_horizons,
        volume_index,
        volume_section,
    )
    from uploads import read_upload
    from velocity import time_to_depth_ms
    from well_state import ARTIFACT_DIR
except ImportError:
    from backend.acl import require_project_access
    from backend.database import get_db
    from backend.models import (
        Project,
        SeismicFault,
        SeismicFaultLink,
        SeismicHorizon,
        SeismicLine,
        SeismicSurface,
        VelocityModel,
    )
    from backend.seismic import (
        auto_track,
        detect_faults,
        index_segy,
        line_section,
        link_faults_3d,
        parse_segy,
        surface_from_horizons,
        volume_index,
        volume_section,
    )
    from backend.uploads import read_upload
    from backend.velocity import time_to_depth_ms
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
        content = handle.read()
    return line_section(content, _seismic_index(row), max_traces=600, max_samples=600)

def _section_for_mode(row: SeismicLine, mode: str, section_value: int | None) -> dict:
    if mode == "line":
        return _section_from_line(row)
    with open(row.file_path, "rb") as handle:
        content = handle.read()
    return volume_section(
        content,
        _seismic_index(row),
        mode,
        int(section_value),
        max_traces=600,
        max_samples=600,
    )

def _section_fields(
    data: dict,
    default_mode: str = "line",
    default_value: int | None = None,
) -> tuple[str, int | None]:
    mode = str(data.get("mode") or default_mode).lower()
    if mode not in {"line", "inline", "crossline"}:
        raise HTTPException(400, "mode must be line, inline or crossline")
    if mode == "line":
        return mode, None
    raw = data.get("section_value", default_value)
    if raw is None:
        raise HTTPException(400, f"section_value is required for {mode} horizons")
    try:
        section_value = int(raw)
    except (TypeError, ValueError):
        raise HTTPException(400, "section_value must be an integer")
    return mode, section_value

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
    try:
        geometry = json.loads(row.geometry_json or "{}")
    except json.JSONDecodeError:
        geometry = {}
    try:
        polygon = json.loads(row.polygon_json or "[]")
    except json.JSONDecodeError:
        polygon = []
    return {
        "id": row.id,
        "line_id": row.line_id,
        "name": row.name,
        "color": row.color,
        "points": points,
        "geometry": geometry,
        "polygon": polygon,
        "score": row.score,
        "inline_start": row.inline_start,
        "inline_end": row.inline_end,
        "crossline_center": row.crossline_center,
        "sample_center": row.sample_center,
        "created_at": row.created_at.isoformat() if row.created_at else "",
    }


def _surface(row: SeismicSurface, include_grid: bool = True) -> dict:
    try:
        grid = json.loads(row.grid_json or "[]")
    except json.JSONDecodeError:
        grid = []
    try:
        inlines = json.loads(row.inlines_json or "[]")
    except json.JSONDecodeError:
        inlines = []
    try:
        crosslines = json.loads(row.crosslines_json or "[]")
    except json.JSONDecodeError:
        crosslines = []
    try:
        stats = json.loads(row.stats_json or "{}")
    except json.JSONDecodeError:
        stats = {}
    try:
        depth_grid = json.loads(row.depth_grid_json or "[]")
    except json.JSONDecodeError:
        depth_grid = []
    try:
        depth_stats = json.loads(row.depth_stats_json or "{}")
    except json.JSONDecodeError:
        depth_stats = {}
    try:
        compartments = json.loads(row.compartments_json or "[]")
    except json.JSONDecodeError:
        compartments = []
    payload = {
        "id": row.id,
        "line_id": row.line_id,
        "name": row.name,
        "inlines": inlines,
        "crosslines": crosslines,
        "sample_interval_ms": row.sample_interval_ms,
        "inline_spacing_m": row.inline_spacing_m,
        "crossline_spacing_m": row.crossline_spacing_m,
        "stats": stats,
        "velocity_model_id": row.velocity_model_id,
        "depth_stats": depth_stats,
        "compartments": compartments,
        "created_at": row.created_at.isoformat() if row.created_at else "",
    }
    if include_grid:
        payload["grid"] = grid
        payload["depth_grid"] = depth_grid
    return payload


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
        "mode": row.mode or "line",
        "section_value": row.section_value,
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
            content = handle.read()
        section = line_section(
            content,
            _seismic_index(row),
            max_traces=max(50, min(int(max_traces), 1500)),
            max_samples=max(50, min(int(max_samples), 1500)),
        )
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        raise HTTPException(500, f"could not read SEG-Y: {exc}")
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
    inline_spacing = data.get("inline_spacing_m")
    crossline_spacing = data.get("crossline_spacing_m")
    inline_spacing = max(1.0, float(inline_spacing)) if inline_spacing else None
    crossline_spacing = max(1.0, float(crossline_spacing)) if crossline_spacing else None
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
            inline_spacing_m=inline_spacing,
            crossline_spacing_m=crossline_spacing,
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
            geometry_json=json.dumps(link.get("geometry") or {}),
            polygon_json=json.dumps(link.get("polygon") or []),
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

@router.post("/seismic/{line_id}/surfaces", status_code=201)
def create_seismic_surface(line_id: int, data: dict, request: Request, db: Session = Depends(get_db)):
    row = _line(db, line_id)
    require_project_access(db, request, row.project_id, write=True)
    name = str(data.get("name") or "").strip()
    if not name:
        raise HTTPException(400, "name is required")
    query = db.query(SeismicHorizon).filter(SeismicHorizon.line_id == line_id)
    horizon_ids = data.get("horizon_ids")
    if horizon_ids:
        try:
            ids = [int(value) for value in horizon_ids]
        except (TypeError, ValueError):
            raise HTTPException(400, "horizon_ids must be integers")
        query = query.filter(SeismicHorizon.id.in_(ids))
    elif data.get("horizon_name"):
        query = query.filter(SeismicHorizon.name == str(data["horizon_name"]).strip())
    else:
        query = query.filter(SeismicHorizon.mode.in_(["inline", "crossline"]))
    horizons = query.order_by(SeismicHorizon.id.asc()).all()
    if not horizons:
        raise HTTPException(400, "no inline/crossline horizons matched")
    inline_spacing = data.get("inline_spacing_m")
    crossline_spacing = data.get("crossline_spacing_m")
    inline_spacing = max(1.0, float(inline_spacing)) if inline_spacing else None
    crossline_spacing = max(1.0, float(crossline_spacing)) if crossline_spacing else None
    max_grid = max(8, min(int(data.get("max_grid", 96) or 96), 200))
    payloads = [
        {
            "mode": horizon.mode,
            "section_value": horizon.section_value,
            "picks": json.loads(horizon.picks_json or "[]"),
        }
        for horizon in horizons
    ]
    try:
        with open(row.file_path, "rb") as handle:
            content = handle.read()
        built = surface_from_horizons(
            content,
            _seismic_index(row),
            payloads,
            max_grid=max_grid,
            inline_spacing_m=inline_spacing,
            crossline_spacing_m=crossline_spacing,
        )
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        raise HTTPException(400, f"could not build surface: {exc}")
    item = SeismicSurface(
        line_id=line_id,
        name=name,
        grid_json=json.dumps(built["grid"]),
        inlines_json=json.dumps(built["inlines"]),
        crosslines_json=json.dumps(built["crosslines"]),
        sample_interval_ms=built["sample_interval_ms"],
        inline_spacing_m=built["inline_spacing_m"],
        crossline_spacing_m=built["crossline_spacing_m"],
        stats_json=json.dumps(built["stats"]),
    )
    db.add(item)
    db.commit()
    db.refresh(item)
    return _surface(item)


@router.get("/seismic/{line_id}/surfaces")
def list_seismic_surfaces(line_id: int, request: Request, db: Session = Depends(get_db)):
    row = _line(db, line_id)
    require_project_access(db, request, row.project_id)
    rows = (
        db.query(SeismicSurface)
        .filter(SeismicSurface.line_id == line_id)
        .order_by(SeismicSurface.id.asc())
        .all()
    )
    return [_surface(item, include_grid=False) for item in rows]


@router.get("/seismic/{line_id}/surfaces/{surface_id}")
def get_seismic_surface(line_id: int, surface_id: int, request: Request, db: Session = Depends(get_db)):
    row = _line(db, line_id)
    require_project_access(db, request, row.project_id)
    item = (
        db.query(SeismicSurface)
        .filter(SeismicSurface.id == surface_id, SeismicSurface.line_id == line_id)
        .first()
    )
    if not item:
        raise HTTPException(404, "Surface not found")
    return _surface(item)


@router.post("/seismic/{line_id}/surfaces/{surface_id}/depth")
def convert_seismic_surface_depth(
    line_id: int,
    surface_id: int,
    data: dict,
    request: Request,
    db: Session = Depends(get_db),
):
    row = _line(db, line_id)
    require_project_access(db, request, row.project_id, write=True)
    item = (
        db.query(SeismicSurface)
        .filter(SeismicSurface.id == surface_id, SeismicSurface.line_id == line_id)
        .first()
    )
    if not item:
        raise HTTPException(404, "Surface not found")
    try:
        model_id = int(data.get("velocity_model_id"))
    except (TypeError, ValueError):
        raise HTTPException(400, "velocity_model_id is required")
    model = (
        db.query(VelocityModel)
        .filter(VelocityModel.id == model_id, VelocityModel.project_id == row.project_id)
        .first()
    )
    if not model:
        raise HTTPException(404, "Velocity model not found for this project")
    try:
        grid = json.loads(item.grid_json or "[]")
    except json.JSONDecodeError:
        grid = []
    if not grid:
        raise HTTPException(400, "surface has no time grid")
    times = np.asarray(grid, dtype=float)
    layers = json.loads(model.layers_json or "[]")
    depths = time_to_depth_ms(times, model.kind or "constant", model.velocity_m_s, layers)
    depth_grid = [[round(float(value), 3) for value in depth_row] for depth_row in depths]
    finite = depths[np.isfinite(depths)]
    item.depth_grid_json = json.dumps(depth_grid)
    item.depth_stats_json = json.dumps({
        "min_depth_m": round(float(np.min(finite)), 3) if len(finite) else None,
        "max_depth_m": round(float(np.max(finite)), 3) if len(finite) else None,
        "mean_depth_m": round(float(np.mean(finite)), 3) if len(finite) else None,
    })
    item.velocity_model_id = model.id
    db.commit()
    db.refresh(item)
    return _surface(item)


@router.get("/seismic/{line_id}/surfaces/{surface_id}/export.csv")
def export_seismic_surface(line_id: int, surface_id: int, request: Request, db: Session = Depends(get_db)):
    row = _line(db, line_id)
    require_project_access(db, request, row.project_id)
    item = (
        db.query(SeismicSurface)
        .filter(SeismicSurface.id == surface_id, SeismicSurface.line_id == line_id)
        .first()
    )
    if not item:
        raise HTTPException(404, "Surface not found")
    payload = _surface(item)
    depth_grid = payload.get("depth_grid") or []
    lines = ["inline,crossline,time_ms" + (",depth_m" if depth_grid else "")]
    for row_index, (inline, grid_row) in enumerate(zip(payload["inlines"], payload.get("grid", []))):
        for column_index, (crossline, value) in enumerate(zip(payload["crosslines"], grid_row)):
            suffix = ""
            if depth_grid and row_index < len(depth_grid) and column_index < len(depth_grid[row_index]):
                suffix = f",{depth_grid[row_index][column_index]}"
            lines.append(f"{inline},{crossline},{value}{suffix}")
    return Response(
        "\n".join(lines),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="surface_{item.id}.csv"'},
    )


@router.delete("/seismic/{line_id}/surfaces/{surface_id}", status_code=204)
def delete_seismic_surface(line_id: int, surface_id: int, request: Request, db: Session = Depends(get_db)):
    row = _line(db, line_id)
    require_project_access(db, request, row.project_id, write=True)
    item = (
        db.query(SeismicSurface)
        .filter(SeismicSurface.id == surface_id, SeismicSurface.line_id == line_id)
        .first()
    )
    if not item:
        raise HTTPException(404, "Surface not found")
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
    mode, section_value = _section_fields(data)
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
        mode=mode,
        section_value=section_value,
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
    horizon = None
    if data.get("horizon_id") is not None:
        horizon = (
            db.query(SeismicHorizon)
            .filter(SeismicHorizon.id == int(data["horizon_id"]), SeismicHorizon.line_id == line_id)
            .first()
        )
        if horizon is None:
            raise HTTPException(404, "Horizon not found")
    mode, section_value = _section_fields(
        data,
        default_mode=(horizon.mode or "line") if horizon is not None else "line",
        default_value=horizon.section_value if horizon is not None else None,
    )
    try:
        section = _section_for_mode(row, mode, section_value)
    except (OSError, ValueError) as exc:
        raise HTTPException(500, f"could not read SEG-Y: {exc}")
    matrix = np.asarray(section["data"], dtype=float)
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
        mode=mode,
        section_value=section_value,
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
