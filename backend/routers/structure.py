"""Fault surfaces and compartment segmentation endpoints."""

from __future__ import annotations

import json
import os

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

try:
    from acl import require_project_access
    from database import get_db
    from models import (
        FaultSurface,
        SeismicFaultLink,
        SeismicLine,
        SeismicSurface,
        VelocityModel,
    )
    from seismic import index_segy
    from structure import build_compartments, build_fault_surface, juxtaposition
except ImportError:
    from backend.acl import require_project_access
    from backend.database import get_db
    from backend.models import (
        FaultSurface,
        SeismicFaultLink,
        SeismicLine,
        SeismicSurface,
        VelocityModel,
    )
    from backend.seismic import index_segy
    from backend.structure import build_compartments, build_fault_surface, juxtaposition

router = APIRouter(prefix="/api", tags=["structure"])


def _line(db: Session, line_id: int) -> SeismicLine:
    row = db.query(SeismicLine).filter(SeismicLine.id == line_id).first()
    if not row:
        raise HTTPException(404, "Seismic line not found")
    return row


def _index(row: SeismicLine) -> dict:
    if row.trace_headers_path and os.path.exists(row.trace_headers_path):
        try:
            with open(row.trace_headers_path, encoding="utf-8") as handle:
                return json.load(handle)
        except (OSError, json.JSONDecodeError):
            pass
    with open(row.file_path, "rb") as handle:
        return index_segy(handle.read())


def _fault_surface(row: FaultSurface) -> dict:
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
    return {
        "id": row.id,
        "line_id": row.line_id,
        "link_id": row.link_id,
        "name": row.name,
        "domain": row.domain,
        "velocity_model_id": row.velocity_model_id,
        "inlines": inlines,
        "crosslines": crosslines,
        "grid": grid,
        "stats": stats,
        "created_at": row.created_at.isoformat() if row.created_at else "",
    }


@router.post("/seismic/{line_id}/fault-links/{link_id}/surface", status_code=201)
def create_fault_surface(line_id: int, link_id: int, data: dict, request: Request, db: Session = Depends(get_db)):
    row = _line(db, line_id)
    require_project_access(db, request, row.project_id, write=True)
    link = (
        db.query(SeismicFaultLink)
        .filter(SeismicFaultLink.id == link_id, SeismicFaultLink.line_id == line_id)
        .first()
    )
    if not link:
        raise HTTPException(404, "Fault link not found")
    try:
        points = json.loads(link.points_json or "[]")
    except json.JSONDecodeError:
        points = []
    if len(points) < 2:
        raise HTTPException(400, "fault link has too few points")
    model = None
    if data.get("velocity_model_id") is not None:
        try:
            model_id = int(data["velocity_model_id"])
        except (TypeError, ValueError):
            raise HTTPException(400, "velocity_model_id must be an integer")
        model = (
            db.query(VelocityModel)
            .filter(VelocityModel.id == model_id, VelocityModel.project_id == row.project_id)
            .first()
        )
        if not model:
            raise HTTPException(404, "Velocity model not found for this project")
    try:
        method = str(data.get("method", "idw") or "idw").lower()
        if method not in {"idw", "kriging"}:
            raise HTTPException(400, "method must be idw or kriging")
        variogram = data.get("variogram") or {}
        if not isinstance(variogram, dict):
            raise HTTPException(400, "variogram must be an object")
        built = build_fault_surface(
            points,
            _index(row)["sample_interval_ms"],
            max_grid=max(4, min(int(data.get("max_grid", 64) or 64), 128)),
            velocity_m_s=model.velocity_m_s if model and (model.kind or "constant") == "constant" else None,
            layers=json.loads(model.layers_json or "[]") if model and model.kind == "layers" else None,
            method=method,
            variogram=variogram,
            anisotropy_ratio=max(0.05, min(float(data.get("anisotropy_ratio", 1.0) or 1.0), 20.0)),
            azimuth_deg=float(data.get("azimuth_deg", 0.0) or 0.0),
        )
    except (TypeError, ValueError, json.JSONDecodeError) as exc:
        raise HTTPException(400, f"could not build fault surface: {exc}")
    item = FaultSurface(
        line_id=line_id,
        link_id=link_id,
        name=str(data.get("name") or link.name),
        grid_json=json.dumps(built["grid"]),
        inlines_json=json.dumps(built["inlines"]),
        crosslines_json=json.dumps(built["crosslines"]),
        domain=built["domain"],
        velocity_model_id=model.id if model else None,
        stats_json=json.dumps(built["stats"]),
    )
    db.add(item)
    db.commit()
    db.refresh(item)
    return _fault_surface(item)


