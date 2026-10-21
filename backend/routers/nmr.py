"""NMR T2 interpretation router."""

from __future__ import annotations

import json

import numpy as np
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

try:
    from database import SessionLocal, get_db
    from jobs import JOB_EXECUTOR, create_job as _create_job, update_job as _update_job, utc_now_iso as _utc_now_iso
    from models import LogRun, NmrInversion, Well
    from nmr import (
        DEFAULT_CUTOFF_MS,
        derived_curves,
        load_amplitudes,
        load_depth,
        nnls,
        read_curve_matrix,
        read_echo_matrix,
        regularized_invert,
        store_derived_curves,
        store_inversion,
        summary,
        t2_grid,
    )
except ImportError:
    from backend.database import SessionLocal, get_db
    from backend.jobs import JOB_EXECUTOR, create_job as _create_job, update_job as _update_job, utc_now_iso as _utc_now_iso
    from backend.models import LogRun, NmrInversion, Well
    from backend.nmr import (
        DEFAULT_CUTOFF_MS,
        derived_curves,
        load_amplitudes,
        load_depth,
        nnls,
        read_curve_matrix,
        read_echo_matrix,
        regularized_invert,
        store_derived_curves,
        store_inversion,
        summary,
        t2_grid,
    )

router = APIRouter(prefix="/api/wells/{wid}", tags=["nmr"])

def _log_run(db: Session, wid: int, lr_id=None) -> LogRun:
    well = db.query(Well).filter(Well.id == wid).first()
    if not well:
        raise HTTPException(404, "Well not found")
    lr = db.query(LogRun).filter(LogRun.id == lr_id).first() if lr_id else (
        db.query(LogRun).filter(LogRun.well_id == wid).order_by(LogRun.num_points.desc()).first()
    )
    if not lr or lr.well_id != wid:
        raise HTTPException(404, "Log run not found")
    return lr

def _bins(data: dict, count: int) -> np.ndarray:
    raw = data.get("t2_bins_ms")
    if raw:
        if not isinstance(raw, list) or len(raw) != count:
            raise HTTPException(400, "t2_bins_ms must be a list matching the number of bin curves")
        try:
            bins = np.asarray([float(v) for v in raw], dtype=np.float64)
        except (TypeError, ValueError):
            raise HTTPException(400, "t2_bins_ms must be numeric")
    else:
        bins = t2_grid(count=count)
    if np.any(~np.isfinite(bins)) or np.any(bins <= 0):
        raise HTTPException(400, "T2 bins must be positive and finite")
    return bins

def _series(values: np.ndarray) -> list:
    return [None if not np.isfinite(v) else round(float(v), 6) for v in values]

def _inversion_meta(inv: NmrInversion) -> dict:
    return {
        "id": inv.id,
        "well_id": inv.well_id,
        "log_run_id": inv.log_run_id,
        "method": inv.method,
        "t2_bins_ms": json.loads(inv.t2_bins_json or "[]"),
        "cutoff_ms": inv.cutoff_ms,
        "lambda": inv.lambda_value,
        "n_depth": inv.n_depth,
        "n_bins": inv.n_bins,
        "params_hash": inv.params_hash,
        "engine_version": inv.engine_version,
        "created_at": inv.created_at.isoformat() if inv.created_at else "",
    }

@router.post("/nmr/interpret")
def interpret_nmr(wid: int, data: dict, db: Session = Depends(get_db)):
    """Interpret existing vendor T2-bin curves as porosity/volume curves."""
    lr = _log_run(db, wid, data.get("log_run_id"))
    names = data.get("bin_mnemonics") or data.get("curves")
    if not isinstance(names, list) or len(names) < 2:
        raise HTTPException(400, "bin_mnemonics must list at least two T2-bin curves")
    names = [str(n) for n in names]
    bins = _bins(data, len(names))
    cutoff = float(data.get("cutoff_ms", DEFAULT_CUTOFF_MS) or DEFAULT_CUTOFF_MS)
    if cutoff <= 0:
        raise HTTPException(400, "cutoff_ms must be > 0")
    sdr_a = float(data.get("sdr_a", 4.0) or 4.0)
    coates_c = float(data.get("coates_c", 1e4) or 1e4)

    try:
        depth, amplitudes, sem = read_curve_matrix(db, lr, names)
    except ValueError as exc:
        raise HTTPException(400, str(exc))
    amplitudes = np.nan_to_num(amplitudes, nan=0.0, posinf=0.0, neginf=0.0)
    derived = derived_curves(amplitudes, bins, cutoff, sdr_a, coates_c)

    inversion_id = None
    curves_saved = []
    if bool(data.get("save", True)):
        inv = store_inversion(
            db, wid, lr.id, "vendor_bins", bins, amplitudes, depth,
            cutoff, 0.0,
            {"method": "vendor_bins", "bin_mnemonics": names, "cutoff_ms": cutoff, "sdr_a": sdr_a, "coates_c": coates_c},
        )
        inversion_id = inv.id
    if bool(data.get("save_curves", True)):
        curves_saved = store_derived_curves(db, lr.id, derived)

    payload = {
        "well_id": wid,
        "log_run_id": lr.id,
        "method": "vendor_bins",
        "inversion_id": inversion_id,
        "t2_bins_ms": [round(float(v), 6) for v in bins],
        "cutoff_ms": cutoff,
        "stats": summary(derived),
        "curves_saved": curves_saved,
        "semantics": sem["metadata"],
    }
    if bool(data.get("include_curves", True)):
        payload["curves"] = {name: _series(values) for name, values in derived.items()}
        payload["depth"] = _series(depth)
    return payload

