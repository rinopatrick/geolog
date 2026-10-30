"""Wedge forward-model endpoint (stateless 1D screening)."""

from __future__ import annotations

import numpy as np

from fastapi import APIRouter, HTTPException

try:
    from wedge import sweep_frequencies, wedge_gather
except ImportError:
    from backend.wedge import sweep_frequencies, wedge_gather

router = APIRouter(prefix="/api/seismic", tags=["seismic"])


def _num(value, name: str, low: float, high: float) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        raise HTTPException(400, f"{name} must be a number")
    if not np.isfinite(number) or not low <= number <= high:
        raise HTTPException(400, f"{name} must be between {low} and {high}")
    return number


@router.post("/wedge-model")
def wedge_model(data: dict):
    try:
        ai_top = _num(data.get("ai_top"), "ai_top", 1e3, 1e8)
        ai_res = _num(data.get("ai_reservoir"), "ai_reservoir", 1e3, 1e8)
        ai_base = _num(data.get("ai_base"), "ai_base", 1e3, 1e8)
        velocity = _num(data.get("velocity_m_s", 3000.0), "velocity_m_s", 500.0, 8000.0)
    except (TypeError, AttributeError):
        raise HTTPException(400, "body must be a JSON object")
    freqs = data.get("freqs_hz", [20.0, 30.0, 40.0])
    if not isinstance(freqs, list) or len(freqs) < 1 or len(freqs) > 9:
        raise HTTPException(400, "freqs_hz must be a list of 1-9 frequencies")
    freqs = [_num(f, "freqs_hz[]", 5.0, 120.0) for f in freqs]
    thick = data.get("thickness_m")
    if not isinstance(thick, list) or len(thick) < 2 or len(thick) > 201:
        raise HTTPException(400, "thickness_m must be a list of 2-201 values")
    thick = [_num(t, "thickness_m[]", 0.0, 500.0) for t in thick]
    try:
        sweep = sweep_frequencies(ai_top, ai_res, ai_base, velocity, freqs, thick)
    except ValueError as exc:
        raise HTTPException(400, str(exc))
    curves = {}
    tuning = {}
    for freq, curve in zip(sweep["freqs_hz"], sweep["curves"]):
        single = wedge_gather(ai_top, ai_res, ai_base, velocity, freq, thick)
        key = str(freq)
        curves[key] = single
        tuning[key] = single["tuning_thickness_m"]
    return {
        "thickness_m": sweep["thickness_m"],
        "freqs_hz": sweep["freqs_hz"],
        "curves": curves,
        "tuning_thickness_per_freq": tuning,
        "p10": sweep["p10"],
        "p50": sweep["p50"],
        "p90": sweep["p90"],
        "model": "1D wedge screening (vertical incidence, no AVO/diffraction)",
    }
