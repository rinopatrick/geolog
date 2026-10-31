"""NPD LOT sanity anchor (TDD Red). LOT mud-equivalent must convert to a
physical Shmin-gradient band; the default assumption must lie near the
data median, not in another county.
"""

from __future__ import annotations

import pytest


def _load():
    import csv

    with open("test_data/npd_lot/lot_subset.csv") as handle:
        return list(csv.DictReader(handle))


def test_lot_gradients_are_physical():
    import numpy as np

    rows = _load()
    assert len(rows) >= 100
    emw = np.array([float(r["wlbLotMudDencity"]) for r in rows])
    grad_psi_ft = emw * 0.4335
    assert np.all(grad_psi_ft > 0.35) and np.all(grad_psi_ft < 1.1)
    assert 0.6 <= float(np.median(grad_psi_ft)) <= 0.9


def test_default_shmin_gradient_near_data_median():
    import numpy as np

    rows = _load()
    emw = np.array([float(r["wlbLotMudDencity"]) for r in rows])
    median_grad = float(np.median(emw)) * 0.4335
    assert abs(0.70 - median_grad) < 0.15


def test_lot_rejects_bad_rows():
    from backend.core_validation import sw_baseline  # placeholder import guard
    import pytest as _pt

    with _pt.raises(ValueError, match="empty"):
        sw_baseline([])

def test_lot_gradient_band_helper():
    from backend.core_validation import lot_gradient_band

    rows = _load()
    out = lot_gradient_band(rows)
    assert out["n"] >= 100
    assert out["p10_psi_ft"] < out["median_psi_ft"] < out["p90_psi_ft"]
    import pytest as _pt

    with _pt.raises(ValueError, match="at least 5"):
        lot_gradient_band([])
