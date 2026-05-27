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


def test_audit_verify_signature_get_rejects_non_hex_signature():
    r = client.get(
        "/api/audit-log/verify/signature",
        headers=_h("viewer"),
        params={
            "payload": "{}",
            "signature": "z" * 64,
        },
    )
    assert r.status_code == 400
    assert "64-char hex" in str(r.json().get("detail", ""))


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


def test_ops_metrics_viewer_access_and_shape():
    # trigger one request so counters move
    _ = client.get("/api/wells", headers=_h("viewer"))

    r = client.get("/api/ops/metrics", headers=_h("viewer"))
    assert r.status_code == 200
    data = r.json()

    assert "requests_total" in data
    assert "requests_by_method" in data
    assert "requests_by_status" in data
    assert "latency_ms_avg" in data
    assert "latency_samples" in data
    assert "recent_events_size" in data
    assert data["requests_total"] >= 1
    assert isinstance(data["requests_by_method"], dict)
    assert isinstance(data["requests_by_status"], dict)


def test_ops_metrics_requires_viewer_role_floor():
    # unknown role normalized to viewer by auth layer; should still pass read access
    r = client.get("/api/ops/metrics", headers=_h("unknown"))
    assert r.status_code == 200


def test_ops_metrics_recent_shape_and_limit():
    _ = client.get("/api/wells", headers=_h("viewer"))
    _ = client.get("/api/projects", headers=_h("viewer"))

    r = client.get("/api/ops/metrics/recent?limit=5", headers=_h("viewer"))
    assert r.status_code == 200
    data = r.json()
    assert "events" in data
    assert "count" in data
    assert "limit" in data
    assert "status_min" in data
    assert "path_contains" in data
    assert data["limit"] == 5
    assert isinstance(data["events"], list)
    assert data["count"] <= 5
    if data["events"]:
        e = data["events"][-1]
        assert "method" in e
        assert "path" in e
        assert "status" in e
        assert "latency_ms" in e


def test_ops_metrics_recent_filters():
    _ = client.get("/api/does-not-exist", headers=_h("viewer"))
    _ = client.get("/api/wells", headers=_h("viewer"))

    r = client.get(
        "/api/ops/metrics/recent?limit=20&status_min=400&path_contains=does-not-exist",
        headers=_h("viewer"),
    )
    assert r.status_code == 200
    data = r.json()
    for e in data.get("events", []):
        assert int(e.get("status", 0)) >= 400
        assert "does-not-exist" in str(e.get("path", "")).lower()


def test_ops_metrics_recent_unknown_role_allowed_as_viewer_floor():
    r = client.get("/api/ops/metrics/recent", headers=_h("unknown"))
    assert r.status_code == 200


def test_ops_slo_status_shape_and_access():
    # generate some traffic
    _ = client.get("/api/wells", headers=_h("viewer"))
    _ = client.get("/api/does-not-exist", headers=_h("viewer"))

    r = client.get("/api/ops/slo-status", headers=_h("viewer"))
    assert r.status_code == 200
    data = r.json()

    assert "ok" in data
    assert "targets" in data
    assert "current" in data
    assert "checks" in data

    assert "latency_ms_avg_max" in data["targets"]
    assert "latency_ms_p95_max" in data["targets"]
    assert "error_rate_max" in data["targets"]
    assert "latency_ms_avg" in data["current"]
    assert "latency_ms_p95" in data["current"]
    assert "error_rate" in data["current"]
    assert "requests_total" in data["current"]
    assert "errors_5xx" in data["current"]
    assert "latency_ok" in data["checks"]
    assert "latency_avg_ok" in data["checks"]
    assert "latency_p95_ok" in data["checks"]
    assert "error_rate_ok" in data["checks"]


def test_ops_slo_status_unknown_role_allowed_as_viewer_floor():
    r = client.get("/api/ops/slo-status", headers=_h("unknown"))
    assert r.status_code == 200


def test_ops_alerts_shape_and_access():
    r = client.get("/api/ops/alerts", headers=_h("viewer"))
    assert r.status_code == 200
    data = r.json()
    assert "ok" in data
    assert "alerts" in data
    assert "count" in data
    assert "severity_counts" in data
    assert "code_counts" in data
    assert "highest_severity" in data
    assert isinstance(data["alerts"], list)
    assert isinstance(data["severity_counts"], dict)
    assert isinstance(data["code_counts"], dict)
    assert data["highest_severity"] in {"none", "warning", "critical"}
    assert "warning" in data["severity_counts"]
    assert "critical" in data["severity_counts"]


