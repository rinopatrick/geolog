"""Geomechanics screening tests."""

from __future__ import annotations

import numpy as np
from fastapi.testclient import TestClient

from backend.main import app

client = TestClient(app)
I = {"X-User-Role": "interpreter"}

def _well(make_well):
    return make_well("GEO", {
        "DEPT": np.arange(1000.0, 1011.0, 1.0),
        "GR": np.full(11, 80.0),
        "RHOB": np.full(11, 2.35),
        "DT": np.full(11, 70.0),
        "DTS": np.full(11, 120.0),
    })

def test_geomechanics_compute_and_model_lifecycle(make_well):
    wid = _well(make_well)
    body = {
        "params": {"shmax_azimuth": 30.0, "mud_weight": 9.0},
        "calibration": {
            "pp": [[1000, 433], [1010, 437]],
            "shmin": [[1000, 700], [1010, 707]],
            "shmax": [[1000, 1100], [1010, 1110]],
            "shmax_azimuth": 30.0,
        },
    }
    r = client.post(f"/api/wells/{wid}/geomechanics/models", headers=I, json=body)
    assert r.status_code == 201, r.text
    model = r.json()
    mid = model["id"]
    compute = client.post(f"/api/wells/{wid}/geomechanics/compute", headers=I,
                          json={"model_id": mid})
    assert compute.status_code == 200, compute.text
    data = compute.json()
    assert data["summary"]["points"] == 11
    assert data["provenance"]["PP"] == "calibrated"
    assert data["provenance"]["SHMAX"] == "calibrated"
    assert len(data["curves"]["E"]) == 11
    assert all(v is not None and v > 0 for v in data["curves"]["E"])
    assert data["curves"]["SV"][-1] > data["curves"]["SV"][0]
    assert data["summary"]["mw_min"] > 0

    cal = client.post(f"/api/wells/{wid}/geomechanics/breakout-calibration", headers=I,
                      json={"model_id": mid, "breakouts": [
                          {"depth": 1004.0, "width_deg": 30, "mud_weight": 9.2},
                          {"depth": 1008.0, "width_deg": 24, "mud_weight": 9.2},
                      ]})
    assert cal.status_code == 200, cal.text
    assert len(cal.json()["points"]) == 2
    assert cal.json()["average_shmax"] > 0

    approve = client.post(f"/api/wells/{wid}/geomechanics/models/{mid}/approve", headers=I)
    assert approve.status_code == 200
    locked = client.put(f"/api/wells/{wid}/geomechanics/models/{mid}", headers=I,
                        json={"params": {"mud_weight": 10}})
    assert locked.status_code == 423
    reports = client.get(f"/api/wells/{wid}/geomechanics/runs")
    assert reports.status_code == 200 and len(reports.json()) == 1

def test_geomechanics_report_csv_and_missing_curves(make_well):
    wid = _well(make_well)
    create = client.post(f"/api/wells/{wid}/geomechanics/models", headers=I,
                         json={"params": {"pore_pressure_method": "hydrostatic"}})
    mid = create.json()["id"]
    csvr = client.get(f"/api/wells/{wid}/geomechanics/report?model_id={mid}&format=csv")
    assert csvr.status_code == 200, csvr.text
    assert "DEPTH,TVD,SV,PP" in csvr.text
    assert len(csvr.text.strip().splitlines()) == 12

    empty = make_well("GEO-EMPTY", {"DEPT": [1000.0, 1001.0], "GR": [10.0, 20.0]})
    bad = client.post(f"/api/wells/{empty}/geomechanics/compute", headers=I, json={})
    assert bad.status_code == 400


def test_vertical_kirsch_limits():
    import numpy as np
    from backend.geomechanics import _borehole_hoop, _far_field_tensor

    tensor = _far_field_tensor(np.array([100.0]), np.array([50.0]), np.array([80.0]), 0.0)
    base_max, base_min, _ = _borehole_hoop(tensor, 0.0, 0.0)
    assert np.isclose(base_max[0], 3 * 100 - 50, atol=1e-6)
    assert np.isclose(base_min[0], 3 * 50 - 100, atol=1e-6)
