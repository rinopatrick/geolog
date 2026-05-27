from pathlib import Path
import sys

from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.main import app


client = TestClient(app)


def _h(role: str):
    return {"X-User-Role": role}


def test_viewer_blocked_on_interpreter_write_endpoints():
    payload = {
        "a": 1.0,
        "m": 2.0,
        "n": 2.0,
        "rw": 0.1,
        "vsh_cutoff": 0.35,
        "phie_cutoff": 0.1,
        "sw_cutoff": 0.6,
        "iterations": 100,
        "variation_pct": 20,
    }
    r1 = client.post("/api/wells/999999/sensitivity", headers=_h("viewer"), json=payload)
    assert r1.status_code == 403
    assert "interpreter" in r1.text.lower()

    r2 = client.post(
        "/api/correlation-markers",
        headers=_h("viewer"),
        json={"well_a_id": 1, "well_b_id": 2, "depth_a": 1000.0, "depth_b": 1001.0, "label": "x"},
    )
    assert r2.status_code == 403


def test_interpreter_not_blocked_by_role_guard_on_same_endpoints():
    payload = {
        "a": 1.0,
        "m": 2.0,
        "n": 2.0,
        "rw": 0.1,
        "vsh_cutoff": 0.35,
        "phie_cutoff": 0.1,
        "sw_cutoff": 0.6,
        "iterations": 100,
        "variation_pct": 20,
    }
    r1 = client.post("/api/wells/999999/sensitivity", headers=_h("interpreter"), json=payload)
    assert r1.status_code != 403

    r2 = client.post(
        "/api/correlation-markers",
        headers=_h("interpreter"),
        json={"well_a_id": 1, "well_b_id": 2, "depth_a": 1000.0, "depth_b": 1001.0, "label": "x"},
    )
    assert r2.status_code != 403


def test_jwt_mode_rejects_missing_bearer_token(monkeypatch):
    from backend import main as main_mod

    old_mode = main_mod.AUTH_CONFIG.mode
    main_mod.AUTH_CONFIG.mode = "jwt"
    try:
        r = client.get("/api/wells")
        assert r.status_code == 401
    finally:
        main_mod.AUTH_CONFIG.mode = old_mode


def test_report_pdf_endpoint_not_found():
    r = client.get(
        "/api/wells/999999/report-pdf",
        params={"template": "professional", "include_curve_summary": True, "include_qc": True},
        headers=_h("viewer"),
    )
    assert r.status_code == 404


def test_report_pdf_endpoint_success_content_type():
    wells = client.get("/api/wells", headers=_h("viewer"))
    assert wells.status_code == 200
    data = wells.json()
    assert isinstance(data, list) and len(data) > 0
    wid = data[0]["id"]

    r = client.get(
        f"/api/wells/{wid}/report-pdf",
        params={"template": "professional", "include_curve_summary": True, "include_qc": True},
        headers=_h("viewer"),
    )
    assert r.status_code == 200
    assert "application/pdf" in (r.headers.get("content-type") or "")


def test_zone_stats_contract_shape():
    wells = client.get("/api/wells", headers=_h("viewer"))
    assert wells.status_code == 200
    data = wells.json()
    assert isinstance(data, list) and len(data) > 0
    wid = data[0]["id"]

    r = client.get(f"/api/wells/{wid}/zone-stats", headers=_h("viewer"))
    assert r.status_code == 200
    payload = r.json()
    assert "zones" in payload
    assert "cutoffs" in payload
    assert isinstance(payload["zones"], list)
    assert isinstance(payload["cutoffs"], dict)
    for key in ("vsh", "phie", "sw"):
        assert key in payload["cutoffs"]


def test_zonation_report_csv_contract():
    wells = client.get("/api/wells", headers=_h("viewer"))
    assert wells.status_code == 200
    data = wells.json()
    assert isinstance(data, list) and len(data) > 0
    wid = data[0]["id"]

    r = client.get(f"/api/wells/{wid}/zonation-report", headers=_h("viewer"))
    assert r.status_code == 200
    assert "text/csv" in (r.headers.get("content-type") or "")
    body = r.text
    assert "# ZONATION REPORT" in body
    assert "# SUMMARY" in body


def test_auto_zone_from_tops_role_gate_viewer_blocked():
    wells = client.get("/api/wells", headers=_h("viewer"))
    assert wells.status_code == 200
    data = wells.json()
    assert isinstance(data, list) and len(data) > 0
    wid = data[0]["id"]

    r = client.post(f"/api/wells/{wid}/auto-zone-from-tops", headers=_h("viewer"))
    assert r.status_code == 403


def test_auto_zone_from_tops_interpreter_not_forbidden():
    wells = client.get("/api/wells", headers=_h("viewer"))
    assert wells.status_code == 200
    data = wells.json()
    assert isinstance(data, list) and len(data) > 0
    wid = data[0]["id"]

    r = client.post(f"/api/wells/{wid}/auto-zone-from-tops", headers=_h("interpreter"))
    assert r.status_code != 403
