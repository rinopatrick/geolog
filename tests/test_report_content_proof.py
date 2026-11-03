"""Report content proof without a PDF text extractor.

ReportLab compresses content streams, so raw PDF bytes carry no readable
text. The PDF document title metadata is uncompressed. This test pins the
well name in the title metadata, and pins zone names in the CSV report,
which is the readable proof of the same data.
"""

from __future__ import annotations

import re

import numpy as np
from fastapi.testclient import TestClient

from backend.main import SessionLocal, app
from backend.models import FormationTop, Well, Zone

client = TestClient(app)
HEADERS = {"X-User-Role": "interpreter"}


def _seed_well_with_zones() -> int:
    wid = client.post(
        "/api/wells/", json={"project_id": 1, "name": "Content Proof Well"},
        headers={"X-User-Role": "admin"},
    ).json()["id"]
    db = SessionLocal()
    try:
        from backend.models import CurveData, LogRun
        lr = LogRun(well_id=wid, run_number=1, filename="cp.las",
                    start_depth=1000.0, stop_depth=1002.0, step=0.5,
                    null_value=-999.25, num_points=5)
        db.add(lr)
        db.flush()
        depth = np.array([1000.0, 1000.5, 1001.0, 1001.5, 1002.0])
        for mnemonic, vals in (
            ("DEPT", depth),
            ("GR", np.array([20.0, 25.0, 150.0, 155.0, 30.0])),
            ("RT", np.array([20.0, 19.0, 2.0, 2.1, 18.0])),
            ("NPHI", np.array([0.21, 0.20, 0.45, 0.44, 0.22])),
            ("RHOB", np.array([2.30, 2.31, 2.45, 2.46, 2.32])),
            ("PHIE", np.array([0.21, 0.20, 0.10, 0.09, 0.20])),
            ("SW", np.array([0.35, 0.36, 0.80, 0.82, 0.38])),
        ):
            arr = np.asarray(vals, dtype=np.float64)
            db.add(CurveData(log_run_id=lr.id, mnemonic=mnemonic, unit="",
                             num_points=5,
                             min_value=float(np.min(arr)),
                             max_value=float(np.max(arr)),
                             data_binary=arr.tobytes()))
        db.add(Zone(well_id=wid, name="Pay Sand",
                    top_depth=1000.0, bottom_depth=1001.0, sort_order=1))
        db.commit()
        return wid
    finally:
        db.close()


def test_report_pdf_title_names_the_well():
    wid = _seed_well_with_zones()
    r = client.get(f"/api/wells/{wid}/report-pdf",
                   params={"template": "professional"},
                   headers=HEADERS)
    assert r.status_code == 200, r.text
    assert r.content.startswith(b"%PDF")
    titles = re.findall(rb"/Title\s*\(([^)]+)\)", r.content)
    assert titles, "PDF carries no title metadata"
    assert b"Content Proof Well" in titles[0]


def test_zonation_csv_names_zones_and_well():
    wells = client.get("/api/wells/", headers=HEADERS).json()
    wid = next(w["id"] for w in wells if w["name"] == "Content Proof Well")
    r = client.get(f"/api/wells/{wid}/zonation-report", headers=HEADERS)
    assert r.status_code == 200, r.text
    assert "Pay Sand" in r.text
