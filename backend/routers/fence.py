"""Arbitrary lines and fence diagrams over SEG-Y volumes."""

from __future__ import annotations

import json
import os

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

try:
    from acl import require_project_access
    from database import get_db
    from fence import arbitrary_line
    from models import SeismicLine
    from seismic import index_segy
except ImportError:
    from backend.acl import require_project_access
    from backend.database import get_db
    from backend.fence import arbitrary_line
    from backend.models import SeismicLine
    from backend.seismic import index_segy

router = APIRouter(prefix="/api", tags=["fences"])


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


def _content(row: SeismicLine) -> bytes:
    with open(row.file_path, "rb") as handle:
        return handle.read()


@router.get("/seismic/{line_id}/arbitrary-line")
def get_arbitrary_line(
    line_id: int,
    request: Request,
    inline1: float,
    crossline1: float,
    inline2: float,
    crossline2: float,
    max_traces: int = 600,
    max_samples: int = 600,
    inline_spacing_m: float | None = None,
    crossline_spacing_m: float | None = None,
    db: Session = Depends(get_db),
):
    row = _line(db, line_id)
    require_project_access(db, request, row.project_id)
    try:
        section = arbitrary_line(
            _content(row),
            _index(row),
            (inline1, crossline1),
            (inline2, crossline2),
            max_traces=max(2, min(int(max_traces), 1500)),
            max_samples=max(2, min(int(max_samples), 1500)),
            inline_spacing_m=inline_spacing_m,
            crossline_spacing_m=crossline_spacing_m,
        )
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        raise HTTPException(400, f"could not build arbitrary line: {exc}")
    return section


@router.post("/seismic/{line_id}/fences")
def create_fence(
    line_id: int,
    data: dict,
    request: Request,
    db: Session = Depends(get_db),
):
    row = _line(db, line_id)
    require_project_access(db, request, row.project_id)
    segments = data.get("segments")
    if not isinstance(segments, list) or not segments or len(segments) > 6:
        raise HTTPException(400, "segments must be a list of 1 to 6 lines")
    content = _content(row)
    index = _index(row)
    fences = []
    for position, segment in enumerate(segments):
        if not isinstance(segment, dict):
            raise HTTPException(400, f"segments[{position}] must be an object")
        try:
            fences.append(arbitrary_line(
                content,
                index,
                (float(segment["inline1"]), float(segment["crossline1"])),
                (float(segment["inline2"]), float(segment["crossline2"])),
                max_traces=max(2, min(int(segment.get("max_traces", 600)), 1500)),
                max_samples=max(2, min(int(segment.get("max_samples", 600)), 1500)),
                inline_spacing_m=segment.get("inline_spacing_m"),
                crossline_spacing_m=segment.get("crossline_spacing_m"),
            ))
        except (KeyError, TypeError, ValueError) as exc:
            raise HTTPException(400, f"segments[{position}]: {exc}")
    return {"line_id": row.id, "fences": fences}
