"""Log-run router for GeoLog.

Covers per-run curve access, depth shifting, filtering, editing and decimation.
Extracted from backend/main.py; the helpers below were used only by these routes.
"""

from __future__ import annotations

import datetime
import hashlib

import numpy as np
from email.utils import format_datetime, parsedate_to_datetime
from fastapi import APIRouter, Depends, Header, HTTPException
from sqlalchemy.orm import Session

try:
    from timeutils import utcnow
except ImportError:
    from backend.timeutils import utcnow

try:
    from database import get_db
    from deps import SafeJSONResponse
    from las_parser import CURVE_TRACKS
    from models import CurveData, DepthControlPoint, LogRun, LogRunDepthShift
    from semantics import apply_run_semantics
    from validation import optional_float, optional_str
except ImportError:
    from backend.database import get_db
    from backend.deps import SafeJSONResponse
    from backend.las_parser import CURVE_TRACKS
    from backend.models import CurveData, DepthControlPoint, LogRun, LogRunDepthShift
    from backend.semantics import apply_run_semantics
    from backend.validation import optional_float, optional_str

router = APIRouter(prefix="/api/log-runs", tags=["log-runs"])

# In-memory original-value snapshots for curve point edits.
# Keyed by "<log_run_id>:<mnemonic>" -> {"index": original_value}
CURVE_EDIT_ORIGINALS = {}


def _httpdate(dt: datetime.datetime) -> str:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=datetime.timezone.utc)
    else:
        dt = dt.astimezone(datetime.timezone.utc)
    return format_datetime(dt, usegmt=True)

def _parse_if_modified_since(value: str):
    if not value:
        return None
    try:
        dt = parsedate_to_datetime(value)
        if dt is None:
            return None
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=datetime.timezone.utc)
        return dt.astimezone(datetime.timezone.utc)
    except Exception:
        return None

def _build_curve_cache_headers(lr_id: int, mnemonics, start, stop, step, max_points=None, extra=""):
    key = f"{lr_id}|{','.join(sorted([str(m) for m in (mnemonics or [])]))}|{start}|{stop}|{step}|{max_points}|{extra}"
    # Cache-busting only — not a security primitive, hence usedforsecurity=False.
    etag = f'W/"{hashlib.sha1(key.encode("utf-8"), usedforsecurity=False).hexdigest()}"'
    return {
        "ETag": etag,
        "Cache-Control": "private, max-age=60",
    }

def _lttb_indices(x: np.ndarray, y: np.ndarray, threshold: int):
    n = len(y)
    if threshold >= n or threshold <= 2 or n <= 2:
        return np.arange(n, dtype=np.int64)

    sampled = np.zeros(threshold, dtype=np.int64)
    sampled[0] = 0
    sampled[-1] = n - 1
    every = (n - 2) / float(threshold - 2)
    a = 0

    for i in range(threshold - 2):
        avg_start = int(np.floor((i + 1) * every)) + 1
        avg_end = int(np.floor((i + 2) * every)) + 1
        avg_end = min(avg_end, n)
        if avg_start < avg_end:
            avg_x = np.nanmean(x[avg_start:avg_end])
            avg_y = np.nanmean(y[avg_start:avg_end])
        else:
            idx = min(avg_start, n - 1)
            avg_x = x[idx]
            avg_y = y[idx]

        if np.isnan(avg_y):
            sampled[i + 1] = min(avg_start, n - 2)
            a = sampled[i + 1]
            continue

        range_offs = int(np.floor(i * every)) + 1
        range_to = int(np.floor((i + 1) * every)) + 1
        range_to = min(range_to, n - 1)

        if range_offs >= range_to:
            sampled[i + 1] = min(range_offs, n - 2)
            a = sampled[i + 1]
            continue

        ax = x[a]
        ay = y[a]
        if np.isnan(ay):
            sampled[i + 1] = min(range_offs, n - 2)
            a = sampled[i + 1]
            continue
        bx = x[range_offs:range_to]
        by = y[range_offs:range_to]
        area = np.abs((ax - avg_x) * (by - ay) - (ax - bx) * (avg_y - ay)) * 0.5
        area = np.where(np.isnan(area), 0, area)
        idx = int(np.nanargmax(area))
        a = range_offs + idx
        sampled[i + 1] = a

    return np.unique(np.clip(sampled, 0, n - 1))

