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
    bad_id = None
    try:
        prev = db.query(AuditLog).order_by(AuditLog.id.desc()).first()
        prev_hash = (prev.entry_hash if prev else "") or ""
        bad = AuditLog(
            action="write:post",
            entity_type="api",
            details="/api/fake",
            request_id="tamper-test",
            auth_subject="u-test",
            auth_role="interpreter",
            route_path="/api/fake",
            method="POST",
            status_code=200,
            payload_hash="0" * 64,
            prev_hash=prev_hash,
            entry_hash="f" * 64,  # intentionally wrong
        )
        db.add(bad)
        db.commit()
        bad_id = bad.id
    finally:
        db.close()

    r = client.get("/api/audit-log/verify", headers=_h("viewer"))
    assert r.status_code == 200
    data = r.json()
    assert data["ok"] is False
    assert any((it.get("id") == bad_id and it.get("type") == "entry_hash_mismatch") for it in data["issues"])


def test_audit_log_update_is_blocked_by_trigger():
    db = SessionLocal()
    try:
        row = db.query(AuditLog).order_by(AuditLog.id.desc()).first()
        assert row is not None
        row.details = "mutated"
        blocked = False
        try:
            db.commit()
        except Exception:
            blocked = True
            db.rollback()
        assert blocked is True
    finally:
        db.close()


def test_audit_log_delete_is_blocked_by_trigger():
    db = SessionLocal()
    try:
        row = db.query(AuditLog).order_by(AuditLog.id.desc()).first()
        assert row is not None
        blocked = False
        try:
            db.delete(row)
            db.commit()
        except Exception:
            blocked = True
            db.rollback()
        assert blocked is True
    finally:
        db.close()


