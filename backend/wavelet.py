"""Statistical wavelet extraction from a seismic trace.

Method: autocorrelation of a windowed trace, smoothed in the cepstral domain
to suppress reflectivity noise, then minimum-phase reconstruction. The peak
frequency comes from the smoothed amplitude spectrum, so the estimate follows
the data instead of assuming a fixed Ricker.
"""

from __future__ import annotations

import numpy as np


def extract_wavelet(
    trace: np.ndarray,
    dt_s: float,
    window: tuple[int, int] | None = None,
    smooth_hz: float = 8.0,
) -> dict:
    values = np.asarray(trace, dtype=float).copy()
    if window is not None:
        start, end = max(0, int(window[0])), min(len(values), int(window[1]))
        if end - start < 16:
            raise ValueError("extraction window needs at least 16 samples")
        values = values[start:end]
    values = values[np.isfinite(values)]
    if len(values) < 32:
        raise ValueError("trace too short for wavelet extraction")
    if not dt_s > 0:
        raise ValueError("dt_s must be positive")
    values = values - float(np.mean(values))

    n = len(values)
    spectrum = np.abs(np.fft.rfft(values))
    freqs = np.fft.rfftfreq(n, d=float(dt_s))
    # Spectral smoothing with a boxcar in the frequency domain: suppresses
    # reflectivity notches while preserving the wavelet band shape.
    half_width = max(1, int(round(float(smooth_hz) / max(float(freqs[1] - freqs[0]), 1e-9))))
    kernel = np.ones(2 * half_width + 1, dtype=float) / (2 * half_width + 1)
    padded = np.pad(spectrum, half_width, mode="edge")
    smooth_amp = np.convolve(padded, kernel, mode="valid")
    peak_index = int(np.argmax(smooth_amp[1:]) + 1) if len(smooth_amp) > 1 else 0
    peak_freq = float(freqs[peak_index]) if peak_index < len(freqs) else 0.0

    # Minimum-phase wavelet from the smoothed amplitude spectrum via the
    # real cepstrum (log amplitude -> lifter -> exponentiate).
    log_amp = np.log(np.maximum(smooth_amp, 1e-12))
    cepstrum = np.fft.irfft(log_amp, n=n)
    lifter = np.zeros(n)
    lifter[0] = 1.0
    if n > 1:
        lifter[1 : n // 2] = 2.0
    min_phase_log = np.fft.rfft(cepstrum * lifter, n=n)
    wavelet = np.real(np.fft.irfft(np.exp(min_phase_log), n=n))
    wavelet = np.roll(wavelet, n // 4)
    peak = float(np.max(np.abs(wavelet))) if len(wavelet) else 0.0
    if peak > 0:
        wavelet = wavelet / peak
    duration = float(n * float(dt_s))
    time = (np.arange(n, dtype=float) * float(dt_s) - duration / 4.0).tolist()
    return {
        "method": "statistical",
        "wavelet": wavelet.tolist(),
        "time_s": time,
        "peak_freq_hz": round(peak_freq, 2),
        "dt_s": float(dt_s),
        "samples": n,
    }