def _group_flagged_intervals(depth: np.ndarray, flags: np.ndarray):
    if depth is None or flags is None or len(depth) == 0 or len(flags) == 0:
        return []
    n = min(len(depth), len(flags))
    intervals = []
    active = False
    start_idx = 0
    for i in range(n):
        is_on = bool(flags[i])
        if is_on and not active:
            active = True
            start_idx = i
        elif not is_on and active:
            end_idx = i - 1
            intervals.append({
                "top": round(float(depth[start_idx]), 2),
                "bottom": round(float(depth[end_idx]), 2),
                "thickness": round(float(max(0.0, depth[end_idx] - depth[start_idx])), 2),
            })
            active = False
    if active:
        end_idx = n - 1
        intervals.append({
            "top": round(float(depth[start_idx]), 2),
            "bottom": round(float(depth[end_idx]), 2),
            "thickness": round(float(max(0.0, depth[end_idx] - depth[start_idx])), 2),
        })
    return intervals

@router.delete("/{lr_id}", status_code=204)
def delete_log_run(lr_id: int, db: Session = Depends(get_db)):
    """Delete a log run and all associated data (curves, zones, markers)."""
    lr = db.query(LogRun).filter(LogRun.id == lr_id).first()
    if not lr:
        raise HTTPException(404, "Log run not found")
    db.query(CurveData).filter(CurveData.log_run_id == lr_id).delete()
    db.query(LogRunDepthShift).filter(LogRunDepthShift.log_run_id == lr_id).delete()
    db.delete(lr)
    db.commit()


@router.post("/diff")
def diff_log_runs(req: dict, db: Session = Depends(get_db)):
    """Compare two log runs and return curve, metadata, and stats differences."""
    log_run_a_id = req.get("log_run_a_id")
    log_run_b_id = req.get("log_run_b_id")

    if log_run_a_id is None or log_run_b_id is None:
        raise HTTPException(400, "log_run_a_id and log_run_b_id are required")

    try:
        log_run_a_id = int(log_run_a_id)
        log_run_b_id = int(log_run_b_id)
    except (TypeError, ValueError):
        raise HTTPException(400, "log_run_a_id and log_run_b_id must be integers")

    run_a = db.query(LogRun).filter(LogRun.id == log_run_a_id).first()
    run_b = db.query(LogRun).filter(LogRun.id == log_run_b_id).first()

    if not run_a:
        raise HTTPException(404, f"Log run A not found: {log_run_a_id}")
    if not run_b:
        raise HTTPException(404, f"Log run B not found: {log_run_b_id}")

    curves_a_rows = db.query(CurveData).filter(CurveData.log_run_id == run_a.id).all()
    curves_b_rows = db.query(CurveData).filter(CurveData.log_run_id == run_b.id).all()

    curves_a = {c.mnemonic: c for c in curves_a_rows}
    curves_b = {c.mnemonic: c for c in curves_b_rows}

    mnemonics_a = set(curves_a.keys())
    mnemonics_b = set(curves_b.keys())
    only_in_a = sorted(mnemonics_a - mnemonics_b)
    only_in_b = sorted(mnemonics_b - mnemonics_a)
    shared = sorted(mnemonics_a & mnemonics_b)

    def _curve_stats(curve: CurveData):
        if not curve or not curve.data_binary:
            return {"mean": None, "min": None, "max": None, "std": None, "count": 0}
        arr = np.frombuffer(curve.data_binary, dtype=np.float64)
        valid = arr[~np.isnan(arr)]
        if len(valid) == 0:
            return {"mean": None, "min": None, "max": None, "std": None, "count": 0}
        return {
            "mean": float(np.mean(valid)),
            "min": float(np.min(valid)),
            "max": float(np.max(valid)),
            "std": float(np.std(valid)),
            "count": int(len(valid)),
        }

    shared_curve_statistics = []
    for mnemonic in shared:
        a_curve = curves_a[mnemonic]
        b_curve = curves_b[mnemonic]
        stats_a = _curve_stats(a_curve)
        stats_b = _curve_stats(b_curve)

        shared_curve_statistics.append({
            "mnemonic": mnemonic,
            "unit_a": a_curve.unit,
            "unit_b": b_curve.unit,
            "description_a": a_curve.description,
            "description_b": b_curve.description,
            "num_points_a": int(a_curve.num_points or 0),
            "num_points_b": int(b_curve.num_points or 0),
            "num_points_diff": int((a_curve.num_points or 0) - (b_curve.num_points or 0)),
            "stats_a": stats_a,
            "stats_b": stats_b,
            "stats_diff": {
                "mean": None if stats_a["mean"] is None or stats_b["mean"] is None else float(stats_a["mean"] - stats_b["mean"]),
                "min": None if stats_a["min"] is None or stats_b["min"] is None else float(stats_a["min"] - stats_b["min"]),
                "max": None if stats_a["max"] is None or stats_b["max"] is None else float(stats_a["max"] - stats_b["max"]),
                "std": None if stats_a["std"] is None or stats_b["std"] is None else float(stats_a["std"] - stats_b["std"]),
                "count": int(stats_a["count"] - stats_b["count"]),
            },
        })

    metadata_differences = {
        "run_a": {
            "id": run_a.id,
            "well_id": run_a.well_id,
            "well_name": run_a.well.name if getattr(run_a, "well", None) else None,
            "filename": run_a.filename,
            "start_depth": run_a.start_depth,
            "stop_depth": run_a.stop_depth,
            "step": run_a.step,
            "num_points": run_a.num_points,
        },
        "run_b": {
            "id": run_b.id,
            "well_id": run_b.well_id,
            "well_name": run_b.well.name if getattr(run_b, "well", None) else None,
            "filename": run_b.filename,
            "start_depth": run_b.start_depth,
            "stop_depth": run_b.stop_depth,
            "step": run_b.step,
            "num_points": run_b.num_points,
        },
        "differences": {
            "start_depth": None if run_a.start_depth is None or run_b.start_depth is None else float(run_a.start_depth - run_b.start_depth),
            "stop_depth": None if run_a.stop_depth is None or run_b.stop_depth is None else float(run_a.stop_depth - run_b.stop_depth),
            "step": None if run_a.step is None or run_b.step is None else float(run_a.step - run_b.step),
            "num_points": int((run_a.num_points or 0) - (run_b.num_points or 0)),
            "well_id": int((run_a.well_id or 0) - (run_b.well_id or 0)),
            "same_well": bool(run_a.well_id == run_b.well_id),
        },
    }

    return {
        "log_run_a_id": run_a.id,
        "log_run_b_id": run_b.id,
        "curve_differences": {
            "only_in_a": only_in_a,
            "only_in_b": only_in_b,
            "shared": shared,
            "shared_count": len(shared),
        },
        "metadata_differences": metadata_differences,
        "shared_curve_statistics": shared_curve_statistics,
        "data_point_count_differences": {
            "total_curves_a": len(curves_a_rows),
            "total_curves_b": len(curves_b_rows),
            "total_curve_diff": len(curves_a_rows) - len(curves_b_rows),
            "run_num_points_a": int(run_a.num_points or 0),
            "run_num_points_b": int(run_b.num_points or 0),
            "run_num_points_diff": int((run_a.num_points or 0) - (run_b.num_points or 0)),
            "shared_curve_valid_points": [
                {
                    "mnemonic": row["mnemonic"],
                    "valid_points_a": row["stats_a"]["count"],
                    "valid_points_b": row["stats_b"]["count"],
                    "valid_points_diff": row["stats_diff"]["count"],
                }
                for row in shared_curve_statistics
            ],
        },
    }