def test_audit_verify_export_has_valid_digest():
    import hashlib
    import json

    r = client.get("/api/audit-log/verify/export", headers=_h("viewer"))
    assert r.status_code == 200
    data = r.json()
    assert "digest_sha256" in data and "payload" in data
    assert isinstance(data["digest_sha256"], str) and len(data["digest_sha256"]) == 64

    canonical = json.dumps(data["payload"], sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    recomputed = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    assert recomputed == data["digest_sha256"]


def test_audit_verify_export_contains_report_shape():
    r = client.get("/api/audit-log/verify/export", headers=_h("viewer"))
    assert r.status_code == 200
    data = r.json()
    payload = data.get("payload", {})
    report = payload.get("report", {})
    assert "generated_at" in payload
    assert "ok" in report
    assert "verified_entries" in report
    assert "issues" in report
    assert data.get("signature") is None
    assert data.get("signature_alg") is None
    assert data.get("signature_detached") is True


def test_audit_verify_export_hmac_signature():
    import hashlib
    import hmac
    import json
    import os

    old = os.environ.get("AUDIT_EXPORT_HMAC_KEY")
    os.environ["AUDIT_EXPORT_HMAC_KEY"] = "unit-test-key"
    try:
        r = client.get("/api/audit-log/verify/export?sign=true", headers=_h("viewer"))
        assert r.status_code == 200
        data = r.json()
        payload = data["payload"]
        canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
        expected = hmac.new(b"unit-test-key", canonical.encode("utf-8"), hashlib.sha256).hexdigest()
        assert data.get("signature_alg") == "hmac-sha256"
        assert data.get("signature_detached") is True
        assert data.get("signature") == expected
    finally:
        if old is None:
            os.environ.pop("AUDIT_EXPORT_HMAC_KEY", None)
        else:
            os.environ["AUDIT_EXPORT_HMAC_KEY"] = old


def test_audit_verify_export_hmac_missing_key_fails():
    import os

    old = os.environ.get("AUDIT_EXPORT_HMAC_KEY")
    os.environ.pop("AUDIT_EXPORT_HMAC_KEY", None)
    os.environ.pop("AUDIT_EXPORT_HMAC_KEYS_JSON", None)
    os.environ.pop("AUDIT_EXPORT_HMAC_ACTIVE_KID", None)
    try:
        r = client.get("/api/audit-log/verify/export?sign=true", headers=_h("viewer"))
        assert r.status_code == 500
    finally:
        if old is not None:
            os.environ["AUDIT_EXPORT_HMAC_KEY"] = old


def test_audit_verify_export_hmac_uses_active_kid_from_keyring():
    import hashlib
    import hmac
    import json
    import os

    old_json = os.environ.get("AUDIT_EXPORT_HMAC_KEYS_JSON")
    old_active = os.environ.get("AUDIT_EXPORT_HMAC_ACTIVE_KID")
    old_legacy = os.environ.get("AUDIT_EXPORT_HMAC_KEY")

    os.environ["AUDIT_EXPORT_HMAC_KEYS_JSON"] = '{"k1":"key-one","k2":"key-two"}'
    os.environ["AUDIT_EXPORT_HMAC_ACTIVE_KID"] = "k2"
    os.environ.pop("AUDIT_EXPORT_HMAC_KEY", None)

    try:
        r = client.get("/api/audit-log/verify/export?sign=true", headers=_h("viewer"))
        assert r.status_code == 200
        data = r.json()
        canonical = json.dumps(data["payload"], sort_keys=True, separators=(",", ":"), ensure_ascii=False)
        expected = hmac.new(b"key-two", canonical.encode("utf-8"), hashlib.sha256).hexdigest()
        assert data.get("signature") == expected
        assert data.get("signature_kid") == "k2"
    finally:
        if old_json is None:
            os.environ.pop("AUDIT_EXPORT_HMAC_KEYS_JSON", None)
        else:
            os.environ["AUDIT_EXPORT_HMAC_KEYS_JSON"] = old_json
        if old_active is None:
            os.environ.pop("AUDIT_EXPORT_HMAC_ACTIVE_KID", None)
        else:
            os.environ["AUDIT_EXPORT_HMAC_ACTIVE_KID"] = old_active
        if old_legacy is None:
            os.environ.pop("AUDIT_EXPORT_HMAC_KEY", None)
        else:
            os.environ["AUDIT_EXPORT_HMAC_KEY"] = old_legacy


def test_audit_verify_export_hmac_honors_requested_kid():
    import hashlib
    import hmac
    import json
    import os

    old_json = os.environ.get("AUDIT_EXPORT_HMAC_KEYS_JSON")
    old_active = os.environ.get("AUDIT_EXPORT_HMAC_ACTIVE_KID")

    os.environ["AUDIT_EXPORT_HMAC_KEYS_JSON"] = '{"k1":"key-one","k2":"key-two"}'
    os.environ["AUDIT_EXPORT_HMAC_ACTIVE_KID"] = "k2"
    try:
        r = client.get("/api/audit-log/verify/export?sign=true&kid=k1", headers=_h("viewer"))
        assert r.status_code == 200
        data = r.json()
        canonical = json.dumps(data["payload"], sort_keys=True, separators=(",", ":"), ensure_ascii=False)
        expected = hmac.new(b"key-one", canonical.encode("utf-8"), hashlib.sha256).hexdigest()
        assert data.get("signature") == expected
        assert data.get("signature_kid") == "k1"
    finally:
        if old_json is None:
            os.environ.pop("AUDIT_EXPORT_HMAC_KEYS_JSON", None)
        else:
            os.environ["AUDIT_EXPORT_HMAC_KEYS_JSON"] = old_json
        if old_active is None:
            os.environ.pop("AUDIT_EXPORT_HMAC_ACTIVE_KID", None)
        else:
            os.environ["AUDIT_EXPORT_HMAC_ACTIVE_KID"] = old_active


def test_audit_verify_export_hmac_unknown_kid_fails():
    import os

    old_json = os.environ.get("AUDIT_EXPORT_HMAC_KEYS_JSON")
    old_active = os.environ.get("AUDIT_EXPORT_HMAC_ACTIVE_KID")

    os.environ["AUDIT_EXPORT_HMAC_KEYS_JSON"] = '{"k1":"key-one"}'
    os.environ["AUDIT_EXPORT_HMAC_ACTIVE_KID"] = "k1"
    try:
        r = client.get("/api/audit-log/verify/export?sign=true&kid=missing", headers=_h("viewer"))
        assert r.status_code == 400
    finally:
        if old_json is None:
            os.environ.pop("AUDIT_EXPORT_HMAC_KEYS_JSON", None)
        else:
            os.environ["AUDIT_EXPORT_HMAC_KEYS_JSON"] = old_json
        if old_active is None:
            os.environ.pop("AUDIT_EXPORT_HMAC_ACTIVE_KID", None)
        else:
            os.environ["AUDIT_EXPORT_HMAC_ACTIVE_KID"] = old_active


def test_audit_verify_signature_endpoint_valid_and_mismatch():
    import os

    old = os.environ.get("AUDIT_EXPORT_HMAC_KEY")
    os.environ["AUDIT_EXPORT_HMAC_KEY"] = "unit-test-key"
    try:
        exported = client.get("/api/audit-log/verify/export?sign=true", headers=_h("viewer"))
        assert exported.status_code == 200
        data = exported.json()

        import json

        payload_json = json.dumps(data["payload"], sort_keys=True, separators=(",", ":"), ensure_ascii=False)
        ok_r = client.get(
            "/api/audit-log/verify/signature",
            headers=_h("viewer"),
            params={
                "payload": payload_json,
                "signature": data["signature"],
                "kid": data.get("signature_kid"),
            },
        )
        assert ok_r.status_code == 200
        ok_data = ok_r.json()
        assert ok_data["ok"] is True
        assert ok_data["reason"] == "signature_valid"
        assert ok_data["reason_code"] == "SIGNATURE_VALID"

        bad_r = client.get(
            "/api/audit-log/verify/signature",
            headers=_h("viewer"),
            params={
                "payload": payload_json,
                "signature": "0" * 64,
                "kid": data.get("signature_kid"),
            },
        )
        assert bad_r.status_code == 200
        bad_data = bad_r.json()
        assert bad_data["ok"] is False
        assert bad_data["reason"] == "signature_mismatch"
        assert bad_data["reason_code"] == "SIGNATURE_MISMATCH"
    finally:
        if old is None:
            os.environ.pop("AUDIT_EXPORT_HMAC_KEY", None)
        else:
            os.environ["AUDIT_EXPORT_HMAC_KEY"] = old


def test_audit_verify_signature_endpoint_unknown_kid_returns_fail_reason():
    import os

    old_json = os.environ.get("AUDIT_EXPORT_HMAC_KEYS_JSON")
    old_active = os.environ.get("AUDIT_EXPORT_HMAC_ACTIVE_KID")
    old_legacy = os.environ.get("AUDIT_EXPORT_HMAC_KEY")

    os.environ["AUDIT_EXPORT_HMAC_KEYS_JSON"] = '{"k1":"key-one"}'
    os.environ["AUDIT_EXPORT_HMAC_ACTIVE_KID"] = "k1"
    os.environ.pop("AUDIT_EXPORT_HMAC_KEY", None)

    try:
        exported = client.get("/api/audit-log/verify/export?sign=true&kid=k1", headers=_h("viewer"))
        assert exported.status_code == 200
        data = exported.json()

        import json

        payload_json = json.dumps(data["payload"], sort_keys=True, separators=(",", ":"), ensure_ascii=False)
        r = client.get(
            "/api/audit-log/verify/signature",
            headers=_h("viewer"),
            params={
                "payload": payload_json,
                "signature": data["signature"],
                "kid": "missing",
            },
        )
        assert r.status_code == 200
        out = r.json()
        assert out["ok"] is False
        assert "unknown signature kid" in out["reason"]
        assert out["reason_code"] == "UNKNOWN_KID"
    finally:
        if old_json is None:
            os.environ.pop("AUDIT_EXPORT_HMAC_KEYS_JSON", None)
        else:
            os.environ["AUDIT_EXPORT_HMAC_KEYS_JSON"] = old_json
        if old_active is None:
            os.environ.pop("AUDIT_EXPORT_HMAC_ACTIVE_KID", None)
        else:
            os.environ["AUDIT_EXPORT_HMAC_ACTIVE_KID"] = old_active
        if old_legacy is None:
            os.environ.pop("AUDIT_EXPORT_HMAC_KEY", None)
        else:
            os.environ["AUDIT_EXPORT_HMAC_KEY"] = old_legacy


def test_audit_verify_signature_openapi_reason_code_enum_present():
    r = client.get("/openapi.json")
    assert r.status_code == 200
    data = r.json()

    schemas = data.get("components", {}).get("schemas", {})
    resp_schema = schemas.get("AuditSignatureVerifyResponse")
    assert resp_schema is not None

    reason_code = resp_schema.get("properties", {}).get("reason_code", {})
    enum_vals = set(reason_code.get("enum", []))
    assert {
        "SIGNATURE_VALID",
        "SIGNATURE_MISMATCH",
        "UNKNOWN_KID",
        "INVALID_KEYRING_JSON",
        "ACTIVE_KID_MISSING",
        "KEY_NOT_CONFIGURED",
        "KEY_RESOLUTION_ERROR",
    }.issubset(enum_vals)


def test_audit_verify_signature_post_requires_interpreter():
    r = client.post(
        "/api/audit-log/verify/signature",
        headers=_h("viewer"),
        json={"payload": {}, "signature": "0" * 64},
    )
    assert r.status_code == 403


def test_audit_verify_signature_post_interpreter_ok_and_mismatch():
    import os

    old = os.environ.get("AUDIT_EXPORT_HMAC_KEY")
    os.environ["AUDIT_EXPORT_HMAC_KEY"] = "unit-test-key"
    try:
        exported = client.get("/api/audit-log/verify/export?sign=true", headers=_h("viewer"))
        assert exported.status_code == 200
        data = exported.json()

        ok_r = client.post(
            "/api/audit-log/verify/signature",
            headers=_h("interpreter"),
            json={
                "payload": data["payload"],
                "signature": data["signature"],
                "kid": data.get("signature_kid"),
            },
        )
        assert ok_r.status_code == 200
        assert ok_r.json().get("ok") is True

        bad_r = client.post(
            "/api/audit-log/verify/signature",
            headers=_h("interpreter"),
            json={
                "payload": data["payload"],
                "signature": "f" * 64,
                "kid": data.get("signature_kid"),
            },
        )
        assert bad_r.status_code == 200
        out = bad_r.json()
        assert out.get("ok") is False
        assert out.get("reason") == "signature_mismatch"
        assert out.get("reason_code") == "SIGNATURE_MISMATCH"
    finally:
        if old is None:
            os.environ.pop("AUDIT_EXPORT_HMAC_KEY", None)
        else:
            os.environ["AUDIT_EXPORT_HMAC_KEY"] = old
