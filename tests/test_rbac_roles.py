from pathlib import Path
import sys
import tempfile

from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend import main as main_mod
from backend.main import app
from backend.main import SessionLocal, AuditLog
from backend.main import _compute_gate_invariants


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
        r = client.post("/api/wells/999999/sensitivity", headers={"Authorization": f"Bearer {token}"}, json=payload)
        assert r.status_code == 403
    finally:
        main_mod.AUTH_CONFIG.mode = old_mode
        main_mod.AUTH_CONFIG.jwt_secret = old_secret
        main_mod.AUTH_CONFIG.jwt_algorithms = old_algs


def test_secrets_source_policy_allows_dev_without_source(monkeypatch):
    from backend import main as main_mod

    monkeypatch.setenv("GEOLOG_ENV", "dev")
    monkeypatch.delenv("GEOLOG_SECRETS_SOURCE", raising=False)
    monkeypatch.setenv("GEOLOG_ENFORCE_SECRETS_SOURCE", "true")
    main_mod._enforce_secrets_source_policy()


def test_secrets_source_policy_blocks_prod_without_source(monkeypatch):
    from backend import main as main_mod

    monkeypatch.setenv("GEOLOG_ENV", "prod")
    monkeypatch.delenv("GEOLOG_SECRETS_SOURCE", raising=False)
    monkeypatch.setenv("GEOLOG_ENFORCE_SECRETS_SOURCE", "true")

    try:
        main_mod._enforce_secrets_source_policy()
        assert False, "expected RuntimeError"
    except RuntimeError as e:
        assert "GEOLOG_SECRETS_SOURCE" in str(e)


def test_secrets_source_policy_allows_prod_with_source(monkeypatch):
    from backend import main as main_mod

    monkeypatch.setenv("GEOLOG_ENV", "prod")
    monkeypatch.setenv("GEOLOG_SECRETS_SOURCE", "vault")
    monkeypatch.setenv("GEOLOG_ENFORCE_SECRETS_SOURCE", "true")
    main_mod._enforce_secrets_source_policy()


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


def test_audit_log_immutability_status_endpoint_reports_triggers_present():
    r = client.get("/api/audit-log/immutability-status", headers=_h("viewer"))
    assert r.status_code == 200
    data = r.json()
    assert data.get("ok") is True
    assert data.get("append_only_enforced") is True
    triggers = data.get("triggers", {})
    assert triggers.get("trg_audit_log_no_update") is True
    assert triggers.get("trg_audit_log_no_delete") is True


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
    r = client.get("/api/audit-log/verify/export?limit=321", headers=_h("viewer"))
    assert r.status_code == 200
    data = r.json()
    payload = data.get("payload", {})
    report = payload.get("report", {})
    trace = payload.get("trace", {})
    assert "generated_at" in payload
    assert "ok" in report
    assert "verified_entries" in report
    assert "issues" in report
    assert "request_id" in trace
    assert "auth_subject" in trace
    assert "auth_role" in trace
    assert "input" in trace and isinstance(trace.get("input"), dict)
    assert int(trace.get("input", {}).get("limit", 0)) == 321
    assert "code_version" in trace and isinstance(trace.get("code_version"), str)
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
    _ = client.get("/api/wells", headers=_h("viewer"), params={"_trace_seed": "1"})

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


def test_request_id_response_header_propagation():
    req_id = "rid-test-123"
    trace_id = "0af7651916cd43dd8448eb211c80319c"
    traceparent = f"00-{trace_id}-b7ad6b7169203331-01"
    r = client.get(
        "/api/ops/metrics",
        headers={**_h("viewer"), "X-Request-ID": req_id, "traceparent": traceparent},
    )
    assert r.status_code == 200
    assert r.headers.get("X-Request-ID") == req_id
    assert r.headers.get("X-Trace-ID") == trace_id


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


def test_ops_alert_rules_shape_and_env_thresholds():
    import os

    old_avg = os.environ.get("OPS_SLO_AVG_MS")
    old_p95 = os.environ.get("OPS_SLO_P95_MS")
    old_err = os.environ.get("OPS_SLO_ERROR_RATE")

    os.environ["OPS_SLO_AVG_MS"] = "321"
    os.environ["OPS_SLO_P95_MS"] = "654"
    os.environ["OPS_SLO_ERROR_RATE"] = "0.123"

    try:
        r = client.get("/api/ops/alert-rules", headers=_h("viewer"))
        assert r.status_code == 200
        data = r.json()
        assert data.get("version") == "1.0"
        rules = data.get("rules", [])
        assert isinstance(rules, list)
        assert len(rules) == 3

        by_code = {str(x.get("code")): x for x in rules if isinstance(x, dict)}
        assert "LATENCY_AVG_SLO_BREACH" in by_code
        assert "LATENCY_P95_SLO_BREACH" in by_code
        assert "ERROR_RATE_SLO_BREACH" in by_code

        assert float(by_code["LATENCY_AVG_SLO_BREACH"].get("threshold")) == 321.0
        assert float(by_code["LATENCY_P95_SLO_BREACH"].get("threshold")) == 654.0
        assert float(by_code["ERROR_RATE_SLO_BREACH"].get("threshold")) == 0.123
        assert str(by_code["ERROR_RATE_SLO_BREACH"].get("severity")) == "critical"
        assert "timestamp" in data
    finally:
        if old_avg is None:
            os.environ.pop("OPS_SLO_AVG_MS", None)
        else:
            os.environ["OPS_SLO_AVG_MS"] = old_avg
        if old_p95 is None:
            os.environ.pop("OPS_SLO_P95_MS", None)
        else:
            os.environ["OPS_SLO_P95_MS"] = old_p95
        if old_err is None:
            os.environ.pop("OPS_SLO_ERROR_RATE", None)
        else:
            os.environ["OPS_SLO_ERROR_RATE"] = old_err


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


