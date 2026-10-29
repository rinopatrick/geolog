"""Well-to-seismic tie endpoints."""

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
    ns = 90
    binary[16:18] = (2000).to_bytes(2, "big")
    binary[20:22] = (ns).to_bytes(2, "big")
    binary[24:26] = (5).to_bytes(2, "big")
    rng = np.random.default_rng(31)
    wave = np.array([0.4, 0.8, 1.2, 0.8, 0.4])
    traces = []
    for inline in range(3):
        for crossline in range(3):
            header = bytearray(240)
            header[114:116] = (ns).to_bytes(2, "big")
            header[188:192] = (100 + inline).to_bytes(4, "big")
            header[192:196] = (200 + crossline).to_bytes(4, "big")
            data = rng.normal(0, 0.01, ns)
            if inline == 1 and crossline == 1:
                data[40:45] += wave
            traces.append(bytes(header) + np.asarray(data, dtype=">f4").tobytes())
    return textual + bytes(binary) + b"".join(traces)


def _curves(length: int = 200) -> dict:
    depth = np.arange(1000.0, 1000.0 + length)
    dt = 70.0 + 20.0 * np.sin(np.arange(length) / 8.0)
    rhob = 2.35 + 0.15 * np.cos(np.arange(length) / 10.0)
    return {"DEPT": depth, "DT": dt, "RHOB": rhob}


def test_seismic_tie_create_list_and_delete(make_well):
    wid = make_well("Tie-01", _curves())
    pid = _project_id()
    upload = client.post(
        f"/api/projects/{pid}/seismic",
        files={"file": ("tie.sgy", _volume(), "application/octet-stream")},
        data={"name": "Tie Volume"},
        headers=ADMIN,
    )
    assert upload.status_code == 201, upload.text
    line_id = upload.json()["id"]

    created = client.post(
        f"/api/wells/{wid}/seismic-ties",
        json={
            "line_id": line_id,
            "inline": 101,
            "crossline": 201,
            "frequency_hz": 30,
            "max_shift_ms": 20,
            "name": "Tie A",
        },
        headers=ADMIN,
    )
    assert created.status_code == 201, created.text
    body = created.json()
    assert body["name"] == "Tie A"
    assert body["correlation"] is not None and -1.0 <= body["correlation"] <= 1.0
    assert abs(body["shift_ms"]) <= 20
    result = body["result"]
    assert result["samples"] == 90
    assert len(result["twt_ms"]) == len(result["seismic"]) == len(result["synthetic"])
    assert result["checkshot_used"] is False

    checkshot = client.post(
        f"/api/wells/{wid}/seismic-ties",
        json={
            "line_id": line_id,
            "inline": 101,
            "crossline": 201,
            "checkshot": [
                {"depth": 1000, "twt_ms": 0},
                {"depth": 1100, "twt_ms": 200},
                {"depth": 1200, "twt_ms": 420},
            ],
            "max_shift_ms": 12,
        },
        headers=ADMIN,
    )
    assert checkshot.status_code == 201, checkshot.text
    assert checkshot.json()["result"]["checkshot_used"] is True
    assert checkshot.json()["result"]["check_samples"] == 3

    listed = client.get(f"/api/wells/{wid}/seismic-ties", headers=ADMIN)
    assert listed.status_code == 200
    assert {row["id"] for row in listed.json()} == {body["id"], checkshot.json()["id"]}
    assert "result" not in listed.json()[0]

    detail = client.get(f"/api/wells/{wid}/seismic-ties/{body['id']}", headers=ADMIN)
    assert detail.status_code == 200
    assert detail.json()["result"]["samples"] == 90

    deleted = client.delete(f"/api/wells/{wid}/seismic-ties/{body['id']}", headers=ADMIN)
    assert deleted.status_code == 204


def test_seismic_tie_validation(make_well):
    wid = make_well("Tie-02", _curves())
    pid = _project_id()
    upload = client.post(
        f"/api/projects/{pid}/seismic",
        files={"file": ("tie-bad.sgy", _volume(), "application/octet-stream")},
        data={"name": "Tie Bad Volume"},
        headers=ADMIN,
    )
    assert upload.status_code == 201, upload.text
    line_id = upload.json()["id"]

    missing = client.post(
        f"/api/wells/{wid}/seismic-ties",
        json={"line_id": line_id, "inline": 101, "crossline": 999},
        headers=ADMIN,
    )
    assert missing.status_code == 404

    bad_checkshot = client.post(
        f"/api/wells/{wid}/seismic-ties",
        json={
            "line_id": line_id,
            "inline": 101,
            "crossline": 201,
            "checkshot": [
                {"depth": 1000, "twt_ms": 0},
                {"depth": 1000, "twt_ms": 200},
            ],
        },
        headers=ADMIN,
    )
    assert bad_checkshot.status_code == 400
