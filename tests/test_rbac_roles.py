from pathlib import Path
import sys

from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.main import app
from backend.main import SessionLocal, AuditLog


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
    old_secret = main_mod.AUTH_CONFIG.jwt_secret
    old_algs = main_mod.AUTH_CONFIG.jwt_algorithms
    main_mod.AUTH_CONFIG.mode = "jwt"
    main_mod.AUTH_CONFIG.jwt_secret = "test-secret"
    main_mod.AUTH_CONFIG.jwt_algorithms = ("HS256",)
    try:
        r = client.get("/api/wells")
        assert r.status_code == 401
    finally:
        main_mod.AUTH_CONFIG.mode = old_mode
        main_mod.AUTH_CONFIG.jwt_secret = old_secret
        main_mod.AUTH_CONFIG.jwt_algorithms = old_algs


def test_jwt_mode_accepts_valid_signed_token_for_viewer_read():
    import jwt
    from backend import main as main_mod

    old_mode = main_mod.AUTH_CONFIG.mode
    old_secret = main_mod.AUTH_CONFIG.jwt_secret
    old_algs = main_mod.AUTH_CONFIG.jwt_algorithms
    main_mod.AUTH_CONFIG.mode = "jwt"
    main_mod.AUTH_CONFIG.jwt_secret = "test-secret"
    main_mod.AUTH_CONFIG.jwt_algorithms = ("HS256",)

    token = jwt.encode({"sub": "u1", "role": "viewer"}, "test-secret", algorithm="HS256")
    try:
        r = client.get("/api/wells", headers={"Authorization": f"Bearer {token}"})
        assert r.status_code == 200
    finally:
        main_mod.AUTH_CONFIG.mode = old_mode
        main_mod.AUTH_CONFIG.jwt_secret = old_secret
        main_mod.AUTH_CONFIG.jwt_algorithms = old_algs


def test_jwt_mode_enforces_role_from_signed_token():
    import jwt
    from backend import main as main_mod

    old_mode = main_mod.AUTH_CONFIG.mode
    old_secret = main_mod.AUTH_CONFIG.jwt_secret
    old_algs = main_mod.AUTH_CONFIG.jwt_algorithms
    main_mod.AUTH_CONFIG.mode = "jwt"
    main_mod.AUTH_CONFIG.jwt_secret = "test-secret"
    main_mod.AUTH_CONFIG.jwt_algorithms = ("HS256",)

    token = jwt.encode({"sub": "u2", "role": "viewer"}, "test-secret", algorithm="HS256")
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
    try:
        r = client.post(
            "/api/wells/999999/sensitivity",
            headers={"Authorization": f"Bearer {token}"},
            json=payload,
        )
        assert r.status_code == 403
    finally:
        main_mod.AUTH_CONFIG.mode = old_mode
        main_mod.AUTH_CONFIG.jwt_secret = old_secret
        main_mod.AUTH_CONFIG.jwt_algorithms = old_algs


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


def test_jwt_mode_enforces_issuer_and_audience_valid():
    import jwt
    from backend import main as main_mod

    old_mode = main_mod.AUTH_CONFIG.mode
    old_secret = main_mod.AUTH_CONFIG.jwt_secret
    old_algs = main_mod.AUTH_CONFIG.jwt_algorithms
    old_iss = main_mod.AUTH_CONFIG.jwt_issuer
    old_aud = main_mod.AUTH_CONFIG.jwt_audience

    main_mod.AUTH_CONFIG.mode = "jwt"
    main_mod.AUTH_CONFIG.jwt_secret = "test-secret"
    main_mod.AUTH_CONFIG.jwt_algorithms = ("HS256",)
    main_mod.AUTH_CONFIG.jwt_issuer = "geolog-auth"
    main_mod.AUTH_CONFIG.jwt_audience = "geolog-api"

    token = jwt.encode(
        {"sub": "u3", "role": "viewer", "iss": "geolog-auth", "aud": "geolog-api"},
        "test-secret",
        algorithm="HS256",
    )
    try:
        r = client.get("/api/wells", headers={"Authorization": f"Bearer {token}"})
        assert r.status_code == 200
    finally:
        main_mod.AUTH_CONFIG.mode = old_mode
        main_mod.AUTH_CONFIG.jwt_secret = old_secret
        main_mod.AUTH_CONFIG.jwt_algorithms = old_algs
        main_mod.AUTH_CONFIG.jwt_issuer = old_iss
        main_mod.AUTH_CONFIG.jwt_audience = old_aud


def test_jwt_mode_rejects_wrong_issuer():
    import jwt
    from backend import main as main_mod

    old_mode = main_mod.AUTH_CONFIG.mode
    old_secret = main_mod.AUTH_CONFIG.jwt_secret
    old_algs = main_mod.AUTH_CONFIG.jwt_algorithms
    old_iss = main_mod.AUTH_CONFIG.jwt_issuer

    main_mod.AUTH_CONFIG.mode = "jwt"
    main_mod.AUTH_CONFIG.jwt_secret = "test-secret"
    main_mod.AUTH_CONFIG.jwt_algorithms = ("HS256",)
    main_mod.AUTH_CONFIG.jwt_issuer = "expected-issuer"
    main_mod.AUTH_CONFIG.jwt_audience = None

    token = jwt.encode({"sub": "u4", "role": "viewer", "iss": "wrong-issuer"}, "test-secret", algorithm="HS256")
    try:
        r = client.get("/api/wells", headers={"Authorization": f"Bearer {token}"})
        assert r.status_code == 401
    finally:
        main_mod.AUTH_CONFIG.mode = old_mode
        main_mod.AUTH_CONFIG.jwt_secret = old_secret
        main_mod.AUTH_CONFIG.jwt_algorithms = old_algs
        main_mod.AUTH_CONFIG.jwt_issuer = old_iss