@router.get("/{lr_id}/curves")
def list_curves(lr_id: int, db: Session = Depends(get_db)):
    """List available curves for a log run."""
    lr = db.query(LogRun).filter(LogRun.id == lr_id).first()
    if not lr:
        raise HTTPException(404, "Log run not found")
    curves = db.query(CurveData).filter(CurveData.log_run_id == lr_id).all()
    return [
        {
            "id": c.id, "mnemonic": c.mnemonic, "unit": c.unit,
            "description": c.description, "num_points": c.num_points,
            "min_value": c.min_value, "max_value": c.max_value,
            "track_config": CURVE_TRACKS.get(c.mnemonic, {}),
        }
        for c in curves
    ]


@router.get("/{lr_id}/depth-control-points")
def list_depth_control_points(lr_id: int, db: Session = Depends(get_db)):
    lr = db.query(LogRun).filter(LogRun.id == lr_id).first()
    if not lr:
        raise HTTPException(404, "Log run not found")
    rows = (
        db.query(DepthControlPoint)
        .filter(DepthControlPoint.log_run_id == lr_id)
        .order_by(DepthControlPoint.sort_order.asc(), DepthControlPoint.md.asc())
        .all()
    )
    return [
        {"md": r.md, "corrected_depth": r.corrected_depth, "sort_order": r.sort_order}
        for r in rows
    ]

@router.put("/{lr_id}/depth-control-points")
def replace_depth_control_points(lr_id: int, data: dict, db: Session = Depends(get_db)):
    lr = db.query(LogRun).filter(LogRun.id == lr_id).first()
    if not lr:
        raise HTTPException(404, "Log run not found")
    points = data.get("points")
    if not isinstance(points, list) or len(points) < 2:
        raise HTTPException(400, "points must contain at least two (md, corrected_depth) objects")
    prepared = []
    for i, point in enumerate(points):
        if not isinstance(point, dict):
            raise HTTPException(400, f"points[{i}] must be an object")
        try:
            md = float(point.get("md"))
            corrected = float(point.get("corrected_depth"))
        except (TypeError, ValueError):
            raise HTTPException(400, f"points[{i}] requires numeric md and corrected_depth")
        if not (np.isfinite(md) and np.isfinite(corrected)):
            raise HTTPException(400, f"points[{i}] must be finite")
        prepared.append((md, corrected))
    prepared.sort(key=lambda p: p[0])
    if any(prepared[i][0] >= prepared[i + 1][0] for i in range(len(prepared) - 1)):
        raise HTTPException(400, "control-point MD values must be strictly increasing")

    db.query(DepthControlPoint).filter(DepthControlPoint.log_run_id == lr_id).delete()
    for order, (md, corrected) in enumerate(prepared):
        db.add(DepthControlPoint(
            log_run_id=lr_id, md=md, corrected_depth=corrected, sort_order=order,
        ))
    db.commit()
    return {"status": "ok", "count": len(prepared)}

