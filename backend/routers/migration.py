"""Post-stack 3D Kirchhoff depth migration endpoints."""

from __future__ import annotations

import json
import os
import uuid

import numpy as np

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

try:
    from acl import require_project_access
    from database import get_db
    from migration3d import kirchhoff_migrate, volume_cube
    from models import SeismicLine, SeismicMigration
    from seismic import index_segy
    from well_state import ARTIFACT_DIR
except ImportError:
    from backend.acl import require_project_access
    from backend.database import get_db
    from backend.migration3d import kirchhoff_migrate, volume_cube
    from backend.models import SeismicLine, SeismicMigration
    from backend.seismic import index_segy
    from backend.well_state import ARTIFACT_DIR

router = APIRouter(prefix="/api", tags=["migration"])
MIGRATION_DIR = os.path.join(ARTIFACT_DIR, "migrations")


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


def _serialized(row: SeismicMigration) -> dict:
    try:
        inlines = json.loads(row.inlines_json or "[]")
        crosslines = json.loads(row.crosslines_json or "[]")
        depths = json.loads(row.depths_json or "[]")
        stats = json.loads(row.stats_json or "{}")
    except json.JSONDecodeError:
        inlines, crosslines, depths, stats = [], [], [], {}
    return {
        "id": row.id,
        "line_id": row.line_id,
        "name": row.name,
        "velocity_m_s": row.velocity_m_s,
        "inline_spacing_m": row.inline_spacing_m,
        "crossline_spacing_m": row.crossline_spacing_m,
        "inlines": inlines,
        "crosslines": crosslines,
        "depths_m": depths,
        "stats": stats,
        "created_at": row.created_at.isoformat() if row.created_at else "",
    }


def _load_cube(row: SeismicMigration) -> dict:
    if not row.file_path or not os.path.exists(row.file_path):
        raise HTTPException(404, "Migration artifact not found")
    with np.load(row.file_path) as data:
        return {
            "cube": data["cube"],
            "inlines": data["inlines"].tolist(),
            "crosslines": data["crosslines"].tolist(),
            "depths": data["depths"].tolist(),
        }


@router.post("/seismic/{line_id}/migrate-3d", status_code=201)
def migrate_3d(line_id: int, data: dict, request: Request, db: Session = Depends(get_db)):
    row = _line(db, line_id)
    require_project_access(db, request, row.project_id, write=True)
    try:
        velocity = float(data.get("velocity_m_s"))
    except (TypeError, ValueError):
        raise HTTPException(400, "velocity_m_s is required")
    try:
        inline_spacing = float(data.get("inline_spacing_m", 25.0))
        crossline_spacing = float(data.get("crossline_spacing_m", 25.0))
    except (TypeError, ValueError):
        raise HTTPException(400, "inline/crossline spacing must be numbers")
    max_inlines = max(2, min(int(data.get("max_inlines", 24) or 24), 32))
    max_crosslines = max(2, min(int(data.get("max_crosslines", 24) or 24), 32))
    max_samples = max(8, min(int(data.get("max_samples", 192) or 192), 256))
    max_depth = max(8, min(int(data.get("max_depth_samples", 128) or 128), 192))
    aperture = data.get("aperture_m")
    aperture = max(1.0, float(aperture)) if aperture else None
    try:
        with open(row.file_path, "rb") as handle:
            content = handle.read()
        volume = volume_cube(content, _index(row), max_inlines, max_crosslines, max_samples)
        migrated = kirchhoff_migrate(
            volume["cube"],
            volume["inlines"],
            volume["crosslines"],
            volume["sample_interval_ms"],
            velocity,
            inline_spacing,
            crossline_spacing,
            max_depth_samples=max_depth,
            aperture_m=aperture,
        )
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        raise HTTPException(400, f"could not migrate 3D volume: {exc}")
    os.makedirs(MIGRATION_DIR, exist_ok=True)
    path = os.path.join(MIGRATION_DIR, f"{uuid.uuid4().hex}.npz")
    np.savez_compressed(
        path,
        cube=migrated["cube"].astype(np.float32),
        inlines=np.asarray(migrated["inlines"], dtype=np.int32),
        crosslines=np.asarray(migrated["crosslines"], dtype=np.int32),
        depths=np.asarray(migrated["depths_m"], dtype=np.float64),
    )
    item = SeismicMigration(
        line_id=line_id,
        name=str(data.get("name") or f"Migration {velocity:.0f} m/s"),
        velocity_m_s=velocity,
        inline_spacing_m=inline_spacing,
        crossline_spacing_m=crossline_spacing,
        file_path=path,
        inlines_json=json.dumps(migrated["inlines"]),
        crosslines_json=json.dumps(migrated["crosslines"]),
        depths_json=json.dumps(migrated["depths_m"]),
        stats_json=json.dumps(migrated["stats"]),
    )
    db.add(item)
    db.commit()
    db.refresh(item)
    return _serialized(item)