@router.get("/seismic/{line_id}/fault-surfaces")
def list_fault_surfaces(line_id: int, request: Request, db: Session = Depends(get_db)):
    row = _line(db, line_id)
    require_project_access(db, request, row.project_id)
    rows = (
        db.query(FaultSurface)
        .filter(FaultSurface.line_id == line_id)
        .order_by(FaultSurface.id.asc())
        .all()
    )
    return [_fault_surface(item) for item in rows]


@router.get("/seismic/{line_id}/fault-surfaces/{surface_id}")
def get_fault_surface(line_id: int, surface_id: int, request: Request, db: Session = Depends(get_db)):
    row = _line(db, line_id)
    require_project_access(db, request, row.project_id)
    item = (
        db.query(FaultSurface)
        .filter(FaultSurface.id == surface_id, FaultSurface.line_id == line_id)
        .first()
    )
    if not item:
        raise HTTPException(404, "Fault surface not found")
    return _fault_surface(item)


@router.delete("/seismic/{line_id}/fault-surfaces/{surface_id}", status_code=204)
def delete_fault_surface(line_id: int, surface_id: int, request: Request, db: Session = Depends(get_db)):
    row = _line(db, line_id)
    require_project_access(db, request, row.project_id, write=True)
    item = (
        db.query(FaultSurface)
        .filter(FaultSurface.id == surface_id, FaultSurface.line_id == line_id)
        .first()
    )
    if not item:
        raise HTTPException(404, "Fault surface not found")
    db.delete(item)
    db.commit()


@router.post("/seismic/{line_id}/surfaces/{surface_id}/compartments")
def create_surface_compartments(
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
    if not item.depth_grid_json or item.depth_grid_json == "[]":
        raise HTTPException(400, "surface must be depth-converted first")
    if not item.inline_spacing_m or not item.crossline_spacing_m:
        raise HTTPException(400, "surface needs inline/crossline spacing")
    try:
        contact = float(data.get("contact_depth_m"))
    except (TypeError, ValueError):
        raise HTTPException(400, "contact_depth_m is required")
    base_surface = None
    if data.get("base_surface_id") is not None:
        try:
            base_id = int(data["base_surface_id"])
        except (TypeError, ValueError):
            raise HTTPException(400, "base_surface_id must be an integer")
        base_surface = (
            db.query(SeismicSurface)
            .filter(SeismicSurface.id == base_id, SeismicSurface.line_id == line_id)
            .first()
        )
        if not base_surface:
            raise HTTPException(404, "Base surface not found on this line")
        if not base_surface.depth_grid_json or base_surface.depth_grid_json == "[]":
            raise HTTPException(400, "base surface must be depth-converted first")
    query = db.query(SeismicFaultLink).filter(SeismicFaultLink.line_id == line_id)
    if data.get("fault_link_ids"):
        try:
            query = query.filter(SeismicFaultLink.id.in_([int(value) for value in data["fault_link_ids"]]))
        except (TypeError, ValueError):
            raise HTTPException(400, "fault_link_ids must be integers")
    links = query.order_by(SeismicFaultLink.id.asc()).all()
    faults = []
    for link in links:
        try:
            points = json.loads(link.points_json or "[]")
        except json.JSONDecodeError:
            points = []
        if points:
            faults.append({"id": link.id, "points": points})
    try:
        top_grid = json.loads(item.depth_grid_json)
        inlines = json.loads(item.inlines_json or "[]")
        crosslines = json.loads(item.crosslines_json or "[]")
        base_grid = json.loads(base_surface.depth_grid_json) if base_surface else None
        built = build_compartments(
            top_grid,
            inlines,
            crosslines,
            contact,
            item.inline_spacing_m,
            item.crossline_spacing_m,
            faults,
            base_depth_grid=base_grid,
        )
        if base_grid is not None:
            built["juxtaposition"] = juxtaposition(top_grid, base_grid, inlines, crosslines, faults)
    except (TypeError, ValueError, json.JSONDecodeError) as exc:
        raise HTTPException(400, f"could not build compartments: {exc}")
    item.compartments_json = json.dumps(built)
    db.commit()
    db.refresh(item)
    return {"surface_id": item.id, **built}
