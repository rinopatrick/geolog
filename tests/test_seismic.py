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


def _segy_large() -> bytes:
    textual = b" " * 3200
    binary = bytearray(400)
    ntraces, ns = 48, 40
    binary[16:18] = (2000).to_bytes(2, "big")
    binary[20:22] = (ns).to_bytes(2, "big")
    binary[24:26] = (5).to_bytes(2, "big")
    rng = np.random.default_rng(4)
    wave = np.array([0.1, 0.5, 1.0, 0.5, 0.1])
    traces = []
    for i in range(ntraces):
        header = bytearray(240)
        header[114:116] = (ns).to_bytes(2, "big")
        header[188:192] = (100 + i).to_bytes(4, "big")
        header[192:196] = (200).to_bytes(4, "big")
        data = rng.normal(0, 0.005, ns)
        center = 10 if i < 24 else 14
        data[center - 2:center + 3] += wave
        traces.append(bytes(header) + np.asarray(data, dtype=">f4").tobytes())
    return textual + bytes(binary) + b"".join(traces)


def test_auto_track_and_fault_endpoints():
    pid = _project_id()
    upload = client.post(
        f"/api/projects/{pid}/seismic",
        files={"file": ("auto.sgy", _segy_large(), "application/octet-stream")},
        data={"name": "Auto Line"},
        headers=ADMIN,
    )
    assert upload.status_code == 201, upload.text
    line_id = upload.json()["id"]

    tracked = client.post(
        f"/api/seismic/{line_id}/horizons/auto-track",
        json={"name": "Auto A", "seed_trace": 0, "seed_sample": 10, "window": 3, "search_radius": 4},
        headers=ADMIN,
    )
    assert tracked.status_code == 201, tracked.text
    assert tracked.json()["picks_count"] >= 20
    assert tracked.json()["confidence"] >= 0.5

    faults = client.post(
        f"/api/seismic/{line_id}/faults/detect",
        json={"threshold": 0.5, "min_points": 4, "max_faults": 5},
        headers=ADMIN,
    )
    assert faults.status_code == 201, faults.text
    assert faults.json()["faults"], faults.text
    fault_id = faults.json()["faults"][0]["id"]
    listed = client.get(f"/api/seismic/{line_id}/faults", headers=ADMIN)
    assert listed.status_code == 200
    assert fault_id in {item["id"] for item in listed.json()}
    deleted = client.delete(f"/api/seismic/{line_id}/faults/{fault_id}", headers=ADMIN)
    assert deleted.status_code == 204

def _segy_volume() -> bytes:
    textual = b" " * 3200
    binary = bytearray(400)
    n_inlines, n_crosslines, ns = 6, 48, 40
    binary[16:18] = (2000).to_bytes(2, "big")
    binary[20:22] = (ns).to_bytes(2, "big")
    binary[24:26] = (5).to_bytes(2, "big")
    rng = np.random.default_rng(4)
    wave = np.array([0.1, 0.5, 1.0, 0.5, 0.1])
    traces = []
    for inline in range(n_inlines):
        for crossline in range(n_crosslines):
            header = bytearray(240)
            header[114:116] = (ns).to_bytes(2, "big")
            header[188:192] = (100 + inline).to_bytes(4, "big")
            header[192:196] = (200 + crossline).to_bytes(4, "big")
            data = rng.normal(0, 0.005, ns)
            center = 10 if crossline < 24 else 14
            data[center - 2:center + 3] += wave
            traces.append(bytes(header) + np.asarray(data, dtype=">f4").tobytes())
    return textual + bytes(binary) + b"".join(traces)


def test_seismic_volume_sections_and_fault_links():
    pid = _project_id()
    upload = client.post(
        f"/api/projects/{pid}/seismic",
        files={"file": ("volume.sgy", _segy_volume(), "application/octet-stream")},
        data={"name": "3D Volume"},
        headers=ADMIN,
    )
    assert upload.status_code == 201, upload.text
    line_id = upload.json()["id"]
    assert upload.json()["trace_count"] == 288

    volume = client.get(f"/api/seismic/{line_id}/volume", headers=ADMIN)
    assert volume.status_code == 200, volume.text
    body = volume.json()
    assert body["is_3d"] is True
    assert body["inlines"] == [100, 101, 102, 103, 104, 105]
    assert body["crosslines"][0] == 200 and len(body["crosslines"]) == 48

    inline = client.get(f"/api/seismic/{line_id}/inline/100/section", headers=ADMIN)
    assert inline.status_code == 200, inline.text
    section = inline.json()["section"]
    assert section["trace_count"] == 48
    assert section["labels"][0] == 200
    assert section["mode"] == "inline"

    crossline = client.get(f"/api/seismic/{line_id}/crossline/247/section", headers=ADMIN)
    assert crossline.status_code == 200, crossline.text
    assert crossline.json()["section"]["trace_count"] == 6
    assert crossline.json()["section"]["labels"] == [100, 101, 102, 103, 104, 105]

    missing = client.get(f"/api/seismic/{line_id}/inline/999/section", headers=ADMIN)
    assert missing.status_code == 400

    linked = client.post(
        f"/api/seismic/{line_id}/faults/link-3d",
        json={"threshold": 0.5, "min_points": 4, "max_sections": 6, "sample_tolerance": 8},
        headers=ADMIN,
    )
    assert linked.status_code == 201, linked.text
    links = linked.json()["links"]
    assert links, linked.text
    assert linked.json()["scanned_inlines"] == 6
    assert links[0]["inline_start"] == 100 and links[0]["inline_end"] == 105
    assert len(links[0]["points"]) >= 6

    listed = client.get(f"/api/seismic/{line_id}/fault-links", headers=ADMIN)
    assert listed.status_code == 200
    assert [item["id"] for item in listed.json()] == [item["id"] for item in links]

    deleted = client.delete(f"/api/seismic/{line_id}/fault-links/{links[0]['id']}", headers=ADMIN)
    assert deleted.status_code == 204
    assert client.get(f"/api/seismic/{line_id}/fault-links", headers=ADMIN).json() == []

