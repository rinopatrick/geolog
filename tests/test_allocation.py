"""A2: production allocation across compartments (TDD Red).

Production-grade bar: mass conservation (sum == total), non-negative shares,
seeded tie-breaks, transmissibility-weighted split, zero-kh compartment gets zero.
"""

from __future__ import annotations

import pytest


def test_allocation_conserves_mass():
    from backend.allocation import allocate_production

    out = allocate_production(
        total_rate_bpd=1000.0,
        compartments=[
            {"id": 1, "kh_md_m": 500.0, "grv_m3": 1e6},
            {"id": 2, "kh_md_m": 300.0, "grv_m3": 2e6},
            {"id": 3, "kh_md_m": 200.0, "grv_m3": 3e6},
        ],
        seed=7,
    )
    rates = [c["rate_bpd"] for c in out["allocations"]]
    assert sum(rates) == pytest.approx(1000.0)
    assert all(r >= 0 for r in rates)
    # kh-weighted: comps get 500/300/200 shares
    assert out["allocations"][0]["rate_bpd"] == pytest.approx(500.0)
    assert out["allocations"][1]["rate_bpd"] == pytest.approx(300.0)
    assert out["allocations"][2]["rate_bpd"] == pytest.approx(200.0)


def test_allocation_zero_kh_gets_zero():
    from backend.allocation import allocate_production

    out = allocate_production(
        total_rate_bpd=1000.0,
        compartments=[
            {"id": 1, "kh_md_m": 100.0, "grv_m3": 1e6},
            {"id": 2, "kh_md_m": 0.0, "grv_m3": 9e6},
        ],
        seed=7,
    )
    by_id = {c["id"]: c["rate_bpd"] for c in out["allocations"]}
    assert by_id[2] == 0.0
    assert by_id[1] == pytest.approx(1000.0)


def test_allocation_rejects_bad_input():
    from backend.allocation import allocate_production

    with pytest.raises(ValueError, match="total_rate"):
        allocate_production(-100.0, [{"id": 1, "kh_md_m": 1.0}], seed=1)
    with pytest.raises(ValueError, match="compartments"):
        allocate_production(100.0, [], seed=1)
    with pytest.raises(ValueError, match="transmissibility"):
        allocate_production(100.0, [{"id": 1, "kh_md_m": 0.0}], seed=1)

def test_allocation_endpoint():
    from fastapi.testclient import TestClient
    from backend.main import SessionLocal, app
    from backend.models import Project
    tclient = TestClient(app)
    admin = {"X-User-Role": "admin"}
    db = SessionLocal()
    try:
        pid = int(db.query(Project.id).order_by(Project.id.asc()).first()[0])
    finally:
        db.close()
    r = tclient.post(
        f"/api/projects/{pid}/production-allocation",
        json={"total_rate_bpd": 1000.0,
              "compartments": [{"id": 1, "kh_md_m": 500.0}, {"id": 2, "kh_md_m": 500.0}],
              "seed": 7},
        headers=admin,
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["allocated_bpd"] == 1000.0
    assert data["method"] == "kh_proportional"
    bad = tclient.post(
        f"/api/projects/{pid}/production-allocation",
        json={"total_rate_bpd": -5.0, "compartments": [{"id": 1, "kh_md_m": 1.0}]},
        headers=admin,
    )
    assert bad.status_code == 400
