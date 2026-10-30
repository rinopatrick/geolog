"""1D wedge forward model with tuning analysis.

Two reflectors (top/base of a reservoir layer) from acoustic-impedance
contrast, convolved with a Ricker or extracted wavelet on a uniform TWT grid.
Peak amplitude vs thickness gives the tuning curve; the tuning thickness is
verified against the quarter-wavelength analytic result.
"""

from __future__ import annotations

import numpy as np


def ricker_wavelet(freq_hz: float, dt_s: float, length_s: float = 0.128) -> np.ndarray:
    if not freq_hz > 0:
        raise ValueError("wavelet frequency must be positive")
    if not dt_s > 0:
        raise ValueError("dt_s must be positive")
    t = np.arange(-length_s / 2, length_s / 2 + dt_s, dt_s)
    w = (1.0 - 2.0 * (np.pi**2) * (freq_hz**2) * (t**2)) * np.exp(
        -((np.pi**2) * (freq_hz**2) * (t**2))
    )
    peak = float(np.max(np.abs(w))) if len(w) else 0.0
    return w / peak if peak > 0 else w


def narrowband_wavelet(freq_hz: float, dt_s: float, cycles: int = 8) -> np.ndarray:
    """Tapered sinusoid for analytic verification (Widess quarter-wavelength)."""
    if not freq_hz > 0:
        raise ValueError("wavelet frequency must be positive")
    if not dt_s > 0:
        raise ValueError("dt_s must be positive")
    n = max(16, int(round(float(cycles) / float(freq_hz) / float(dt_s))))
    t = (np.arange(n, dtype=float) - n // 2) * float(dt_s)
    taper = np.hanning(n)
    w = taper * np.cos(2.0 * np.pi * float(freq_hz) * t)
    peak = float(np.max(np.abs(w))) if len(w) else 0.0
    return w / peak if peak > 0 else w


def rc_from_ai(ai_top: float, ai_mid: float, ai_base: float) -> tuple[float, float]:
    if min(ai_top, ai_mid, ai_base) <= 0:
        raise ValueError("acoustic impedances must be positive")
    rc_top = (ai_mid - ai_top) / (ai_mid + ai_top)
    rc_base = (ai_base - ai_mid) / (ai_base + ai_mid)
    return float(rc_top), float(rc_base)


def wedge_gather(
    ai_top: float,
    ai_reservoir: float,
    ai_base: float,
    velocity_m_s: float,
    wavelet_freq_hz: float,
    thickness_m: np.ndarray | list[float],
    dt_s: float = 0.001,
    wavelet: np.ndarray | None = None,
) -> dict:
    if not velocity_m_s > 0:
        raise ValueError("velocity must be positive")
    thicknesses = np.asarray(thickness_m, dtype=float)
    if np.any(thicknesses < 0):
        raise ValueError("thickness must be non-negative")
    rc_top, rc_base = rc_from_ai(ai_top, ai_reservoir, ai_base)
    if wavelet is None:
        wave = ricker_wavelet(float(wavelet_freq_hz), float(dt_s))
    else:
        wave = np.asarray(wavelet, dtype=float)
        if len(wave) < 3:
            raise ValueError("wavelet too short")

    # Time window wide enough for the thickest bed plus wavelet tails.
    max_lag_s = float(np.max(thicknesses)) * 2.0 / float(velocity_m_s)
    half_n = int(round((max_lag_s / 2.0 + len(wave) * float(dt_s)) / float(dt_s))) + len(wave)
    n = 2 * half_n + 1
    center = half_n
    gathers = []
    peak_amplitude = []
    for thick in thicknesses:
        lag_samples = int(round(float(thick) * 2.0 / float(velocity_m_s) / float(dt_s)))
        rc = np.zeros(n)
        rc[center] = rc_top
        rc[min(center + lag_samples, n - 1)] += rc_base
        trace = np.convolve(rc, wave, mode="same")
        gathers.append(trace.tolist())
        peak_amplitude.append(float(np.max(np.abs(trace))))
    peak_amplitude = np.asarray(peak_amplitude)
    tuning_index = int(np.argmax(peak_amplitude))
    return {
        "thickness_m": [round(float(v), 3) for v in thicknesses],
        "peak_amplitude": [round(float(v), 6) for v in peak_amplitude],
        "tuning_thickness_m": round(float(thicknesses[tuning_index]), 3),
        "tuning_amplitude": round(float(peak_amplitude[tuning_index]), 6),
        "analytic_tuning_m": round(float(velocity_m_s) / (4.0 * float(wavelet_freq_hz)), 3),
        "rc_top": round(rc_top, 6),
        "rc_base": round(rc_base, 6),
        "velocity_m_s": float(velocity_m_s),
        "wavelet_freq_hz": float(wavelet_freq_hz),
        "dt_s": float(dt_s),
    }


def sweep_frequencies(ai_top, ai_reservoir, ai_base, velocity_m_s, freqs_hz, thickness_m, dt_s=0.001):
    """Run wedge_gather per frequency; return curves + P10/P50/P90 band."""
    freqs = [float(f) for f in freqs_hz]
    if len(freqs) < 2:
        raise ValueError("sweep needs at least two frequencies")
    if any(not f > 0 for f in freqs):
        raise ValueError("frequencies must be positive")
    curves = []
    for f in freqs:
        r = wedge_gather(ai_top, ai_reservoir, ai_base, velocity_m_s, f, thickness_m, dt_s)
        curves.append(r["peak_amplitude"])
    arr = np.asarray(curves, dtype=float)
    return {
        "freqs_hz": freqs,
        "thickness_m": [round(float(v), 3) for v in np.asarray(thickness_m, dtype=float)],
        "curves": curves,
        "p10": [round(float(v), 6) for v in np.percentile(arr, 10, axis=0)],
        "p50": [round(float(v), 6) for v in np.percentile(arr, 50, axis=0)],
        "p90": [round(float(v), 6) for v in np.percentile(arr, 90, axis=0)],
        "dt_s": float(dt_s),
    }