def test_ops_observability_status_shape_and_request_id_signal():
    rid = "obs-rid-001"
    trace_id = "4bf92f3577b34da6a3ce929d0e0e4736"
    traceparent = f"00-{trace_id}-00f067aa0ba902b7-01"
    _ = client.get(
        "/api/ops/metrics",
        headers={**_h("viewer"), "X-Request-ID": rid, "traceparent": traceparent},
    )
    r = client.get("/api/ops/observability-status", headers=_h("viewer"))
    assert r.status_code == 200
    data = r.json()
    assert data.get("ok") is True
    assert data.get("request_id_propagation") is True
    assert data.get("trace_context_propagation") is True
    assert data.get("structured_logging") is True
    assert data.get("recent_events_include_request_id") is True
    assert data.get("recent_events_include_trace_id") is True
    assert "otel_enabled" in data
    assert "timestamp" in data


def test_ops_otel_status_shape_and_env_signals():
    import os

    old_endpoint = os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT")
    old_service = os.environ.get("OTEL_SERVICE_NAME")
    old_attrs = os.environ.get("OTEL_RESOURCE_ATTRIBUTES")

    os.environ["OTEL_EXPORTER_OTLP_ENDPOINT"] = "http://otel-collector:4318"
    os.environ["OTEL_SERVICE_NAME"] = "geolog-api"
    os.environ["OTEL_RESOURCE_ATTRIBUTES"] = "service.namespace=geolog,deployment.environment=dev"

    try:
        r = client.get("/api/ops/otel-status", headers=_h("viewer"))
        assert r.status_code == 200
        data = r.json()
        assert data.get("ok") is True
        assert data.get("enabled") is True
        assert data.get("exporter_otlp_endpoint_set") is True
        assert data.get("service_name") == "geolog-api"
        assert data.get("resource_attributes_set") is True
        assert "timestamp" in data
    finally:
        if old_endpoint is None:
            os.environ.pop("OTEL_EXPORTER_OTLP_ENDPOINT", None)
        else:
            os.environ["OTEL_EXPORTER_OTLP_ENDPOINT"] = old_endpoint
        if old_service is None:
            os.environ.pop("OTEL_SERVICE_NAME", None)
        else:
            os.environ["OTEL_SERVICE_NAME"] = old_service
        if old_attrs is None:
            os.environ.pop("OTEL_RESOURCE_ATTRIBUTES", None)
        else:
            os.environ["OTEL_RESOURCE_ATTRIBUTES"] = old_attrs


def test_ops_evidence_status_shape_and_acceptance_gate():
    import os

    keys = ["OPS_DASHBOARD_URL", "OPS_ALERT_TARGET", "OPS_TRACE_BACKEND_URL"]
    old = {k: os.environ.get(k) for k in keys}

    os.environ["OPS_DASHBOARD_URL"] = "http://grafana.local/d/geolog"
    os.environ["OPS_ALERT_TARGET"] = "slack:#ops-alerts"
    os.environ["OPS_TRACE_BACKEND_URL"] = "http://jaeger.local:16686"

    try:
        r = client.get("/api/ops/evidence-status", headers=_h("viewer"))
        assert r.status_code == 200
        data = r.json()
        assert data.get("ok") is True
        assert data.get("dashboard_configured") is True
        assert data.get("alert_delivery_configured") is True
        assert data.get("trace_backend_configured") is True
        assert data.get("ready_for_phase2_acceptance") is True
        assert data.get("probes_enabled") is False
        assert data.get("dashboard_reachable") is None
        assert data.get("trace_backend_reachable") is None
        assert data.get("dashboard_url") == "http://grafana.local/d/geolog"
        assert data.get("alert_delivery_target") == "slack:#ops-alerts"
        assert data.get("trace_backend_url") == "http://jaeger.local:16686"
        assert "timestamp" in data

        os.environ["OPS_DASHBOARD_URL"] = "http://127.0.0.1:9/unreachable"
        os.environ["OPS_TRACE_BACKEND_URL"] = "http://127.0.0.1:9/unreachable"
        r2 = client.get("/api/ops/evidence-status?probe=true", headers=_h("viewer"))
        assert r2.status_code == 200
        data2 = r2.json()
        assert data2.get("probes_enabled") is True
        assert data2.get("dashboard_reachable") is False
        assert data2.get("trace_backend_reachable") is False
        assert data2.get("ready_for_phase2_acceptance") is False

        os.environ.pop("OPS_TRACE_BACKEND_URL", None)
        r3 = client.get("/api/ops/evidence-status", headers=_h("viewer"))
        assert r3.status_code == 200
        data3 = r3.json()
        assert data3.get("trace_backend_configured") is False
        assert data3.get("ready_for_phase2_acceptance") is False
    finally:
        for k, v in old.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v


def test_ops_security_posture_status_shape_and_env_signals():
    import os

    old_source = os.environ.get("GEOLOG_SECRETS_SOURCE")
    old_tls = os.environ.get("GEOLOG_REQUIRE_TLS")

    os.environ["GEOLOG_SECRETS_SOURCE"] = "vault"
    os.environ["GEOLOG_REQUIRE_TLS"] = "true"

    try:
        r = client.get("/api/ops/security-posture-status", headers=_h("viewer"))
        assert r.status_code == 200
        data = r.json()
        assert data.get("container_non_root") is True
        assert data.get("secrets_source_configured") is True
        assert data.get("tls_required") is True
        assert data.get("branch_protection_checklist_present") is True
        assert data.get("security_evidence_template_present") is True
        assert "ci_security_gates_enabled" in data
        assert "backup_drill_script_present" in data
        assert "timestamp" in data
    finally:
        if old_source is None:
            os.environ.pop("GEOLOG_SECRETS_SOURCE", None)
        else:
            os.environ["GEOLOG_SECRETS_SOURCE"] = old_source
        if old_tls is None:
            os.environ.pop("GEOLOG_REQUIRE_TLS", None)
        else:
            os.environ["GEOLOG_REQUIRE_TLS"] = old_tls


