"""Prospect volumetrics and risking."""

from __future__ import annotations

import json

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

try:
    from acl import require_project_access
    from database import get_db
    from models import Project, Prospect, SeismicLine, SeismicSurface
    from volumetrics import calculate_prospect
except ImportError:
    from backend.acl import require_project_access
    from backend.database import get_db
    from backend.models import Project, Prospect, SeismicLine, SeismicSurface
    from backend.volumetrics import calculate_prospect

router = APIRouter(prefix="/api", tags=["prospects"])


def _serialized(row: Prospect, include_result: bool = True) -> dict:
    payload = {
        "id": row.id,
        "project_id": row.project_id,
        "line_id": row.line_id,
        "surface_id": row.surface_id,
        "name": row.name,
        "contact_depth_m": row.contact_depth_m,
        "grv_m3": row.grv_m3,
        "area_m2": row.area_m2,
        "created_at": row.created_at.isoformat() if row.created_at else "",
    }
    if include_result:
        try:
            payload["result"] = json.loads(row.result_json or "{}")
        except json.JSONDecodeError:
            payload["result"] = {}
    return payload


@router.get("/projects/{pid}/prospects")
def list_prospects(pid: int, request: Request, db: Session = Depends(get_db)):
    if not db.query(Project.id).filter(Project.id == pid).first():
        raise HTTPException(404, "Project not found")
    require_project_access(db, request, pid)
    rows = (
        db.query(Prospect)
        .filter(Prospect.project_id == pid)
        .order_by(Prospect.id.desc())
        .all()
    )
    return [_serialized(row, include_result=False) for row in rows]


@router.post("/projects/{pid}/prospects", status_code=201)
def create_prospect(pid: int, data: dict, request: Request, db: Session = Depends(get_db)):
    if not db.query(Project.id).filter(Project.id == pid).first():
        raise HTTPException(404, "Project not found")
    require_project_access(db, request, pid, write=True)
    name = str(data.get("name") or "").strip()
    if not name:
        raise HTTPException(400, "name is required")
    try:
        surface_id = int(data.get("surface_id"))
    except (TypeError, ValueError):
        raise HTTPException(400, "surface_id is required")
    surface = (
        db.query(SeismicSurface)
        .join(SeismicLine, SeismicLine.id == SeismicSurface.line_id)
        .filter(SeismicSurface.id == surface_id, SeismicLine.project_id == pid)
        .first()
    )
    if not surface:
        raise HTTPException(404, "Surface not found in this project")
    if not surface.velocity_model_id or not surface.depth_grid_json or surface.depth_grid_json == "[]":
        raise HTTPException(400, "surface must be depth-converted first")
    if not surface.inline_spacing_m or not surface.crossline_spacing_m:
        raise HTTPException(400, "surface needs inline/crossline spacing")
    try:
        contact = float(data.get("contact_depth_m"))
    except (TypeError, ValueError):
        raise HTTPException(400, "contact_depth_m is required")
    try:
        result = calculate_prospect(
            depth_grid=json.loads(surface.depth_grid_json),
            contact_depth_m=contact,
            inline_spacing_m=surface.inline_spacing_m,
            crossline_spacing_m=surface.crossline_spacing_m,
            inlines=json.loads(surface.inlines_json or "[]"),
            crosslines=json.loads(surface.crosslines_json or "[]"),
            porosity=data.get("porosity", 0.2),
            water_saturation=data.get("water_saturation", 0.3),
            recovery_factor=data.get("recovery_factor", 0.35),
            net_to_gross=data.get("net_to_gross", 1.0),
            bo=data.get("bo", 1.2),
            risk=data.get("risk", 1.0),
            risks=data.get("risks"),
            iterations=data.get("iterations", 1000),
            seed=data.get("seed"),
        )
    except (TypeError, ValueError, json.JSONDecodeError) as exc:
        raise HTTPException(400, str(exc))
    item = Prospect(
        project_id=pid,
        line_id=surface.line_id,
        surface_id=surface.id,
        name=name,
        contact_depth_m=contact,
        grv_m3=result["grv"]["grv_m3"],
        area_m2=result["grv"]["area_m2"],
        result_json=json.dumps(result),
    )
    db.add(item)
    db.commit()
    db.refresh(item)
    return _serialized(item)


@router.get("/projects/{pid}/prospects/{prospect_id}")
def get_prospect(pid: int, prospect_id: int, request: Request, db: Session = Depends(get_db)):
    if not db.query(Project.id).filter(Project.id == pid).first():
        raise HTTPException(404, "Project not found")
    require_project_access(db, request, pid)
    item = (
        db.query(Prospect)
        .filter(Prospect.id == prospect_id, Prospect.project_id == pid)
        .first()
    )
    if not item:
        raise HTTPException(404, "Prospect not found")
    return _serialized(item)


@router.delete("/projects/{pid}/prospects/{prospect_id}", status_code=204)
def delete_prospect(pid: int, prospect_id: int, request: Request, db: Session = Depends(get_db)):
    if not db.query(Project.id).filter(Project.id == pid).first():
        raise HTTPException(404, "Project not found")
    require_project_access(db, request, pid, write=True)
    item = (
        db.query(Prospect)
        .filter(Prospect.id == prospect_id, Prospect.project_id == pid)
        .first()
    )
    if not item:
        raise HTTPException(404, "Prospect not found")
    db.delete(item)
    db.commit()