@router.post("/nmr/invert-async", status_code=202)
def invert_nmr_async(wid: int, data: dict):
    """Queue raw CPMG echo inversion; use /api/jobs/{job_id} to poll."""
    if nnls is None:
        raise HTTPException(503, "SciPy is required for raw-echo NMR inversion")
    lr_id = data.get("log_run_id")
    echoes = data.get("echo_mnemonics")
    te_ms = data.get("te_ms")
    if not isinstance(echoes, list) or len(echoes) < 2:
        raise HTTPException(400, "echo_mnemonics must list at least two echo curves")
    if not isinstance(te_ms, list) or len(te_ms) != len(echoes):
        raise HTTPException(400, "te_ms must be a list matching echo_mnemonics")
    try:
        te = [float(v) for v in te_ms]
    except (TypeError, ValueError):
        raise HTTPException(400, "te_ms must be numeric")
    if any(v <= 0 for v in te):
        raise HTTPException(400, "TE values must be positive")
    bins = _bins(data, int(data.get("n_bins", 24) or 24))
    cutoff = float(data.get("cutoff_ms", DEFAULT_CUTOFF_MS) or DEFAULT_CUTOFF_MS)
    lam = float(data.get("lambda_value", data.get("lambda", 0.1)) or 0.1)

    # Validate the run before queueing so the job does not fail on a typo.
    db = SessionLocal()
    try:
        lr = _log_run(db, wid, lr_id)
        lr_id = lr.id
    finally:
        db.close()

    job_id = _create_job("nmr-inversion")

    def _run():
        db2 = SessionLocal()
        try:
            _update_job(job_id, status="running", progress=10, started_at=_utc_now_iso())
            lr2 = _log_run(db2, wid, lr_id)
            depth, matrix, _ = read_echo_matrix(db2, lr2, [str(v) for v in echoes], te)
            amplitudes = regularized_invert(matrix, te, bins, lam)
            derived = derived_curves(amplitudes, bins, cutoff)
            inv = store_inversion(
                db2, wid, lr2.id, "nnls", bins, amplitudes, depth,
                cutoff, lam,
                {"method": "nnls", "echo_mnemonics": echoes, "te_ms": te, "cutoff_ms": cutoff, "lambda": lam},
            )
            saved = store_derived_curves(db2, lr2.id, derived)
            _update_job(
                job_id, status="done", progress=100,
                result={"inversion_id": inv.id, "stats": summary(derived), "curves_saved": saved},
            )
        except Exception as exc:
            _update_job(job_id, status="failed", progress=100, error=str(exc))
        finally:
            _update_job(job_id, finished_at=_utc_now_iso())
            db2.close()

    JOB_EXECUTOR.submit(_run)
    return {"job_id": job_id, "status": "queued"}

@router.get("/nmr/inversions")
def list_nmr_inversions(wid: int, db: Session = Depends(get_db)):
    if not db.query(Well.id).filter(Well.id == wid).first():
        raise HTTPException(404, "Well not found")
    rows = (
        db.query(NmrInversion)
        .filter(NmrInversion.well_id == wid)
        .order_by(NmrInversion.id.desc())
        .all()
    )
    return [_inversion_meta(row) for row in rows]

@router.get("/nmr/inversions/{inversion_id}")
def get_nmr_inversion(wid: int, inversion_id: int, db: Session = Depends(get_db)):
    inv = (
        db.query(NmrInversion)
        .filter(NmrInversion.id == inversion_id, NmrInversion.well_id == wid)
        .first()
    )
    if not inv:
        raise HTTPException(404, "NMR inversion not found")
    return _inversion_meta(inv)

@router.get("/nmr/inversions/{inversion_id}/distribution")
def get_nmr_distribution(wid: int, inversion_id: int, max_points: int = 800, db: Session = Depends(get_db)):
    inv = (
        db.query(NmrInversion)
        .filter(NmrInversion.id == inversion_id, NmrInversion.well_id == wid)
        .first()
    )
    if not inv:
        raise HTTPException(404, "NMR inversion not found")
    amps = load_amplitudes(inv)
    depth = load_depth(inv)
    if amps.size == 0:
        return {"inversion_id": inv.id, "depth": [], "t2_bins_ms": [], "amplitudes": []}
    max_points = max(1, min(int(max_points or 800), 5000))
    step = max(1, int(np.ceil(len(depth) / max_points)))
    return {
        "inversion_id": inv.id,
        "t2_bins_ms": json.loads(inv.t2_bins_json or "[]"),
        "depth": [round(float(v), 4) for v in depth[::step]],
        "amplitudes": [[round(float(v), 6) for v in row] for row in amps[::step]],
        "n_points": int(len(depth[::step])),
    }