@router.delete("/{lr_id}/depth-control-points", status_code=204)
def clear_depth_control_points(lr_id: int, db: Session = Depends(get_db)):
    lr = db.query(LogRun).filter(LogRun.id == lr_id).first()
    if not lr:
        raise HTTPException(404, "Log run not found")
    db.query(DepthControlPoint).filter(DepthControlPoint.log_run_id == lr_id).delete()
    db.commit()

@router.post("/{lr_id}/data")
def get_curve_data(
    lr_id: int,
    req: dict,
    if_none_match: str = Header(default=None),
    if_modified_since: str = Header(default=None),
    db: Session = Depends(get_db),
):
    """Get curve data for specified mnemonics with corrected depth and TVD."""
    mnemonics = req.get("curve_mnemonics", [])
    start = req.get("start_depth")
    stop = req.get("stop_depth")
    try:
        step = int(req.get("step", 1) or 1)
    except (TypeError, ValueError):
        raise HTTPException(400, "step must be an integer")

    if not mnemonics:
        raise HTTPException(400, "No curves requested")

    lr = db.query(LogRun).filter(LogRun.id == lr_id).first()
    if not lr:
        raise HTTPException(404, "Log run not found")

    try:
        result = apply_run_semantics(db, lr, mnemonics, start, stop, step)
    except (TypeError, ValueError) as exc:
        raise HTTPException(400, f"invalid depth range: {exc}")

    headers = _build_curve_cache_headers(
        lr_id, mnemonics, start, stop, step,
        extra=result["metadata"]["input_hash"],
    )
    last_modified_dt = (lr.uploaded_at or utcnow()).replace(tzinfo=datetime.timezone.utc)
    headers["Last-Modified"] = _httpdate(last_modified_dt)

    if if_none_match and if_none_match.strip() == headers["ETag"]:
        return SafeJSONResponse(status_code=304, content=None, headers=headers)
    ims = _parse_if_modified_since(if_modified_since)
    if ims is not None and last_modified_dt <= ims:
        return SafeJSONResponse(status_code=304, content=None, headers=headers)

    content = dict(result["curves"])
    content["semantics"] = result["metadata"]
    return SafeJSONResponse(content=content, headers=headers)

