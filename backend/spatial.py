"""Stationary Gaussian random fields for laterally correlated simulation.

Circulant-embedding FFT synthesis with an isotropic exponential covariance:
exact up to the periodic embedding, fast enough for screening grids.
The field is standardised to the requested mean/std so the correlation
structure (range) is decoupled from the marginal scale.
"""

from __future__ import annotations

import numpy as np


def _embedding_size(n: int) -> int:
    size = 1
    while size < 2 * n:
        size *= 2
    return size


def simulate_gaussian_field(
    rows: int,
    cols: int,
    mean: float = 0.0,
    std: float = 1.0,
    range_cells: float = 5.0,
    seed: int | None = None,
) -> np.ndarray:
    if not isinstance(rows, int) or isinstance(rows, bool) or rows <= 0:
        raise ValueError("rows must be a positive integer")
    if not isinstance(cols, int) or isinstance(cols, bool) or cols <= 0:
        raise ValueError("cols must be a positive integer")
    if not np.isfinite(std) or std <= 0:
        raise ValueError("std must be positive finite")
    if not np.isfinite(range_cells) or range_cells <= 0:
        raise ValueError("range_cells must be positive finite")
    if not np.isfinite(mean):
        raise ValueError("mean must be finite")

    rng = np.random.default_rng(seed)
    size_r, size_c = _embedding_size(rows), _embedding_size(cols)
    # Anisotropic-free: radial lag grid in cell units.
    ii, jj = np.meshgrid(np.arange(size_r), np.arange(size_c), indexing="ij")
    lag = np.sqrt(np.minimum(ii, size_r - ii) ** 2 + np.minimum(jj, size_c - jj) ** 2)
    # Exponential covariance, practical range ~ 3 * range_cells.
    cov = np.exp(-3.0 * lag / float(range_cells))
    spectrum = np.real(np.fft.fft2(cov))
    spectrum = np.clip(spectrum, 0.0, None)
    noise = rng.standard_normal((size_r, size_c))
    field = np.real(np.fft.ifft2(np.fft.fft2(noise) * np.sqrt(spectrum)))
    field = field[:rows, :cols]
    flat = field.ravel()
    sd = float(np.std(flat))
    if sd < 1e-12:
        return np.full((rows, cols), float(mean))
    field = (field - float(np.mean(flat))) / sd * float(std) + float(mean)
    return field