def test_jwt_mode_rejects_wrong_audience():
    import jwt
    from backend import main as main_mod

    old_mode = main_mod.AUTH_CONFIG.mode
    old_secret = main_mod.AUTH_CONFIG.jwt_secret
    old_algs = main_mod.AUTH_CONFIG.jwt_algorithms
    old_aud = main_mod.AUTH_CONFIG.jwt_audience

    main_mod.AUTH_CONFIG.mode = "jwt"
    main_mod.AUTH_CONFIG.jwt_secret = "test-secret"
    main_mod.AUTH_CONFIG.jwt_algorithms = ("HS256",)
    main_mod.AUTH_CONFIG.jwt_issuer = None
    main_mod.AUTH_CONFIG.jwt_audience = "expected-aud"

    token = jwt.encode({"sub": "u5", "role": "viewer", "aud": "wrong-aud"}, "test-secret", algorithm="HS256")
    try:
        r = client.get("/api/wells", headers={"Authorization": f"Bearer {token}"})
        assert r.status_code == 401
    finally:
        main_mod.AUTH_CONFIG.mode = old_mode
        main_mod.AUTH_CONFIG.jwt_secret = old_secret
        main_mod.AUTH_CONFIG.jwt_algorithms = old_algs
        main_mod.AUTH_CONFIG.jwt_audience = old_aud


def test_jwt_mode_uses_roles_array_fallback():
    import jwt
    from backend import main as main_mod

    old_mode = main_mod.AUTH_CONFIG.mode
    old_secret = main_mod.AUTH_CONFIG.jwt_secret
    old_algs = main_mod.AUTH_CONFIG.jwt_algorithms

    main_mod.AUTH_CONFIG.mode = "jwt"
    main_mod.AUTH_CONFIG.jwt_secret = "test-secret"
    main_mod.AUTH_CONFIG.jwt_algorithms = ("HS256",)
    main_mod.AUTH_CONFIG.jwt_issuer = None
    main_mod.AUTH_CONFIG.jwt_audience = None

    token = jwt.encode({"sub": "u6", "roles": ["interpreter"]}, "test-secret", algorithm="HS256")
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
    try:
        r = client.post(
            "/api/wells/999999/sensitivity",
            headers={"Authorization": f"Bearer {token}"},
            json=payload,
        )
        # should pass auth+RBAC, then fail domain (well not found)
        assert r.status_code == 404
    finally:
        main_mod.AUTH_CONFIG.mode = old_mode
        main_mod.AUTH_CONFIG.jwt_secret = old_secret
        main_mod.AUTH_CONFIG.jwt_algorithms = old_algs


def test_immutable_audit_chain_records_successful_writes():
    wells = client.get("/api/wells", headers=_h("viewer"))
    assert wells.status_code == 200
    ws = wells.json()
    assert len(ws) >= 2
    w1, w2 = ws[0]["id"], ws[1]["id"]

    payload1 = {"well_a_id": w1, "well_b_id": w2, "depth_a": 1000.0, "depth_b": 1001.0, "label": "chain-a"}
    payload2 = {"well_a_id": w1, "well_b_id": w2, "depth_a": 1002.0, "depth_b": 1003.0, "label": "chain-b"}

    r1 = client.post("/api/correlation-markers", headers=_h("interpreter"), json=payload1)
    assert r1.status_code in (200, 201)
    r2 = client.post("/api/correlation-markers", headers=_h("interpreter"), json=payload2)
    assert r2.status_code in (200, 201)

    db = SessionLocal()
    try:
        rows = (
            db.query(AuditLog)
            .filter(AuditLog.action == "write:post", AuditLog.route_path == "/api/correlation-markers")
            .order_by(AuditLog.id.desc())
            .limit(2)
            .all()
        )
        assert len(rows) == 2
        newest, previous = rows[0], rows[1]
        assert (newest.entry_hash or "") != "" and len(newest.entry_hash or "") == 64
        assert (newest.payload_hash or "") != "" and len(newest.payload_hash or "") == 64
        assert (newest.prev_hash or "") == (previous.entry_hash or "")
    finally:
        db.close()


def test_audit_verify_endpoint_reports_ok_for_clean_chain():
    r = client.get("/api/audit-log/verify", headers=_h("viewer"))
    assert r.status_code == 200
    data = r.json()
    assert "ok" in data and "verified_entries" in data and "issues" in data
    assert isinstance(data["issues"], list)


def test_audit_verify_endpoint_detects_tamper_gap():
    db = SessionLocal()
    target_id = None
    old_prev = None
    try:
        row = db.query(AuditLog).filter(AuditLog.action == "write:post").order_by(AuditLog.id.desc()).first()
        assert row is not None
        target_id = row.id
        old_prev = row.prev_hash
        row.prev_hash = "tampered_prev_hash"
        db.commit()
    finally:
        db.close()

    try:
        r = client.get("/api/audit-log/verify", headers=_h("viewer"))
        assert r.status_code == 200
        data = r.json()
        assert data["ok"] is False
        assert any((it.get("id") == target_id and it.get("type") == "prev_hash_mismatch") for it in data["issues"])
    finally:
        db2 = SessionLocal()
        try:
            row2 = db2.query(AuditLog).filter(AuditLog.id == target_id).first()
            if row2 is not None:
                row2.prev_hash = old_prev
                db2.commit()
        finally:
            db2.close()