def _segy_many_traces(count: int = 3000) -> bytes:
    textual = b" " * 3200
    binary = bytearray(400)
    ns = 8
    binary[16:18] = (2000).to_bytes(2, "big")
    binary[20:22] = (ns).to_bytes(2, "big")
    binary[24:26] = (5).to_bytes(2, "big")
    rng = np.random.default_rng(9)
    traces = []
    for index in range(count):
        header = bytearray(240)
        header[114:116] = (ns).to_bytes(2, "big")
        header[188:192] = (100).to_bytes(4, "big")
        header[192:196] = (200 + index).to_bytes(4, "big")
        data = rng.normal(0, 0.01, ns).astype(">f4")
        traces.append(bytes(header) + data.tobytes())
    return textual + bytes(binary) + b"".join(traces)


def test_sequential_section_decimates_the_whole_line():
    pid = _project_id()
    upload = client.post(
        f"/api/projects/{pid}/seismic",
        files={"file": ("long.sgy", _segy_many_traces(), "application/octet-stream")},
        data={"name": "Long Line"},
        headers=ADMIN,
    )
    assert upload.status_code == 201, upload.text
    line_id = upload.json()["id"]
    assert upload.json()["trace_count"] == 3000

    section = client.get(
        f"/api/seismic/{line_id}/section?max_traces=400&max_samples=8",
        headers=ADMIN,
    )
    assert section.status_code == 200, section.text
    body = section.json()["section"]
    assert body["line_trace_count"] == 3000
    assert body["trace_count"] == 400
    assert body["sampled"] is True
    assert body["labels"][0] == 0
    assert body["labels"][-1] == 2999

def test_seismic_3d_horizon_picks_and_auto_track():
    pid = _project_id()
    upload = client.post(
        f"/api/projects/{pid}/seismic",
        files={"file": ("volume-horizon.sgy", _segy_volume(), "application/octet-stream")},
        data={"name": "3D Horizon Volume"},
        headers=ADMIN,
    )
    assert upload.status_code == 201, upload.text
    line_id = upload.json()["id"]

    created = client.post(
        f"/api/seismic/{line_id}/horizons",
        json={
            "name": "Inline 100 pick",
            "mode": "inline",
            "section_value": 100,
            "picks": [{"trace": 2, "sample": 10}, {"trace": 3, "sample": 10}],
        },
        headers=ADMIN,
    )
    assert created.status_code == 201, created.text
    assert created.json()["mode"] == "inline"
    assert created.json()["section_value"] == 100

    tracked = client.post(
        f"/api/seismic/{line_id}/horizons/auto-track",
        json={
            "name": "Inline auto",
            "mode": "inline",
            "section_value": 100,
            "seed_trace": 10,
            "seed_sample": 10,
            "window": 3,
            "search_radius": 4,
        },
        headers=ADMIN,
    )
    assert tracked.status_code == 201, tracked.text
    assert tracked.json()["horizon"]["mode"] == "inline"
    assert tracked.json()["horizon"]["section_value"] == 100
    assert tracked.json()["picks_count"] >= 20

    invalid = client.post(
        f"/api/seismic/{line_id}/horizons",
        json={"name": "Bad", "mode": "inline", "picks": []},
        headers=ADMIN,
    )
    assert invalid.status_code == 400

    bad_mode = client.post(
        f"/api/seismic/{line_id}/horizons",
        json={"name": "Bad mode", "mode": "depth", "picks": []},
        headers=ADMIN,
    )
    assert bad_mode.status_code == 400

    rows = client.get(f"/api/seismic/{line_id}/horizons", headers=ADMIN).json()
    assert {row["mode"] for row in rows} == {"inline"}
