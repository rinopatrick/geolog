"""Analytic checks for shaly-sand saturation equations."""

from __future__ import annotations

import numpy as np
import pytest

from backend.saturation import saturation


def test_archie_and_clean_shaly_sand_equivalence():
    archie = saturation("archie", 10.0, 0.2, 0.0, a=1.0, m=2.0, n=2.0, rw=0.1)
    simandoux = saturation("simandoux", 10.0, 0.2, 0.0, a=1.0, m=2.0, n=2.0, rw=0.1, rsh=4.0)
    indonesian = saturation("indonesian", 10.0, 0.2, 0.0, a=1.0, m=2.0, n=2.0, rw=0.1, rsh=4.0)
    expected = np.sqrt(0.1 / (0.2 ** 2 * 10.0))
    assert archie == pytest.approx(expected)
    assert simandoux == pytest.approx(archie)
    assert indonesian == pytest.approx(archie)


def test_simandoux_analytic_value():
    # Sw^2 = (a Rw / phi^m) (1/Rt - Vsh/Rsh)
    expected = np.sqrt((0.1 / 0.2 ** 2) * (1 / 10.0 - 0.2 / 4.0))
    value = saturation("simandoux", 10.0, 0.2, 0.2, a=1.0, m=2.0, n=2.0, rw=0.1, rsh=4.0)
    assert value == pytest.approx(expected)


def test_indonesian_analytic_value():
    denominator = np.sqrt(0.2 ** 2 / 0.1) + np.sqrt(0.2 / 4.0)
    expected = (1.0 / (np.sqrt(10.0) * denominator)) ** (2.0 / 2.0)
    value = saturation("indonesian", 10.0, 0.2, 0.2, a=1.0, m=2.0, n=2.0, rw=0.1, rsh=4.0)
    assert value == pytest.approx(expected)


def test_saturation_array_and_clipping():
    values = saturation("simandoux", np.array([0.1, 1.0, 100.0]), 0.2, 0.2)
    assert values.shape == (3,)
    assert np.all(values >= 0) and np.all(values <= 1)