@router.post("/{lr_id}/shoulder-bed-correction")
def shoulder_bed_correction(lr_id: int, data: dict, db: Session = Depends(get_db)):
    lr = db.query(LogRun).filter(LogRun.id == lr_id).first()
    if not lr:
        raise HTTPException(404, "Log run not found")

    mnemonic = str(data.get("mnemonic", "")).strip().upper()
    if not mnemonic:
        raise HTTPException(400, "mnemonic is required")

    method = str(data.get("method", "linear")).strip().lower()
    if method not in {"linear", "simandoux"}:
        raise HTTPException(400, "method must be 'linear' or 'simandoux'")

    bed_thickness_threshold = float(data.get("bed_thickness_threshold", 2.0) or 2.0)
    if bed_thickness_threshold <= 0:
        raise HTTPException(400, "bed_thickness_threshold must be > 0")

    curve_cd = db.query(CurveData).filter(CurveData.log_run_id == lr_id, CurveData.mnemonic == mnemonic).first()
    if not curve_cd:
        raise HTTPException(404, f"Curve {mnemonic} not found")

    depth_cd = db.query(CurveData).filter(CurveData.log_run_id == lr_id, CurveData.mnemonic.in_(["DEPT", "DEPTH", "MD", "TVD"])).first()
    if not depth_cd:
        raise HTTPException(404, "Depth curve not found")

    z_meas = np.frombuffer(curve_cd.data_binary, dtype=np.float64).copy()
    depth = np.frombuffer(depth_cd.data_binary, dtype=np.float64).copy()
    n = min(len(depth), len(z_meas))
    depth = depth[:n]
    z_meas = z_meas[:n]
    if int(np.sum(~np.isnan(z_meas))) < 5:
        raise HTTPException(400, "Not enough valid data points")

    rt_cd = db.query(CurveData).filter(CurveData.log_run_id == lr_id, CurveData.mnemonic.in_(["RT", "RESD", "RILD", "ILD"])) .first()
    rxo_cd = db.query(CurveData).filter(CurveData.log_run_id == lr_id, CurveData.mnemonic.in_(["RXO", "RILM", "RLLS", "MSFL"])) .first()
    gr_cd = db.query(CurveData).filter(CurveData.log_run_id == lr_id, CurveData.mnemonic.in_(["GR", "SGR", "CGR"])) .first()
    cali_cd = db.query(CurveData).filter(CurveData.log_run_id == lr_id, CurveData.mnemonic.in_(["CALI", "CAL", "HCAL"])) .first()
    bs_cd = db.query(CurveData).filter(CurveData.log_run_id == lr_id, CurveData.mnemonic.in_(["BS", "BIT", "BITSIZE"])) .first()

    rt = np.frombuffer(rt_cd.data_binary, dtype=np.float64).copy()[:n] if rt_cd else None
    rxo = np.frombuffer(rxo_cd.data_binary, dtype=np.float64).copy()[:n] if rxo_cd else None
    gr = np.frombuffer(gr_cd.data_binary, dtype=np.float64).copy()[:n] if gr_cd else None
    cali = np.frombuffer(cali_cd.data_binary, dtype=np.float64).copy()[:n] if cali_cd else None
    bs = np.frombuffer(bs_cd.data_binary, dtype=np.float64).copy()[:n] if bs_cd else None

    dv = np.abs(np.diff(z_meas))
    dv = dv[~np.isnan(dv)]
    if len(dv) == 0:
        raise HTTPException(400, "Cannot detect bed boundaries")
    mad = np.median(np.abs(dv - np.median(dv)))
    change_threshold = max(np.percentile(dv, 75), np.median(dv) + 3.0 * mad, 1e-9)

    boundaries = [0]
    for i in range(1, n):
        p = z_meas[i - 1]
        c = z_meas[i]
        if np.isnan(p) or np.isnan(c):
            continue
        if abs(c - p) > change_threshold:
            boundaries.append(i)
    if boundaries[-1] != n - 1:
        boundaries.append(n - 1)

    z_corr = z_meas.copy()
    thin_bed_flags = np.zeros(n, dtype=bool)
    thin_beds = []

    for b in range(len(boundaries) - 1):
        i0 = boundaries[b]
        i1 = boundaries[b + 1]
        if i1 <= i0:
            continue
        top_d = float(depth[i0])
        bot_d = float(depth[i1])
        thickness = max(0.0, bot_d - top_d)
        if thickness >= bed_thickness_threshold:
            continue

        seg = z_meas[i0:i1 + 1]
        if len(seg) == 0 or np.all(np.isnan(seg)):
            continue
        thin_bed_flags[i0:i1 + 1] = True

        up_shoulder = np.nan
        down_shoulder = np.nan
        if b > 0:
            up_shoulder = np.nanmean(z_meas[boundaries[b - 1]:i0])
        if b + 2 < len(boundaries):
            down_shoulder = np.nanmean(z_meas[i1 + 1:boundaries[b + 2] + 1])
        shoulders = [v for v in (up_shoulder, down_shoulder) if np.isfinite(v)]
        z_shoulder = float(np.mean(shoulders)) if shoulders else float(np.nanmean(seg))

        for i in range(i0, i1 + 1):
            if np.isnan(z_meas[i]):
                continue
            thickness_scale = max(0.25, min(2.0, bed_thickness_threshold / max(thickness, 0.25)))
            invasion_mod = 1.0
            if rt is not None and rxo is not None and np.isfinite(rt[i]) and np.isfinite(rxo[i]) and rt[i] > 0 and rxo[i] > 0:
                ratio = rt[i] / rxo[i]
                invasion_mod = 1.0 + 0.35 * min(2.0, abs(np.log10(max(ratio, 1e-6))))
            correction_factor = float(max(0.15, min(1.5, 0.5 * thickness_scale * invasion_mod)))

            if method == "simandoux":
                vsh = 0.2
                if gr is not None:
                    gv = gr[~np.isnan(gr)]
                    if len(gv) > 5 and np.isfinite(gr[i]):
                        gmin = float(np.percentile(gv, 5))
                        gmax = float(np.percentile(gv, 95))
                        if gmax > gmin:
                            vsh = max(0.0, min(1.0, (gr[i] - gmin) / (gmax - gmin)))
                correction_factor *= (1.0 - 0.45 * vsh)

            z_corr[i] = z_meas[i] + (z_meas[i] - z_shoulder) * correction_factor

        thin_beds.append({
            "top": round(top_d, 2),
            "bottom": round(bot_d, 2),
            "thickness": round(thickness, 2),
            "indices": [int(i0), int(i1)],
        })

    bad_hole_flags = np.zeros(n, dtype=bool)
    washout_flags = np.zeros(n, dtype=bool)
    tight_flags = np.zeros(n, dtype=bool)
    bit_size = float(np.nanmedian(bs)) if bs is not None and np.sum(~np.isnan(bs)) > 0 else 8.5
    if cali is not None:
        washout_flags = np.nan_to_num(cali > (bit_size + 1.0), nan=False)
        tight_flags = np.nan_to_num(cali < (bit_size - 0.5), nan=False)
        bad_hole_flags = washout_flags | tight_flags
    bad_hole_intervals = _group_flagged_intervals(depth, bad_hole_flags)

    invaded_flags = np.zeros(n, dtype=bool)
    invasion_indicator = [None] * n
    if rt is not None and rxo is not None:
        for i in range(n):
            if not (np.isfinite(rt[i]) and np.isfinite(rxo[i])) or rt[i] <= 0 or rxo[i] <= 0:
                continue
            ratio = rt[i] / rxo[i]
            if ratio >= 1.5:
                invaded_flags[i] = True
                invasion_indicator[i] = "deep_invasion_or_oil_mud"
            elif ratio <= 0.67:
                invaded_flags[i] = True
                invasion_indicator[i] = "shallow_invasion_or_supercharged"
            else:
                invasion_indicator[i] = "normal"

    total = max(1, n)
    qc_summary = {
        "thin_beds_pct": round(float(np.sum(thin_bed_flags)) * 100.0 / total, 2),
        "bad_hole_pct": round(float(np.sum(bad_hole_flags)) * 100.0 / total, 2),
        "invaded_pct": round(float(np.sum(invaded_flags)) * 100.0 / total, 2),
        "thin_bed_count": len(thin_beds),
        "bad_hole_interval_count": len(bad_hole_intervals),
    }

    return {
        "log_run_id": lr_id,
        "mnemonic": mnemonic,
        "method": method,
        "bed_thickness_threshold": bed_thickness_threshold,
        "corrected_curve": [None if np.isnan(v) else round(float(v), 4) for v in z_corr],
        "thin_beds": thin_beds,
        "thin_bed_flags": thin_bed_flags.astype(bool).tolist(),
        "bad_hole": {
            "bit_size": round(bit_size, 3),
            "washout_flags": washout_flags.astype(bool).tolist(),
            "tight_hole_flags": tight_flags.astype(bool).tolist(),
            "bad_hole_flags": bad_hole_flags.astype(bool).tolist(),
            "intervals": bad_hole_intervals,
        },
        "invasion": {
            "flags": invaded_flags.astype(bool).tolist(),
            "indicator": invasion_indicator,
        },
        "qc_summary": qc_summary,
    }


