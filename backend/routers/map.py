"""Project map workspace data."""

from __future__ import annotations

import json

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

try:
    from acl import require_project_access
    from database import get_db
    from models import (
        Project,
        Prospect,
        SeismicFaultLink,
        SeismicLine,
        SeismicSurface,
        Well,
        WellSeismicTie,
    )
except ImportError:
    from backend.acl import require_project_access
    from backend.database import get_db
    from backend.models import (
        Project,
        Prospect,
        SeismicFaultLink,
        SeismicLine,
        SeismicSurface,
        Well,
        WellSeismicTie,
    )

router = APIRouter(prefix="/api", tags=["map"])


def _centroid(raw: str) -> tuple[float | None, float | None]:
    try:
        values = json.loads(raw or "[]")
    except json.JSONDecodeError:
        return None, None
    if not values:
        return None, None
    numbers = [float(value) for value in values]
    return sum(numbers) / len(numbers), (min(numbers) + max(numbers)) / 2


@router.get("/projects/{pid}/map")
def project_map(pid: int, request: Request, line_id: int | None = None, db: Session = Depends(get_db)):
    if not db.query(Project.id).filter(Project.id == pid).first():
        raise HTTPException(404, "Project not found")
    require_project_access(db, request, pid)
    wells = db.query(Well).filter(Well.project_id == pid).order_by(Well.id.asc()).all()
    line_query = db.query(SeismicLine).filter(SeismicLine.project_id == pid)
    if line_id is not None:
        line_query = line_query.filter(SeismicLine.id == line_id)
    lines = line_query.order_by(SeismicLine.id.asc()).all()
    line_ids = [line.id for line in lines]
    ties = (
        db.query(WellSeismicTie, Well)
        .join(Well, Well.id == WellSeismicTie.well_id)
        .filter(WellSeismicTie.line_id.in_(line_ids))
        .order_by(WellSeismicTie.id.asc())
        .all()
        if line_ids
        else []
    )
    faults = (
        db.query(SeismicFaultLink)
        .filter(SeismicFaultLink.line_id.in_(line_ids))
        .order_by(SeismicFaultLink.id.asc())
        .all()
        if line_ids
        else []
    )
    surfaces = (
        db.query(SeismicSurface)
        .filter(SeismicSurface.line_id.in_(line_ids))
        .order_by(SeismicSurface.id.asc())
        .all()
        if line_ids
        else []
    )
    prospects = (
        db.query(Prospect)
        .filter(Prospect.project_id == pid)
        .order_by(Prospect.id.asc())
        .all()
    )
    return {
        "project_id": pid,
        "wells": [
            {
                "id": well.id,
                "name": well.name,
                "latitude": well.latitude,
                "longitude": well.longitude,
                "total_depth": well.total_depth,
                "depth_unit": well.depth_unit,
            }
            for well in wells
        ],
        "lines": [
            {
                "id": line.id,
                "name": line.name,
                "inline_min": line.inline_min,
                "inline_max": line.inline_max,
                "crossline_min": line.crossline_min,
                "crossline_max": line.crossline_max,
            }
            for line in lines
        ],
        "ties": [
            {
                "id": tie.id,
                "well_id": tie.well_id,
                "well_name": well.name,
                "line_id": tie.line_id,
                "inline": tie.inline,
                "crossline": tie.crossline,
                "correlation": tie.correlation,
                "shift_ms": tie.shift_ms,
            }
            for tie, well in ties
        ],
        "faults": [
            {
                "id": fault.id,
                "line_id": fault.line_id,
                "name": fault.name,
                "points": json.loads(fault.points_json or "[]"),
                "polygon": json.loads(fault.polygon_json or "[]"),
                "geometry": json.loads(fault.geometry_json or "{}"),
            }
            for fault in faults
        ],
        "surfaces": [
            {
                "id": surface.id,
                "line_id": surface.line_id,
                "name": surface.name,
                "inline_center": _centroid(surface.inlines_json)[0],
                "crossline_center": _centroid(surface.crosslines_json)[0],
                "depth_stats": json.loads(surface.depth_stats_json or "{}"),
                "velocity_model_id": surface.velocity_model_id,
            }
            for surface in surfaces
        ],
        "prospects": [
            {
                "id": prospect.id,
                "name": prospect.name,
                "fluid_type": prospect.fluid_type or "oil",
                "surface_id": prospect.surface_id,
                "grv_m3": prospect.grv_m3,
                "area_m2": prospect.area_m2,
                "contact_depth_m": prospect.contact_depth_m,
                "result": json.loads(prospect.result_json or "{}"),
            }
            for prospect in prospects
        ],
    }
