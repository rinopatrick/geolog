from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

import numpy as np
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

try:
    from database import get_db
    from models import Well, LogRun, CurveData
except ImportError:
    from backend.database import get_db
    from backend.models import Well, LogRun, CurveData


router = APIRouter(prefix="/api/wells/{wid}", tags=["qc"])

EXPECTED_RANGES: Dict[str, Tuple[float, float]] = {
    "GR": (0.0, 200.0),
    "RT": (0.1, 10000.0),
    "RHOB": (1.5, 3.0),
    "NPHI": (-0.15, 0.60),
    "DT": (40.0, 200.0),
    "CALI": (4.0, 20.0),
}

RESISTIVITY_DEEP = ["RT", "RILD", "ILD", "LLD"]
RESISTIVITY_SHALLOW = ["RILM", "ILM", "MSFL", "RXO", "LLS"]
CALI_ALIASES = ["CALI", "CALI1", "CALI2", "CAL", "HCAL"]


def _sanitize(obj: Any) -> Any:
    if isinstance(obj, dict):
        return {k: _sanitize(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_sanitize(v) for v in obj]
    if isinstance(obj, np.ndarray):
        return _sanitize(obj.tolist())
    if isinstance(obj, (np.integer,)):
        return int(obj)
    if isinstance(obj, (np.floating, float)):
        v = float(obj)
        if np.isnan(v) or np.isinf(v):
            return None
        return v
    return obj


def _get_latest_log_run(db: Session, wid: int) -> LogRun:
    well = db.query(Well).filter(Well.id == wid).first()
    if not well:
        raise HTTPException(status_code=404, detail="Well not found")

    lr = (
        db.query(LogRun)
        .filter(LogRun.well_id == wid)
        .order_by(LogRun.uploaded_at.desc(), LogRun.id.desc())
        .first()
    )
    if not lr:
        raise HTTPException(status_code=404, detail="No log run found for well")
    return lr


def _curve_array(cd: CurveData, n: int) -> np.ndarray:
    if not cd or not cd.data_binary:
        return np.full(n, np.nan, dtype=np.float32)
    arr = np.frombuffer(cd.data_binary, dtype=np.float32)
    if arr.size < n:
        padded = np.full(n, np.nan, dtype=np.float32)
        padded[: arr.size] = arr
        return padded
    if arr.size > n:
        return arr[:n]
    return arr


def _missing_intervals(mask: np.ndarray, depth: np.ndarray, step: float, mnemonic: str) -> List[Dict[str, Any]]:
    intervals: List[Dict[str, Any]] = []
    start = -1
    for i, miss in enumerate(mask.tolist()):
        if miss and start < 0:
            start = i
        elif (not miss) and start >= 0:
            end = i - 1
            count = end - start + 1
            intervals.append(
                {
                    "curve": mnemonic,
                    "start_index": start,
                    "end_index": end,
                    "start_depth": float(depth[start]),
                    "end_depth": float(depth[end]),
                    "num_points": count,
                    "gap_length": float(count * abs(step)),
                }
            )
            start = -1
    if start >= 0:
        end = len(mask) - 1
        count = end - start + 1
        intervals.append(
            {
                "curve": mnemonic,
                "start_index": start,
                "end_index": end,
                "start_depth": float(depth[start]),
                "end_depth": float(depth[end]),
                "num_points": count,
                "gap_length": float(count * abs(step)),
            }
        )
    return intervals


def detect_spikes_iqr(arr: np.ndarray) -> Tuple[np.ndarray, Optional[float], Optional[float]]:
    if arr.size == 0:
        return np.zeros(0, dtype=bool), None, None
    valid = arr[~np.isnan(arr)]
    if valid.size == 0:
        return np.zeros(arr.shape, dtype=bool), None, None
    q1, q3 = np.percentile(valid, [25, 75])
    iqr = q3 - q1
    if iqr == 0:
        mask = np.zeros(arr.shape, dtype=bool)
        return mask, float(q1), float(q3)
    lower = q1 - 1.5 * iqr
    upper = q3 + 1.5 * iqr
    mask = (arr < lower) | (arr > upper)
    mask[np.isnan(arr)] = False
    return mask, float(lower), float(upper)


def _mask_to_intervals(mask: np.ndarray, depth: np.ndarray, step: float, min_points: int = 1) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    s = -1
    for i, flag in enumerate(mask.tolist()):
        if flag and s < 0:
            s = i
        elif (not flag) and s >= 0:
            e = i - 1
            n = e - s + 1
            if n >= min_points:
                out.append(
                    {
                        "start_index": s,
                        "end_index": e,
                        "start_depth": float(depth[s]),
                        "end_depth": float(depth[e]),
                        "num_points": n,
                        "length": float(n * abs(step)),
                    }
                )
            s = -1
    if s >= 0:
        e = len(mask) - 1
        n = e - s + 1
        if n >= min_points:
            out.append(
                {
                    "start_index": s,
                    "end_index": e,
                    "start_depth": float(depth[s]),
                    "end_depth": float(depth[e]),
                    "num_points": n,
                    "length": float(n * abs(step)),
                }
            )
    return out


def _high_density_outlier_intervals(mask: np.ndarray, depth: np.ndarray, step: float, window: int = 25, threshold: float = 0.25) -> List[Dict[str, Any]]:
    if mask.size == 0:
        return []
    dens = np.zeros(mask.size, dtype=bool)
    half = max(1, window // 2)
    for i in range(mask.size):
        a = max(0, i - half)
        b = min(mask.size, i + half + 1)
        d = np.mean(mask[a:b]) if b > a else 0
        dens[i] = d >= threshold
    return _mask_to_intervals(dens, depth, step, min_points=max(3, window // 3))


def _find_first_curve(curves: Dict[str, np.ndarray], names: List[str]) -> Optional[str]:
    for name in names:
        if name in curves:
            return name
    return None


def _environment_flags(curves: Dict[str, np.ndarray], depth: np.ndarray, step: float) -> Dict[str, Any]:
    flags = {"washout": None, "mud_invasion": None, "tool_standoff": None}

    cal_name = _find_first_curve(curves, CALI_ALIASES)
    if cal_name:
        cal = curves[cal_name]
        valid = cal[~np.isnan(cal)]
        if valid.size:
            bit_size = 8.5
            washout_mask = (cal > bit_size) & ~np.isnan(cal)
            frac = float(np.mean(washout_mask[~np.isnan(cal)])) if np.any(~np.isnan(cal)) else 0.0
            intervals = _mask_to_intervals(washout_mask, depth, step, min_points=3)
            flags["washout"] = {
                "curve": cal_name,
                "bit_size": bit_size,
                "mean_cali": float(np.nanmean(cal)),
                "fraction_over_bit": frac,
                "severity": "high" if frac > 0.5 else ("medium" if frac > 0.25 else "low"),
                "intervals": intervals,
            }
            standoff_mask = (cal > (bit_size + 1.5)) & ~np.isnan(cal)
            sfrac = float(np.mean(standoff_mask[~np.isnan(cal)])) if np.any(~np.isnan(cal)) else 0.0
            flags["tool_standoff"] = {
                "curve": cal_name,
                "criterion": "CALI > bit_size + 1.5in",
                "fraction": sfrac,
                "severity": "high" if sfrac > 0.35 else ("medium" if sfrac > 0.15 else "low"),
                "intervals": _mask_to_intervals(standoff_mask, depth, step, min_points=3),
            }

    d_name = _find_first_curve(curves, RESISTIVITY_DEEP)
    s_name = _find_first_curve(curves, RESISTIVITY_SHALLOW)
    if d_name and s_name:
        deep = curves[d_name]
        shallow = curves[s_name]
        n = min(len(deep), len(shallow))
        d = deep[:n]
        s = shallow[:n]
        valid = (~np.isnan(d)) & (~np.isnan(s)) & (d > 0) & (s > 0)
        sep_mask = np.zeros(n, dtype=bool)
        ratio = np.full(n, np.nan, dtype=np.float32)
        ratio[valid] = d[valid] / s[valid]
        sep_mask[valid] = (ratio[valid] > 1.5) | (ratio[valid] < 0.67)
        vcount = int(np.sum(valid))
        sep_frac = float(np.sum(sep_mask) / vcount) if vcount else 0.0
        flags["mud_invasion"] = {
            "deep_curve": d_name,
            "shallow_curve": s_name,
            "valid_points": vcount,
            "separation_fraction": sep_frac,
            "severity": "high" if sep_frac > 0.5 else ("medium" if sep_frac > 0.25 else "low"),
            "intervals": _mask_to_intervals(sep_mask, depth[:n], step, min_points=3),
            "ratio_preview": ratio.tolist(),
        }

    return flags


def _curve_quality(mnemonic: str, arr: np.ndarray, outlier_mask: np.ndarray) -> Dict[str, Any]:
    total = int(arr.size)
    valid_mask = ~np.isnan(arr)
    valid_count = int(np.sum(valid_mask))
    completeness_score = (valid_count / total) * 40.0 if total else 0.0

    outlier_count = int(np.sum(outlier_mask & valid_mask)) if total else 0
    outlier_pct = (outlier_count / valid_count) * 100.0 if valid_count else 0.0
    outlier_score = max(0.0, 30.0 - outlier_pct * 10.0)

    range_score = 30.0
    expected = EXPECTED_RANGES.get(mnemonic.upper())
    out_of_range_pct = 0.0
    if expected and valid_count:
        lo, hi = expected
        vals = arr[valid_mask]
        oor = np.sum((vals < lo) | (vals > hi))
        out_of_range_pct = float(oor / valid_count)
        range_score = max(0.0, 30.0 - out_of_range_pct * 30.0)

    score = completeness_score + outlier_score + range_score
    score = max(0.0, min(100.0, score))

    return {
        "completeness_score": float(completeness_score),
        "outlier_score": float(outlier_score),
        "range_score": float(range_score),
        "outlier_pct": float(outlier_pct),
        "out_of_range_fraction": float(out_of_range_pct),
        "score": float(score),
    }


def _run_advanced_qc(wid: int, db: Session) -> Dict[str, Any]:
    lr = _get_latest_log_run(db, wid)
    if not lr.num_points or lr.num_points <= 0:
        raise HTTPException(status_code=400, detail="Log run has no data points")

    depth = np.linspace(float(lr.start_depth), float(lr.stop_depth), int(lr.num_points), dtype=np.float32)
    step = float(lr.step) if lr.step not in (None, 0) else float((lr.stop_depth - lr.start_depth) / max(1, lr.num_points - 1))

    cds = db.query(CurveData).filter(CurveData.log_run_id == lr.id).all()
    curves: Dict[str, np.ndarray] = {}
    for cd in cds:
        curves[cd.mnemonic] = _curve_array(cd, int(lr.num_points))

    curve_results: Dict[str, Any] = {}
    missing_all: List[Dict[str, Any]] = []
    spikes_all: Dict[str, Any] = {}

    for mn, arr in curves.items():
        miss_mask = np.isnan(arr)
        miss_intervals = _missing_intervals(miss_mask, depth, step, mn)
        missing_all.extend(miss_intervals)

        spike_mask, lower, upper = detect_spikes_iqr(arr)
        spike_idx = np.where(spike_mask)[0]
        spike_points = [
            {
                "index": int(i),
                "depth": float(depth[i]),
                "value": float(arr[i]) if not np.isnan(arr[i]) else None,
            }
            for i in spike_idx.tolist()
        ]
        dense_intervals = _high_density_outlier_intervals(spike_mask, depth, step)
        spike_intervals = _mask_to_intervals(spike_mask, depth, step, min_points=2)

        quality = _curve_quality(mn, arr, spike_mask)
        valid = arr[~np.isnan(arr)]
        curve_results[mn] = {
            "mnemonic": mn,
            "total_points": int(arr.size),
            "valid_points": int(valid.size),
            "missing_points": int(np.sum(miss_mask)),
            "missing_fraction": float(np.mean(miss_mask)) if arr.size else 0.0,
            "min": float(np.min(valid)) if valid.size else None,
            "max": float(np.max(valid)) if valid.size else None,
            "mean": float(np.mean(valid)) if valid.size else None,
            "spike_count": int(np.sum(spike_mask)),
            "spike_bounds": {"lower": lower, "upper": upper},
            "missing_intervals": miss_intervals,
            "spike_intervals": spike_intervals,
            "high_density_spike_intervals": dense_intervals,
            "quality": quality,
        }

        spikes_all[mn] = {
            "mnemonic": mn,
            "spike_count": int(np.sum(spike_mask)),
            "bounds": {"lower": lower, "upper": upper},
            "points": spike_points,
            "intervals": spike_intervals,
            "high_density_intervals": dense_intervals,
            "spike_mask": spike_mask.astype(int).tolist(),
        }

    env_flags = _environment_flags(curves, depth, step)

    curve_scores = [v["quality"]["score"] for v in curve_results.values()]
    overall_score = float(np.mean(curve_scores)) if curve_scores else 0.0
    if overall_score >= 85:
        rating = "EXCELLENT"
    elif overall_score >= 70:
        rating = "GOOD"
    elif overall_score >= 50:
        rating = "FAIR"
    else:
        rating = "POOR"

    result = {
        "well_id": wid,
        "log_run_id": lr.id,
        "depth": depth.tolist(),
        "step": step,
        "curve_stats": curve_results,
        "missing_intervals": sorted(missing_all, key=lambda x: (x["curve"], x["start_index"])),
        "spikes": spikes_all,
        "env_flags": env_flags,
        "summary": {
            "overall_score": max(0.0, min(100.0, overall_score)),
            "overall_rating": rating,
            "curve_count": len(curve_results),
            "total_missing_intervals": len(missing_all),
            "total_spike_points": int(sum(v["spike_count"] for v in spikes_all.values())),
        },
    }
    return _sanitize(result)


@router.get("/advanced-qc")
def advanced_qc(wid: int, db: Session = Depends(get_db)):
    return _run_advanced_qc(wid, db)


@router.get("/advanced-qc/missing-intervals")
def missing_intervals(wid: int, db: Session = Depends(get_db)):
    qc = _run_advanced_qc(wid, db)
    return {"well_id": wid, "missing_intervals": qc.get("missing_intervals", []), "summary": qc.get("summary", {})}


@router.get("/advanced-qc/spikes")
def spikes(wid: int, db: Session = Depends(get_db)):
    qc = _run_advanced_qc(wid, db)
    return {"well_id": wid, "spikes": qc.get("spikes", {}), "summary": qc.get("summary", {})}


@router.get("/advanced-qc/env-flags")
def env_flags(wid: int, db: Session = Depends(get_db)):
    qc = _run_advanced_qc(wid, db)
    return {"well_id": wid, "env_flags": qc.get("env_flags", {}), "summary": qc.get("summary", {})}
