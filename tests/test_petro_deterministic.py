"""Deterministic solver validation vs Volve F-1 reference (TDD Red).

Bar: same inputs as the Volve professional interpretation must reproduce
VSH/PHIE/SW within stated tolerances. Documents exactly where the
deterministic chain matches and where it diverges.
"""

from __future__ import annotations

import pytest


def _load():
    import csv
    import numpy as np

    with open("test_data/volve_f1/input.csv") as handle:
        inp = list(csv.DictReader(handle))
    with open("test_data/volve_f1/reference_output.csv") as handle:
        ref = list(csv.DictReader(handle))
    return inp, ref


def test_vclay_igr_matches_reference_formula():
    from backend.petro_deterministic import vclay

    inp, ref = _load()
    import numpy as np

    gr = np.array([float(r["GR"]) for r in inp])
    vsh_ref = np.array([float(r["VSH"]) for r in ref])
    # Reference fit recovers gr_clean=15, gr_shale=135 exactly (linear R2=1).
    # The Volve report header cites (GR-15)/235, but the delivered curves
    # match (GR-15)/120 — pinned here so a fixture swap cannot slip by.
    vsh = vclay(gr, gr_clean=15.0, gr_shale=135.0, method="igr")
    # Tolerance is CSV rounding (reference stored at ~4 decimals), not model error.
    assert float(np.mean(np.abs(vsh - vsh_ref))) < 1e-3


def test_phie_blend_matches_reference_trend():
    from backend.petro_deterministic import porosity_blend

    inp, ref = _load()
    import numpy as np

    nphi = np.array([float(r["NPHI"]) for r in inp])
    rhob = np.array([float(r["RHOB"]) for r in inp])
    vsh = np.array([float(r["VSH"]) for r in ref])
    phif = np.array([float(r["PHIF"]) for r in ref])
    phi_raw = porosity_blend(nphi, rhob, vsh, rho_ma=2.65, rho_f=1.0, phi_sh=0.07)
    # Same blend the calibration harness uses: must track reference PHIF.
    resid = np.abs(phi_raw - phif)
    assert float(np.mean(resid)) < 0.02
    assert float(np.max(resid)) < 0.08


def test_archie_sw_tracks_reference():
    from backend.petro_deterministic import porosity_blend, water_saturation

    inp, ref = _load()
    import numpy as np
    from scipy.stats import spearmanr

    nphi = np.array([float(r["NPHI"]) for r in inp])
    rhob = np.array([float(r["RHOB"]) for r in inp])
    rt = np.array([float(r["RT"]) for r in inp])
    vsh = np.array([float(r["VSH"]) for r in ref])
    sw_ref = np.array([float(r["SW"]) for r in ref])
    phi = porosity_blend(nphi, rhob, vsh, rho_ma=2.65, rho_f=1.0, phi_sh=0.07)
    # The interpreter's Archie parameters are not in the delivered curves,
    # so absolute Sw is not reproducible. What IS pinned: with a formation
    # Rw that unsaturates the interval, rank order must track the reference.
    # rw=0.1 (default) saturates everything to 1.0 — documented, not hidden.
    sw = water_saturation("archie", rt, phi, vsh, rw=0.02)
    mask = np.isfinite(sw) & np.isfinite(sw_ref) & (phi > 0.05)
    rho = float(spearmanr(sw[mask], sw_ref[mask]).statistic)
    assert rho > 0.7
    assert float(np.mean(np.abs(sw[mask] - sw_ref[mask]))) < 0.15


def test_deterministic_rejects_bad_input():
    from backend.petro_deterministic import porosity_blend, vclay, water_saturation
    import numpy as np

    with pytest.raises(ValueError, match="gr_shale"):
        vclay(np.array([50.0]), gr_clean=250.0, gr_shale=15.0, method="igr")
    with pytest.raises(ValueError, match="length"):
        porosity_blend(np.array([0.2]), np.array([2.4, 2.5]), np.array([0.1]))
    with pytest.raises(ValueError, match="model"):
        water_saturation("unknown_model", np.array([10.0]), np.array([0.2]), np.array([0.1]))
