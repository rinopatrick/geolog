"""SEG-Y parsing and line/horizon endpoints."""

from __future__ import annotations

import numpy as np
import pytest
from fastapi.testclient import TestClient

from backend.main import SessionLocal, app
from backend.models import Project
from backend.seismic import ibm_to_ieee, parse_segy

client = TestClient(app)
ADMIN = {"X-User-Role": "admin"}


def _segy_bytes() -> bytes:
    textual = b" " * 3200
    binary = bytearray(400)
    binary[16:18] = (2000).to_bytes(2, "big")  # 2 ms
    binary[20:22] = (6).to_bytes(2, "big")
    binary[24:26] = (5).to_bytes(2, "big")  # IEEE float
    traces = []
    for inline, values in enumerate(([1.0, 2.0, 3.0, 2.0, 1.0, 0.0],
                                     [0.0, 1.0, 2.0, 3.0, 2.0, 1.0],
                                     [-1.0, 0.0, 1.0, 2.0, 1.0, 0.0])):
        header = bytearray(240)
        header[114:116] = (6).to_bytes(2, "big")
        header[188:192] = (100 + inline).to_bytes(4, "big")
        header[192:196] = (200 + inline).to_bytes(4, "big")
        traces.append(bytes(header) + np.asarray(values, dtype=">f4").tobytes())
    return textual + bytes(binary) + b"".join(traces)


def test_parse_segy_ieee():
    parsed = parse_segy(_segy_bytes())
    assert parsed["trace_count"] == 3
    assert parsed["samples_per_trace"] == 6
    assert parsed["sample_interval_ms"] == 2.0
    assert parsed["inline_min"] == 100 and parsed["inline_max"] == 102
    assert parsed["matrix"].shape == (3, 6)


def test_ibm_float_conversion():
    # IBM 0x41100000 = 1.0, 0xC1100000 = -1.0
    result = ibm_to_ieee(bytes.fromhex("41100000c1100000"))
    assert result[0] == pytest.approx(1.0)
    assert result[1] == pytest.approx(-1.0)


def _project_id() -> int:
    db = SessionLocal()
    try:
        return int(db.query(Project.id).order_by(Project.id.asc()).first()[0])
    finally:
        db.close()


def test_seismic_upload_section_and_horizons():
    pid = _project_id()
    upload = client.post(
        f"/api/projects/{pid}/seismic",
        files={"file": ("line.sgy", _segy_bytes(), "application/octet-stream")},
        data={"name": "Test Line"},
        headers=ADMIN,
    )
    assert upload.status_code == 201, upload.text
    line = upload.json()
    line_id = line["id"]
    assert line["trace_count"] == 3

    listed = client.get(f"/api/projects/{pid}/seismic", headers=ADMIN)
    assert listed.status_code == 200
    assert line_id in {item["id"] for item in listed.json()}

    section = client.get(f"/api/seismic/{line_id}/section", headers=ADMIN)
    assert section.status_code == 200, section.text
    body = section.json()["section"]
    assert body["trace_count"] == 3
    assert body["sample_count"] == 6
    assert len(body["data"]) == 3
    assert len(body["data"][0]) == 6

    horizon = client.post(
        f"/api/seismic/{line_id}/horizons",
        json={"name": "Top A", "color": "#ff0000", "picks": [{"trace": 0, "sample": 2}, {"trace": 1, "sample": 3}]},
        headers=ADMIN,
    )
    assert horizon.status_code == 201, horizon.text
    horizon_id = horizon.json()["id"]
    rows = client.get(f"/api/seismic/{line_id}/horizons", headers=ADMIN)
    assert rows.status_code == 200
    assert rows.json()[0]["picks"][0]["sample"] == 2

    deleted = client.delete(f"/api/seismic/{line_id}/horizons/{horizon_id}", headers=ADMIN)
    assert deleted.status_code == 204


def test_seismic_rejects_invalid_file():
    pid = _project_id()
    r = client.post(
        f"/api/projects/{pid}/seismic",
        files={"file": ("bad.sgy", b"not-segy", "application/octet-stream")},
        headers=ADMIN,
    )
    assert r.status_code == 400