def test_ops_security_evidence_status_valid_signature_happy_path():
    import os
    import json
    import hmac
    import hashlib
    import tempfile

    old_dir = os.environ.get("GEOLOG_BACKUP_DRILL_ARTIFACT_DIR")
    old_key = os.environ.get("BACKUP_DRILL_SIGNING_KEY")

    with tempfile.TemporaryDirectory() as td:
        report_path = os.path.join(td, "report.json")
        sig_path = os.path.join(td, "report.signature.json")
        report_obj = {"backup_ok": True, "restore_ok": True}
        report_bytes = json.dumps(report_obj, sort_keys=True, separators=(",", ":")).encode("utf-8")
        with open(report_path, "wb") as f:
            f.write(report_bytes)

        key = "unit-test-secret"
        sha = hashlib.sha256(report_bytes).hexdigest()
        sig = hmac.new(key.encode("utf-8"), sha.encode("utf-8"), hashlib.sha256).hexdigest()
        with open(sig_path, "w", encoding="utf-8") as f:
            json.dump(
                {
                    "report_sha256": sha,
                    "signature_alg": "hmac-sha256",
                    "signature_kid": "backup-drill",
                    "signature": sig,
                    "retention_days": 30,
                },
                f,
            )

        os.environ["GEOLOG_BACKUP_DRILL_ARTIFACT_DIR"] = td
        os.environ["BACKUP_DRILL_SIGNING_KEY"] = key

        try:
            r = client.get("/api/ops/security-evidence-status", headers=_h("viewer"))
            assert r.status_code == 200
            data = r.json()
            assert data.get("ok") is True
            assert data.get("report_present") is True
            assert data.get("signature_present") is True
            assert data.get("report_sha256_matches_signature") is True
            assert data.get("hmac_signature_valid") is True
            assert data.get("signature_alg") == "hmac-sha256"
            assert data.get("signature_kid") == "backup-drill"
            assert data.get("retention_days") == 30
            assert "timestamp" in data
        finally:
            if old_dir is None:
                os.environ.pop("GEOLOG_BACKUP_DRILL_ARTIFACT_DIR", None)
            else:
                os.environ["GEOLOG_BACKUP_DRILL_ARTIFACT_DIR"] = old_dir
            if old_key is None:
                os.environ.pop("BACKUP_DRILL_SIGNING_KEY", None)
            else:
                os.environ["BACKUP_DRILL_SIGNING_KEY"] = old_key


def test_ops_security_evidence_status_detects_mismatch():
    import os
    import json
    import tempfile

    old_dir = os.environ.get("GEOLOG_BACKUP_DRILL_ARTIFACT_DIR")

    with tempfile.TemporaryDirectory() as td:
        with open(os.path.join(td, "report.json"), "w", encoding="utf-8") as f:
            json.dump({"backup_ok": True}, f)
        with open(os.path.join(td, "report.signature.json"), "w", encoding="utf-8") as f:
            json.dump(
                {
                    "report_sha256": "0" * 64,
                    "signature_alg": "hmac-sha256",
                    "signature": "f" * 64,
                },
                f,
            )

        os.environ["GEOLOG_BACKUP_DRILL_ARTIFACT_DIR"] = td
        os.environ.pop("BACKUP_DRILL_SIGNING_KEY", None)

        try:
            r = client.get("/api/ops/security-evidence-status", headers=_h("viewer"))
            assert r.status_code == 200
            data = r.json()
            assert data.get("ok") is False
            assert data.get("report_present") is True
            assert data.get("signature_present") is True
            assert data.get("report_sha256_matches_signature") is False
            assert data.get("hmac_signature_valid") is False
        finally:
            if old_dir is None:
                os.environ.pop("GEOLOG_BACKUP_DRILL_ARTIFACT_DIR", None)
            else:
                os.environ["GEOLOG_BACKUP_DRILL_ARTIFACT_DIR"] = old_dir


def test_ops_security_evidence_status_resolves_latest_nested_artifact_dir():
    import os
    import json
    import hmac
    import hashlib
    import tempfile
    import pathlib

    old_dir = os.environ.get("GEOLOG_BACKUP_DRILL_ARTIFACT_DIR")
    old_key = os.environ.get("BACKUP_DRILL_SIGNING_KEY")

    with tempfile.TemporaryDirectory() as td:
        base = pathlib.Path(td)
        key = "nested-secret"

        old = base / "20260101T000000Z"
        old.mkdir(parents=True, exist_ok=True)
        old_report = json.dumps({"v": "old"}, sort_keys=True, separators=(",", ":")).encode("utf-8")
        (old / "report.json").write_bytes(old_report)
        (old / "report.signature.json").write_text(
            json.dumps(
                {
                    "report_sha256": hashlib.sha256(old_report).hexdigest(),
                    "signature_alg": "hmac-sha256",
                    "signature": hmac.new(key.encode("utf-8"), hashlib.sha256(old_report).hexdigest().encode("utf-8"), hashlib.sha256).hexdigest(),
                }
            ),
            encoding="utf-8",
        )

        latest = base / "20260101T000001Z"
        latest.mkdir(parents=True, exist_ok=True)
        latest_report = json.dumps({"v": "latest"}, sort_keys=True, separators=(",", ":")).encode("utf-8")
        (latest / "report.json").write_bytes(latest_report)
        (latest / "report.signature.json").write_text(
            json.dumps(
                {
                    "report_sha256": hashlib.sha256(latest_report).hexdigest(),
                    "signature_alg": "hmac-sha256",
                    "signature": hmac.new(key.encode("utf-8"), hashlib.sha256(latest_report).hexdigest().encode("utf-8"), hashlib.sha256).hexdigest(),
                    "signature_kid": "k-latest",
                }
            ),
            encoding="utf-8",
        )

        os.environ["GEOLOG_BACKUP_DRILL_ARTIFACT_DIR"] = str(base)
        os.environ["BACKUP_DRILL_SIGNING_KEY"] = key

        try:
            r = client.get("/api/ops/security-evidence-status", headers=_h("viewer"))
            assert r.status_code == 200
            data = r.json()
            assert data.get("ok") is True
            assert data.get("signature_kid") == "k-latest"
            assert data.get("hmac_signature_valid") is True
        finally:
            if old_dir is None:
                os.environ.pop("GEOLOG_BACKUP_DRILL_ARTIFACT_DIR", None)
            else:
                os.environ["GEOLOG_BACKUP_DRILL_ARTIFACT_DIR"] = old_dir
            if old_key is None:
                os.environ.pop("BACKUP_DRILL_SIGNING_KEY", None)
            else:
                os.environ["BACKUP_DRILL_SIGNING_KEY"] = old_key


