"""Saved report templates for the custom PDF builder."""

from __future__ import annotations

import json

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

try:
    from database import get_db
    from deps import require_admin, require_interpreter, require_viewer
    from models import ReportTemplate
except ImportError:
    from backend.database import get_db
    from backend.deps import require_admin, require_interpreter, require_viewer
    from backend.models import ReportTemplate

router = APIRouter(prefix="/api/report-templates", tags=["reports"])

ALLOWED_SECTIONS = {
    "rock_source", "zonation", "production", "qc", "curves",
}


def _config(data: dict) -> dict:
    name = str(data.get("name") or "").strip()
    if not name:
        raise HTTPException(400, "name is required")
    sections = data.get("sections") or ["rock_source", "zonation", "production", "qc", "curves"]
    if not isinstance(sections, list):
        raise HTTPException(400, "sections must be a list")
    cleaned = []
    for section in sections:
        key = str(section).strip().lower()
        if key in ALLOWED_SECTIONS and key not in cleaned:
            cleaned.append(key)
    if not cleaned:
        raise HTTPException(400, "at least one valid section is required")
    return {
        "name": name,
        "description": str(data.get("description") or ""),
        "sections": cleaned,
        "include_curves": bool(data.get("include_curves", "curves" in cleaned)),
        "title": str(data.get("title") or "GeoLog Well Report"),
    }


def _payload(row: ReportTemplate) -> dict:
    try:
        config = json.loads(row.config_json or "{}")
    except json.JSONDecodeError:
        config = {}
    return {
        "id": row.id,
        "name": row.name,
        "description": row.description or "",
        "config": config,
        "created_at": row.created_at.isoformat() if row.created_at else "",
        "updated_at": row.updated_at.isoformat() if row.updated_at else "",
    }


@router.get("")
def list_templates(db: Session = Depends(get_db), _role: str = Depends(require_viewer)):
    rows = db.query(ReportTemplate).order_by(ReportTemplate.id.desc()).all()
    return [_payload(row) for row in rows]


@router.post("", status_code=201)
def create_template(data: dict, db: Session = Depends(get_db), _role: str = Depends(require_interpreter)):
    config = _config(data)
    row = ReportTemplate(
        name=config["name"],
        description=config["description"],
        config_json=json.dumps(config),
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return _payload(row)


@router.put("/{template_id}")
def update_template(template_id: int, data: dict, db: Session = Depends(get_db), _role: str = Depends(require_interpreter)):
    row = db.query(ReportTemplate).filter(ReportTemplate.id == template_id).first()
    if not row:
        raise HTTPException(404, "Template not found")
    config = _config(data)
    row.name = config["name"]
    row.description = config["description"]
    row.config_json = json.dumps(config)
    db.commit()
    db.refresh(row)
    return _payload(row)


@router.delete("/{template_id}", status_code=204)
def delete_template(template_id: int, db: Session = Depends(get_db), _role: str = Depends(require_admin)):
    row = db.query(ReportTemplate).filter(ReportTemplate.id == template_id).first()
    if not row:
        raise HTTPException(404, "Template not found")
    db.delete(row)
    db.commit()
