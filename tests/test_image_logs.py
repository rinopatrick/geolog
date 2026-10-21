"""Image asset upload, DLIS failure path and manual dip fitting."""

from __future__ import annotations

import io
import math

import numpy as np
from fastapi.testclient import TestClient

from backend.image_logs import save_png_gray
from backend.main import app

client = TestClient(app)
I = {"X-User-Role": "interpreter"}

def _png() -> bytes:
    image = np.tile(np.linspace(0, 255, 64), (32, 1))
    path = "artifacts/test-image.png"
    save_png_gray(image, path)
    with open(path, "rb") as fh:
        return fh.read()

def test_image_upload_and_dip_fit(make_well):
    wid = make_well("IMG", {"DEPT": [1000.0, 1001.0], "GR": [10.0, 20.0]})
    files = {"file": ("image.png", _png(), "image/png")}
    data = {"depth_top": "1000", "depth_bottom": "1010", "image_type": "FMI",
            "borehole_radius": "10", "source": "test"}
    r = client.post(f"/api/wells/{wid}/image-assets", headers=I, files=files, data=data)
    assert r.status_code == 201, r.text
    asset = r.json()
    assert asset["width"] == 64 and asset["height"] == 32
    aid = asset["id"]
    assert client.get(f"/api/wells/{wid}/image-assets/{aid}/file").content[:8] == b"\x89PNG\r\n\x1a\n"

    trace = [[1000 + 2 * math.cos(math.radians(a - 45)), a] for a in range(0, 360, 30)]
    r = client.post(f"/api/wells/{wid}/image-assets/{aid}/dips", headers=I, json={"trace": trace})
    assert r.status_code == 201, r.text
    dip = r.json()
    assert abs(dip["dip_angle"] - math.degrees(math.atan(2 / 10))) < 0.5
    assert abs(dip["dip_azimuth"] - 45) < 1.0
    assert dip["r2"] > 0.99
    assert dip["method"] == "manual_trace"

    assert client.post(f"/api/wells/{wid}/image-assets/{aid}/dips/{dip['id']}/approve", headers=I).status_code == 200
    detail = client.get(f"/api/wells/{wid}/image-assets/{aid}").json()
    assert detail["dip_rows"][0]["approved"] is True

    edited = client.put(f"/api/wells/{wid}/image-assets/{aid}", headers=I,
                        json={"image_type": "FMI-2", "source": "edited"})
    assert edited.status_code == 200, edited.text
    assert edited.json()["image_type"] == "FMI-2"
    assert edited.json()["source"] == "edited"

    direct = client.post(f"/api/wells/{wid}/image-assets/{aid}/dips", headers=I,
                         json={"depth": 1002, "dip_angle": 20, "dip_azimuth": 120})
    assert direct.status_code == 201
    assert len(client.get(f"/api/wells/{wid}/image-assets/{aid}/dips").json()) == 2

def test_image_dlis_failure_and_bad_trace(make_well):
    wid = make_well("IMG-BAD", {"DEPT": [1000.0], "GR": [10.0]})
    files = {"file": ("image.png", _png(), "image/png")}
    asset = client.post(f"/api/wells/{wid}/image-assets", headers=I, files=files,
                        data={"depth_top": "1000", "depth_bottom": "1010", "borehole_radius": "10"}).json()
    aid = asset["id"]
    bad = client.post(f"/api/wells/{wid}/image-assets/{aid}/dips", headers=I,
                      json={"trace": [[1000, 0], [1001, 0], [1002, 0]]})
    assert bad.status_code == 400
    bad_dlis = client.post(f"/api/wells/{wid}/image-assets/import-dlis", headers=I,
                           files={"file": ("x.dlis", b"not a dlis", "application/octet-stream")},
                           data={"channel": "IMG"})
    assert bad_dlis.status_code == 400
