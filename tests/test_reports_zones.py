"""Coverage for the zone-based report paths in backend/routers/reports.py.

`zone_stats`, `zonation_report` and `report-pdf` each branch on "are there
zones?". The seeded demo well has none, so those branches — including the whole
net-pay computation and the PDF zone table/plot — were never executed.
"""

from __future__ import annotations

import numpy as np
import pytest
from fastapi.testclient import TestClient

from backend.main import SessionLocal, Well, LogRun, CurveData, Zone
from backend.main import app


client = TestClient(app)
HEADERS = {"X-User-Role": "interpreter"}


@pytest.fixture(scope="module")
def zoned_well_id():
    """Seed a well with petrophysical curves and zones, once for this module."""
    db = SessionLocal()
    try:
        well = db.query(Well).order_by(Well.id.asc()).first()
        assert well is not None, "conftest should have seeded demo wells"

        lr = (
            db.query(LogRun)
            .filter(LogRun.well_id == well.id)
            .order_by(LogRun.id.desc())
            .first()
        )
        depth_cd = (
            db.query(CurveData)
            .filter(CurveData.log_run_id == lr.id, CurveData.mnemonic == "DEPT")
            .first()
        )
        depth = np.frombuffer(depth_cd.data_binary, dtype=np.float64)
        n = len(depth)

        rng = np.random.default_rng(7)
        # Values chosen to sit inside the default cutoffs so net pay is non-zero.
        synthetic = {
            "PHIE": np.clip(0.22 + rng.normal(0, 0.02, n), 0.01, 0.40),
            "SW": np.clip(0.30 + rng.normal(0, 0.03, n), 0.05, 0.95),
            "VSH": np.clip(0.18 + rng.normal(0, 0.03, n), 0.0, 0.90),
            "K": np.clip(120.0 + rng.normal(0, 20, n), 0.1, 5000.0),
        }
        for mnemonic, arr in synthetic.items():
            existing = (
                db.query(CurveData)
                .filter(CurveData.log_run_id == lr.id, CurveData.mnemonic == mnemonic)
                .first()
            )
            if existing is not None:
                existing.data_binary = arr.tobytes()
                existing.num_points = n
            else:
                db.add(CurveData(
                    log_run_id=lr.id,
                    mnemonic=mnemonic,
                    unit="MD" if mnemonic == "K" else "V/V",
                    num_points=n,
                    data_binary=arr.tobytes(),
                ))

        mid = float(depth[n // 2])
        wanted = [
            ("Upper Sand", float(depth[0]), mid),
            ("Lower Sand", mid, float(depth[-1])),
            # Degenerate cases: the loops must skip these, not crash.
            ("Inverted", mid + 10.0, mid),
            ("Off Log", 999_000.0, 999_100.0),
        ]
        for name, top, bottom in wanted:
            exists = db.query(Zone).filter(Zone.well_id == well.id, Zone.name == name).first()
            if exists is None:
                db.add(Zone(
                    well_id=well.id, name=name, top_depth=top,
                    bottom_depth=bottom, sort_order=1,
                ))

        db.commit()
        return well.id
    finally:
        db.close()


def test_zone_stats_computes_net_pay_when_zones_exist(zoned_well_id):
    r = client.get(f"/api/wells/{zoned_well_id}/zone-stats", headers=HEADERS)
    assert r.status_code == 200
    payload = r.json()

    zones = {z["name"]: z for z in payload["zones"]}
    assert "Upper Sand" in zones and "Lower Sand" in zones
    # Degenerate zones must be filtered out, not reported.
    assert "Inverted" not in zones and "Off Log" not in zones

    for zone in zones.values():
        assert zone["points"] > 0
        assert zone["gross_ft"] > 0
        assert zone["net_pay_ft"] > 0, f"expected pay in {zone['name']}"
        assert 0 < zone["ntg"] <= 1
        assert zone["avg_phie"] is not None
        assert zone["avg_sw"] is not None
        assert zone["avg_vsh"] is not None
        assert zone["avg_k"] is not None

    for key in ("vsh", "phie", "sw"):
        assert key in payload["cutoffs"]


def test_zonation_report_csv_includes_zone_rows_and_weighted_averages(zoned_well_id):
    r = client.get(f"/api/wells/{zoned_well_id}/zonation-report", headers=HEADERS)
    assert r.status_code == 200
    assert "text/csv" in r.headers.get("content-type", "")

    body = r.text
    assert "# ZONATION REPORT" in body
    assert "# SUMMARY" in body
    assert "Upper Sand" in body and "Lower Sand" in body
    assert "# Wtd Avg PHIE" in body
    assert "# Wtd Avg Sw" in body
    assert "# Wtd Avg Vsh" in body
    assert "TOTAL" in body


@pytest.mark.parametrize("template", ["professional", "executive", "compact"])
def test_report_pdf_renders_with_zones(zoned_well_id, template):
    r = client.get(
        f"/api/wells/{zoned_well_id}/report-pdf",
        params={
            "template": template,
            "include_curve_summary": True,
            "include_qc": True,
        },
        headers=HEADERS,
    )
    assert r.status_code == 200
    assert "application/pdf" in r.headers.get("content-type", "")
    assert r.content.startswith(b"%PDF")
    assert len(r.content) > 2000


def test_report_pdf_minimal_options(zoned_well_id):
    """Exercise the branches that skip the curve summary and QC sections."""
    r = client.get(
        f"/api/wells/{zoned_well_id}/report-pdf",
        params={
            "template": "unknown-template",
            "include_curve_summary": False,
            "include_qc": False,
        },
        headers=HEADERS,
    )
    assert r.status_code == 200
    assert r.content.startswith(b"%PDF")


def test_zone_stats_and_report_404_for_unknown_well():
    assert client.get("/api/wells/999999/zone-stats", headers=HEADERS).status_code == 404
    assert client.get("/api/wells/999999/zonation-report", headers=HEADERS).status_code == 404
    assert client.get("/api/wells/999999/report-pdf", headers=HEADERS).status_code == 404
