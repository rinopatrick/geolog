"""Broader coverage for the wells router CRUD and light compute paths."""

from __future__ import annotations

import numpy as np
from fastapi.testclient import TestClient

from backend.main import app
from backend.models import Well

client = TestClient(app)
INTERPRETER = {"X-User-Role": "interpreter"}
VIEWER = {"X-User-Role": "viewer"}


def _well(make_well, name: str = "CRUD-WELL") -> int:
    depth = np.arange(1000.0, 1020.0, 1.0)
    return make_well(
        name,
        {
            "DEPT": depth,
            "GR": np.linspace(20.0, 90.0, len(depth)),
            "RHOB": np.full(len(depth), 2.35),
            "NPHI": np.full(len(depth), 0.22),
            "RT": np.full(len(depth), 10.0),
        },
    )


def test_well_get_update_and_list(make_well):
    wid = _well(make_well, "CRUD-ONE")
    got = client.get(f"/api/wells/{wid}", headers=VIEWER)
    assert got.status_code == 200
    assert got.json()["id"] == wid
    assert got.json()["log_runs"]

    updated = client.put(
        f"/api/wells/{wid}",
        json={"name": "CRUD-ONE-RENAMED", "operator": "ACME"},
        headers=INTERPRETER,
    )
    assert updated.status_code == 200, updated.text
    assert updated.json()["name"] == "CRUD-ONE-RENAMED"

    listed = client.get("/api/wells", headers=VIEWER)
    assert listed.status_code == 200
    assert wid in {w["id"] for w in listed.json()}
    assert client.get("/api/wells/999999", headers=VIEWER).status_code == 404


def test_tops_and_zones_crud(make_well):
    wid = _well(make_well, "TOPS-ZONES")
    top = client.post(
        f"/api/wells/{wid}/tops",
        json={"formation_name": "Top X", "depth": 1005.0, "color": "#123456"},
        headers=INTERPRETER,
    )
    assert top.status_code == 201, top.text
    assert client.get(f"/api/wells/{wid}/tops", headers=VIEWER).json()[0]["formation_name"] == "Top X"

    zones = client.post(
        f"/api/wells/{wid}/zones",
        json={"zones": [{"name": "Z1", "top": 1001, "bottom": 1008}, {"name": "bad", "top": 9, "bottom": 1}]},
        headers=INTERPRETER,
    )
    assert zones.status_code == 201, zones.text
    listed = client.get(f"/api/wells/{wid}/zones", headers=VIEWER).json()
    assert len(listed) == 1
    assert listed[0]["name"] == "Z1"


def test_operational_data_crud(make_well):
    wid = _well(make_well, "OPS-DATA")
    ann = client.post(
        f"/api/wells/{wid}/annotations",
        json={"depth": 1002.0, "text": "note"},
        headers=INTERPRETER,
    )
    assert ann.status_code == 201, ann.text

    dst = client.post(
        f"/api/wells/{wid}/dst",
        json={"top_depth": 1001.0, "bottom_depth": 1003.0},
        headers=INTERPRETER,
    )
    assert dst.status_code == 201, dst.text

    rft = client.post(
        f"/api/wells/{wid}/rft",
        json={"depth": 1002.0, "pressure": 3200.0},
        headers=INTERPRETER,
    )
    assert rft.status_code == 201, rft.text

    completion = client.post(
        f"/api/wells/{wid}/completion",
        json={"component_type": "casing", "depth_top": 1000.0, "depth_base": 1005.0},
        headers=INTERPRETER,
    )
    assert completion.status_code == 201, completion.text

    production = client.post(
        f"/api/wells/{wid}/production",
        json={"date": "2026-01-01", "oil_rate": 1200.0},
        headers=INTERPRETER,
    )
    assert production.status_code == 201, production.text

    for path in ("annotations", "dst", "rft", "completion", "production"):
        assert client.get(f"/api/wells/{wid}/{path}", headers=VIEWER).status_code == 200


def test_aliases_and_trajectory(make_well):
    wid = _well(make_well, "ALIAS-TRAJ")
    aliases = client.post(
        f"/api/wells/{wid}/aliases",
        json={"aliases": [{"original": "GR", "alias": "GAMMA"}]},
        headers=INTERPRETER,
    )
    assert aliases.status_code == 200, aliases.text
    assert client.get(f"/api/wells/{wid}/aliases", headers=VIEWER).json() == [
        {"original": "GR", "alias": "GAMMA"}
    ]

    saved = client.post(
        f"/api/wells/{wid}/trajectory",
        json={"points": [{"md": 0, "inc": 0, "azi": 0}, {"md": 100, "inc": 0, "azi": 0}]},
        headers=INTERPRETER,
    )
    assert saved.status_code == 200, saved.text
    traj = client.get(f"/api/wells/{wid}/trajectory", headers=VIEWER)
    assert traj.status_code == 200
    assert len(traj.json()["points"]) == 2


def test_export_and_data_paths(make_well):
    wid = _well(make_well, "EXPORT-WELL")
    las = client.get(f"/api/wells/{wid}/export-las", headers=VIEWER)
    assert las.status_code == 200
    assert "~Version Information" in las.text

    package = client.get(f"/api/wells/{wid}/export-package", headers=VIEWER)
    assert package.status_code == 200
    assert package.json()["well"]["id"] == wid

    table = client.get(f"/api/wells/{wid}/data-table?curve=GR&limit=5", headers=VIEWER)
    assert table.status_code == 200, table.text
    assert len(table.json()["rows"]) <= 5


def test_light_compute_endpoints(make_well):
    wid = _well(make_well, "COMPUTE-WELL")
    for path, payload in (
        ("dual-water", {}),
        ("compute-sw", {"model": "archie"}),
        ("permeability", {}),
        ("vcl-models", {}),
        ("lithology", {}),
    ):
        r = client.post(f"/api/wells/{wid}/{path}", json=payload, headers=INTERPRETER)
        assert r.status_code == 200, f"{path}: {r.text}"


def test_well_not_found_on_compute_endpoints():
    r = client.post("/api/wells/999999/compute-sw", json={"model": "archie"}, headers=INTERPRETER)
    assert r.status_code == 404


def test_curve_calc_uses_safe_expression_evaluator(make_well):
    wid = _well(make_well, "SAFE-CALC")
    ok = client.post(
        f"/api/wells/{wid}/curve-calc",
        json={"expression": "GR * 2 + 1", "output_name": "GR2"},
        headers=INTERPRETER,
    )
    assert ok.status_code == 200, ok.text

    bad = client.post(
        f"/api/wells/{wid}/curve-calc",
        json={"expression": "__import__('os').system('echo nope')", "output_name": "BAD"},
        headers=INTERPRETER,
    )
    assert bad.status_code == 400, bad.text
