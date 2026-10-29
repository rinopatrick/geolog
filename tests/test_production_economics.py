"""Probabilistic production economics endpoint."""

from __future__ import annotations

import numpy as np
from fastapi.testclient import TestClient

from backend.main import SessionLocal, app
from backend.models import ProductionData

client = TestClient(app)
INTERPRETER = {"X-User-Role": "interpreter"}
VIEWER = {"X-User-Role": "viewer"}


def _well_with_production(make_well) -> int:
    depth = np.arange(1000.0, 1010.0, 1.0)
    wid = make_well("ECON-WELL", {"DEPT": depth, "GR": np.full(len(depth), 50.0)})
    rates = [1000, 850, 720, 610, 520, 450, 380, 320, 270, 230]
    for i, rate in enumerate(rates):
        r = client.post(
            f"/api/wells/{wid}/production",
            json={"date": f"2026-{i + 1:02d}-01", "oil_rate": rate},
            headers=INTERPRETER,
        )
        assert r.status_code == 201, r.text
    return wid


def test_probabilistic_economics_ordering_and_determinism(make_well):
    wid = _well_with_production(make_well)
    payload = {
        "oil_price": 72.0,
        "opex_per_bbl": 11.0,
        "capex": 2_000_000,
        "discount_rate": 0.10,
        "royalty_rate": 0.125,
        "working_interest": 1.0,
        "tax_rate": 0.25,
        "economic_limit": 10.0,
        "years": 20,
        "iterations": 200,
        "seed": 7,
        "qi_uncertainty_pct": 20,
        "di_uncertainty_pct": 25,
    }
    first = client.post(f"/api/wells/{wid}/production/economics", json=payload, headers=INTERPRETER)
    assert first.status_code == 200, first.text
    body = first.json()
    assert body["base"]["eur_bbl"] > 0
    assert np.isfinite(body["base"]["npv"])
    assert body["forecast"]
    eur = body["probabilistic"]["eur_bbl"]
    assert eur["p90"] <= eur["p50"] <= eur["p10"]
    assert body["probabilistic"]["iterations"] == 200

    second = client.post(f"/api/wells/{wid}/production/economics", json=payload, headers=INTERPRETER)
    assert second.status_code == 200
    assert second.json()["probabilistic"]["eur_bbl"]["p50"] == eur["p50"]


def test_economics_requires_production(make_well):
    wid = make_well("ECON-EMPTY", {"DEPT": np.array([1000.0, 1001.0]), "GR": np.array([40.0, 41.0])})
    db = SessionLocal()
    try:
        db.query(ProductionData).filter(ProductionData.well_id == wid).delete()
        db.commit()
    finally:
        db.close()
    r = client.post(f"/api/wells/{wid}/production/economics", json={}, headers=INTERPRETER)
    assert r.status_code == 400, r.text


def test_economics_is_interpreter_only(make_well):
    wid = _well_with_production(make_well)
    r = client.post(f"/api/wells/{wid}/production/economics", json={}, headers=VIEWER)
    assert r.status_code == 403
