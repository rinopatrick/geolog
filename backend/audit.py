"""Audit trail helpers shared by main.py and the audit/ops routers.

`log_audit` is used by routes throughout main.py, and the chain/signature helpers
are used by the /api/audit-log and /api/ops routes, so all of them live here
rather than in either caller.

Every row in `audit_log` must be chained: it stores the previous row's
`entry_hash` and its own. There is exactly one place that appends a row
(`append_audit_entry`), because a second, unchained writer silently breaks the
chain — which is what used to happen; see the note on `log_audit`.

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
from threading import Lock
from typing import Optional

from fastapi import HTTPException
from sqlalchemy import text
from sqlalchemy.orm import Session

try:
    from database import engine
    from models import AuditLog
    from validation import canonical_json
except ImportError:
    from backend.database import engine
    from backend.models import AuditLog
    from backend.validation import canonical_json

try:
    from filelock import interprocess_lock
except ImportError:
    from backend.filelock import interprocess_lock

try:
    from secretstore import read_secret
except ImportError:
    from backend.secretstore import read_secret

try:
    from well_state import ARTIFACT_DIR
except ImportError:
    from backend.well_state import ARTIFACT_DIR

# Serialises the read-previous-hash / insert pair. Without it two concurrent
# writes can both chain onto the same predecessor, producing two rows claiming
# the same prev_hash and a chain that fails its own verification.
_CHAIN_LOCK = Lock()
AUDIT_LOCK_FILE = os.path.join(ARTIFACT_DIR, "audit.lock")


def _canonical_payload(
    *,
    request_id: str,
    subject: str,
    role: str,
    method: str,
    path: str,
    status_code: int,
    payload_hash: str,
    prev_hash: str,
    well_id: Optional[int],
    project_id: Optional[int],
) -> str:
    """The exact bytes the chain hash is computed over.

    `compute_audit_chain_report` rebuilds this same object when verifying, so the
    field set and the JSON options must match it exactly.
    """
    return json.dumps({
        "request_id": request_id,
        "subject": subject,
        "role": role,
        "method": (method or "").upper(),
        "path": path,
        "status": int(status_code),
        "payload_hash": payload_hash,
        "prev_hash": prev_hash,
        "well_id": well_id,
        "project_id": project_id,
    }, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def append_audit_entry(
    db: Session,
    *,
    action: str,
    entity_type: str = "",
    entity_id: Optional[int] = None,
    well_id: Optional[int] = None,
    project_id: Optional[int] = None,
    details: str = "",
    request_id: str = "",
    subject: str = "",
    role: str = "viewer",
    method: str = "",
    path: str = "",
    status_code: Optional[int] = None,
    payload_hash: str = "",
    commit: bool = True,
) -> str:
    """Append one chained entry and return its entry_hash.

    The only writer of `audit_log`. Reads the previous entry's hash and inserts
    under a lock, so the chain cannot fork.
    """
    def _append_locked() -> str:
        previous = db.query(AuditLog).order_by(AuditLog.id.desc()).first()
        prev_hash = (getattr(previous, "entry_hash", "") or "") if previous else ""

        canonical = _canonical_payload(
            request_id=request_id or "",
            subject=subject or "",
            role=role or "viewer",
            method=method or "",
            path=path or "",
            status_code=status_code if status_code is not None else 0,
            payload_hash=payload_hash or "",
            prev_hash=prev_hash,
            well_id=well_id,
            project_id=project_id,
        )
        entry_hash = hashlib.sha256(canonical.encode("utf-8")).hexdigest()

        db.add(AuditLog(
            project_id=project_id,
            well_id=well_id,
            action=action,
            entity_type=entity_type,
            entity_id=entity_id,
            details=details,
            user_label="local",
            request_id=request_id or "",
            auth_subject=subject or "",
            auth_role=role or "viewer",
            route_path=path or "",
            method=method or "",
            status_code=status_code,
            payload_hash=payload_hash or "",
            prev_hash=prev_hash,
            entry_hash=entry_hash,
        ))
        if commit:
            db.commit()
        return entry_hash

    if engine.dialect.name == "postgresql":
        with _CHAIN_LOCK:
            # Postgres transaction-scoped advisory lock serialises the chain
            # across every instance, not just this host.
            db.execute(text("SELECT pg_advisory_xact_lock(:key)"), {"key": 0x47454F4C})
            return _append_locked()

    with _CHAIN_LOCK, interprocess_lock(AUDIT_LOCK_FILE):
        return _append_locked()

def log_audit(db: Session, action: str, entity_type: str = "", entity_id: int = None,
              well_id: int = None, project_id: int = None, details: str = ""):
    """Write an audit trail entry for an application-level action.

    This used to insert a bare AuditLog row with no prev_hash or entry_hash. That
    left the row failing verification and, worse, the next request-logged row
    chained onto an empty hash — so every route calling this broke the chain.
    Measured: POST /api/wells/1/template-lock produced two chain issues. It now
    uses the same chained append as the middleware.
    """
    return append_audit_entry(
        db,
        action=action,
        entity_type=entity_type,
        entity_id=entity_id,
        well_id=well_id,
        project_id=project_id,
        details=details,
    )


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
    keys_json = (read_secret("AUDIT_EXPORT_HMAC_KEYS_JSON") or "").strip()
    active_kid = (read_secret("AUDIT_EXPORT_HMAC_ACTIVE_KID") or "").strip()

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
        legacy = (read_secret("AUDIT_EXPORT_HMAC_KEY") or "").strip()
        if requested_kid == "legacy" and legacy:
            return "legacy", legacy
        raise HTTPException(status_code=400, detail=f"unknown signature kid: {requested_kid}")

    if active_kid and active_kid in key_map:
        return active_kid, key_map[active_kid]

    legacy = (read_secret("AUDIT_EXPORT_HMAC_KEY") or "").strip()
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

    canonical = canonical_json(payload_obj)

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
