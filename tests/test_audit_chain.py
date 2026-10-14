"""Audit chain integrity.

`audit_log` is an append-only provenance chain: each row stores the previous
row's entry_hash and its own. `/api/audit-log/verify` recomputes the chain, and
the security-evidence gate depends on it.

Two writers append rows — the request middleware in main.py and `log_audit()`,
which routes call directly. `log_audit()` used to insert a bare row with no
prev_hash or entry_hash. That broke the chain twice over: the row itself failed
verification, and the next request-logged row chained onto an empty hash.

Measured before the fix: `POST /api/wells/1/template-lock` produced exactly two
chain issues. Both writers now go through `append_audit_entry`.
"""

from __future__ import annotations

import hashlib
import json

from fastapi.testclient import TestClient

from backend.audit import _canonical_payload, append_audit_entry
from backend.database import SessionLocal
from backend.main import app
from backend.models import AuditLog

client = TestClient(app)
HEADERS = {"X-User-Role": "interpreter"}
VIEWER = {"X-User-Role": "viewer"}


def _verify() -> dict:
    response = client.get("/api/audit-log/verify", headers=VIEWER)
    assert response.status_code == 200, response.text[:200]
    return response.json()


def test_chain_is_intact_to_start_with():
    assert _verify()["ok"] is True, _verify()["issues"][:3]


def test_log_audit_routes_do_not_break_the_chain():
    """Regression: these routes used to append an unchained row."""
    before = _verify()

    # Routes that call log_audit() internally.
    client.post("/api/wells/1/template-lock", json={}, headers=HEADERS)
    client.post("/api/wells/1/template-unlock", json={}, headers=HEADERS)

    after = _verify()
    assert after["ok"] is True, (
        f"a log_audit() route broke the chain: {after['issues'][:3]}"
    )
    assert after["verified_entries"] >= before["verified_entries"]


def test_every_row_has_both_chain_fields():
    """No row may be written without prev_hash/entry_hash."""
    db = SessionLocal()
    try:
        rows = db.query(AuditLog).all()
    finally:
        db.close()

    assert rows, "no audit rows to check"
    missing = [r.id for r in rows if not (r.entry_hash or "").strip()]
    assert missing == [], f"rows written without an entry_hash: {missing[:10]}"


def test_rows_are_chained_in_id_order():
    """Each row's prev_hash must equal the previous row's entry_hash."""
    db = SessionLocal()
    try:
        rows = db.query(AuditLog).order_by(AuditLog.id.asc()).all()
    finally:
        db.close()

    previous_hash = ""
    broken = []
    for row in rows:
        if (row.prev_hash or "") != previous_hash:
            broken.append((row.id, previous_hash[:12], (row.prev_hash or "")[:12]))
        previous_hash = row.entry_hash or ""
    assert broken == [], f"prev_hash does not chain at rows: {broken[:5]}"


def test_entry_hash_matches_the_canonical_payload():
    """The stored hash must equal a recomputation from the stored fields."""
    db = SessionLocal()
    try:
        rows = db.query(AuditLog).order_by(AuditLog.id.asc()).all()
    finally:
        db.close()

    mismatched = []
    for row in rows:
        canonical = _canonical_payload(
            request_id=row.request_id or "",
            subject=row.auth_subject or "",
            role=row.auth_role or "viewer",
            method=row.method or "",
            path=row.route_path or "",
            status_code=int(row.status_code) if row.status_code is not None else 0,
            payload_hash=row.payload_hash or "",
            prev_hash=row.prev_hash or "",
            well_id=row.well_id,
            project_id=row.project_id,
        )
        recomputed = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
        if recomputed != (row.entry_hash or ""):
            mismatched.append(row.id)
    assert mismatched == [], f"entry_hash does not match its payload: {mismatched[:5]}"


def test_append_audit_entry_links_to_the_previous_row():
    db = SessionLocal()
    try:
        last = db.query(AuditLog).order_by(AuditLog.id.desc()).first()
        expected_prev = (last.entry_hash or "") if last else ""

        entry_hash = append_audit_entry(db, action="test:append", details="unit test")

        new_row = db.query(AuditLog).order_by(AuditLog.id.desc()).first()
        assert new_row.entry_hash == entry_hash
        assert new_row.prev_hash == expected_prev, "new row did not chain onto the last"
    finally:
        db.close()

    assert _verify()["ok"] is True


def test_tampering_is_blocked_by_the_immutability_trigger():
    """The primary defence: an UPDATE on audit_log is refused outright."""
    import pytest as _pytest
    from sqlalchemy.exc import IntegrityError

    db = SessionLocal()
    try:
        row = db.query(AuditLog).order_by(AuditLog.id.desc()).first()
        assert row is not None
        with _pytest.raises(IntegrityError):
            db.query(AuditLog).filter(AuditLog.id == row.id).update(
                {"payload_hash": "tampered"}
            )
            db.commit()
        db.rollback()
    finally:
        db.close()


def test_chain_detects_a_row_that_does_not_match_its_hash():
    """Secondary defence: if a row is altered out of band, verify reports it.

    The trigger blocks a normal UPDATE, so this drops it to simulate a change made
    outside the application (direct file edit, restore from a modified backup).
    """
    from sqlalchemy import text as sa_text

    db = SessionLocal()
    original_payload_hash = None
    try:
        row = db.query(AuditLog).order_by(AuditLog.id.desc()).first()
        assert row is not None
        row_id = row.id
        original_payload_hash = row.payload_hash or ""

        db.execute(sa_text("DROP TRIGGER IF EXISTS trg_audit_log_no_update"))
        db.commit()
        try:
            db.execute(
                sa_text("UPDATE audit_log SET payload_hash = :h WHERE id = :i"),
                {"h": "deadbeef" * 8, "i": row_id},
            )
            db.commit()
        finally:
            # Restore the trigger so later tests still see it.
            db.execute(sa_text("""
                CREATE TRIGGER IF NOT EXISTS trg_audit_log_no_update
                BEFORE UPDATE ON audit_log
                BEGIN
                    SELECT RAISE(ABORT, 'audit_log is immutable');
                END;
            """))
            db.commit()
    finally:
        db.close()

    result = _verify()
    assert result["ok"] is False, "a row inconsistent with its hash was not detected"
    assert any(i["type"] == "entry_hash_mismatch" for i in result["issues"]), (
        result["issues"][:3]
    )

    # Restore the row so later tests see an intact chain again.
    db = SessionLocal()
    try:
        db.execute(sa_text("DROP TRIGGER IF EXISTS trg_audit_log_no_update"))
        db.commit()
        try:
            db.execute(
                sa_text("UPDATE audit_log SET payload_hash = :h WHERE id = :i"),
                {"h": original_payload_hash, "i": row_id},
            )
            db.commit()
        finally:
            db.execute(sa_text("""
                CREATE TRIGGER IF NOT EXISTS trg_audit_log_no_update
                BEFORE UPDATE ON audit_log
                BEGIN
                    SELECT RAISE(ABORT, 'audit_log is immutable');
                END;
            """))
            db.commit()
    finally:
        db.close()

    assert _verify()["ok"] is True, "the tamper test did not restore the row"