def test_ops_alerts_can_report_breach_with_strict_env_thresholds():
    import os

    old_lat = os.environ.get("OPS_SLO_P95_MS")
    old_err = os.environ.get("OPS_SLO_ERROR_RATE")
    os.environ["OPS_SLO_P95_MS"] = "0"
    os.environ["OPS_SLO_ERROR_RATE"] = "0"

    try:
        _ = client.get("/api/wells", headers=_h("viewer"))
        _ = client.get("/api/does-not-exist", headers=_h("viewer"))
        r = client.get("/api/ops/alerts", headers=_h("viewer"))
        assert r.status_code == 200
        data = r.json()
        assert data["ok"] is False
        codes = {a.get("code") for a in data.get("alerts", [])}
        assert (
            "LATENCY_AVG_SLO_BREACH" in codes
            or "LATENCY_P95_SLO_BREACH" in codes
            or "ERROR_RATE_SLO_BREACH" in codes
        )
        sev = data.get("severity_counts", {})
        codes_count = data.get("code_counts", {})
        hs = data.get("highest_severity")
        assert isinstance(sev, dict)
        assert isinstance(codes_count, dict)
        assert hs in {"none", "warning", "critical"}
        assert int(sev.get("warning", 0)) >= 0
        assert int(sev.get("critical", 0)) >= 0
        assert int(sev.get("warning", 0)) + int(sev.get("critical", 0)) == int(data.get("count", 0))
        assert sum(int(v) for v in codes_count.values()) == int(data.get("count", 0))
        if int(sev.get("critical", 0)) > 0:
            assert hs == "critical"
        elif int(sev.get("warning", 0)) > 0:
            assert hs == "warning"
        else:
            assert hs == "none"
    finally:
        if old_lat is None:
            os.environ.pop("OPS_SLO_P95_MS", None)
        else:
            os.environ["OPS_SLO_P95_MS"] = old_lat
        if old_err is None:
            os.environ.pop("OPS_SLO_ERROR_RATE", None)
        else:
            os.environ["OPS_SLO_ERROR_RATE"] = old_err


def test_ops_metrics_prometheus_exposition_shape():
    _ = client.get("/api/wells", headers=_h("viewer"))
    r = client.get("/api/ops/metrics/prometheus", headers=_h("viewer"))
    assert r.status_code == 200
    text = r.text
    assert "# HELP geolog_requests_total" in text
    assert "# TYPE geolog_requests_total counter" in text
    assert "geolog_requests_total" in text
    assert "geolog_request_latency_ms_sum" in text
    assert "geolog_request_latency_ms_count" in text


def test_ops_health_shape_and_access():
    r = client.get("/api/ops/health", headers=_h("viewer"))
    assert r.status_code == 200
    data = r.json()
    assert "ok" in data
    assert "db_ok" in data
    assert "slo_ok" in data
    assert "alerts_ok" in data
    assert "alert_count" in data


def test_ops_health_unknown_role_allowed_as_viewer_floor():
    r = client.get("/api/ops/health", headers=_h("unknown"))
    assert r.status_code == 200


def test_ops_summary_shape_and_access():
    _ = client.get("/api/wells", headers=_h("viewer"))
    r = client.get("/api/ops/summary", headers=_h("viewer"))
    assert r.status_code == 200
    data = r.json()

    assert "ok" in data
    assert "contract_version" in data
    assert "status" in data
    assert "alerts" in data
    assert "traffic" in data
    assert "slo" in data

    status = data["status"]
    alerts = data["alerts"]
    traffic = data["traffic"]
    slo = data["slo"]

    assert "db_ok" in status
    assert "slo_ok" in status
    assert "alerts_ok" in status

    assert "count" in alerts
    assert "highest_severity" in alerts
    assert "severity_counts" in alerts
    assert "code_counts" in alerts

    assert "requests_total" in traffic
    assert "latency_ms_avg" in traffic
    assert "error_rate" in traffic
    assert "recent_events_size" in traffic

    assert "targets" in slo
    assert "current" in slo
    assert "checks" in slo


