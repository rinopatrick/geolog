"""A1: per-cell P10/P50/P90 maps + hydrocarbon probability (TDD Red).

Production-grade bar: seeded reproducibility, analytic column check,
monotonic P10<=P50<=P90 everywhere, probability in [0,1].
"""

from __future__ import annotations

import numpy as np
import pytest


def _flat_top():
    return [[2000.0, 2000.0], [2000.0, 2000.0]]


def test_cell_maps_reproducible_with_seed():
    from backend.cell_maps import cell_posterior_maps

    a = cell_posterior_maps(
        _flat_top(), contact_depth_m=2100, inline_spacing_m=25, crossline_spacing_m=25,
        porosity=0.2, water_saturation=0.3, net_to_gross=0.8,
        iterations=500, seed=7,
    )
    b = cell_posterior_maps(
        _flat_top(), contact_depth_m=2100, inline_spacing_m=25, crossline_spacing_m=25,
        porosity=0.2, water_saturation=0.3, net_to_gross=0.8,
        iterations=500, seed=7,
    )
    assert a["p50_column_m"] == b["p50_column_m"]
    assert a["hydrocarbon_probability"] == b["hydrocarbon_probability"]


def test_cell_maps_monotonic_and_bounded():
    from backend.cell_maps import cell_posterior_maps

    out = cell_posterior_maps(
        _flat_top(), contact_depth_m=2100, inline_spacing_m=25, crossline_spacing_m=25,
        porosity={"low": 0.12, "mode": 0.2, "high": 0.28},
        water_saturation=0.3, net_to_gross=0.8,
        iterations=500, seed=7,
    )
    p10 = np.asarray(out["p10_column_m"])
    p50 = np.asarray(out["p50_column_m"])
    p90 = np.asarray(out["p90_column_m"])
    prob = np.asarray(out["hydrocarbon_probability"])
    assert np.all(p10 <= p50) and np.all(p50 <= p90)
    assert np.all(prob >= 0.0) and np.all(prob <= 1.0)
    # Flat 100 m column, deterministic props: P50 column ~100*0.8*0.2*0.7
    assert p50[0][0] == pytest.approx(100 * 0.8 * 0.2 * 0.7, rel=0.15)


def test_cell_maps_contact_above_surface_gives_zero_probability():
    from backend.cell_maps import cell_posterior_maps

    out = cell_posterior_maps(
        _flat_top(), contact_depth_m=1900, inline_spacing_m=25, crossline_spacing_m=25,
        porosity=0.2, water_saturation=0.3, net_to_gross=0.8,
        iterations=200, seed=7,
    )
    assert np.asarray(out["hydrocarbon_probability"]).max() == 0.0


def test_cell_maps_rejects_bad_input():
    from backend.cell_maps import cell_posterior_maps

    with pytest.raises(ValueError, match="iterations"):
        cell_posterior_maps(_flat_top(), 2100, 25, 25, 0.2, 0.3, iterations=5, seed=1)
    with pytest.raises(ValueError, match="porosity"):
        cell_posterior_maps(_flat_top(), 2100, 25, 25, {"low": 0.9, "mode": 0.1, "high": 0.2}, 0.3, iterations=200, seed=1)

def test_prospect_maps_endpoint_rejects_and_accepts():
    from fastapi.testclient import TestClient
    from backend.main import SessionLocal, app
    from backend.models import Project
    from tests.test_prospects import _depth_surface

    tclient = TestClient(app)
    admin = {"X-User-Role": "admin"}
    db = SessionLocal()
    try:
        pid = int(db.query(Project.id).order_by(Project.id.asc()).first()[0])
    finally:
        db.close()
    _, surface = _depth_surface(pid)
    bad = tclient.post(
        f"/api/projects/{pid}/prospect-maps",
        json={"surface_id": surface["id"]},
        headers=admin,
    )
    assert bad.status_code == 400
    good = tclient.post(
        f"/api/projects/{pid}/prospect-maps",
        json={
            "surface_id": surface["id"], "contact_depth_m": 1000,
            "porosity": 0.2, "water_saturation": 0.3,
            "net_to_gross": 0.8, "iterations": 200, "seed": 7,
        },
        headers=admin,
    )
    assert good.status_code == 200, good.text
    data = good.json()
    assert data["surface_id"] == surface["id"]
    assert len(data["p50_column_m"]) == len(data["hydrocarbon_probability"])
    assert min(min(r) for r in data["p10_column_m"]) <= max(max(r) for r in data["p90_column_m"])

def test_cell_maps_rejects_oversize_workload():
    from backend.cell_maps import cell_posterior_maps
    big = [[2000.0] * 200 for _ in range(200)]
    with pytest.raises(ValueError, match="workload too large"):
        cell_posterior_maps(big, 2100, 25, 25, 0.2, 0.3, iterations=1000, seed=7)
    ok = cell_posterior_maps([[2000.0] * 40 for _ in range(40)], 2100, 25, 25, 0.2, 0.3, iterations=1000, seed=7)
    assert ok["rows"] == 40

def test_lateral_mode_neighbors_move_together():
    from backend.cell_maps import cell_posterior_maps
    import numpy as np
    grid = [[2000.0] * 16 for _ in range(16)]
    kw = dict(contact_depth_m=2100, inline_spacing_m=25, crossline_spacing_m=25,
              porosity=0.2, water_saturation=0.3, net_to_gross={"low": 0.4, "mode": 0.8, "high": 1.0},
              iterations=300, seed=7)
    ind = cell_posterior_maps(grid, correlation="none", **kw)
    lat = cell_posterior_maps(grid, correlation="lateral", correlation_range_cells=6.0, **kw)
    assert lat["inputs"]["correlation"] == "lateral"
    # Lateral NTG moves together: the mean column map carries spatial
    # structure (independent mode is perfectly flat on a flat gross grid),
    # and neighbours correlate positively.
    a = np.asarray(lat["mean_column_m"])
    assert float(np.std(a)) > 0
    horiz = float(np.corrcoef(a[:, :-1].ravel(), a[:, 1:].ravel())[0, 1])
    assert horiz > 0.3

def test_cell_maps_rejects_bad_correlation():
    from backend.cell_maps import cell_posterior_maps
    import pytest as _pt
    with _pt.raises(ValueError, match="correlation"):
        cell_posterior_maps([[2000.0]], 2100, 25, 25, 0.2, 0.3, correlation="kriging", seed=1)
    with _pt.raises(ValueError, match="correlation_range_cells"):
        cell_posterior_maps([[2000.0]], 2100, 25, 25, 0.2, 0.3, correlation="lateral", correlation_range_cells=0.0, seed=1)
