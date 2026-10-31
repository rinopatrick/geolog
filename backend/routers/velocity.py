"""Project velocity models and time-depth conversion."""

from __future__ import annotations

import json

import numpy as np

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

try:
    from acl import require_project_access
    from database import get_db
    from models import Project, SeismicSurface, VelocityModel
    from velocity import normalize_model, time_to_depth_ms
    from velocity_inversion import invert_checkshot
except ImportError:
    from backend.acl import require_project_access
    from backend.database import get_db
    from backend.models import Project, SeismicSurface, VelocityModel
    from backend.velocity import normalize_model, time_to_depth_ms
    from backend.velocity_inversion import invert_checkshot

router = APIRouter(prefix="/api", tags=["velocity"])


def _model(row: VelocityModel) -> dict:
    try:
        layers = json.loads(row.layers_json or "[]")
    except json.JSONDecodeError:
        layers = []
    return {
        "id": row.id,
        "project_id": row.project_id,
        "name": row.name,
        "kind": row.kind or "constant",
        "velocity_m_s": row.velocity_m_s,
        "layers": layers,
        "created_at": row.created_at.isoformat() if row.created_at else "",
    }


def _project(db: Session, pid: int) -> Project:
    project = db.query(Project).filter(Project.id == pid).first()
    if not project:
        raise HTTPException(404, "Project not found")
    return project


@router.get("/projects/{pid}/velocity-models")
def list_velocity_models(pid: int, request: Request, db: Session = Depends(get_db)):
    _project(db, pid)
    require_project_access(db, request, pid)
    rows = (
        db.query(VelocityModel)
        .filter(VelocityModel.project_id == pid)
        .order_by(VelocityModel.id.asc())
        .all()
    )
    return [_model(row) for row in rows]


@router.post("/projects/{pid}/velocity-models", status_code=201)
def create_velocity_model(pid: int, data: dict, request: Request, db: Session = Depends(get_db)):
    _project(db, pid)
    require_project_access(db, request, pid, write=True)
    try:
        normalized = normalize_model(data)
    except ValueError as exc:
        raise HTTPException(400, str(exc))
    item = VelocityModel(
        project_id=pid,
        name=normalized["name"],
        kind=normalized["kind"],
        velocity_m_s=normalized["velocity_m_s"],
        layers_json=json.dumps(normalized["layers"]),
    )
    db.add(item)
    db.commit()
    db.refresh(item)
    return _model(item)


@router.put("/projects/{pid}/velocity-models/{model_id}")
def update_velocity_model(pid: int, model_id: int, data: dict, request: Request, db: Session = Depends(get_db)):
    _project(db, pid)
    require_project_access(db, request, pid, write=True)
    item = (
        db.query(VelocityModel)
        .filter(VelocityModel.id == model_id, VelocityModel.project_id == pid)
        .first()
    )
    if not item:
        raise HTTPException(404, "Velocity model not found")
    try:
        normalized = normalize_model(data)
    except ValueError as exc:
        raise HTTPException(400, str(exc))
    item.name = normalized["name"]
    item.kind = normalized["kind"]
    item.velocity_m_s = normalized["velocity_m_s"]
    item.layers_json = json.dumps(normalized["layers"])
    db.commit()
    db.refresh(item)
    return _model(item)


@router.delete("/projects/{pid}/velocity-models/{model_id}", status_code=204)
def delete_velocity_model(pid: int, model_id: int, request: Request, db: Session = Depends(get_db)):
    _project(db, pid)
    require_project_access(db, request, pid, write=True)
    item = (
        db.query(VelocityModel)
        .filter(VelocityModel.id == model_id, VelocityModel.project_id == pid)
        .first()
    )
    if not item:
        raise HTTPException(404, "Velocity model not found")
    db.query(SeismicSurface).filter(SeismicSurface.velocity_model_id == item.id).update(
        {"velocity_model_id": None, "depth_grid_json": "[]", "depth_stats_json": "{}"}
    )
    db.delete(item)
    db.commit()


@router.post("/projects/{pid}/velocity-models/{model_id}/convert")
def convert_times(pid: int, model_id: int, data: dict, request: Request, db: Session = Depends(get_db)):
    _project(db, pid)
    require_project_access(db, request, pid)
    item = (
        db.query(VelocityModel)
        .filter(VelocityModel.id == model_id, VelocityModel.project_id == pid)
        .first()
    )
    if not item:
        raise HTTPException(404, "Velocity model not found")
    raw = data.get("times_ms")
    if raw is None:
        raw = [data.get("time_ms", 0.0)]
    if not isinstance(raw, list) or len(raw) > 10000:
        raise HTTPException(400, "times_ms must be a list of at most 10000 values")
    try:
        times = np.asarray([float(value) for value in raw], dtype=float)
    except (TypeError, ValueError):
        raise HTTPException(400, "times_ms must contain numbers")
    if np.any(~np.isfinite(times)) or np.any(times < 0):
        raise HTTPException(400, "times_ms must be finite and non-negative")
    layers = json.loads(item.layers_json or "[]")
    depths = time_to_depth_ms(times, item.kind or "constant", item.velocity_m_s, layers)
    return {
        "model": _model(item),
        "times_ms": times.tolist(),
        "depths_m": [round(float(value), 3) for value in depths],
    }

@router.post("/projects/{pid}/velocity-models/invert-checkshot", status_code=201)
def invert_checkshot_model(pid: int, data: dict, request: Request, db: Session = Depends(get_db)):
    """Invert interval velocities from checkshot pairs; optionally save."""
    _project(db, pid)
    require_project_access(db, request, pid, write=True)
    points = data.get("checkshot")
    if not isinstance(points, list) or not points:
        raise HTTPException(400, "checkshot must be a non-empty list")
    try:
        n_layers = int(data.get("n_layers", 2))
    except (TypeError, ValueError):
        raise HTTPException(400, "n_layers must be an integer")
    holdout = data.get("holdout")
    if holdout is not None and not isinstance(holdout, list):
        raise HTTPException(400, "holdout must be a list")
    name = str(data.get("name") or "checkshot inversion").strip() or "checkshot inversion"
    try:
        result = invert_checkshot(points, n_layers=n_layers, holdout=holdout)
    except ValueError as exc:
        raise HTTPException(400, str(exc))
    saved = None
    if bool(data.get("save")):
        try:
            normalized = normalize_model({
                "name": name, "kind": "layers", "layers": result["layers"],
            })
        except ValueError as exc:
            raise HTTPException(400, str(exc))
        item = VelocityModel(
            project_id=pid,
            name=normalized["name"],
            kind=normalized["kind"],
            velocity_m_s=normalized["velocity_m_s"],
            layers_json=json.dumps(normalized["layers"]),
        )
        db.add(item)
        db.commit()
        db.refresh(item)
        saved = _model(item)
    return {"inversion": result, "saved_model": saved}
