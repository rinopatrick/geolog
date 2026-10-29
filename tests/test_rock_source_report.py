"""Rock-type/source-rock PDF report."""

from __future__ import annotations

import numpy as np
from fastapi.testclient import TestClient

from backend.main import SessionLocal, app
from backend.models import CoreDataset, CorePlug

client = TestClient(app)
INTERPRETER = {"X-User-Role": "interpreter"}


def test_rock_source_report_pdf(make_well):
    depth = np.arange(1000.0, 1020.0, 1.0)
    n = len(depth)
    wid = make_well("ROCK-REPORT", {
        "DEPT": depth,
        "RT": np.linspace(2.0, 30.0, n),
        "DT": np.linspace(100.0, 60.0, n),
        "RHOB": np.linspace(2.55, 2.30, n),
    })
    db = SessionLocal()
    try:
        ds = CoreDataset(well_id=wid, version=1, status="draft", source="test")
        db.add(ds)
        db.flush()
        db.add(CorePlug(dataset_id=ds.id, well_id=wid, plug_name="P1", depth_md=1001, porosity=0.25, perm_air=1000))
        db.add(CorePlug(dataset_id=ds.id, well_id=wid, plug_name="P2", depth_md=1002, porosity=0.08, perm_air=1))
        db.commit()
    finally:
        db.close()

    src = client.post(f"/api/wells/{wid}/source-rock", json={"method": "passey"}, headers=INTERPRETER)
    assert src.status_code == 200, src.text
    rt = client.post(f"/api/wells/{wid}/core/rock-types/classify", json={}, headers=INTERPRETER)
    assert rt.status_code == 200, rt.text

    report = client.get(f"/api/wells/{wid}/report/rock-source.pdf", headers=INTERPRETER)
    assert report.status_code == 200, report.text
    assert report.headers["content-type"].startswith("application/pdf")
    assert report.content[:4] == b"%PDF"
    assert len(report.content) > 1000
