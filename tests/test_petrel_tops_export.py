"""Petrel tops export format contract at the API seam.

Header row is the Petrel column contract. One row per top, ordered by
depth. Well name and UWI ride on every row. Unknown well is 404.
"""

from __future__ import annotations

import csv
import io

from fastapi.testclient import TestClient

from backend.main import SessionLocal, app
from backend.models import FormationTop, Well

client = TestClient(app)
HEADERS = {"X-User-Role": "interpreter"}
ADMIN = {"X-User-Role": "admin"}

EXPECTED_HEADER = ["WELL", "UWI", "HORIZON", "MD", "TVD", "X_OFFSET",
                   "Y_OFFSET", "LATITUDE", "LONGITUDE", "COMMENTS"]


def _seed_well_with_tops() -> int:
    r = client.post("/api/wells/",
                    json={"project_id": 1, "name": "Petrel Well", "uwi": "UWI-99"},
                    headers=ADMIN)
    assert r.status_code == 201, r.text
    wid = r.json()["id"]
    db = SessionLocal()
    try:
        db.add(FormationTop(well_id=wid, formation_name="Shallow",
                            depth=1000.0, top_depth=1000.0, base_depth=1010.0,
                            notes="top one"))
        db.add(FormationTop(well_id=wid, formation_name="Deep",
                            depth=1020.0, top_depth=1020.0, base_depth=1030.0))
        db.commit()
        return wid
    finally:
        db.close()


def test_petrel_export_header_and_row_order():
    wid = _seed_well_with_tops()
    r = client.get(f"/api/wells/{wid}/tops-petrel", headers=HEADERS)
    assert r.status_code == 200, r.text
    assert "text/csv" in r.headers.get("content-type", "")
    rows = list(csv.reader(io.StringIO(r.text)))
    assert rows[0] == EXPECTED_HEADER
    assert len(rows) == 3
    assert rows[1][2] == "Shallow"
    assert rows[2][2] == "Deep"
    assert float(rows[1][3]) < float(rows[2][3])


def test_petrel_export_carries_well_identity_and_notes():
    wells = client.get("/api/wells/", headers=HEADERS).json()
    wid = next(w["id"] for w in wells if w["name"] == "Petrel Well")
    r = client.get(f"/api/wells/{wid}/tops-petrel", headers=HEADERS)
    rows = list(csv.reader(io.StringIO(r.text)))
    for row in rows[1:]:
        assert row[0] == "Petrel Well"
        assert row[1] == "UWI-99"
    assert rows[1][9] == "top one"


def test_petrel_export_unknown_well_is_404():
    r = client.get("/api/wells/999999/tops-petrel", headers=HEADERS)
    assert r.status_code == 404
