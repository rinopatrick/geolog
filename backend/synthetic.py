"""Synthetic seismogram generation on a uniform two-way-time grid."""

from __future__ import annotations

import numpy as np


def _depth_scale(unit: str | None) -> float:
    text = str(unit or "FT").strip().upper()
    return 0.3048 if "FT" in text or text in {"F", "FEET"} else 1.0


def _dt_scale(unit: str | None) -> float:
    """Convert DT to seconds per metre."""
    text = str(unit or "US/F").strip().upper().replace(" ", "")
    if "/M" in text or "US/M" in text:
        return 1e-6
    return 3.28084e-6


def compute_synthetic_seismogram(
    dt: np.ndarray,
    rhob: np.ndarray,
    depth: np.ndarray,
    dt_unit: str | None = "US/F",
    depth_unit: str | None = "FT",
    wavelet_freq: float = 30.0,
    polarity: str = "normal",
    phase: int = 0,
    max_points: int = 2000,
) -> dict:
    dt = np.asarray(dt, dtype=float).copy()
    rhob = np.asarray(rhob, dtype=float).copy()
    depth = np.asarray(depth, dtype=float).copy()
    length = min(len(dt), len(rhob), len(depth))
    dt, rhob, depth = dt[:length], rhob[:length], depth[:length]
    valid = np.isfinite(dt) & np.isfinite(rhob) & np.isfinite(depth) & (dt > 0) & (rhob > 1.5) & (rhob < 3.5)
    dt = dt[valid]
    rhob = rhob[valid]
    depth = depth[valid]
    if len(dt) < 10:
        raise ValueError("Not enough valid DT/RHOB data")

    depth_m = depth * _depth_scale(depth_unit)
    dt_s_per_m = dt * _dt_scale(dt_unit)
    velocity = 1.0 / np.maximum(dt_s_per_m, 1e-12)
    ai = (rhob * 1000.0) * velocity
    rc = np.zeros(len(ai), dtype=float)
    ai_sum = ai[1:] + ai[:-1]
    safe = np.abs(ai_sum) > 1e-12
    rc_vals = np.zeros(len(ai) - 1, dtype=float)
    rc_vals[safe] = (ai[1:][safe] - ai[:-1][safe]) / ai_sum[safe]
    rc[1:] = rc_vals

    d_depth = np.diff(depth_m)
    if len(d_depth) == 0:
        raise ValueError("Not enough depth samples")
    median_dd = float(np.nanmedian(np.abs(d_depth[d_depth != 0]))) if np.any(d_depth != 0) else 0.5
    d_depth_safe = np.where(np.abs(d_depth) > 0, np.abs(d_depth), median_dd if median_dd > 0 else 0.5)
    twt = np.zeros(len(depth_m), dtype=float)
    twt[1:] = 2.0 * np.cumsum(dt_s_per_m[:-1] * d_depth_safe)

    span = float(twt[-1] - twt[0]) if len(twt) > 1 else 0.0
    if span <= 0:
        raise ValueError("time-depth curve has no duration")
    target_dt = max(0.0002, min(0.002, span / 4000.0))
    uniform_time = np.arange(twt[0], twt[-1] + target_dt * 0.5, target_dt)
    rc_uniform = np.interp(uniform_time, twt, rc, left=0.0, right=0.0)

    frequency = float(np.clip(wavelet_freq, 10.0, 80.0))
    half_length = min(0.064, max(0.008, span / 4.0))
    wavelet_time = np.arange(-half_length, half_length + target_dt, target_dt)
    wavelet = (1.0 - 2.0 * (np.pi ** 2) * (frequency ** 2) * (wavelet_time ** 2)) * np.exp(
        -(np.pi ** 2) * (frequency ** 2) * (wavelet_time ** 2)
    )
    peak = float(np.max(np.abs(wavelet))) if len(wavelet) else 0.0
    if peak > 0:
        wavelet = wavelet / peak

    synthetic_uniform = np.convolve(rc_uniform, wavelet, mode="full")
    start = len(wavelet) // 2
    synthetic_uniform = synthetic_uniform[start:start + len(rc_uniform)]
    if int(float(phase)) == 90:
        synthetic_uniform = np.imag(_hilbert(synthetic_uniform))
    if str(polarity).lower() == "reversed":
        synthetic_uniform = -synthetic_uniform
    synthetic = np.interp(twt, uniform_time, synthetic_uniform, left=0.0, right=0.0)

    step = max(1, len(depth) // max(1, int(max_points)))
    return {
        "depth": depth[::step].tolist(),
        "twt": twt[::step].tolist(),
        "ai": ai[::step].tolist(),
        "rc": rc[::step].tolist(),
        "synthetic": synthetic[::step].tolist(),
        "wavelet": {
            "time": wavelet_time.tolist(),
            "amplitude": wavelet.tolist(),
        },
        "params": {
            "wavelet_freq": frequency,
            "polarity": str(polarity).lower(),
            "phase": 90 if int(float(phase)) == 90 else 0,
            "time_sample_s": target_dt,
            "n_points": len(depth),
            "depth_unit": "M" if _depth_scale(depth_unit) == 1.0 else "FT",
            "dt_unit": dt_unit or "US/F",
        },
        "stats": {
            "ai_min": round(float(np.min(ai)), 1),
            "ai_max": round(float(np.max(ai)), 1),
            "ai_mean": round(float(np.mean(ai)), 1),
            "rc_min": round(float(np.min(rc)), 4),
            "rc_max": round(float(np.max(rc)), 4),
            "twt_min_s": round(float(np.min(twt)), 4),
            "twt_max_s": round(float(np.max(twt)), 4),
        },
    }


def _hilbert(values: np.ndarray) -> np.ndarray:
    values = np.asarray(values, dtype=float)
    length = len(values)
    if length == 0:
        return values.copy()
    spectrum = np.fft.fft(values)
    multiplier = np.zeros(length)
    if length % 2 == 0:
        multiplier[0] = 1.0
        multiplier[length // 2] = 1.0
        multiplier[1:length // 2] = 2.0
    else:
        multiplier[0] = 1.0
        multiplier[1:(length + 1) // 2] = 2.0
    return np.fft.ifft(spectrum * multiplier)
