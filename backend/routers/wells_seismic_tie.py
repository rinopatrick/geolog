"""Well-to-seismic ties at an inline/crossline location."""

from __future__ import annotations

import json
import os

import numpy as np

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

try:
    from acl import require_project_access, require_well_access
    from database import get_db
    from models import SeismicLine, Well, WellSeismicTie
    from seismic import index_segy, read_indexed_traces
    from seismic_tie import build_tie, validate_checkshot
except ImportError:
    from backend.acl import require_project_access, require_well_access
    from backend.database import get_db
    from backend.models import SeismicLine, Well, WellSeismicTie
    from backend.seismic import index_segy, read_indexed_traces
    from backend.seismic_tie import build_tie, validate_checkshot

router = APIRouter(prefix="/api/wells", tags=["well-seismic-tie"])


def _serialized(row: WellSeismicTie, include_result: bool = False) -> dict:
    payload = {
        "id": row.id,
        "well_id": row.well_id,
        "line_id": row.line_id,
        "name": row.name,
        "inline": row.inline,
        "crossline": row.crossline,
        "shift_ms": row.shift_ms,
        "correlation": row.correlation,
        "created_at": row.created_at.isoformat() if row.created_at else "",
    }
    if include_result:
        try:
            payload["result"] = json.loads(row.result_json or "{}")
        except json.JSONDecodeError:
            payload["result"] = {}
        try:
            payload["checkshot"] = json.loads(row.checkshot_json or "[]")
        except json.JSONDecodeError:
            payload["checkshot"] = []
    return payload


def _index(row: SeismicLine) -> dict:
    if row.trace_headers_path and os.path.exists(row.trace_headers_path):
        try:
            with open(row.trace_headers_path, encoding="utf-8") as handle:
                return json.load(handle)
        except (OSError, json.JSONDecodeError):
            pass
    with open(row.file_path, "rb") as handle:
        return index_segy(handle.read())


@router.post("/{wid}/seismic-ties", status_code=201)
def create_seismic_tie(wid: int, data: dict, request: Request, db: Session = Depends(get_db)):
    require_well_access(db, request, wid, write=True)
    well = db.query(Well).filter(Well.id == wid).first()
    if not well:
        raise HTTPException(404, "Well not found")
    try:
        line_id = int(data.get("line_id"))
        inline = int(data.get("inline"))
        crossline = int(data.get("crossline"))
    except (TypeError, ValueError):
        raise HTTPException(400, "line_id, inline and crossline are required integers")
    line = db.query(SeismicLine).filter(SeismicLine.id == line_id).first()
    if not line:
        raise HTTPException(404, "Seismic line not found")
    require_project_access(db, request, line.project_id)
    try:
        checkshot = validate_checkshot(data.get("checkshot"))
    except ValueError as exc:
        raise HTTPException(400, str(exc))
    trace_delay_ms = 0.0
    try:
        with open(line.file_path, "rb") as handle:
            content = handle.read()
        index = _index(line)
        positions = [
            position
            for position, (trace_inline, trace_crossline) in enumerate(
                zip(index.get("trace_inlines", []), index.get("trace_crosslines", []))
            )
            if int(trace_inline) == inline and int(trace_crossline) == crossline
        ]
        if not positions:
            raise HTTPException(404, f"no trace at inline {inline}, crossline {crossline}")
        delays = index.get("trace_delays") or []
        if delays:
            trace_delay_ms = float(delays[positions[0]])
        traces = read_indexed_traces(content, index, positions)
        seismic = np.mean(traces, axis=0)
    except HTTPException:
        raise
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        raise HTTPException(500, f"could not read seismic trace: {exc}")

    try:
        from routers.wells_analytics import _compute_synthetic_seismogram
    except ImportError:
        from backend.routers.wells_analytics import _compute_synthetic_seismogram
    synthetic = _compute_synthetic_seismogram(
        wid,
        {
            "wavelet_freq": data.get("frequency_hz", data.get("wavelet_freq", 30)),
            "polarity": data.get("polarity", "normal"),
            "phase": data.get("phase", 0),
        },
        db,
    )
    max_shift = max(1.0, min(float(data.get("max_shift_ms", 40) or 40), 500.0))
    datum_ms = float(data.get("datum_ms", 0) or 0)
    try:
        result = build_tie(
            synthetic,
            np.asarray(seismic, dtype=float),
            float(index["sample_interval_ms"]),
            checkshot,
            max_shift_ms=max_shift,
            time_origin_ms=trace_delay_ms + datum_ms,
        )
    except ValueError as exc:
        raise HTTPException(400, str(exc))
    name = str(data.get("name") or f"{well.name} @ {inline}/{crossline}").strip()
    item = WellSeismicTie(
        well_id=wid,
        line_id=line_id,
        name=name,
        inline=inline,
        crossline=crossline,
        checkshot_json=json.dumps(checkshot),
        result_json=json.dumps(result),
        shift_ms=result["shift_ms"],
        correlation=result["correlation"],
    )
    db.add(item)
    db.commit()
    db.refresh(item)
    return _serialized(item, include_result=True)


@router.get("/{wid}/seismic-ties")
def list_seismic_ties(wid: int, request: Request, db: Session = Depends(get_db)):
    require_well_access(db, request, wid)
    rows = (
        db.query(WellSeismicTie)
        .filter(WellSeismicTie.well_id == wid)
        .order_by(WellSeismicTie.id.desc())
        .all()
    )
    return [_serialized(row) for row in rows]


@router.get("/{wid}/seismic-ties/{tie_id}")
def get_seismic_tie(wid: int, tie_id: int, request: Request, db: Session = Depends(get_db)):
    require_well_access(db, request, wid)
    item = (
        db.query(WellSeismicTie)
        .filter(WellSeismicTie.id == tie_id, WellSeismicTie.well_id == wid)
        .first()
    )
    if not item:
        raise HTTPException(404, "Seismic tie not found")
    return _serialized(item, include_result=True)


@router.delete("/{wid}/seismic-ties/{tie_id}", status_code=204)
def delete_seismic_tie(wid: int, tie_id: int, request: Request, db: Session = Depends(get_db)):
    require_well_access(db, request, wid, write=True)
    item = (
        db.query(WellSeismicTie)
        .filter(WellSeismicTie.id == tie_id, WellSeismicTie.well_id == wid)
        .first()
    )
    if not item:
        raise HTTPException(404, "Seismic tie not found")
    db.delete(item)
    db.commit()
