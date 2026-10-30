"""1D wedge forward model + tuning curve (TDD Red).

Physics: two reflectors (top/base) from AI contrast, convolved with a
wavelet on a uniform TWT grid. Tuning thickness verified analytically:
peak amplitude at thickness = v / (4 * f) for a Ricker wavelet.
"""

from __future__ import annotations

import numpy as np
import pytest


def _test_placeholder():
    pass


def test_wedge_tuning_matches_quarter_wavelength():
    # Narrowband wavelet: tuning is exactly lambda/4 (Widess). This locks
    # the kernel geometry; the broadband Ricker test below pins its
    # empirical peak separately.
    from backend.wedge import narrowband_wavelet, wedge_gather

    velocity = 3000.0
    freq = 30.0
    wave = narrowband_wavelet(freq, 0.001)
    result = wedge_gather(
        ai_top=6000.0 * 2300.0,
        ai_reservoir=8000.0 * 2600.0,
        ai_base=6000.0 * 2300.0,
        velocity_m_s=velocity,
        wavelet_freq_hz=freq,
        thickness_m=np.linspace(0, 60, 61),
        dt_s=0.001,
        wavelet=wave,
    )
    tuning = result["tuning_thickness_m"]
    expected = velocity / (4.0 * freq)
    assert tuning == pytest.approx(expected, rel=0.1)


def test_ricker_tuning_within_broadband_band():
    # Broadband Ricker: peak sits below lambda/4. Pins the empirical value
    # so a kernel regression cannot silently shift it.
    from backend.wedge import wedge_gather

    result = wedge_gather(
        ai_top=6000.0 * 2300.0,
        ai_reservoir=8000.0 * 2600.0,
        ai_base=6000.0 * 2300.0,
        velocity_m_s=3000.0,
        wavelet_freq_hz=30.0,
        thickness_m=np.linspace(0, 60, 61),
        dt_s=0.001,
    )
    assert result["tuning_thickness_m"] == pytest.approx(19.0, abs=2.0)
    assert result["analytic_tuning_m"] == pytest.approx(25.0)


def test_wedge_zero_thickness_is_transparent():
    from backend.wedge import wedge_gather

    result = wedge_gather(
        ai_top=6000.0 * 2300.0,
        ai_reservoir=8000.0 * 2600.0,
        ai_base=6000.0 * 2300.0,
        velocity_m_s=3000.0,
        wavelet_freq_hz=30.0,
        thickness_m=[0.0, 1.0, 50.0],
        dt_s=0.001,
    )
    amps = result["peak_amplitude"]
    assert amps[0] == pytest.approx(0.0, abs=1e-6)
    # Thick bed: top and base resolve separately, amplitude plateaus.
    assert amps[2] > 0


def test_opposite_polarity_wedge_notches():
    # Soft gas sand: top negative, base positive -> destructive tuning
    # gives an amplitude minimum below the thick-bed plateau.
    from backend.wedge import wedge_gather

    result = wedge_gather(
        ai_top=8000.0 * 2500.0,
        ai_reservoir=4500.0 * 2100.0,
        ai_base=8000.0 * 2500.0,
        velocity_m_s=3000.0,
        wavelet_freq_hz=30.0,
        thickness_m=np.linspace(0, 60, 61),
        dt_s=0.001,
    )
    amps = np.asarray(result["peak_amplitude"])
    assert amps[0] == pytest.approx(0.0, abs=1e-6)
    # Mid wedge (near tuning) exceeds the isolated-reflector plateau.
    assert amps[len(amps) // 2] > amps[-1]

def test_sweep_p10_p90_band_brackets_nominal():
    from backend.wedge import sweep_frequencies
    out = sweep_frequencies(
        ai_top=6000.0*2300.0, ai_reservoir=8000.0*2600.0, ai_base=6000.0*2300.0,
        velocity_m_s=3000.0, freqs_hz=[20.0, 30.0, 40.0],
        thickness_m=np.linspace(0, 60, 31), dt_s=0.001)
    assert out["freqs_hz"] == [20.0, 30.0, 40.0]
    n = len(out["thickness_m"])
    assert len(out["p10"]) == n and len(out["p90"]) == n and len(out["p50"]) == n
    for lo, mid, hi in zip(out["p10"], out["p50"], out["p90"]):
        assert lo <= mid <= hi
    i = n // 2
    f20, f30, f40 = (c[i] for c in out["curves"])
    assert f20 != f30 != f40

def test_sweep_rejects_single_freq():
    from backend.wedge import sweep_frequencies
    import pytest as _pt
    with _pt.raises(ValueError, match="at least two"):
        sweep_frequencies(1.0, 2.0, 1.0, 3000.0, [30.0], [0.0, 10.0])

def test_misfit_self_recovery_is_near_perfect():
    from backend.wedge import misfit_tie
    import numpy as _np
    rng = _np.random.default_rng(3)
    synth = rng.normal(0, 1, 400)
    out = misfit_tie(synth, synth.copy())
    assert out["correlation"] > 0.999
    assert out["shift_samples"] == 0

def test_misfit_recovers_known_lag():
    from backend.wedge import misfit_tie
    import numpy as _np
    rng = _np.random.default_rng(11)
    synth = rng.normal(0, 1, 400)
    shifted = _np.roll(synth, 7)
    out = misfit_tie(synth, shifted, max_lag=20)
    assert out["shift_samples"] == -7 or out["shift_samples"] == 7
    assert out["correlation"] > 0.99

def test_misfit_on_reference_fixture_high():
    # Full blind round-trip on Hawkins: extract wavelet from a noisy
    # reference trace, rebuild the synthetic with it, correlate back.
    # 0.93 with the recovered (~24 Hz) wavelet vs 0.99 with the true one.
    from backend.wedge import misfit_tie
    from backend.wavelet import extract_wavelet
    from backend.synthetic import compute_synthetic_seismogram
    from backend.las_parser import LASParser
    from tests.test_wavelet_recovery import _reference_trace
    from pathlib import Path
    import numpy as _np
    trace, twt, dt_s, freq = _reference_trace(Path("data/hawkins_01.las"), 30.0, 0.05, 7)
    ex = extract_wavelet(trace, dt_s)
    las = LASParser.parse_file("data/hawkins_01.las")
    dt = _np.asarray(las.data["DT"], float)
    rhob = _np.asarray(las.data["RHOB"], float)
    depth = _np.asarray(las.data["DEPT"], float)
    rebuilt = compute_synthetic_seismogram(
        dt, rhob, depth, dt_unit="US/F", depth_unit="FT",
        wavelet_freq=ex["peak_freq_hz"], max_points=5000,
    )
    a = _np.asarray(rebuilt["synthetic"])
    out = misfit_tie(a, trace[: len(a)])
    assert out["correlation"] > 0.9
    assert abs(out["shift_samples"]) <= 2