def test_ops_summary_unknown_role_allowed_as_viewer_floor():
    r = client.get("/api/ops/summary", headers=_h("unknown"))
    assert r.status_code == 200


def test_ops_contracts_shape_and_access():
    r = client.get("/api/ops/contracts", headers=_h("viewer"))
    assert r.status_code == 200
    data = r.json()

    assert data.get("api_group") == "ops-audit"
    assert "contract_version" in data
    assert "digest_sha256" in data
    assert data.get("signature") is None
    assert data.get("signature_alg") is None
    assert data.get("signature_kid") is None
    digest = str(data.get("digest_sha256", ""))
    assert len(digest) == 64
    assert all(c in "0123456789abcdef" for c in digest.lower())
    endpoints = data.get("endpoints", {})
    assert isinstance(endpoints, dict)
    assert "/api/ops/summary" in endpoints
    assert "/api/ops/alerts" in endpoints
    assert "/api/audit-log/verify/signature" in endpoints


def test_ops_contracts_sign_hmac_with_requested_kid(monkeypatch):
    import os

    old_ring = os.environ.get("AUDIT_EXPORT_HMAC_KEYS_JSON")
    old_active = os.environ.get("AUDIT_EXPORT_HMAC_ACTIVE_KID")
    old_legacy = os.environ.get("AUDIT_EXPORT_HMAC_KEY")

    os.environ["AUDIT_EXPORT_HMAC_KEYS_JSON"] = '{"k1":"secret-one","k2":"secret-two"}'
    os.environ["AUDIT_EXPORT_HMAC_ACTIVE_KID"] = "k2"
    os.environ.pop("AUDIT_EXPORT_HMAC_KEY", None)

    try:
        r = client.get("/api/ops/contracts?sign=true&kid=k1", headers=_h("viewer"))
        assert r.status_code == 200
        data = r.json()
        sig = str(data.get("signature") or "")
        assert len(sig) == 64
        assert data.get("signature_alg") == "hmac-sha256"
        assert data.get("signature_kid") == "k1"

        rv = client.get(f"/api/ops/contracts/verify-signature?kid=k1&signature={sig}", headers=_h("viewer"))
        assert rv.status_code == 200
        out = rv.json()
        assert out.get("ok") is True
        assert out.get("reason_code") == "SIGNATURE_VALID"

        rp = client.post(
            "/api/ops/contracts/verify-signature",
            headers=_h("interpreter"),
            json={"payload": {"ignored": True}, "signature": sig, "kid": "k1"},
        )
        assert rp.status_code == 200
        outp = rp.json()
        assert outp.get("ok") is True
        assert outp.get("reason_code") == "SIGNATURE_VALID"

        rf = client.post(
            "/api/ops/contracts/verify-signature",
            headers=_h("viewer"),
            json={"payload": {"ignored": True}, "signature": sig, "kid": "k1"},
        )
        assert rf.status_code == 403
    finally:
        if old_ring is None:
            os.environ.pop("AUDIT_EXPORT_HMAC_KEYS_JSON", None)
        else:
            os.environ["AUDIT_EXPORT_HMAC_KEYS_JSON"] = old_ring
        if old_active is None:
            os.environ.pop("AUDIT_EXPORT_HMAC_ACTIVE_KID", None)
        else:
            os.environ["AUDIT_EXPORT_HMAC_ACTIVE_KID"] = old_active
        if old_legacy is None:
            os.environ.pop("AUDIT_EXPORT_HMAC_KEY", None)
        else:
            os.environ["AUDIT_EXPORT_HMAC_KEY"] = old_legacy


def test_ops_contracts_verify_signature_rejects_non_hex_signature_formats():
    rg = client.get(
        "/api/ops/contracts/verify-signature",
        headers=_h("viewer"),
        params={"kid": "k1", "signature": "z" * 64},
    )
    assert rg.status_code == 400

    rp = client.post(
        "/api/ops/contracts/verify-signature",
        headers=_h("interpreter"),
        json={"payload": {"ignored": True}, "signature": "z" * 64, "kid": "k1"},
    )
    assert rp.status_code == 422


def test_ops_contracts_unknown_role_allowed_as_viewer_floor():
    r = client.get("/api/ops/contracts", headers=_h("unknown"))
    assert r.status_code == 200