@router.get("/seismic/{line_id}/migrations")
def list_migrations(line_id: int, request: Request, db: Session = Depends(get_db)):
    row = _line(db, line_id)
    require_project_access(db, request, row.project_id)
    rows = (
        db.query(SeismicMigration)
        .filter(SeismicMigration.line_id == line_id)
        .order_by(SeismicMigration.id.desc())
        .all()
    )
    return [_serialized(item) for item in rows]


@router.get("/seismic/{line_id}/migrations/{migration_id}")
def get_migration(line_id: int, migration_id: int, request: Request, db: Session = Depends(get_db)):
    row = _line(db, line_id)
    require_project_access(db, request, row.project_id)
    item = (
        db.query(SeismicMigration)
        .filter(SeismicMigration.id == migration_id, SeismicMigration.line_id == line_id)
        .first()
    )
    if not item:
        raise HTTPException(404, "Migration not found")
    return _serialized(item)


@router.get("/seismic/{line_id}/migrations/{migration_id}/section")
def migration_section(
    line_id: int,
    migration_id: int,
    request: Request,
    inline: int | None = None,
    crossline: int | None = None,
    db: Session = Depends(get_db),
):
    row = _line(db, line_id)
    require_project_access(db, request, row.project_id)
    item = (
        db.query(SeismicMigration)
        .filter(SeismicMigration.id == migration_id, SeismicMigration.line_id == line_id)
        .first()
    )
    if not item:
        raise HTTPException(404, "Migration not found")
    artifact = _load_cube(item)
    cube = artifact["cube"]
    inlines = artifact["inlines"]
    crosslines = artifact["crosslines"]
    depths = artifact["depths"]
    if inline is not None:
        if inline not in inlines:
            raise HTTPException(404, "Inline not present in migration")
        index = inlines.index(inline)
        data = cube[index, :, :].T
        return {
            "mode": "inline",
            "value": inline,
            "labels": crosslines,
            "depths_m": depths,
            "data": np.round(data, 6).tolist(),
        }
    if crossline is not None:
        if crossline not in crosslines:
            raise HTTPException(404, "Crossline not present in migration")
        index = crosslines.index(crossline)
        data = cube[:, index, :].T
        return {
            "mode": "crossline",
            "value": crossline,
            "labels": inlines,
            "depths_m": depths,
            "data": np.round(data, 6).tolist(),
        }
    center_inline = inlines[len(inlines) // 2]
    index = inlines.index(center_inline)
    data = cube[index, :, :].T
    return {
        "mode": "inline",
        "value": center_inline,
        "labels": crosslines,
        "depths_m": depths,
        "data": np.round(data, 6).tolist(),
    }


@router.delete("/seismic/{line_id}/migrations/{migration_id}", status_code=204)
def delete_migration(line_id: int, migration_id: int, request: Request, db: Session = Depends(get_db)):
    row = _line(db, line_id)
    require_project_access(db, request, row.project_id, write=True)
    item = (
        db.query(SeismicMigration)
        .filter(SeismicMigration.id == migration_id, SeismicMigration.line_id == line_id)
        .first()
    )
    if not item:
        raise HTTPException(404, "Migration not found")
    path = item.file_path
    db.delete(item)
    db.commit()
    try:
        if path and os.path.exists(path):
            os.remove(path)
    except OSError:
        pass
