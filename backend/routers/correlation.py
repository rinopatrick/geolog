from __future__ import annotations

from typing import Dict, List, Optional, Tuple

import numpy as np
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

try:
    from database import get_db
except Exception:  # pragma: no cover
    from backend.database import get_db

try:
    from models import (
        CorrelationMarker,
        CorrelationProfile,
        CurveData,
        FormationTop,
        LogRun,
        Well,
    )
except Exception:  # pragma: no cover
    from backend.models import (
        CorrelationMarker,
        CorrelationProfile,
        CurveData,
        FormationTop,
        LogRun,
        Well,
    )


router = APIRouter(prefix="/api/correlation", tags=["correlation"])


def _to_safe_value(v):
    if v is None:
        return None
    try:
        fv = float(v)
    except Exception:
        return None
    if not np.isfinite(fv):
        return None
    return fv


def _to_safe_list(arr: np.ndarray) -> List[Optional[float]]:
    if arr is None:
        return []
    if not isinstance(arr, np.ndarray):
        arr = np.asarray(arr, dtype=np.float32)
    out: List[Optional[float]] = []
    for v in arr:
        out.append(_to_safe_value(v))
    return out


def _norm_name(name: str) -> str:
    return str(name or "").strip().lower()


def _depth_of_top(t: FormationTop) -> Optional[float]:
    return _to_safe_value(getattr(t, "top_depth", None) if getattr(t, "top_depth", None) is not None else getattr(t, "depth", None))


def _load_curve(db: Session, well_id: int, curve: str) -> Tuple[Optional[LogRun], Optional[np.ndarray], Optional[np.ndarray], Optional[str]]:
    lr = db.query(LogRun).filter(LogRun.well_id == well_id).order_by(LogRun.id.desc()).first()
    if not lr:
        return None, None, None, None
    if not lr.num_points or lr.num_points <= 1 or lr.start_depth is None or lr.stop_depth is None:
        return lr, None, None, None

    depth = np.linspace(float(lr.start_depth), float(lr.stop_depth), int(lr.num_points), dtype=np.float32)
    cd = db.query(CurveData).filter(CurveData.log_run_id == lr.id, CurveData.mnemonic == curve).first()
    if not cd or not cd.data_binary:
        return lr, depth, None, None

    arr = np.frombuffer(cd.data_binary, dtype=np.float32)
    n = min(len(arr), len(depth))
    if n <= 1:
        return lr, depth, None, cd.unit or ""
    return lr, depth[:n], arr[:n], cd.unit or ""


def _interp_at(depth_arr: np.ndarray, val_arr: np.ndarray, sample_depths: np.ndarray) -> np.ndarray:
    if depth_arr is None or val_arr is None or len(depth_arr) < 2 or len(val_arr) < 2:
        return np.full_like(sample_depths, np.nan, dtype=np.float32)
    order = np.argsort(depth_arr)
    x = depth_arr[order]
    y = val_arr[order]
    finite = np.isfinite(y)
    if finite.sum() < 2:
        return np.full_like(sample_depths, np.nan, dtype=np.float32)
    x = x[finite]
    y = y[finite]
    return np.interp(sample_depths, x, y, left=np.nan, right=np.nan).astype(np.float32)


