"""Permeability save persists per-model curves as readable CurveData.

Default stays stateless. With save=true, each selected model is stored under
mnemonic PERM_<MODEL> on the same log run, idempotent by overwrite.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from backend.main import SessionLocal, app
from backend.models import CurveData

client = TestClient(app)
HEADERS = {"X-User-Role": "interpreter"}


def _clean_sand():
    return {
        "DEPT": [1000.0, 1000.5],
        "GR": [15.0, 16.0],
        "RT": [20.0, 19.0],
        "NPHI": [0.21, 0.20],
        "RHOB": [2.30, 2.31],
        "PHIE": [0.21, 0.20],
        "SW": [0.35, 0.36],
    }


def _count_curves(lr_id: int) -> int:
    db = SessionLocal()
    try:
        return db.query(CurveData).filter(CurveData.log_run_id == lr_id).count()
    finally:
        db.close()


def test_permeability_default_is_stateless(make_well):
    wid = make_well("perm-stateless", _clean_sand())
    r = client.post(f"/api/wells/{wid}/permeability",
                    json={"model": "coates"}, headers=HEADERS)
    assert r.status_code == 200, r.text
    assert "saved" not in r.json()
    assert _count_curves(r.json()["log_run_id"]) == 7


def test_permeability_save_persists_model_curve(make_well):
    wid = make_well("perm-save", _clean_sand())
    r = client.post(f"/api/wells/{wid}/permeability",
                    json={"model": "coates", "save": True}, headers=HEADERS)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["saved"]["log_run_id"] == body["log_run_id"]
    assert body["saved"]["mnemonics"] == ["PERM_COATES"]
    lr_id = body["log_run_id"]
    curves = client.get(f"/api/log-runs/{lr_id}/curves", headers=HEADERS).json()
    names = {c["mnemonic"] for c in curves} if isinstance(curves, list) \
        else set(curves.keys())
    assert "PERM_COATES" in names


def test_permeability_save_is_idempotent(make_well):
    wid = make_well("perm-idem", _clean_sand())
    payload = {"model": "all", "save": True}
    assert client.post(f"/api/wells/{wid}/permeability", json=payload,
                       headers=HEADERS).status_code == 200
    r = client.post(f"/api/wells/{wid}/permeability", json=payload,
                    headers=HEADERS)
    assert r.status_code == 200
    assert set(r.json()["saved"]["mnemonics"]) == {"PERM_COATES", "PERM_TIMUR"}
    db = SessionLocal()
    try:
        for mnemonic in ("PERM_COATES", "PERM_TIMUR"):
            n = db.query(CurveData).filter(
                CurveData.log_run_id == r.json()["log_run_id"],
                CurveData.mnemonic == mnemonic).count()
            assert n == 1, mnemonic
    finally:
        db.close()
