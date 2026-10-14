"""Audit trail helpers shared by main.py and the audit/ops routers.

`log_audit` is used by routes throughout main.py, and the chain/signature helpers
are used by the /api/audit-log and /api/ops routes, so all of them live here
rather than in either caller.

The signing keys come from the environment (AUDIT_EXPORT_HMAC_KEYS_JSON with
AUDIT_EXPORT_HMAC_ACTIVE_KID for rotation, or the legacy single
AUDIT_EXPORT_HMAC_KEY). Nothing here issues tokens; it signs and verifies the
evidence bundles this service exports.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os

from fastapi import HTTPException
from sqlalchemy.orm import Session

try:
    from models import AuditLog
except ImportError:
    from backend.models import AuditLog


def log_audit(db: Session, action: str, entity_type: str = "", entity_id: int = None,
               well_id: int = None, project_id: int = None, details: str = ""):
    """Write an audit trail entry."""
    db.add(AuditLog(
        project_id=project_id, well_id=well_id, action=action,
        entity_type=entity_type, entity_id=entity_id, details=details
    ))
    db.commit()


def compute_audit_chain_report(limit: int, db: Session):
    rows = db.query(AuditLog).order_by(AuditLog.id.asc()).limit(min(max(limit, 1), 10000)).all()
    issues = []
    verified = 0
    prev_hash = ""

    for r in rows:
        canonical = json.dumps({
            "request_id": r.request_id or "",
            "subject": r.auth_subject or "",
            "role": r.auth_role or "viewer",
            "method": (r.method or "").upper(),
            "path": r.route_path or "",
            "status": int(r.status_code) if r.status_code is not None else 0,
            "payload_hash": r.payload_hash or "",
            "prev_hash": r.prev_hash or "",
            "well_id": r.well_id,
            "project_id": r.project_id,
        }, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
        recomputed = hashlib.sha256(canonical.encode("utf-8")).hexdigest()

        if (r.prev_hash or "") != prev_hash:
            issues.append({"id": r.id, "type": "prev_hash_mismatch", "expected": prev_hash, "actual": r.prev_hash or ""})
        if (r.entry_hash or "") != recomputed:
            issues.append({"id": r.id, "type": "entry_hash_mismatch", "expected": recomputed, "actual": r.entry_hash or ""})

        prev_hash = r.entry_hash or ""
        verified += 1

    return {
        "ok": len(issues) == 0,
        "verified_entries": verified,
        "issues": issues,
    }


def resolve_audit_export_signing_key(requested_kid: str | None = None):
    """Resolve signing key with optional key rotation.

    Priority:
    1) requested_kid -> AUDIT_EXPORT_HMAC_KEYS_JSON map
    2) AUDIT_EXPORT_HMAC_ACTIVE_KID -> AUDIT_EXPORT_HMAC_KEYS_JSON map
    3) legacy AUDIT_EXPORT_HMAC_KEY (kid='legacy')
    """
    keys_json = (os.getenv("AUDIT_EXPORT_HMAC_KEYS_JSON") or "").strip()
    active_kid = (os.getenv("AUDIT_EXPORT_HMAC_ACTIVE_KID") or "").strip()

    key_map = {}
    if keys_json:
        try:
            parsed = json.loads(keys_json)
            if isinstance(parsed, dict):
                key_map = {str(k): str(v) for k, v in parsed.items() if str(v)}
        except Exception:
            raise HTTPException(status_code=500, detail="AUDIT_EXPORT_HMAC_KEYS_JSON is invalid JSON")

    if requested_kid:
        if requested_kid in key_map:
            return requested_kid, key_map[requested_kid]
        legacy = (os.getenv("AUDIT_EXPORT_HMAC_KEY") or "").strip()
        if requested_kid == "legacy" and legacy:
            return "legacy", legacy
        raise HTTPException(status_code=400, detail=f"unknown signature kid: {requested_kid}")

    if active_kid and active_kid in key_map:
        return active_kid, key_map[active_kid]

    legacy = (os.getenv("AUDIT_EXPORT_HMAC_KEY") or "").strip()
    if legacy:
        return "legacy", legacy

    if active_kid and key_map and active_kid not in key_map:
        raise HTTPException(status_code=500, detail="AUDIT_EXPORT_HMAC_ACTIVE_KID not present in AUDIT_EXPORT_HMAC_KEYS_JSON")

    raise HTTPException(status_code=500, detail="no signing key configured")


def verify_audit_export_signature_payload(payload_obj: dict, signature: str, kid: str | None = None):
    if not isinstance(payload_obj, dict):
        raise HTTPException(status_code=400, detail="payload JSON must be an object")
    if (
        not isinstance(signature, str)
        or len(signature) != 64
        or any(ch not in "0123456789abcdefABCDEF" for ch in signature)
    ):
        raise HTTPException(status_code=400, detail="signature must be a 64-char hex string")

    canonical = json.dumps(payload_obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)

    try:
        resolved_kid, key_raw = resolve_audit_export_signing_key(kid or None)
    except HTTPException as e:
        detail = str(e.detail)
        reason_code = "KEY_RESOLUTION_ERROR"
        if "unknown signature kid" in detail:
            reason_code = "UNKNOWN_KID"
        elif "invalid JSON" in detail:
            reason_code = "INVALID_KEYRING_JSON"
        elif "not present" in detail:
            reason_code = "ACTIVE_KID_MISSING"
        elif "no signing key configured" in detail:
            reason_code = "KEY_NOT_CONFIGURED"
        return {
            "ok": False,
            "reason": detail,
            "reason_code": reason_code,
            "signature_alg": "hmac-sha256",
            "signature_kid": kid or None,
        }

    expected = hmac.new(key_raw.encode("utf-8"), canonical.encode("utf-8"), hashlib.sha256).hexdigest()
    ok = hmac.compare_digest(expected, signature)

    return {
        "ok": ok,
        "reason": "signature_valid" if ok else "signature_mismatch",
        "reason_code": "SIGNATURE_VALID" if ok else "SIGNATURE_MISMATCH",
        "signature_alg": "hmac-sha256",
        "signature_kid": resolved_kid,
    }


# Aliases matching the names main.py used before these moved, so no call site in
# main.py had to change.
_log_audit = log_audit
_compute_audit_chain_report = compute_audit_chain_report
_resolve_audit_export_signing_key = resolve_audit_export_signing_key
_verify_audit_export_signature_payload = verify_audit_export_signature_payload