def _shape_score(gr_a_depth: np.ndarray, gr_a: np.ndarray, top_a: float,
                 gr_b_depth: np.ndarray, gr_b: np.ndarray, top_b: float,
                 window: float = 20.0, samples: int = 81) -> float:
    rel = np.linspace(-window, window, samples, dtype=np.float32)
    sa = _interp_at(gr_a_depth, gr_a, top_a + rel)
    sb = _interp_at(gr_b_depth, gr_b, top_b + rel)
    mask = np.isfinite(sa) & np.isfinite(sb)
    if mask.sum() < max(8, samples // 8):
        return -1e6
    sa = sa[mask]
    sb = sb[mask]
    sa_std = float(np.std(sa))
    sb_std = float(np.std(sb))
    if sa_std < 1e-9 or sb_std < 1e-9:
        return -1e6
    sa = (sa - float(np.mean(sa))) / sa_std
    sb = (sb - float(np.mean(sb))) / sb_std
    mse = float(np.mean((sa - sb) ** 2))
    corr = float(np.corrcoef(sa, sb)[0, 1]) if len(sa) > 2 else -1.0
    if not np.isfinite(corr):
        corr = -1.0
    return (1.0 - mse) + corr


@router.get("/cross-section")
def get_cross_section(well_ids: str, curve: str = "GR", db: Session = Depends(get_db)):
    ids: List[int] = []
    for x in (well_ids or "").split(","):
        x = x.strip()
        if not x:
            continue
        try:
            ids.append(int(x))
        except Exception as exc:
            raise HTTPException(status_code=400, detail=f"Invalid well_id: {x}") from exc

    if len(ids) < 2:
        raise HTTPException(status_code=400, detail="Provide at least two well IDs")

    wells_payload = []
    global_min = None
    global_max = None

    for wid in ids:
        well = db.query(Well).filter(Well.id == wid).first()
        if not well:
            continue
        lr, depth, values, unit = _load_curve(db, wid, curve)
        tops = db.query(FormationTop).filter(FormationTop.well_id == wid).order_by(FormationTop.depth.asc()).all()
        tops_payload = []
        for t in tops:
            d = _depth_of_top(t)
            if d is None:
                continue
            tops_payload.append({
                "id": t.id,
                "formation_name": t.formation_name,
                "depth": d,
                "color": t.color or "#888888",
            })

        if depth is not None and len(depth) > 1:
            dmin = float(np.nanmin(depth))
            dmax = float(np.nanmax(depth))
            global_min = dmin if global_min is None else min(global_min, dmin)
            global_max = dmax if global_max is None else max(global_max, dmax)

        wells_payload.append({
            "well_id": wid,
            "well_name": well.name,
            "curve": curve,
            "unit": unit or "",
            "depth": _to_safe_list(depth if depth is not None else np.array([], dtype=np.float32)),
            "values": _to_safe_list(values if values is not None else np.array([], dtype=np.float32)),
            "tops": tops_payload,
        })

    if len(wells_payload) < 2:
        raise HTTPException(status_code=404, detail="Insufficient well data for cross-section")

    return {
        "curve": curve,
        "depth_range": {
            "min": _to_safe_value(global_min),
            "max": _to_safe_value(global_max),
        },
        "wells": wells_payload,
    }


@router.get("/tie-lines")
def get_tie_lines(well_a_id: int, well_b_id: int, include_top_matches: bool = True, db: Session = Depends(get_db)):
    rows = db.query(CorrelationMarker).filter(
        ((CorrelationMarker.well_a_id == well_a_id) & (CorrelationMarker.well_b_id == well_b_id)) |
        ((CorrelationMarker.well_a_id == well_b_id) & (CorrelationMarker.well_b_id == well_a_id))
    ).order_by(CorrelationMarker.id.asc()).all()

    ties = []
    for r in rows:
        if r.well_a_id == well_a_id:
            a_depth = _to_safe_value(r.a_depth)
            b_depth = _to_safe_value(r.b_depth)
        else:
            a_depth = _to_safe_value(r.b_depth)
            b_depth = _to_safe_value(r.a_depth)
        if a_depth is None or b_depth is None:
            continue
        ties.append({
            "id": r.id,
            "label": r.label or "",
            "well_a_id": well_a_id,
            "well_b_id": well_b_id,
            "a_depth": a_depth,
            "b_depth": b_depth,
            "source": "marker",
        })

    if include_top_matches:
        tops_a = db.query(FormationTop).filter(FormationTop.well_id == well_a_id).all()
        tops_b = db.query(FormationTop).filter(FormationTop.well_id == well_b_id).all()
        by_name_b: Dict[str, FormationTop] = {_norm_name(t.formation_name): t for t in tops_b if _norm_name(t.formation_name)}
        for ta in tops_a:
            key = _norm_name(ta.formation_name)
            tb = by_name_b.get(key)
            if not tb:
                continue
            ad = _depth_of_top(ta)
            bd = _depth_of_top(tb)
            if ad is None or bd is None:
                continue
            ties.append({
                "id": f"top-{ta.id}-{tb.id}",
                "label": ta.formation_name,
                "well_a_id": well_a_id,
                "well_b_id": well_b_id,
                "a_depth": ad,
                "b_depth": bd,
                "source": "formation_top",
                "color": ta.color or tb.color or "#8b949e",
            })

    return {
        "well_a_id": well_a_id,
        "well_b_id": well_b_id,
        "tie_lines": ties,
    }


@router.post("/auto-correlate")
def auto_correlate(payload: dict, db: Session = Depends(get_db)):
    well_a_id = int(payload.get("well_a_id", 0) or 0)
    well_b_id = int(payload.get("well_b_id", 0) or 0)
    curve = str(payload.get("curve", "GR") or "GR")
    depth_tolerance = float(payload.get("depth_tolerance", 50.0) or 50.0)
    window = float(payload.get("window", 20.0) or 20.0)

    if not well_a_id or not well_b_id:
        raise HTTPException(status_code=400, detail="well_a_id and well_b_id are required")
    if well_a_id == well_b_id:
        raise HTTPException(status_code=400, detail="well_a_id and well_b_id must be different")

    _, da, ga, _ = _load_curve(db, well_a_id, curve)
    _, dbb, gb, _ = _load_curve(db, well_b_id, curve)

    tops_a = db.query(FormationTop).filter(FormationTop.well_id == well_a_id).order_by(FormationTop.depth.asc()).all()
    tops_b = db.query(FormationTop).filter(FormationTop.well_id == well_b_id).order_by(FormationTop.depth.asc()).all()
    if not tops_a or not tops_b:
        return {"matches": [], "count": 0, "curve": curve}

    b_candidates = []
    for tb in tops_b:
        d = _depth_of_top(tb)
        if d is None:
            continue
        b_candidates.append((tb, d, _norm_name(tb.formation_name)))

    matches = []
    used_b = set()

    for ta in tops_a:
        a_depth = _depth_of_top(ta)
        if a_depth is None:
            continue
        name_key = _norm_name(ta.formation_name)
        local = []
        for tb, b_depth, b_name in b_candidates:
            if tb.id in used_b:
                continue
            if abs(a_depth - b_depth) > depth_tolerance:
                continue
            depth_score = max(0.0, 1.0 - (abs(a_depth - b_depth) / max(depth_tolerance, 1e-6)))
            name_bonus = 0.5 if (name_key and name_key == b_name) else 0.0
            shape = 0.0
            if da is not None and ga is not None and dbb is not None and gb is not None:
                shape = _shape_score(da, ga, a_depth, dbb, gb, b_depth, window=window)
            total = (1.5 * depth_score) + name_bonus + shape
            local.append((total, depth_score, shape, tb, b_depth))

        if not local:
            continue

        local.sort(key=lambda x: x[0], reverse=True)
        total, depth_score, shape, best_tb, best_b_depth = local[0]
        used_b.add(best_tb.id)
        matches.append({
            "well_a_id": well_a_id,
            "well_b_id": well_b_id,
            "a_top_id": ta.id,
            "b_top_id": best_tb.id,
            "formation_a": ta.formation_name,
            "formation_b": best_tb.formation_name,
            "a_depth": _to_safe_value(a_depth),
            "b_depth": _to_safe_value(best_b_depth),
            "depth_delta": _to_safe_value(best_b_depth - a_depth),
            "depth_score": _to_safe_value(depth_score),
            "shape_score": _to_safe_value(shape),
            "total_score": _to_safe_value(total),
            "label": ta.formation_name or best_tb.formation_name or "Auto",
        })

    matches.sort(key=lambda m: (m.get("a_depth") if m.get("a_depth") is not None else 1e12))

    # Optional profile hint from matched tops.
    profile_hint = None
    if matches:
        deltas = np.array([m["depth_delta"] for m in matches if m.get("depth_delta") is not None], dtype=np.float32)
        if len(deltas) > 0:
            shift = float(np.nanmedian(deltas))
            profile_hint = {
                "depth_shift": _to_safe_value(shift),
                "stretch": 1.0,
                "snap_to_tops": 1,
                "curve": curve,
            }

    # Return current profile as reference.
    current_profile = db.query(CorrelationProfile).filter(
        ((CorrelationProfile.well_a_id == well_a_id) & (CorrelationProfile.well_b_id == well_b_id)) |
        ((CorrelationProfile.well_a_id == well_b_id) & (CorrelationProfile.well_b_id == well_a_id))
    ).first()

    return {
        "well_a_id": well_a_id,
        "well_b_id": well_b_id,
        "curve": curve,
        "count": len(matches),
        "matches": matches,
        "profile_hint": profile_hint,
        "current_profile": {
            "depth_shift": _to_safe_value(current_profile.depth_shift) if current_profile else 0.0,
            "stretch": _to_safe_value(current_profile.stretch) if current_profile else 1.0,
            "snap_to_tops": int(current_profile.snap_to_tops) if current_profile else 1,
            "curve": current_profile.curve if current_profile else curve,
        },
    }