@router.get("/{lr_id}/depth-shift")
def get_depth_shift(lr_id: int, db: Session = Depends(get_db)):
    ds = db.query(LogRunDepthShift).filter(LogRunDepthShift.log_run_id == lr_id).first()
    if not ds:
        return {"log_run_id": lr_id, "shift": 0.0, "stretch": 1.0, "notes": ""}
    return {"log_run_id": lr_id, "shift": ds.shift, "stretch": ds.stretch, "notes": ds.notes or ""}


@router.post("/{lr_id}/depth-shift")
def save_depth_shift(lr_id: int, data: dict, db: Session = Depends(get_db)):
    shift = optional_float(data, "shift", 0.0)
    stretch = optional_float(data, "stretch", 1.0)
    notes = optional_str(data, "notes")
    if stretch == 0:
        raise HTTPException(400, "stretch must not be zero")
    existing = db.query(LogRunDepthShift).filter(LogRunDepthShift.log_run_id == lr_id).first()
    if existing:
        existing.shift = shift
        existing.stretch = stretch
        existing.notes = notes
    else:
        db.add(LogRunDepthShift(
            log_run_id=lr_id,
            shift=shift,
            stretch=stretch,
            notes=notes,
        ))
    db.commit()
    return {"status": "ok"}


@router.post("/{lr_id}/filter")
def filter_curve(lr_id: int, data: dict, db: Session = Depends(get_db)):
    """Apply despiking (median filter) or smoothing (moving average) to a curve."""
    mnemonic = data.get("mnemonic", "GR")
    filter_type = data.get("filter", "despike")  # despike or smooth
    window = int(data.get("window", 5))
    if window % 2 == 0:
        window += 1
    window = max(3, min(window, 51))

    cd = db.query(CurveData).filter(CurveData.log_run_id == lr_id, CurveData.mnemonic == mnemonic).first()
    if not cd:
        raise HTTPException(404, f"Curve {mnemonic} not found")

    arr = np.frombuffer(cd.data_binary, dtype=np.float64).copy()
    result = arr.copy()

    valid_idx = ~np.isnan(arr)
    vals = arr[valid_idx]

    half = window // 2
    if len(vals) == 0:
        filtered = vals
    elif filter_type == "despike":
        padded = np.pad(vals, (half, half), mode="edge")
        windows = np.lib.stride_tricks.sliding_window_view(padded, window)
        med = np.median(windows, axis=1)
        spread = np.std(windows, axis=1)
        replace = np.abs(vals - med) > 2 * spread
        if half > 0:
            replace[:half] = False
            replace[len(vals) - half:] = False
        filtered = vals.copy()
        filtered[replace] = med[replace]
    else:
        padded = np.pad(vals, (half, half), mode="edge")
        filtered = np.convolve(padded, np.ones(window) / window, mode="valid")
    result[valid_idx] = filtered

    # Create new curve with suffix
    new_mnemonic = f"{mnemonic}_{'D' if filter_type == 'despike' else 'S'}{window}"
    valid = result[~np.isnan(result)]

    # Check if filtered curve already exists
    existing = db.query(CurveData).filter(CurveData.log_run_id == lr_id, CurveData.mnemonic == new_mnemonic).first()
    if existing:
        existing.data_binary = result.tobytes()
        existing.num_points = len(result)
        existing.min_value = float(np.min(valid)) if len(valid) else None
        existing.max_value = float(np.max(valid)) if len(valid) else None
    else:
        db.add(CurveData(
            log_run_id=lr_id, mnemonic=new_mnemonic, unit=cd.unit,
            description=f"{filter_type} filtered {mnemonic} (w={window})",
            num_points=len(result),
            min_value=float(np.min(valid)) if len(valid) else None,
            max_value=float(np.max(valid)) if len(valid) else None,
            data_binary=result.tobytes(),
        ))
    db.commit()
    return {"status": "ok", "new_curve": new_mnemonic, "filter": filter_type, "window": window}


