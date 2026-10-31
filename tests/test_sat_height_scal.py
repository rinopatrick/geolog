"""SCAL Pc validation (TDD Red). Berea/Viking must fit Brooks-Corey R2>=0.8;
Tuscaloosa bimodal must score R2<0.5 (model knows its limits).
"""

from __future__ import annotations

import pytest


def _load(name: str):
    import csv
    import numpy as np

    with open(f"test_data/scal_pc/{name}_sw_pc.csv") as handle:
        rows = list(csv.DictReader(handle))
    pc = np.array([float(r["pc_psi"]) for r in rows])
    sw = np.array([float(r["sw_frac"]) for r in rows])
    return pc, sw


def test_brooks_corey_fits_textbook_curves():
    from backend.saturation_height import fit_model

    for name in ("berea_sandstone", "viking_sandstone"):
        pc, sw = _load(name)
        out = fit_model("brooks_corey", pc, sw)
        assert out["r2"] >= 0.8, name
        assert out["parameters"]["pe"] > 0
        assert out["parameters"]["lambda"] > 0


def test_bimodal_curve_scores_below_floor():
    from backend.saturation_height import fit_model

    pc, sw = _load("tuscaloosa_sandstone")
    out = fit_model("brooks_corey", pc, sw)
    assert out["r2"] < 0.5


def test_scal_fixtures_have_minimum_size():
    import csv

    for name in ("berea_sandstone", "viking_sandstone", "tuscaloosa_sandstone"):
        with open(f"test_data/scal_pc/{name}_sw_pc.csv") as handle:
            rows = list(csv.DictReader(handle))
        assert len(rows) >= 40, name