def test_ops_summary_openapi_contract_present():
    r = client.get("/openapi.json")
    assert r.status_code == 200
    doc = r.json()

    op = doc.get("paths", {}).get("/api/ops/summary", {}).get("get", {})
    assert op.get("operationId")

    schemas = doc.get("components", {}).get("schemas", {})
    summary = schemas.get("OpsSummaryResponse", {})
    props = summary.get("properties", {})
    assert "contract_version" in props
    assert "status" in props
    assert "alerts" in props
    assert "traffic" in props
    assert "slo" in props


def test_ops_slo_and_alerts_openapi_contract_present():
    r = client.get("/openapi.json")
    assert r.status_code == 200
    doc = r.json()

    paths = doc.get("paths", {})
    metrics_get = paths.get("/api/ops/metrics", {}).get("get", {})
    metrics_recent_get = paths.get("/api/ops/metrics/recent", {}).get("get", {})
    metrics_prom_get = paths.get("/api/ops/metrics/prometheus", {}).get("get", {})
    slo_get = paths.get("/api/ops/slo-status", {}).get("get", {})
    alerts_get = paths.get("/api/ops/alerts", {}).get("get", {})
    health_get = paths.get("/api/ops/health", {}).get("get", {})
    contracts_get = paths.get("/api/ops/contracts", {}).get("get", {})
    contracts_verify_path = paths.get("/api/ops/contracts/verify-signature", {})
    contracts_verify_get = contracts_verify_path.get("get", {})
    contracts_verify_post = contracts_verify_path.get("post", {})
    runbook_get = paths.get("/api/ops/runbook", {}).get("get", {})
    assert metrics_get.get("operationId")
    assert metrics_recent_get.get("operationId")
    assert metrics_prom_get.get("operationId")
    assert slo_get.get("operationId")
    assert alerts_get.get("operationId")
    assert health_get.get("operationId")
    assert contracts_get.get("operationId")
    assert contracts_verify_get.get("operationId")
    assert contracts_verify_post.get("operationId")
    assert runbook_get.get("operationId")

    prom_200 = metrics_prom_get.get("responses", {}).get("200", {})
    prom_content = prom_200.get("content", {})
    assert "text/plain" in prom_content

    schemas = doc.get("components", {}).get("schemas", {})
    assert "OpsMetricsResponse" in schemas
    assert "OpsMetricsRecentResponse" in schemas
    assert "OpsSloStatusResponse" in schemas
    assert "OpsAlertsResponse" in schemas
    assert "OpsHealthResponse" in schemas
    assert "OpsContractsResponse" in schemas
    assert "OpsRunbookResponse" in schemas

    contracts_schema = schemas.get("OpsContractsResponse", {})
    contracts_props = contracts_schema.get("properties", {})
    assert "digest_sha256" in contracts_props
    assert "signature" in contracts_props
    assert "signature_alg" in contracts_props
    assert "signature_kid" in contracts_props


def test_ops_runbook_shape_and_alert_entries():
    r = client.get("/api/ops/runbook", headers=_h("viewer"))
    assert r.status_code == 200
    data = r.json()

    assert data.get("version") == "1.0"
    alerts = data.get("alerts", {})
    assert "LATENCY_AVG_SLO_BREACH" in alerts
    assert "LATENCY_P95_SLO_BREACH" in alerts
    assert "ERROR_RATE_SLO_BREACH" in alerts

    lat_avg = alerts["LATENCY_AVG_SLO_BREACH"]
    lat_p95 = alerts["LATENCY_P95_SLO_BREACH"]
    err = alerts["ERROR_RATE_SLO_BREACH"]
    assert lat_avg.get("severity") == "warning"
    assert lat_p95.get("severity") == "warning"
    assert err.get("severity") == "critical"
    assert isinstance(lat_avg.get("checks"), list) and len(lat_avg.get("checks")) > 0
    assert isinstance(lat_p95.get("checks"), list) and len(lat_p95.get("checks")) > 0
    assert isinstance(err.get("actions"), list) and len(err.get("actions")) > 0


def test_ops_runbook_unknown_role_allowed_as_viewer_floor():
    r = client.get("/api/ops/runbook", headers=_h("unknown"))
    assert r.status_code == 200