def test_ops_security_evidence_attest_happy_path():
    import os
    import json
    import hashlib
    import hmac

    report = {"backup_ok": True, "restore_ok": True}
    report_bytes = json.dumps(report, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    report_sha = hashlib.sha256(report_bytes).hexdigest()

    old_key = os.environ.get("BACKUP_DRILL_SIGNING_KEY")
    os.environ["BACKUP_DRILL_SIGNING_KEY"] = "unit-test-secret"
    sig = hmac.new(b"unit-test-secret", report_sha.encode("utf-8"), hashlib.sha256).hexdigest()

    try:
        r = client.post(
            "/api/ops/security-evidence/attest",
            headers=_h("interpreter"),
            json={
                "report": report,
                "signature": {
                    "report_sha256": report_sha,
                    "signature_alg": "hmac-sha256",
                    "signature_kid": "backup-drill",
                    "signature": sig,
                    "retention_days": 30,
                },
            },
        )
        assert r.status_code == 200
        data = r.json()
        assert data.get("ok") is True
        assert data.get("reason_code") == "ATTEST_VALID"
        assert data.get("report_sha256") == report_sha
    finally:
        if old_key is None:
            os.environ.pop("BACKUP_DRILL_SIGNING_KEY", None)
        else:
            os.environ["BACKUP_DRILL_SIGNING_KEY"] = old_key


def test_ops_security_evidence_attest_rejects_viewer_role():
    r = client.post(
        "/api/ops/security-evidence/attest",
        headers=_h("viewer"),
        json={"report": {"x": 1}, "signature": {"report_sha256": "0" * 64}},
    )
    assert r.status_code == 403


def test_ops_security_evidence_attest_latest_happy_path():
    import os
    import json
    import tempfile
    import hashlib
    import hmac
    import time

    old_dir = os.environ.get("GEOLOG_BACKUP_DRILL_ARTIFACT_DIR")
    old_key = os.environ.get("BACKUP_DRILL_SIGNING_KEY")

    with tempfile.TemporaryDirectory() as td:
        report = {"backup_ok": True, "restore_ok": True}
        report_bytes = json.dumps(report, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
        report_sha = hashlib.sha256(report_bytes).hexdigest()

        report_path = os.path.join(td, "report.json")
        sig_path = os.path.join(td, "report.signature.json")
        with open(report_path, "w", encoding="utf-8") as f:
            json.dump(report, f)

        key = "unit-test-secret"
        sig = hmac.new(key.encode("utf-8"), report_sha.encode("utf-8"), hashlib.sha256).hexdigest()
        with open(sig_path, "w", encoding="utf-8") as f:
            json.dump(
                {
                    "report_sha256": report_sha,
                    "signature_alg": "hmac-sha256",
                    "signature_kid": "backup-drill",
                    "signature": sig,
                    "retention_days": 30,
                },
                f,
            )

        os.environ["GEOLOG_BACKUP_DRILL_ARTIFACT_DIR"] = td
        os.environ["BACKUP_DRILL_SIGNING_KEY"] = key

        try:
            r = client.get("/api/ops/security-evidence/attest/latest", headers=_h("viewer"))
            assert r.status_code == 200
            data = r.json()
            assert data.get("ok") is True
            assert data.get("reason_code") == "ATTEST_VALID"
            assert data.get("report_sha256") == report_sha

            rf = client.get("/api/ops/security-evidence/freshness?max_age_seconds=86400", headers=_h("viewer"))
            assert rf.status_code == 200
            fresh = rf.json()
            assert fresh.get("ok") is True
            assert fresh.get("stale") is False
            assert fresh.get("reason_code") == "FRESH"

            rk = client.post(
                "/api/ops/security-evidence/gate/check?max_age_seconds=86400&min_retention_days=31",
                headers=_h("interpreter"),
            )
            assert rk.status_code == 200
            retention_fail = rk.json()
            assert retention_fail.get("ok") is False
            assert retention_fail.get("retention_ok") is False
            assert retention_fail.get("retention_reason_code") == "RETENTION_TOO_SHORT"
            assert "retention" in (retention_fail.get("failed_checks") or [])

            rk_attest_only = client.post(
                "/api/ops/security-evidence/gate/check?max_age_seconds=86400&min_retention_days=31&required_checks=attest",
                headers=_h("interpreter"),
            )
            assert rk_attest_only.status_code == 200
            attest_only = rk_attest_only.json()
            assert attest_only.get("ok") is True
            assert attest_only.get("evaluated_checks") == ["attest"]
            assert attest_only.get("failed_checks") == []
            assert attest_only.get("requested_checks") == ["attest"]
            assert attest_only.get("ignored_checks") == []
            assert attest_only.get("defaulted_checks") is False

            rk_with_invalid = client.post(
                "/api/ops/security-evidence/gate/check?max_age_seconds=86400&min_retention_days=31&required_checks=attest,foo,attest",
                headers=_h("interpreter"),
            )
            assert rk_with_invalid.status_code == 200
            with_invalid = rk_with_invalid.json()
            assert with_invalid.get("evaluated_checks") == ["attest"]
            assert with_invalid.get("ignored_checks") == ["foo"]
            assert with_invalid.get("duplicate_checks") == ["attest"]
            assert with_invalid.get("strict_required_checks") is False
            assert with_invalid.get("gate_reason_code") in {"GATE_PASS", "GATE_FAIL"}
            assert isinstance(with_invalid.get("gate_failed_count"), int)
            assert isinstance(with_invalid.get("gate_passed_count"), int)
            assert isinstance(with_invalid.get("gate_total_count"), int)
            assert isinstance(with_invalid.get("gate_pass_ratio"), float)
            assert isinstance(with_invalid.get("gate_fail_ratio"), float)
            assert isinstance(with_invalid.get("gate_consistency_ok"), bool)
            assert with_invalid.get("gate_consistency_reason") in {"CONSISTENT", "COUNT_MISMATCH", "RATIO_MISMATCH"}
            assert with_invalid.get("gate_failed_count") + with_invalid.get("gate_passed_count") == len(with_invalid.get("evaluated_checks") or [])
            assert with_invalid.get("gate_total_count") == len(with_invalid.get("evaluated_checks") or [])

            rk_defaulted = client.post(
                "/api/ops/security-evidence/gate/check?max_age_seconds=86400&min_retention_days=31&required_checks=foo",
                headers=_h("interpreter"),
            )
            assert rk_defaulted.status_code == 200
            defaulted = rk_defaulted.json()
            assert defaulted.get("defaulted_checks") is True
            assert defaulted.get("evaluated_checks") == ["attest", "freshness", "retention"]
            assert defaulted.get("gate_reason_code") in {"GATE_PASS", "GATE_FAIL"}
            assert isinstance(defaulted.get("gate_failed_count"), int)
            assert isinstance(defaulted.get("gate_passed_count"), int)
            assert isinstance(defaulted.get("gate_total_count"), int)
            assert isinstance(defaulted.get("gate_pass_ratio"), float)
            assert isinstance(defaulted.get("gate_fail_ratio"), float)
            assert isinstance(defaulted.get("gate_consistency_ok"), bool)
            assert defaulted.get("gate_consistency_reason") in {"CONSISTENT", "COUNT_MISMATCH", "RATIO_MISMATCH"}
            assert defaulted.get("gate_failed_count") + defaulted.get("gate_passed_count") == len(defaulted.get("evaluated_checks") or [])
            assert defaulted.get("gate_total_count") == len(defaulted.get("evaluated_checks") or [])

            rk_with_invalid_strict = client.post(
                "/api/ops/security-evidence/gate/check?max_age_seconds=86400&min_retention_days=31&required_checks=attest,foo,attest&strict_required_checks=true",
                headers=_h("interpreter"),
            )
            assert rk_with_invalid_strict.status_code == 400
            strict_detail = rk_with_invalid_strict.json().get("detail", {})
            assert strict_detail.get("error") == "invalid required_checks values"
            assert strict_detail.get("ignored_checks") == ["foo"]
            assert strict_detail.get("duplicate_checks") == ["attest"]
            assert strict_detail.get("gate_reason_code") is None

            rka = client.post(
                "/api/ops/security-evidence/gate/assert?max_age_seconds=86400&min_retention_days=31",
                headers=_h("interpreter"),
            )
            assert rka.status_code == 503
            kdetail = rka.json().get("detail", {})
            assert kdetail.get("retention_reason_code") == "RETENTION_TOO_SHORT"
            assert "retention" in (kdetail.get("failed_checks") or [])
            assert isinstance(kdetail.get("gate_passed_count"), int)
            assert isinstance(kdetail.get("gate_total_count"), int)
            assert isinstance(kdetail.get("gate_pass_ratio"), float)
            assert isinstance(kdetail.get("gate_fail_ratio"), float)
            assert isinstance(kdetail.get("gate_consistency_ok"), bool)
            assert kdetail.get("gate_consistency_reason") in {"CONSISTENT", "COUNT_MISMATCH", "RATIO_MISMATCH"}
            assert kdetail.get("gate_total_count") == len(kdetail.get("evaluated_checks") or [])

            old_ts = time.time() - 7200
            os.utime(report_path, (old_ts, old_ts))

            rs = client.get("/api/ops/security-evidence/freshness?max_age_seconds=60", headers=_h("viewer"))
            assert rs.status_code == 200
            stale = rs.json()
            assert stale.get("ok") is False
            assert stale.get("stale") is True
            assert stale.get("reason_code") == "STALE"

            rg = client.get("/api/ops/security-evidence/gate?max_age_seconds=60", headers=_h("viewer"))
            assert rg.status_code == 200
            gate = rg.json()
            assert gate.get("ok") is False
            assert gate.get("attest_ok") is True
            assert gate.get("freshness_ok") is False
            assert gate.get("freshness_reason_code") == "STALE"
            assert "freshness" in (gate.get("failed_checks") or [])

            re = client.get("/api/ops/security-evidence/gate/enforce?max_age_seconds=60", headers=_h("viewer"))
            assert re.status_code == 503
            detail = re.json().get("detail", {})
            assert detail.get("freshness_reason_code") == "STALE"
            assert "freshness" in (detail.get("failed_checks") or [])
            assert detail.get("gate_consistency_ok") == gate.get("gate_consistency_ok")
            assert detail.get("gate_consistency_reason") == gate.get("gate_consistency_reason")

            ra_forbidden = client.post("/api/ops/security-evidence/gate/assert?max_age_seconds=60", headers=_h("viewer"))
            assert ra_forbidden.status_code == 403

            ra = client.post("/api/ops/security-evidence/gate/assert?max_age_seconds=60", headers=_h("interpreter"))
            assert ra.status_code == 503
            adetail = ra.json().get("detail", {})
            assert adetail.get("freshness_reason_code") == "STALE"
            assert "freshness" in (adetail.get("failed_checks") or [])

            rc_viewer = client.post("/api/ops/security-evidence/gate/check?max_age_seconds=60", headers=_h("viewer"))
            assert rc_viewer.status_code == 403

            rc = client.post("/api/ops/security-evidence/gate/check?max_age_seconds=60", headers=_h("interpreter"))
            assert rc.status_code == 200
            check = rc.json()
            assert check.get("ok") is False
            assert check.get("freshness_reason_code") == "STALE"
        finally:
            if old_dir is None:
                os.environ.pop("GEOLOG_BACKUP_DRILL_ARTIFACT_DIR", None)
            else:
                os.environ["GEOLOG_BACKUP_DRILL_ARTIFACT_DIR"] = old_dir
            if old_key is None:
                os.environ.pop("BACKUP_DRILL_SIGNING_KEY", None)
            else:
                os.environ["BACKUP_DRILL_SIGNING_KEY"] = old_key


def test_ops_security_evidence_manifest_sign_happy_path():
    import os
    import json
    import tempfile
    import hashlib

    old_dir = os.environ.get("GEOLOG_BACKUP_DRILL_ARTIFACT_DIR")
    old_ring = os.environ.get("AUDIT_EXPORT_HMAC_KEYS_JSON")
    old_active = os.environ.get("AUDIT_EXPORT_HMAC_ACTIVE_KID")

    with tempfile.TemporaryDirectory() as td:
        report = {"backup_ok": True}
        report_path = os.path.join(td, "report.json")
        sig_path = os.path.join(td, "report.signature.json")
        with open(report_path, "w", encoding="utf-8") as f:
            json.dump(report, f)
        with open(sig_path, "w", encoding="utf-8") as f:
            json.dump({"report_sha256": hashlib.sha256(json.dumps(report).encode("utf-8")).hexdigest()}, f)

        os.environ["GEOLOG_BACKUP_DRILL_ARTIFACT_DIR"] = td
        os.environ["AUDIT_EXPORT_HMAC_KEYS_JSON"] = '{"k1":"secret-one"}'
        os.environ["AUDIT_EXPORT_HMAC_ACTIVE_KID"] = "k1"

        try:
            r = client.get("/api/ops/security-evidence/manifest?sign=true", headers=_h("viewer"))
            assert r.status_code == 200
            data = r.json()
            assert data.get("ok") is True
            assert data.get("signature_alg") == "hmac-sha256"
            assert data.get("signature_kid") == "k1"
            assert len(str(data.get("bundle_digest_sha256") or "")) == 64
            assert len(str(data.get("signature") or "")) == 64

            sig = str(data.get("signature") or "")
            rv = client.get(f"/api/ops/security-evidence/manifest/verify-signature?kid=k1&signature={sig}", headers=_h("viewer"))
            assert rv.status_code == 200
            out = rv.json()
            assert out.get("ok") is True
            assert out.get("reason_code") == "SIGNATURE_VALID"

            rp = client.post(
                "/api/ops/security-evidence/manifest/verify-signature",
                headers=_h("interpreter"),
                json={"signature": sig, "kid": "k1"},
            )
            assert rp.status_code == 200
            outp = rp.json()
            assert outp.get("ok") is True
            assert outp.get("reason_code") == "SIGNATURE_VALID"
        finally:
            if old_dir is None:
                os.environ.pop("GEOLOG_BACKUP_DRILL_ARTIFACT_DIR", None)
            else:
                os.environ["GEOLOG_BACKUP_DRILL_ARTIFACT_DIR"] = old_dir
            if old_ring is None:
                os.environ.pop("AUDIT_EXPORT_HMAC_KEYS_JSON", None)
            else:
                os.environ["AUDIT_EXPORT_HMAC_KEYS_JSON"] = old_ring
            if old_active is None:
                os.environ.pop("AUDIT_EXPORT_HMAC_ACTIVE_KID", None)
            else:
                os.environ["AUDIT_EXPORT_HMAC_ACTIVE_KID"] = old_active


def test_ops_security_evidence_manifest_verify_post_rejects_viewer():
    r = client.post(
        "/api/ops/security-evidence/manifest/verify-signature",
        headers=_h("viewer"),
        json={"signature": "f" * 64, "kid": "k1"},
    )
    assert r.status_code == 403


def test_ops_security_evidence_attest_reports_digest_mismatch():
    r = client.post(
        "/api/ops/security-evidence/attest",
        headers=_h("interpreter"),
        json={
            "report": {"backup_ok": True},
            "signature": {
                "report_sha256": "0" * 64,
                "signature_alg": "hmac-sha256",
                "signature": "f" * 64,
            },
        },
    )
    assert r.status_code == 200
    data = r.json()
    assert data.get("ok") is False
    assert data.get("reason_code") == "DIGEST_MISMATCH"


def test_ops_security_evidence_attest_requires_key_for_hmac():
    import os
    import json
    import hashlib

    report = {"backup_ok": True}
    report_bytes = json.dumps(report, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    report_sha = hashlib.sha256(report_bytes).hexdigest()

    old_key = os.environ.get("BACKUP_DRILL_SIGNING_KEY")
    os.environ.pop("BACKUP_DRILL_SIGNING_KEY", None)
    try:
        r = client.post(
            "/api/ops/security-evidence/attest",
            headers=_h("interpreter"),
            json={
                "report": report,
                "signature": {
                    "report_sha256": report_sha,
                    "signature_alg": "hmac-sha256",
                    "signature": "f" * 64,
                },
            },
        )
        assert r.status_code == 200
        data = r.json()
        assert data.get("ok") is False
        assert data.get("reason_code") == "HMAC_KEY_MISSING"
    finally:
        if old_key is None:
            os.environ.pop("BACKUP_DRILL_SIGNING_KEY", None)
        else:
            os.environ["BACKUP_DRILL_SIGNING_KEY"] = old_key


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
    assert "/api/ops/observability-status" in endpoints
    assert "/api/ops/otel-status" in endpoints
    assert "/api/ops/evidence-status" in endpoints
    assert "/api/ops/security-posture-status" in endpoints
    assert "/api/ops/security-evidence-status" in endpoints
    assert "/api/ops/security-evidence/manifest" in endpoints
    assert "/api/ops/security-evidence/manifest/verify-signature" in endpoints
    assert "/api/ops/security-evidence/attest" in endpoints
    assert "/api/ops/security-evidence/attest/latest" in endpoints
    assert "/api/ops/security-evidence/freshness" in endpoints
    assert "/api/ops/security-evidence/gate" in endpoints
    assert "/api/ops/security-evidence/gate/enforce" in endpoints
    assert "/api/ops/security-evidence/gate/assert" in endpoints
    assert "/api/ops/security-evidence/gate/check" in endpoints
    assert endpoints.get("/api/ops/security-evidence/gate") == "1.14"
    assert endpoints.get("/api/ops/security-evidence/gate/enforce") == "1.14"
    assert endpoints.get("/api/ops/security-evidence/gate/assert") == "1.14"
    assert endpoints.get("/api/ops/security-evidence/gate/check") == "1.14"
    assert "/api/ops/alert-rules" in endpoints
    assert "/api/ops/alerts" in endpoints
    assert "/api/audit-log/verify/signature" in endpoints
    assert "/api/audit-log/immutability-status" in endpoints


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
    alert_rules_get = paths.get("/api/ops/alert-rules", {}).get("get", {})
    health_get = paths.get("/api/ops/health", {}).get("get", {})
    obs_status_get = paths.get("/api/ops/observability-status", {}).get("get", {})
    otel_status_get = paths.get("/api/ops/otel-status", {}).get("get", {})
    evidence_status_get = paths.get("/api/ops/evidence-status", {}).get("get", {})
    security_posture_get = paths.get("/api/ops/security-posture-status", {}).get("get", {})
    security_evidence_get = paths.get("/api/ops/security-evidence-status", {}).get("get", {})
    security_evidence_manifest_get = paths.get("/api/ops/security-evidence/manifest", {}).get("get", {})
    security_evidence_manifest_verify_path = paths.get("/api/ops/security-evidence/manifest/verify-signature", {})
    security_evidence_manifest_verify_get = security_evidence_manifest_verify_path.get("get", {})
    security_evidence_manifest_verify_post = security_evidence_manifest_verify_path.get("post", {})
    security_evidence_attest_post = paths.get("/api/ops/security-evidence/attest", {}).get("post", {})
    security_evidence_attest_latest_get = paths.get("/api/ops/security-evidence/attest/latest", {}).get("get", {})
    security_evidence_freshness_get = paths.get("/api/ops/security-evidence/freshness", {}).get("get", {})
    security_evidence_gate_get = paths.get("/api/ops/security-evidence/gate", {}).get("get", {})
    security_evidence_gate_enforce_get = paths.get("/api/ops/security-evidence/gate/enforce", {}).get("get", {})
    security_evidence_gate_assert_post = paths.get("/api/ops/security-evidence/gate/assert", {}).get("post", {})
    security_evidence_gate_check_post = paths.get("/api/ops/security-evidence/gate/check", {}).get("post", {})
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
    assert alert_rules_get.get("operationId")
    assert health_get.get("operationId")
    assert obs_status_get.get("operationId")
    assert otel_status_get.get("operationId")
    assert evidence_status_get.get("operationId")
    assert security_posture_get.get("operationId")
    assert security_evidence_get.get("operationId")
    assert security_evidence_manifest_get.get("operationId")
    assert security_evidence_manifest_verify_get.get("operationId")
    assert security_evidence_manifest_verify_post.get("operationId")
    assert security_evidence_attest_post.get("operationId")
    assert security_evidence_attest_latest_get.get("operationId")
    assert security_evidence_freshness_get.get("operationId")
    assert security_evidence_gate_get.get("operationId")
    assert security_evidence_gate_enforce_get.get("operationId")
    assert security_evidence_gate_assert_post.get("operationId")
    assert security_evidence_gate_check_post.get("operationId")
    assert contracts_get.get("operationId")

    gate_enforce_503 = security_evidence_gate_enforce_get.get("responses", {}).get("503", {})
    gate_assert_503 = security_evidence_gate_assert_post.get("responses", {}).get("503", {})
    gate_enforce_503_schema = gate_enforce_503.get("content", {}).get("application/json", {}).get("schema", {})
    gate_assert_503_schema = gate_assert_503.get("content", {}).get("application/json", {}).get("schema", {})
    assert gate_enforce_503_schema.get("$ref", "").endswith("/OpsSecurityEvidenceGateErrorResponse")
    assert gate_assert_503_schema.get("$ref", "").endswith("/OpsSecurityEvidenceGateErrorResponse")
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
    assert "OpsAlertRulesResponse" in schemas
    assert "OpsHealthResponse" in schemas
    assert "OpsObservabilityStatusResponse" in schemas
    assert "OpsOtelStatusResponse" in schemas
    assert "OpsEvidenceStatusResponse" in schemas
    assert "OpsSecurityPostureStatusResponse" in schemas
    assert "OpsSecurityEvidenceStatusResponse" in schemas
    assert "OpsSecurityEvidenceManifestResponse" in schemas
    assert "OpsSecurityEvidenceManifestVerifyRequest" in schemas
    assert "OpsSecurityEvidenceAttestRequest" in schemas
    assert "OpsSecurityEvidenceAttestResponse" in schemas
    assert "OpsSecurityEvidenceFreshnessResponse" in schemas
    assert "OpsSecurityEvidenceGateResponse" in schemas
    assert "OpsSecurityEvidenceGateErrorDetail" in schemas
    assert "OpsSecurityEvidenceGateErrorResponse" in schemas
    gate_error_detail_props = schemas.get("OpsSecurityEvidenceGateErrorDetail", {}).get("properties", {})
    assert "evaluated_checks" in gate_error_detail_props
    assert "failed_checks" in gate_error_detail_props
    assert "strict_required_checks" in gate_error_detail_props
    assert "defaulted_checks" in gate_error_detail_props
    assert "gate_reason_code" in gate_error_detail_props
    assert "gate_failed_count" in gate_error_detail_props
    assert "gate_passed_count" in gate_error_detail_props
    assert "gate_total_count" in gate_error_detail_props
    assert "gate_pass_ratio" in gate_error_detail_props
    assert "gate_fail_ratio" in gate_error_detail_props
    assert "gate_consistency_ok" in gate_error_detail_props
    assert "gate_consistency_reason" in gate_error_detail_props
    assert "requested_checks" in gate_error_detail_props
    assert "ignored_checks" in gate_error_detail_props
    assert "duplicate_checks" in gate_error_detail_props
    gate_schema = schemas.get("OpsSecurityEvidenceGateResponse", {})
    gate_props = gate_schema.get("properties", {})
    assert "retention_ok" in gate_props
    assert "retention_reason_code" in gate_props
    assert "retention_days" in gate_props
    assert "min_retention_days" in gate_props
    assert "evaluated_checks" in gate_props
    assert "failed_checks" in gate_props
    assert "strict_required_checks" in gate_props
    assert "defaulted_checks" in gate_props
    assert "gate_reason_code" in gate_props
    assert "gate_failed_count" in gate_props
    assert "gate_passed_count" in gate_props
    assert "gate_total_count" in gate_props
    assert "gate_pass_ratio" in gate_props
    assert "gate_fail_ratio" in gate_props
    assert "gate_consistency_ok" in gate_props
    assert "gate_consistency_reason" in gate_props
    assert "requested_checks" in gate_props
    assert "ignored_checks" in gate_props
    assert "duplicate_checks" in gate_props
    assert "OpsContractsResponse" in schemas
    assert "OpsRunbookResponse" in schemas

    obs_schema = schemas.get("OpsObservabilityStatusResponse", {})
    obs_props = obs_schema.get("properties", {})
    assert "trace_context_propagation" in obs_props
    assert "recent_events_include_trace_id" in obs_props

    otel_schema = schemas.get("OpsOtelStatusResponse", {})
    otel_props = otel_schema.get("properties", {})
    assert "enabled" in otel_props
    assert "exporter_otlp_endpoint_set" in otel_props
    assert "service_name" in otel_props

    evidence_schema = schemas.get("OpsEvidenceStatusResponse", {})
    evidence_props = evidence_schema.get("properties", {})
    assert "dashboard_configured" in evidence_props
    assert "dashboard_reachable" in evidence_props
    assert "alert_delivery_configured" in evidence_props
    assert "trace_backend_configured" in evidence_props
    assert "trace_backend_reachable" in evidence_props
    assert "probes_enabled" in evidence_props
    assert "ready_for_phase2_acceptance" in evidence_props

    security_posture_schema = schemas.get("OpsSecurityPostureStatusResponse", {})
    security_posture_props = security_posture_schema.get("properties", {})
    assert "container_non_root" in security_posture_props
    assert "secrets_source_configured" in security_posture_props
    assert "tls_required" in security_posture_props
    assert "ci_security_gates_enabled" in security_posture_props
    assert "branch_protection_checklist_present" in security_posture_props
    assert "security_evidence_template_present" in security_posture_props

    alert_rules_schema = schemas.get("OpsAlertRulesResponse", {})
    alert_rules_props = alert_rules_schema.get("properties", {})
    assert "version" in alert_rules_props
    assert "rules" in alert_rules_props

    contracts_schema = schemas.get("OpsContractsResponse", {})
    contracts_props = contracts_schema.get("properties", {})
    assert "digest_sha256" in contracts_props
    assert "signature" in contracts_props
    assert "signature_alg" in contracts_props
    assert "signature_kid" in contracts_props


def test_compute_gate_invariants_scenarios():
    zero = _compute_gate_invariants([], [])
    assert zero["gate_failed_count"] == 0
    assert zero["gate_passed_count"] == 0
    assert zero["gate_total_count"] == 0
    assert zero["gate_pass_ratio"] == 0.0
    assert zero["gate_fail_ratio"] == 0.0
    assert zero["gate_consistency_ok"] is True
    assert zero["gate_consistency_reason"] == "CONSISTENT"

    one_fail = _compute_gate_invariants(["freshness"], ["freshness"])
    assert one_fail["gate_failed_count"] == 1
    assert one_fail["gate_passed_count"] == 0
    assert one_fail["gate_total_count"] == 1
    assert one_fail["gate_pass_ratio"] == 0.0
    assert one_fail["gate_fail_ratio"] == 1.0
    assert one_fail["gate_consistency_ok"] is True
    assert one_fail["gate_consistency_reason"] == "CONSISTENT"

    all_fail = _compute_gate_invariants(["attest", "freshness"], ["attest", "freshness"])
    assert all_fail["gate_failed_count"] == 2
    assert all_fail["gate_passed_count"] == 0
    assert all_fail["gate_total_count"] == 2
    assert all_fail["gate_pass_ratio"] == 0.0
    assert all_fail["gate_fail_ratio"] == 1.0
    assert all_fail["gate_consistency_ok"] is True
    assert all_fail["gate_consistency_reason"] == "CONSISTENT"

    mixed = _compute_gate_invariants(["freshness"], ["attest", "freshness", "retention"])
    assert mixed["gate_failed_count"] == 1
    assert mixed["gate_passed_count"] == 2
    assert mixed["gate_total_count"] == 3
    assert mixed["gate_pass_ratio"] == 2 / 3
    assert mixed["gate_fail_ratio"] == 1 / 3
    assert mixed["gate_consistency_ok"] is True
    assert mixed["gate_consistency_reason"] == "CONSISTENT"


def test_snapshot_approval_optimistic_lock_and_history(monkeypatch):
    with tempfile.TemporaryDirectory() as td:
        monkeypatch.setattr(main_mod, "SNAPSHOT_DIR", td)
        wells_resp = client.get("/api/wells/", headers=_h("viewer"))
        assert wells_resp.status_code == 200
        wells = wells_resp.json()
        assert isinstance(wells, list) and wells
        wid = int(wells[0]["id"])

        r_create = client.post(f"/api/wells/{wid}/snapshots", headers=_h("interpreter"), json={"label": "v1"})
        assert r_create.status_code == 201
        snap = r_create.json()
        sid = snap["snapshot_id"]
        assert snap.get("snapshot_version") == 1
        assert snap.get("approval_status") == "pending"
        assert snap.get("approval_history") == []

        r_conflict = client.post(
            f"/api/wells/{wid}/snapshots/{sid}/approve",
            headers=_h("interpreter"),
            json={"expected_version": 999, "approved_by": "qa-a"},
        )
        assert r_conflict.status_code == 409
        detail = r_conflict.json().get("detail", {})
        assert detail.get("error") == "snapshot version conflict"
        assert detail.get("current_version") == 1

        r_ok = client.post(
            f"/api/wells/{wid}/snapshots/{sid}/approve",
            headers=_h("interpreter"),
            json={"expected_version": 1, "approved_by": "qa-a"},
        )
        assert r_ok.status_code == 200
        approved = r_ok.json()
        assert approved.get("approved") is True
        assert approved.get("approval_status") == "approved"
        assert approved.get("approved_by") == "qa-a"
        assert approved.get("snapshot_version") == 2
        history = approved.get("approval_history") or []
        assert len(history) == 1
        assert history[0].get("action") == "approve"
        assert history[0].get("from_version") == 1
        assert history[0].get("to_version") == 2

        r_conflict_2 = client.post(
            f"/api/wells/{wid}/snapshots/{sid}/approve",
            headers=_h("interpreter"),
            json={"expected_version": 1, "approved_by": "qa-b"},
        )
        assert r_conflict_2.status_code == 409


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
