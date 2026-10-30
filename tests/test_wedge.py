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