@router.post("/{lr_id}/curve-override")
def curve_override(lr_id: int, data: dict, db: Session = Depends(get_db)):
    """Override curve values in a depth range."""
    mnemonic = data.get("mnemonic", "GR")
    start_raw = data.get("start")
    end_raw = data.get("end")
    value_raw = data.get("value")
    if start_raw is None or end_raw is None or value_raw is None:
        raise HTTPException(400, "start, end, and value are required")
    start = float(start_raw)
    end = float(end_raw)
    value = float(value_raw)

    cd = db.query(CurveData).filter(CurveData.log_run_id == lr_id, CurveData.mnemonic == mnemonic).first()
    if not cd:
        raise HTTPException(404, f"Curve {mnemonic} not found")

    dept_cd = db.query(CurveData).filter(CurveData.log_run_id == lr_id, CurveData.mnemonic.in_(["DEPT", "DEPTH"])).first()
    if not dept_cd:
        raise HTTPException(404, "Depth not found")

    arr = np.frombuffer(cd.data_binary, dtype=np.float64).copy()
    dept = np.frombuffer(dept_cd.data_binary, dtype=np.float64)

    count = 0
    for i in range(len(arr)):
        if dept[i] >= start and dept[i] <= end:
            arr[i] = value
            count += 1

    valid = arr[~np.isnan(arr)]
    cd.data_binary = arr.tobytes()
    cd.min_value = float(np.min(valid)) if len(valid) else None
    cd.max_value = float(np.max(valid)) if len(valid) else None
    db.commit()
    return {"status": "ok", "points_overridden": count}


