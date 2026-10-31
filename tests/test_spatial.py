"""Lateral correlation for cell maps (TDD Red).

Production-grade bar: correlated field must (a) reproduce the target
marginal mean/variance, (b) show distance-decaying correlation matching
the variogram range, (c) stay seeded-reproducible, (d) reject bad input.
"""

from __future__ import annotations

import pytest


def test_correlated_field_matches_marginal():
    from backend.spatial import simulate_gaussian_field
    import numpy as np

    field = simulate_gaussian_field(
        rows=20, cols=20, mean=0.0, std=1.0,
        range_cells=5.0, seed=7,
    )
    assert field.shape == (20, 20)
    assert abs(float(np.mean(field))) < 0.3
    assert 0.5 < float(np.std(field)) < 1.5


def test_correlation_decays_with_distance():
    from backend.spatial import simulate_gaussian_field
    import numpy as np

    field = simulate_gaussian_field(
        rows=30, cols=30, mean=0.0, std=1.0,
        range_cells=8.0, seed=7,
    )
    # Empirical covariogram along rows: lag-1 strongly correlated,
    # lag-8 (== range) near zero.
    def lag_corr(k):
        a = field[:-k, :].ravel()
        b = field[k:, :].ravel()
        return float(np.corrcoef(a, b)[0, 1])
    c1, c2, c8 = lag_corr(1), lag_corr(2), lag_corr(8)
    assert c1 > 0.4, c1
    assert c1 > c2 > c8, (c1, c2, c8)
    assert abs(c8) < 0.25, c8


def test_seeded_reproducibility():
    from backend.spatial import simulate_gaussian_field
    import numpy as np

    a = simulate_gaussian_field(rows=10, cols=10, mean=1.0, std=0.5, range_cells=4.0, seed=42)
    b = simulate_gaussian_field(rows=10, cols=10, mean=1.0, std=0.5, range_cells=4.0, seed=42)
    assert np.array_equal(a, b)


def test_spatial_rejects_bad_input():
    from backend.spatial import simulate_gaussian_field
    import pytest as _pt

    with _pt.raises(ValueError, match="positive"):
        simulate_gaussian_field(rows=0, cols=10, mean=0.0, std=1.0, range_cells=5.0, seed=1)
    with _pt.raises(ValueError, match="range"):
        simulate_gaussian_field(rows=10, cols=10, mean=0.0, std=1.0, range_cells=0.0, seed=1)
    with _pt.raises(ValueError, match="std"):
        simulate_gaussian_field(rows=10, cols=10, mean=0.0, std=-1.0, range_cells=5.0, seed=1)
