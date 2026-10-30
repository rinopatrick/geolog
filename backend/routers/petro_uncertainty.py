"""Per-depth petrophysical uncertainty bands."""

from __future__ import annotations

import numpy as np

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

try:
    from acl import require_well_access
    from database import get_db
    from models import CurveData, LogRun, Well
    from saturation import saturation
except ImportError:
    from backend.acl import require_well_access
    from backend.database import get_db
    from backend.models import CurveData, LogRun, Well
    from backend.saturation import saturation

router = APIRouter(prefix="/api/wells", tags=["petro-uncertainty"])


def _curve(db: Session, run_id: int, names: list[str]) -> np.ndarray | None:
    row = db.query(CurveData).filter(CurveData.log_run_id == run_id, CurveData.mnemonic.in_(names)).first()
    return np.frombuffer(row.data_binary, dtype=np.float64).copy() if row else None


@router.post("/{wid}/petro-uncertainty")
def petro_uncertainty(wid: int, data: dict, request: Request, db: Session = Depends(get_db)):
    require_well_access(db, request, wid)
    if not db.query(Well.id).filter(Well.id == wid).first():
        raise HTTPException(404, "Well not found")
    lr_id = data.get("log_run_id")
    run = (
        db.query(LogRun).filter(LogRun.id == lr_id).first()
        if lr_id
        else db.query(LogRun).filter(LogRun.well_id == wid).order_by(LogRun.num_points.desc()).first()
    )
    if not run:
        raise HTTPException(404, "No log run")
    rt = _curve(db, run.id, ["RT", "RESD", "RILD", "ILD"])
    nphi = _curve(db, run.id, ["NPHI", "NPHI_LS"])
    if rt is None or nphi is None:
        raise HTTPException(400, "Need RT and NPHI curves")
    gr = _curve(db, run.id, ["GR", "SGR", "CGR"])
    rhob = _curve(db, run.id, ["RHOB", "RHOZ", "DEN"])
    depth = _curve(db, run.id, ["DEPT", "DEPTH"])
    if depth is None:
        depth = np.arange(len(rt), dtype=float)
    length = min(len(rt), len(nphi), len(depth))
    rt, nphi, depth = rt[:length], nphi[:length], depth[:length]
    gr = gr[:length] if gr is not None else np.zeros(length)
    rhob = rhob[:length] if rhob is not None and len(rhob) >= length else None
    start = data.get("start_depth")
    stop = data.get("stop_depth")
    mask = np.isfinite(rt) & np.isfinite(nphi) & (rt > 0) & (nphi >= 0)
    if start is not None:
        mask &= depth >= float(start)
    if stop is not None:
        mask &= depth <= float(stop)
    if mask.sum() < 5:
        raise HTTPException(400, "Not enough valid RT/NPHI samples in the interval")
    indices = np.flatnonzero(mask)
    if len(indices) > 3000:
        indices = indices[np.linspace(0, len(indices) - 1, 3000).round().astype(int)]
    rt = rt[indices]
    nphi = nphi[indices]
    gr = gr[indices]
    rhob = rhob[indices] if rhob is not None else None
    depth = depth[indices]

    gr_valid = gr[np.isfinite(gr)]
    gr_min = float(np.min(gr_valid)) if len(gr_valid) else 0.0
    gr_max = float(np.max(gr_valid)) if len(gr_valid) else 150.0
    if gr_max <= gr_min:
        gr_max = gr_min + 1.0
    vsh = np.clip((gr - gr_min) / (gr_max - gr_min), 0.0, 1.0)
    rho_ma = float(data.get("rho_ma", 2.65))
    rho_f = float(data.get("rho_f", 1.0))
    phi_sh = float(data.get("phi_sh", 0.30))
    if rhob is not None:
        phi_d = np.clip((rho_ma - rhob) / max(1e-9, rho_ma - rho_f), -0.15, 0.60)
        phi_raw = np.where(
            np.isfinite(phi_d) & np.isfinite(nphi),
            np.where(nphi < phi_d - 0.03, phi_d, (phi_d + nphi) / 2.0),
            np.where(np.isfinite(phi_d), phi_d, nphi),
        )
    else:
        phi_raw = nphi
    phi_base = np.maximum(0.0, phi_raw - vsh * phi_sh)

    model = str(data.get("saturation_model", "archie")).lower()
    if model not in {"archie", "simandoux", "indonesian"}:
        raise HTTPException(400, "saturation_model must be archie, simandoux or indonesian")
    iterations = max(20, min(int(data.get("iterations", 200)), 500))
    variation = max(0.0, min(float(data.get("variation_pct", 25)) / 100.0, 0.95))
    a_base = max(float(data.get("a", 1.0)), 1e-6)
    m_base = max(float(data.get("m", 2.0)), 0.2)
    n_base = max(float(data.get("n", 2.0)), 0.2)
    rw_base = max(float(data.get("rw", 0.1)), 1e-6)
    rsh_base = max(float(data.get("rsh", 4.0)), 1e-6)
    seed = data.get("seed")
    rng = np.random.default_rng(seed)

    def sample(base: float, low: float, high: float) -> float:
        return float(np.clip(base * (1.0 + rng.uniform(-variation, variation)), low, high))

    sw_samples = np.empty((iterations, len(rt)), dtype=float)
    phie_samples = np.empty_like(sw_samples)
    vsh_samples = np.empty_like(sw_samples)
    for index in range(iterations):
        a_v = sample(a_base, 1e-6, 10.0)
        m_v = sample(m_base, 0.2, 8.0)
        n_v = sample(n_base, 0.2, 8.0)
        rw_v = sample(rw_base, 1e-6, 5.0)
        rsh_v = sample(rsh_base, 1e-6, 50.0)
        vsh_scale = sample(1.0, 0.4, 1.6)
        phie_scale = sample(1.0, 0.5, 1.5)
        vsh_i = np.clip(vsh * vsh_scale, 0.0, 1.0)
        phi_i = np.clip((phi_base + vsh * phi_sh - vsh_i * phi_sh) * phie_scale, 0.0, 0.6)
        sw_samples[index] = saturation(
            model,
            rt,
            phi_i,
            vsh_i,
            a=a_v,
            m=m_v,
            n=n_v,
            rw=rw_v,
            rsh=rsh_v,
        )
        phie_samples[index] = phi_i
        vsh_samples[index] = vsh_i

    def band(samples: np.ndarray) -> dict[str, list[float]]:
        p90, p50, p10 = np.percentile(samples, [10, 50, 90], axis=0)
        return {
            "p90": [round(float(value), 5) for value in p90],
            "p50": [round(float(value), 5) for value in p50],
            "p10": [round(float(value), 5) for value in p10],
        }

    step = max(1, len(depth) // 1500)
    return {
        "iterations": iterations,
        "variation_pct": round(variation * 100, 2),
        "saturation_model": model,
        "rsh": rsh_base,
        "depth": [round(float(value), 3) for value in depth[::step]],
        "sw": {key: values[::step] for key, values in band(sw_samples).items()},
        "phie": {key: values[::step] for key, values in band(phie_samples).items()},
        "vsh": {key: values[::step] for key, values in band(vsh_samples).items()},
        "summary": {
            "sw_p50_mean": round(float(np.mean(np.percentile(sw_samples, 50, axis=0))), 4),
            "phie_p50_mean": round(float(np.mean(np.percentile(phie_samples, 50, axis=0))), 4),
            "vsh_p50_mean": round(float(np.mean(np.percentile(vsh_samples, 50, axis=0))), 4),
        },
    }
