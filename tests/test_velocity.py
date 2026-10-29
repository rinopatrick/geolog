"""Velocity models and surface depth conversion."""

from __future__ import annotations

import numpy as np
from fastapi.testclient import TestClient

from backend.main import SessionLocal, app
from backend.models import Project

client = TestClient(app)
ADMIN = {"X-User-Role": "admin"}


def _project_id() -> int:
    db = SessionLocal()
    try:
        return int(db.query(Project.id).order_by(Project.id.asc()).first()[0])
    finally:
        db.close()


def _volume() -> bytes:
    textual = b" " * 3200
    binary = bytearray(400)
    ns = 12
    binary[16:18] = (2000).to_bytes(2, "big")
    binary[20:22] = (ns).to_bytes(2, "big")
    binary[24:26] = (5).to_bytes(2, "big")
    rng = np.random.default_rng(21)
    traces = []
    for inline in range(3):
        for crossline in range(3):
            header = bytearray(240)
            header[114:116] = (ns).to_bytes(2, "big")
            header[188:192] = (100 + inline).to_bytes(4, "big")
            header[192:196] = (200 + crossline).to_bytes(4, "big")
            data = rng.normal(0, 0.01, ns).astype(">f4")
            traces.append(bytes(header) + data.tobytes())
    return textual + bytes(binary) + b"".join(traces)


def _build_surface() -> tuple[int, int]:
    pid = _project_id()
    upload = client.post(
        f"/api/projects/{pid}/seismic",
        files={"file": ("depth.sgy", _volume(), "application/octet-stream")},
        data={"name": "Depth Volume"},
        headers=ADMIN,
    )
    assert upload.status_code == 201, upload.text
    line_id = upload.json()["id"]
    for index, inline in enumerate([100, 101, 102]):
        created = client.post(
            f"/api/seismic/{line_id}/horizons",
            json={
                "name": "Depth Top",
                "mode": "inline",
                "section_value": inline,
                "picks": [
                    {"trace": 0, "sample": 2 + index},
                    {"trace": 1, "sample": 3 + index},
                    {"trace": 2, "sample": 4 + index},
                ],
            },
            headers=ADMIN,
        )
        assert created.status_code == 201, created.text
    surface = client.post(
        f"/api/seismic/{line_id}/surfaces",
        json={"name": "Depth Surface", "horizon_name": "Depth Top", "max_grid": 12},
        headers=ADMIN,
    )
    assert surface.status_code == 201, surface.text
    return line_id, surface.json()["id"]


def test_velocity_model_conversion_and_surface_depth():
    pid = _project_id()
    constant = client.post(
        f"/api/projects/{pid}/velocity-models",
        json={"name": "Constant 2500", "kind": "constant", "velocity_m_s": 2500},
        headers=ADMIN,
    )
    assert constant.status_code == 201, constant.text
    model_id = constant.json()["id"]

    converted = client.post(
        f"/api/projects/{pid}/velocity-models/{model_id}/convert",
        json={"times_ms": [0, 1000, 2000]},
        headers=ADMIN,
    )
    assert converted.status_code == 200, converted.text
    assert converted.json()["depths_m"] == [0.0, 1250.0, 2500.0]

    layers = client.post(
        f"/api/projects/{pid}/velocity-models",
        json={
            "name": "Two layer",
            "kind": "layers",
            "layers": [
                {"top_ms": 0, "velocity_m_s": 2000},
                {"top_ms": 1000, "velocity_m_s": 3000},
            ],
        },
        headers=ADMIN,
    )
    assert layers.status_code == 201, layers.text
    layer_id = layers.json()["id"]
    layered = client.post(
        f"/api/projects/{pid}/velocity-models/{layer_id}/convert",
        json={"times_ms": [500, 1500]},
        headers=ADMIN,
    )
    assert layered.status_code == 200, layered.text
    assert layered.json()["depths_m"] == [500.0, 1750.0]

    line_id, surface_id = _build_surface()
    depth = client.post(
        f"/api/seismic/{line_id}/surfaces/{surface_id}/depth",
        json={"velocity_model_id": model_id},
        headers=ADMIN,
    )
    assert depth.status_code == 200, depth.text
    body = depth.json()
    assert body["velocity_model_id"] == model_id
    assert len(body["depth_grid"]) == len(body["grid"])
    assert body["depth_stats"]["min_depth_m"] > 0
    assert body["depth_stats"]["max_depth_m"] >= body["depth_stats"]["min_depth_m"]

    exported = client.get(f"/api/seismic/{line_id}/surfaces/{surface_id}/export.csv", headers=ADMIN)
    assert exported.status_code == 200
    assert exported.text.splitlines()[0] == "inline,crossline,time_ms,depth_m"
    assert len(exported.text.splitlines()[0].split(",")) == 4


def test_velocity_model_validation_and_crud():
    pid = _project_id()
    invalid = client.post(
        f"/api/projects/{pid}/velocity-models",
        json={
            "name": "Bad layers",
            "kind": "layers",
            "layers": [
                {"top_ms": 100, "velocity_m_s": 2000},
                {"top_ms": 200, "velocity_m_s": 3000},
            ],
        },
        headers=ADMIN,
    )
    assert invalid.status_code == 400

    created = client.post(
        f"/api/projects/{pid}/velocity-models",
        json={"name": "Editable", "kind": "constant", "velocity_m_s": 2400},
        headers=ADMIN,
    )
    assert created.status_code == 201, created.text
    model_id = created.json()["id"]

    updated = client.put(
        f"/api/projects/{pid}/velocity-models/{model_id}",
        json={"name": "Edited", "kind": "constant", "velocity_m_s": 2600},
        headers=ADMIN,
    )
    assert updated.status_code == 200, updated.text
    assert updated.json()["velocity_m_s"] == 2600

    listed = client.get(f"/api/projects/{pid}/velocity-models", headers=ADMIN)
    assert listed.status_code == 200
    assert model_id in {item["id"] for item in listed.json()}

    deleted = client.delete(f"/api/projects/{pid}/velocity-models/{model_id}", headers=ADMIN)
    assert deleted.status_code == 204
