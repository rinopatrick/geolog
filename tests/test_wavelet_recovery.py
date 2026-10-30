"""Statistical wavelet extraction + synthetic recovery fixtures (Opsi A).

Validasi = synthetic recovery test: jejak referensi dibangun dari log LAS
publik (Hawkins, KGS) via forward-model yang DIKETAHUI (Ricker f + noise),
lalu ekstraktor buta harus memulihkan frekuensi dan fase wavelet.
Ini BUKAN tie lapangan — docs catat eksplisit.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from backend.las_parser import LASParser
from backend.synthetic import compute_synthetic_seismogram

ROOT = Path(__file__).resolve().parents[1]
HAWKINS = ROOT / "data" / "hawkins_01.las"


def _ricker(freq: float, dt_s: float, length_s: float = 0.128) -> np.ndarray:
    t = np.arange(-length_s / 2, length_s / 2 + dt_s, dt_s)
    w = (1.0 - 2.0 * (np.pi**2) * (freq**2) * (t**2)) * np.exp(
        -((np.pi**2) * (freq**2) * (t**2))
    )
    peak = float(np.max(np.abs(w))) if len(w) else 0.0
    return w / peak if peak > 0 else w


def _reference_trace(log_path: Path, freq: float, noise: float, seed: int):
    las = LASParser.parse_file(str(log_path))
    depth = np.asarray(las.data["DEPT"], dtype=float)
    dt = np.asarray(las.data["DT"], dtype=float)
    rhob = np.asarray(las.data["RHOB"], dtype=float)
    synth = compute_synthetic_seismogram(
        dt, rhob, depth, dt_unit="US/F", depth_unit="FT",
        wavelet_freq=freq, max_points=5000,
    )
    rng = np.random.default_rng(seed)
    trace = np.asarray(synth["synthetic"], dtype=float)
    trace = trace + rng.normal(0, noise * float(np.max(np.abs(trace)) or 1.0), len(trace))
    twt = np.asarray(synth["twt"], dtype=float)
    dt_s = float(np.median(np.diff(twt)))
    return trace, twt, dt_s, freq


def test_recovery_fixture_builds():
    trace, twt, dt_s, freq = _reference_trace(HAWKINS, 30.0, 0.05, 7)
    assert len(trace) > 100
    assert dt_s > 0 and np.all(np.diff(twt) >= 0)
    assert np.max(np.abs(trace)) > 0


def test_extracted_wavelet_recovers_known_frequency():
    from backend.wavelet import extract_wavelet

    for true_freq in (25.0, 35.0):
        trace, twt, dt_s, _ = _reference_trace(HAWKINS, true_freq, 0.05, 7)
        result = extract_wavelet(trace, dt_s)
        assert result["peak_freq_hz"] == pytest.approx(true_freq, rel=0.25)
        assert result["method"] == "statistical"
