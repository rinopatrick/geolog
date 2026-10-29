"""Source-rock TOC and kerogen screening endpoints."""

from __future__ import annotations

import json

import numpy as np
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

try:
    from database import get_db
    from models import CurveData, LogRun, SourceRockAnalysis, Well
    from routers.wells import _aligned, _first_curve, _semantic_curves
    from source_rock import kerogen_volume, passey_toc, schmoker_toc, stats
except ImportError:
    from backend.database import get_db
    from backend.models import CurveData, LogRun, SourceRockAnalysis, Well
    from backend.routers.wells import _aligned, _first_curve, _semantic_curves
    from backend.source_rock import kerogen_volume, passey_toc, schmoker_toc, stats

router = APIRouter(prefix="/api/wells", tags=["wells"])


def _upsert_curve(db: Session, log_run_id: int, mnemonic: str, values: np.ndarray, unit: str, description: str) -> str:
    valid = values[np.isfinite(values)]
    existing = (
        db.query(CurveData)
        .filter(CurveData.log_run_id == log_run_id, CurveData.mnemonic == mnemonic)
        .first()
    )
    if existing:
        existing.data_binary = values.tobytes()
        existing.num_points = len(values)
        existing.min_value = float(np.min(valid)) if len(valid) else None
        existing.max_value = float(np.max(valid)) if len(valid) else None
        existing.unit = unit
        existing.description = description
        return existing.mnemonic
    db.add(
        CurveData(
            log_run_id=log_run_id,
            mnemonic=mnemonic,
            unit=unit,
            description=description,
            num_points=len(values),
            min_value=float(np.min(valid)) if len(valid) else None,
            max_value=float(np.max(valid)) if len(valid) else None,
            data_binary=values.tobytes(),
        )
    )
    return mnemonic


def _optional_float(data: dict, key: str, default: float | None = None) -> float | None:
    value = data.get(key)
    if value in (None, ""):
        return default
    try:
        return float(value)
    except (TypeError, ValueError):
        raise HTTPException(400, f"{key} must be a number")


