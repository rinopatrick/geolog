"""Coverage for correlation and zonation routes and their pure helpers."""

from __future__ import annotations

import numpy as np
from fastapi.testclient import TestClient

from backend.main import SessionLocal, app
from backend.models import FormationTop, Zone
from backend.routers.zonation import (
    _compute_zone_stats,
    _find_gr_valleys,
    _find_pay_intervals,
)

client = TestClient(app)
INTERPRETER = {"X-User-Role": "interpreter"}
VIEWER = {"X-User-Role": "viewer"}


def _well_with_gr(make_well, name: str, depth0: float = 1000.0) -> int:
    depth = np.arange(depth0, depth0 + 50, 1.0)
    gr = 60.0 + 20.0 * np.sin(np.arange(len(depth)) / 4.0)
    return make_well(name, {"DEPT": depth, "GR": gr})


def _add_top(wid: int, name: str, depth: float) -> int:
    db = SessionLocal()
    try:
        top = FormationTop(well_id=wid, formation_name=name, depth=depth, color="#ff0000")
        db.add(top)
        db.commit()
        db.refresh(top)
        return top.id
    finally:
        db.close()


def test_cross_section_and_tie_lines(make_well):
    a = _well_with_gr(make_well, "CORR-A", 1000.0)
    b = _well_with_gr(make_well, "CORR-B", 1005.0)
    _add_top(a, "Alpha", 1010.0)
    _add_top(b, "Alpha", 1015.0)

    section = client.get(
        f"/api/correlation/cross-section?well_ids={a},{b}&curve=GR", headers=VIEWER
    )
    assert section.status_code == 200, section.text
    body = section.json()
    assert len(body["wells"]) == 2
    assert body["wells"][0]["values"]

    ties = client.get(
        f"/api/correlation/tie-lines?well_a_id={a}&well_b_id={b}&include_top_matches=true",
        headers=VIEWER,
    )
    assert ties.status_code == 200, ties.text
    sources = {t["source"] for t in ties.json()["tie_lines"]}
    assert "formation_top" in sources


def test_auto_correlate_scores_matching_tops(make_well):
    a = _well_with_gr(make_well, "AUTO-A", 1000.0)
    b = _well_with_gr(make_well, "AUTO-B", 1000.0)
    _add_top(a, "Alpha", 1010.0)
    _add_top(b, "Alpha", 1012.0)

    r = client.post(
        "/api/correlation/auto-correlate",
        json={"well_a_id": a, "well_b_id": b, "curve": "GR", "depth_tolerance": 20.0},
        headers=INTERPRETER,
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["count"] >= 1
    assert body["matches"][0]["formation_a"] == "Alpha"
    assert body["profile_hint"] is not None


def test_correlation_rejects_bad_input(make_well):
    wid = _well_with_gr(make_well, "CORR-BAD", 1000.0)
    assert client.get("/api/correlation/cross-section?well_ids=1", headers=VIEWER).status_code == 400
    assert client.get(
        "/api/correlation/cross-section?well_ids=abc,2", headers=VIEWER
    ).status_code == 400
    assert client.post(
        "/api/correlation/auto-correlate",
        json={"well_a_id": wid, "well_b_id": wid},
        headers=INTERPRETER,
    ).status_code == 400
    assert client.post(
        "/api/correlation/auto-correlate", json={}, headers=INTERPRETER
    ).status_code == 400


def test_auto_zone_from_tops_and_exports(make_well):
    wid = _well_with_gr(make_well, "ZONE-TOPS", 1000.0)
    _add_top(wid, "Top A", 1010.0)
    _add_top(wid, "Top B", 1020.0)
    _add_top(wid, "Top C", 1030.0)

    created = client.post(f"/api/wells/{wid}/auto-zone-from-tops", headers=INTERPRETER)
    assert created.status_code == 200, created.text
    assert created.json()["zones_created"] == 2

    report = client.get(f"/api/wells/{wid}/zone-report", headers=VIEWER)
    assert report.status_code == 200, report.text
    assert report.json()["summary"]["num_zones"] == 2

    csv_resp = client.get(f"/api/wells/{wid}/zone-report/csv", headers=VIEWER)
    assert csv_resp.status_code == 200
    assert "Zone,Top Depth" in csv_resp.text

    pdf_resp = client.get(f"/api/wells/{wid}/zone-report/pdf", headers=VIEWER)
    assert pdf_resp.status_code == 200
    assert pdf_resp.content[:4] == b"%PDF"


def test_auto_zone_from_curves(make_well):
    depth = np.arange(1000.0, 1010.0, 1.0)
    wid = make_well(
        "ZONE-CURVES",
        {
            "DEPT": depth,
            "VSH": np.full(len(depth), 0.2),
            "PHIE": np.full(len(depth), 0.2),
            "SW": np.full(len(depth), 0.3),
        },
    )
    r = client.post(
        f"/api/wells/{wid}/auto-zone",
        json={"vsh_max": 0.4, "phie_min": 0.1, "sw_max": 0.5},
        headers=INTERPRETER,
    )
    assert r.status_code == 200, r.text
    assert r.json()["summary"]["num_zones"] >= 1

    # auto-zone returns a computation preview; it does not persist zones.


def test_zone_report_missing_well():
    assert client.get("/api/wells/999999/zone-report", headers=VIEWER).status_code == 404
    assert client.get("/api/wells/999999/zone-report/csv", headers=VIEWER).status_code == 200


def test_zonation_pure_helpers():
    depth = np.arange(0.0, 10.0)
    mask = np.array([False, True, True, False, False, True, True, True, False, False])
    intervals = _find_pay_intervals(mask, depth, gap_merge_ft=0)
    assert intervals == [(1, 2), (5, 7)]

    merged = _find_pay_intervals(mask, depth, gap_merge_ft=3.0)
    assert merged == [(1, 7)]

    stats = _compute_zone_stats(
        [(0, 4)],
        depth,
        vsh=np.full(10, 0.2),
        phie=np.full(10, 0.25),
        sw=np.full(10, 0.3),
        step=1.0,
    )
    assert stats[0]["name"] == "Zone_1"
    assert stats[0]["gross_ft"] == 4.0
    assert stats[0]["avg_phie"] == 0.25

    signal = 50.0 + 10.0 * np.sin(np.linspace(0, 8 * np.pi, 400))
    valleys = _find_gr_valleys(signal, distance=40, prominence=1.0)
    assert len(valleys) >= 3
