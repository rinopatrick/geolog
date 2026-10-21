"""Core/SCAL CRUD, import, FZI flow units and saturation-height."""

from __future__ import annotations

import numpy as np
from fastapi.testclient import TestClient

from backend.main import app

client = TestClient(app)
I = {"X-User-Role": "interpreter"}

def _create_plug(wid, name, depth, phi, perm, **kw):
    body = {"plug_name": name, "depth_md": depth, "porosity": phi, "perm_air": perm}
    body.update(kw)
    r = client.post(f"/api/wells/{wid}/core/plugs", headers=I, json=body)
    assert r.status_code == 201, r.text
    return r.json()

def test_core_plug_crud_and_measurements(make_well):
    wid = make_well("CORE", {"DEPT": [1000.0, 1001.0], "GR": [10.0, 20.0]})
    rt = client.post(f"/api/wells/{wid}/core/rock-types", headers=I, json={"name": "Sand A"})
    assert rt.status_code == 201, rt.text
    rid = rt.json()["id"]
    plug = _create_plug(wid, "P1", 1000.5, 0.22, 150.0, rock_type_id=rid, formation="A")
    pid = plug["id"]
    assert plug["dataset_id"]
    assert plug["rock_type_id"] == rid

    r = client.post(f"/api/wells/{wid}/core/plugs/{pid}/measurements", headers=I,
                    json={"measurement_type": "porosity", "value": 0.21, "unit": "v/v"})
    assert r.status_code == 201, r.text
    r = client.post(f"/api/wells/{wid}/core/plugs/{pid}/capillary-pressure", headers=I,
                    json={"points": [[10, 0.95], [20, 0.8], [40, 0.55], [80, 0.3]]})
    assert r.status_code == 201, r.text
    r = client.post(f"/api/wells/{wid}/core/plugs/{pid}/photos", headers=I,
                    json={"file_path": "core/1/P1.jpg", "caption": "P1"})
    assert r.status_code == 201, r.text

    detail = client.get(f"/api/wells/{wid}/core/plugs/{pid}")
    assert detail.status_code == 200
    body = detail.json()
    assert body["measurements"] == 1
    assert body["pc_rows"][0]["points"][0] == [10.0, 0.95]

    datasets = client.get(f"/api/wells/{wid}/core/datasets").json()
    assert datasets and datasets[0]["status"] == "draft"
    did = datasets[0]["id"]
    assert client.post(f"/api/wells/{wid}/core/datasets/{did}/approve", headers=I).status_code == 200
    lock = client.put(f"/api/wells/{wid}/core/plugs/{pid}", headers=I, json={"porosity": 0.3})
    assert lock.status_code == 423

def test_core_csv_import_and_conflict(make_well):
    wid = make_well("CORE-CSV", {"DEPT": [1000.0], "GR": [10.0]})
    csv_data = "plug_name,depth_md,porosity,perm_air,formation\nP1,1000.5,0.22,150,A\nP2,1001.0,0.18,80,B\n"
    files = {"file": ("core.csv", csv_data.encode(), "text/csv")}
    r = client.post(f"/api/wells/{wid}/core/import?dry_run=true", headers=I, files=files)
    assert r.status_code == 200, r.text
    assert r.json()["would_import"] == 2
    assert client.get(f"/api/wells/{wid}/core/plugs").json() == []

    files = {"file": ("core.csv", csv_data.encode(), "text/csv")}
    r = client.post(f"/api/wells/{wid}/core/import", headers=I, files=files)
    assert r.status_code == 200, r.text
    assert r.json()["imported"] == 2
    assert len(client.get(f"/api/wells/{wid}/core/plugs").json()) == 2

    files = {"file": ("core.csv", csv_data.encode(), "text/csv")}
    r = client.post(f"/api/wells/{wid}/core/import", headers=I, files=files)
    assert r.status_code == 200
    assert len(r.json()["conflicts"]) == 2

def test_flow_units_cluster(make_well):
    wid = make_well("FZI", {"DEPT": [1000.0], "GR": [10.0]})
    for i in range(6):
        _create_plug(wid, f"P{i}", 1000 + i, 0.10 + i * 0.03, 5.0 * (i + 1))
    r = client.post(f"/api/wells/{wid}/core/flow-units/cluster", headers=I, json={"k": 3})
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["k"] == 3
    units = client.get(f"/api/wells/{wid}/core/flow-units").json()
    assert len(units) == 3
    assert units[0]["fzi_min"] <= units[0]["fzi_max"]

def test_saturation_height_fit_and_apply(make_well):
    wid = make_well("SH", {
        "DEPT": np.array([1000.0, 1001.0, 1002.0]),
        "PHIE": np.array([0.20, 0.18, 0.22]),
        "PERM": np.array([100.0, 80.0, 120.0]),
    })
    plug = _create_plug(wid, "P1", 1001.0, 0.20, 100.0)
    pid = plug["id"]
    r = client.post(f"/api/wells/{wid}/core/plugs/{pid}/capillary-pressure", headers=I,
                    json={"points": [[5, 0.98], [10, 0.9], [20, 0.75], [40, 0.5], [80, 0.3]]})
    assert r.status_code == 201
    contact = client.post(f"/api/wells/{wid}/core/contacts", headers=I,
                          json={"contact_type": "FWL", "depth": 1050.0})
    assert contact.status_code == 201
    cid = contact.json()["id"]
    fit = client.post(f"/api/wells/{wid}/core/saturation-height/fit", headers=I,
                      json={"model_type": "j_function", "contact_id": cid})
    assert fit.status_code == 200, fit.text
    model = fit.json()
    assert model["r2"] is not None
    apply = client.post(f"/api/wells/{wid}/core/saturation-height/apply", headers=I,
                        json={"model_id": model["id"]})
    assert apply.status_code == 200, apply.text
    assert len(apply.json()["sw"]) == 3