@router.post("/{wid}/source-rock")
def compute_source_rock(wid: int, data: dict, db: Session = Depends(get_db)):
    if not db.query(Well.id).filter(Well.id == wid).first():
        raise HTTPException(404, "Well not found")
    lr_id = data.get("log_run_id")
    lr = (
        db.query(LogRun).filter(LogRun.id == lr_id).first()
        if lr_id
        else db.query(LogRun).filter(LogRun.well_id == wid).order_by(LogRun.num_points.desc()).first()
    )
    if not lr or lr.well_id != wid:
        raise HTTPException(404, "No log run found")
    if not lr.num_points or lr.num_points < 3:
        raise HTTPException(400, "Log run has insufficient data")

    depth, by_name = _semantic_curves(db, lr)
    n = len(depth)
    rt = _first_curve(by_name, ["RT", "LLD", "ILD", "RILD", "RESD", "MSFL"])
    if rt is None:
        raise HTTPException(400, "A resistivity curve is required (RT/LLD/ILD/RESD/MSFL)")
    rt = _aligned(rt, n)

    method = str(data.get("method", "passey") or "passey").lower()
    porosity_mode = str(data.get("porosity_mode", "sonic") or "sonic").lower()
    rhob = _first_curve(by_name, ["RHOB", "DEN", "ZDEN"])
    rhob_arr = _aligned(rhob, n) if rhob is not None else None
    warnings: list[str] = []

    if method == "schmoker":
        if rhob_arr is None:
            raise HTTPException(400, "Schmoker TOC requires a density curve (RHOB/DEN/ZDEN)")
        toc = schmoker_toc(rhob_arr)
        baseline = {"method": "schmoker"}
        method = "schmoker"
    elif method == "passey":
        mode = porosity_mode
        if mode == "density":
            porosity = rhob_arr
            if porosity is None:
                raise HTTPException(400, "Passey density mode requires a density curve")
        else:
            porosity = _first_curve(by_name, ["DT", "DTC", "AC", "SONIC"])
            if porosity is None:
                raise HTTPException(400, "Passey sonic mode requires a sonic curve (DT/DTC/AC)")
            porosity = _aligned(porosity, n)
        baseline_data = data.get("baseline") if isinstance(data.get("baseline"), dict) else {}
        try:
            toc, baseline = passey_toc(
                rt,
                porosity,
                porosity_mode=mode,
                rt_base=_optional_float(baseline_data, "rt_base"),
                porosity_base=_optional_float(baseline_data, "porosity_base"),
                lom=_optional_float(data, "lom", 10.0) or 10.0,
                toc_base=_optional_float(data, "toc_base", 0.0) or 0.0,
            )
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc
        method = "passey"
    else:
        raise HTTPException(400, "method must be 'passey' or 'schmoker'")

    toc = _aligned(toc, n)
    if rhob_arr is None:
        rhob_for_vker = np.full(n, 2.5, dtype=np.float64)
        warnings.append("RHOB missing; kerogen volume assumes 2.5 g/cc bulk density")
    else:
        rhob_for_vker = rhob_arr
    vker = kerogen_volume(toc, rhob_for_vker)

    toc_name = _upsert_curve(db, lr.id, "TOC", toc, "wt%", f"{method} TOC")
    vker_name = _upsert_curve(db, lr.id, "VKER", vker, "v/v", f"{method} kerogen volume")
    toc_stats = stats(toc)
    vker_stats = stats(vker)
    analysis = SourceRockAnalysis(
        well_id=wid,
        log_run_id=lr.id,
        method=method,
        porosity_mode=porosity_mode,
        lom=(baseline or {}).get("lom") if isinstance(baseline, dict) else None,
        toc_base=(baseline or {}).get("toc_base") if isinstance(baseline, dict) else None,
        rt_base=(baseline or {}).get("rt_base") if isinstance(baseline, dict) else None,
        porosity_base=(baseline or {}).get("porosity_base") if isinstance(baseline, dict) else None,
        toc_curve=toc_name,
        vker_curve=vker_name,
        stats_json=json.dumps({"toc": toc_stats, "vker": vker_stats}),
        warnings_json=json.dumps(warnings),
    )
    db.add(analysis)
    db.commit()
    db.refresh(analysis)

    return {
        "status": "ok",
        "analysis_id": analysis.id,
        "well_id": wid,
        "log_run_id": lr.id,
        "method": method,
        "curves": {"toc": toc_name, "vker": vker_name},
        "baseline": baseline,
        "stats": {"toc": toc_stats, "vker": vker_stats},
        "warnings": warnings,
    }


@router.get("/{wid}/source-rock/analyses")
def list_source_rock_analyses(wid: int, db: Session = Depends(get_db)):
    if not db.query(Well.id).filter(Well.id == wid).first():
        raise HTTPException(404, "Well not found")
    rows = (
        db.query(SourceRockAnalysis)
        .filter(SourceRockAnalysis.well_id == wid)
        .order_by(SourceRockAnalysis.id.desc())
        .all()
    )
    result = []
    for row in rows:
        try:
            result.append({
                "id": row.id,
                "well_id": row.well_id,
                "log_run_id": row.log_run_id,
                "method": row.method,
                "porosity_mode": row.porosity_mode,
                "lom": row.lom,
                "toc_base": row.toc_base,
                "rt_base": row.rt_base,
                "porosity_base": row.porosity_base,
                "toc_curve": row.toc_curve,
                "vker_curve": row.vker_curve,
                "stats": json.loads(row.stats_json or "{}"),
                "warnings": json.loads(row.warnings_json or "[]"),
                "created_at": row.created_at.isoformat() if row.created_at else "",
            })
        except Exception:
            continue
    return result
