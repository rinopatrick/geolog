"""Winland R35 / FZI rock typing endpoint."""

from __future__ import annotations

import numpy as np
from fastapi.testclient import TestClient

from backend.main import SessionLocal, app
from backend.models import CoreDataset, CorePlug
from backend.rock_typing import classify_plug

client = TestClient(app)
INTERPRETER = {"X-User-Role": "interpreter"}


def _well_with_plugs(make_well, name="ROCKTYPE-WELL"):
    depth = np.arange(1000.0, 1010.0, 1.0)
    wid = make_well(name, {"DEPT": depth, "GR": np.full(len(depth), 45.0)})
    db = SessionLocal()
    try:
        ds = CoreDataset(well_id=wid, version=1, status="draft", source="test")
        db.add(ds)
        db.flush()
        samples = [
            ("P1", 0.25, 1000.0),
            ("P2", 0.10, 10.0),
            ("P3", 0.08, 1.0),
            ("P4", 0.05, 0.1),
        ]
        for i, (plug_name, phi, perm) in enumerate(samples):
            db.add(CorePlug(dataset_id=ds.id, well_id=wid, plug_name=plug_name, depth_md=1000.0 + i, porosity=phi, perm_air=perm))
        db.commit()
    finally:
        db.close()
    return wid


def test_classify_plug_thresholds():
    assert classify_plug(0.25, 1000.0)["winland_class"] == "macroport"
    assert classify_plug(0.10, 10.0)["winland_class"] == "mesoport"
    assert classify_plug(0.08, 1.0)["winland_class"] == "microport"
    assert classify_plug(0.05, 0.1)["winland_class"] == "nanoport"
    assert classify_plug(0.0, 10.0) is None


def test_classify_endpoint_creates_and_assigns_rock_types(make_well):
    wid = _well_with_plugs(make_well)
    r = client.post(f"/api/wells/{wid}/core/rock-types/classify", json={"assign": True}, headers=INTERPRETER)
    assert r.status_code == 200, r.text
    body = r.json()
    names = {item["class"]: item["count"] for item in body["classes"]}
    assert names == {"macroport": 1, "mesoport": 1, "microport": 1, "nanoport": 1}
    assert len(body["plugs"]) == 4
    assert all(item["r35"] > 0 for item in body["plugs"])

    db = SessionLocal()
    try:
        plugs = db.query(CorePlug).filter(CorePlug.well_id == wid).all()
        assert all(p.rock_type_id is not None for p in plugs)
    finally:
        db.close()


def test_classify_endpoint_preview_does_not_assign(make_well):
    wid = _well_with_plugs(make_well, "ROCKTYPE-PREVIEW")
    r = client.post(f"/api/wells/{wid}/core/rock-types/classify", json={"assign": False}, headers=INTERPRETER)
    assert r.status_code == 200, r.text
    db = SessionLocal()
    try:
        plugs = db.query(CorePlug).filter(CorePlug.well_id == wid).all()
        assert all(p.rock_type_id is None for p in plugs)
    finally:
        db.close()


def test_classify_requires_plugs(make_well):
    depth = np.arange(1000.0, 1002.0, 1.0)
    wid = make_well("ROCKTYPE-EMPTY", {"DEPT": depth, "GR": np.full(len(depth), 40.0)})
    r = client.post(f"/api/wells/{wid}/core/rock-types/classify", json={}, headers=INTERPRETER)
    assert r.status_code == 400
