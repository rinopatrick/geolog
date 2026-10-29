"""Audit-log router for GeoLog.

Append-only provenance chain: listing, chain verification, and signed export
verification. The signing and chain helpers live in backend/audit.py because the
/api/ops routes use the same ones.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.orm import Session

try:
    from timeutils import utcnow
except ImportError:
    from backend.timeutils import utcnow

try:
    from acl import can_access_well, require_project_access, require_well_access, request_role, request_subject, visible_project_ids
    from audit import (
        compute_audit_chain_report,
        resolve_audit_export_signing_key,
        verify_audit_export_signature_payload,
    )
    from database import engine, get_db
    from deps import require_interpreter, require_viewer
    from models import AuditLog
    from version import __version__
except ImportError:
    from backend.acl import can_access_well, require_project_access, require_well_access, request_role, request_subject, visible_project_ids
    from backend.audit import (
        compute_audit_chain_report,
        resolve_audit_export_signing_key,
        verify_audit_export_signature_payload,
    )
    from backend.database import engine, get_db
    from backend.deps import require_interpreter, require_viewer
    from backend.models import AuditLog
    from backend.version import __version__

router = APIRouter(prefix="/api/audit-log", tags=["audit"])


AuditReasonCode = Literal[
    "SIGNATURE_VALID",
    "SIGNATURE_MISMATCH",
    "UNKNOWN_KID",
    "INVALID_KEYRING_JSON",
    "ACTIVE_KID_MISSING",
    "KEY_NOT_CONFIGURED",
    "KEY_RESOLUTION_ERROR",
]


class AuditSignatureVerifyRequest(BaseModel):
    payload: dict[str, Any]
    signature: str = Field(..., min_length=64, max_length=64, pattern="^[0-9a-fA-F]{64}$")
    kid: str | None = None


class AuditSignatureVerifyResponse(BaseModel):
    ok: bool
    reason: str
    reason_code: AuditReasonCode
    signature_alg: str
    signature_kid: str | None = None


@router.get("")
def get_audit_log(request: Request, project_id: int = None, well_id: int = None,
                  limit: int = 100, db: Session = Depends(get_db)):
    """Return audit trail, optionally filtered by project or well."""
    q = db.query(AuditLog)
    if project_id:
        require_project_access(db, request, project_id)
        q = q.filter(AuditLog.project_id == project_id)
    if well_id:
        require_well_access(db, request, well_id)
        q = q.filter(AuditLog.well_id == well_id)
    if not project_id and not well_id:
        all_ids = [row[0] for row in db.query(AuditLog.project_id).distinct().all() if row[0] is not None]
        visible = visible_project_ids(db, request_subject(request), request_role(request), all_ids)
        if visible is not None:
            q = q.filter(AuditLog.project_id.in_(visible))
    rows = q.order_by(AuditLog.created_at.desc()).limit(min(limit, 500)).all()
    if request_role(request) != "admin":
        subject = request_subject(request)
        role = request_role(request)
        rows = [
            r for r in rows
            if not r.well_id or can_access_well(db, int(r.well_id), subject, role)
        ]
    result = []
    for r in rows:
        d = {c.name: getattr(r, c.name) for c in AuditLog.__table__.columns}
        d["created_at"] = d["created_at"].isoformat() if d["created_at"] else ""
        result.append(d)
    return result


@router.get("/verify")
def verify_audit_log_chain(limit: int = 2000, db: Session = Depends(get_db)):
    """Recompute immutable audit chain and report tamper gaps."""
    return compute_audit_chain_report(limit, db)


@router.get("/immutability-status")
def audit_log_immutability_status(_role: str = Depends(require_viewer)):
    """Report whether append-only audit triggers are installed."""
    trigger_names = ["trg_audit_log_no_update", "trg_audit_log_no_delete"]
    present: dict[str, bool] = {k: False for k in trigger_names}

    with engine.connect() as conn:
        rows = conn.execute(
            text("SELECT name FROM sqlite_master WHERE type='trigger' AND name IN ('trg_audit_log_no_update','trg_audit_log_no_delete')")
        ).fetchall()

    for row in rows:
        n = str(row[0])
        if n in present:
            present[n] = True

    return {
        "ok": all(present.values()),
        "append_only_enforced": all(present.values()),
        "triggers": present,
    }


@router.get("/verify/export")
def export_audit_log_verification(
    request: Request,
    limit: int = 2000,
    sign: bool = False,
    kid: str | None = None,
    db: Session = Depends(get_db),
):
    """Export verification report with SHA256 digest and optional detached HMAC signature."""
    report = compute_audit_chain_report(limit, db)
    payload = {
        "generated_at": utcnow().isoformat() + "Z",
        "report": report,
        "trace": {
            "request_id": request.headers.get("X-Request-ID") or "",
            "auth_subject": str(getattr(request.state, "auth_subject", "") or ""),
            "auth_role": str(getattr(request.state, "user_role", "viewer") or "viewer"),
            "input": {"limit": int(limit)},
            "code_version": (os.getenv("GEOLOG_CODE_VERSION") or __version__).strip() or "unknown",
        },
    }
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()

    out = {
        "digest_sha256": digest,
        "payload": payload,
        "signature": None,
        "signature_alg": None,
        "signature_detached": True,
        "signature_kid": None,
    }

    if sign:
        resolved_kid, key_raw = resolve_audit_export_signing_key(kid)
        key = key_raw.encode("utf-8")
        sig = hmac.new(key, canonical.encode("utf-8"), hashlib.sha256).hexdigest()
        out["signature"] = sig
        out["signature_alg"] = "hmac-sha256"
        out["signature_kid"] = resolved_kid

    return out


@router.get(
    "/verify/signature",
    response_model=AuditSignatureVerifyResponse,
    responses={
        200: {
            "description": "Signature verification result",
            "content": {
                "application/json": {
                    "examples": {
                        "valid": {
                            "summary": "Valid signature",
                            "value": {
                                "ok": True,
                                "reason": "signature_valid",
                                "reason_code": "SIGNATURE_VALID",
                                "signature_alg": "hmac-sha256",
                                "signature_kid": "k1",
                            },
                        },
                        "mismatch": {
                            "summary": "Signature mismatch",
                            "value": {
                                "ok": False,
                                "reason": "signature_mismatch",
                                "reason_code": "SIGNATURE_MISMATCH",
                                "signature_alg": "hmac-sha256",
                                "signature_kid": "k1",
                            },
                        },
                    }
                }
            },
        }
    },
)
def verify_audit_log_export_signature(payload: str, signature: str, kid: str | None = None):
    """Verify detached HMAC signature for exported audit verification payload.

    payload: canonical payload JSON string.
    """
    if not isinstance(payload, str) or not payload.strip():
        raise HTTPException(status_code=400, detail="payload must be a non-empty JSON string")

    try:
        parsed_payload = json.loads(payload)
    except Exception:
        raise HTTPException(status_code=400, detail="payload must be valid JSON")

    return verify_audit_export_signature_payload(parsed_payload, signature, kid)


@router.post(
    "/verify/signature",
    response_model=AuditSignatureVerifyResponse,
)
def verify_audit_log_export_signature_post(
    data: AuditSignatureVerifyRequest,
    _role: str = Depends(require_interpreter),
):
    """M2M verifier. Body: {payload: object, signature: hex64, kid?: string}."""
    return verify_audit_export_signature_payload(data.payload, data.signature, data.kid)