@router.post("/{lr_id}/curve-edit")
def curve_edit(lr_id: int, data: dict, db: Session = Depends(get_db)):
    """Apply manual point edits to a curve and track original values for undo."""
    mnemonic = str(data.get("mnemonic", "")).strip().upper()
    edits = data.get("edits") or []
    if not mnemonic:
        raise HTTPException(400, "mnemonic is required")
    if not isinstance(edits, list) or not edits:
        raise HTTPException(400, "edits[] is required")

    cd = db.query(CurveData).filter(CurveData.log_run_id == lr_id, CurveData.mnemonic == mnemonic).first()
    if not cd:
        raise HTTPException(404, f"Curve {mnemonic} not found")

    dept_cd = db.query(CurveData).filter(CurveData.log_run_id == lr_id, CurveData.mnemonic.in_(["DEPT", "DEPTH"])) .first()
    if not dept_cd:
        raise HTTPException(404, "Depth curve not found")

    arr = np.frombuffer(cd.data_binary, dtype=np.float64).copy()
    dept = np.frombuffer(dept_cd.data_binary, dtype=np.float64)
    if len(arr) != len(dept):
        n = min(len(arr), len(dept))
        arr = arr[:n]
        dept = dept[:n]

    key = f"{lr_id}:{mnemonic}"
    originals = CURVE_EDIT_ORIGINALS.setdefault(key, {})

    applied = []
    changed = 0
    nulled = 0
    for e in edits:
        if not isinstance(e, dict):
            continue
        depth_raw = e.get("depth")
        if depth_raw is None:
            continue
        try:
            depth = float(depth_raw)
        except Exception:
            continue

        idx = int(np.argmin(np.abs(dept - depth)))
        old_val = arr[idx]
        if idx not in originals:
            originals[idx] = None if np.isnan(old_val) else float(old_val)

        nv_raw = e.get("new_value")
        try:
            new_val = np.nan if nv_raw is None else float(nv_raw)
        except (ValueError, TypeError):
            raise HTTPException(400, f"Invalid new_value: {nv_raw}")
        arr[idx] = new_val
        changed += 1
        if np.isnan(new_val):
            nulled += 1

        applied.append({
            "index": idx,
            "depth": float(dept[idx]),
            "old_value": None if np.isnan(old_val) else float(old_val),
            "new_value": None if np.isnan(new_val) else float(new_val),
        })

    valid = arr[~np.isnan(arr)]
    cd.data_binary = arr.tobytes()
    cd.num_points = int(len(arr))
    cd.min_value = float(np.min(valid)) if len(valid) else None
    cd.max_value = float(np.max(valid)) if len(valid) else None
    db.commit()

    return {
        "status": "ok",
        "mnemonic": mnemonic,
        "applied_count": len(applied),
        "changed_count": changed,
        "nulled_count": nulled,
        "original_store_count": len(originals),
        "curve_stats": {
            "num_points": int(len(arr)),
            "valid_points": int(len(valid)),
            "null_points": int(len(arr) - len(valid)),
            "min": float(np.min(valid)) if len(valid) else None,
            "max": float(np.max(valid)) if len(valid) else None,
        },
        "applied_edits": applied,
    }


@router.get("/{lr_id}/data-decimated")
def get_decimated_data(
    lr_id: int,
    max_points: int = 3000,
    start_depth: float = None,
    stop_depth: float = None,
    if_none_match: str = Header(default=None),
    if_modified_since: str = Header(default=None),
    db: Session = Depends(get_db),
):
    """Return corrected curve data decimated to <= max_points using LTTB."""
    lr = db.query(LogRun).filter(LogRun.id == lr_id).first()
    if not lr:
        raise HTTPException(404, "Log run not found")

    max_points = max(200, min(int(max_points or 3000), 50000))
    try:
        result = apply_run_semantics(db, lr, None, start_depth, stop_depth, 1)
    except (TypeError, ValueError) as exc:
        raise HTTPException(400, f"invalid depth range: {exc}")

    headers = _build_curve_cache_headers(
        lr_id, [c["name"] for c in result["metadata"]["aliases"]],
        start_depth, stop_depth, 1, max_points=max_points,
        extra=result["metadata"]["input_hash"],
    )
    last_modified_dt = (lr.uploaded_at or utcnow()).replace(tzinfo=datetime.timezone.utc)
    headers["Last-Modified"] = _httpdate(last_modified_dt)

    if if_none_match and if_none_match.strip() == headers["ETag"]:
        return SafeJSONResponse(status_code=304, content=None, headers=headers)
    ims = _parse_if_modified_since(if_modified_since)
    if ims is not None and last_modified_dt <= ims:
        return SafeJSONResponse(status_code=304, content=None, headers=headers)

    depth = np.asarray(result["depth"], dtype=np.float64)
    tvd = np.asarray(result["tvd"], dtype=np.float64)
    series = {
        name: np.asarray(values, dtype=np.float64)
        for name, values in result["curves"].items()
        if name not in {"DEPTH", "TVD"}
    }
    n = int(len(depth))
    decimated = False
    if n > max_points:
        reference = next((arr for arr in series.values() if len(arr) >= n), None)
        if reference is not None:
            indices = _lttb_indices(depth, reference[:n], max_points)
        else:
            step = int(np.ceil(n / float(max_points)))
            indices = np.arange(0, n, step, dtype=np.int64)[:max_points]
        decimated = True
    else:
        indices = np.arange(n, dtype=np.int64)

    curves = {}
    for name, arr in series.items():
        curves[name] = [
            None if int(i) >= len(arr) or np.isnan(arr[int(i)]) else round(float(arr[int(i)]), 6)
            for i in indices
        ]
    output_points = int(len(indices))
    return SafeJSONResponse(content={
        "curves": curves,
        "depth": [round(float(depth[i]), 4) for i in indices],
        "tvd": [round(float(tvd[i]), 4) for i in indices],
        "decimated": decimated,
        "original_points": n,
        "output_points": output_points,
        "max_points": max_points,
        "semantics": result["metadata"],
    }, headers=headers)
