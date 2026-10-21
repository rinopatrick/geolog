"""Saturation-height model fits and evaluation."""

from __future__ import annotations

import numpy as np

from backend.saturation_height import apply_model, fit_model


def test_j_function_fit():
    j = np.array([1.0, 2.0, 4.0, 8.0, 16.0, 32.0])
    pc = j.copy()
    sw = 0.8 * np.power(j, -0.4)
    fitted = fit_model("j_function", pc, sw, j)
    assert fitted["r2"] > 0.999
    assert abs(fitted["parameters"]["a"] - 0.8) < 1e-3
    assert abs(fitted["parameters"]["b"] + 0.4) < 1e-3
    assert np.allclose(apply_model("j_function", fitted["parameters"], pc, j), sw, atol=1e-3)


def test_brooks_corey_fit():
    pc = np.array([5.0, 10.0, 20.0, 40.0, 80.0, 120.0])
    sw = np.power(10.0 / pc, 1.2)
    fitted = fit_model("brooks_corey", pc, sw)
    assert fitted["r2"] > 0.999
    assert abs(fitted["parameters"]["pe"] - 10.0) < 1e-2
    assert abs(fitted["parameters"]["lambda"] - 1.2) < 1e-2
    assert np.allclose(apply_model("brooks_corey", fitted["parameters"], pc), np.clip(sw, 0, 1), atol=1e-3)


def test_lambda_thomeer_skelt_fit():
    pc = np.array([5.0, 10.0, 20.0, 40.0, 80.0, 120.0])
    cases = {
        "lambda": (20.0, 1.5, lambda p, pe, lam: np.power(1 + p / pe, -lam)),
        "thomeer": (10.0, 1.5, lambda p, pe, g: 1 - np.exp(-g * pe / p)),
        "skelt_harrison": (15.0, 2.0, lambda p, pe, n: np.power(1 + np.power(p / pe, n), -1 / n)),
    }
    for kind, (p1, p2, formula) in cases.items():
        sw = formula(pc, p1, p2)
        fitted = fit_model(kind, pc, sw)
        assert fitted["r2"] > 0.99, (kind, fitted)
        assert np.allclose(apply_model(kind, fitted["parameters"], pc), sw, atol=2e-2), kind
