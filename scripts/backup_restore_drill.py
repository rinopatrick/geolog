#!/usr/bin/env python3
"""Backup and restore drill for the SQLite database and artifact directory.

The drill is intentionally a real restore: it copies the database through
SQLite's backup API, copies the artifact tree, writes a SHA-256 manifest, then
restores both into a scratch directory and verifies every hash and row count.
The signed report is what the ops gate consumes.
"""

from __future__ import annotations

import argparse
import datetime
import hashlib
import hmac
import json
import os
import shutil
import sqlite3
from pathlib import Path
from typing import Any


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def backup_sqlite(source: Path, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists():
        destination.unlink()
    src = sqlite3.connect(str(source))
    try:
        dst = sqlite3.connect(str(destination))
        try:
            src.backup(dst)
        finally:
            dst.close()
    finally:
        src.close()


def table_counts(path: Path) -> dict[str, int]:
    conn = sqlite3.connect(str(path))
    try:
        cur = conn.cursor()
        cur.execute(
            "SELECT name FROM sqlite_master WHERE type='table' "
            "AND name NOT LIKE 'sqlite_%' ORDER BY name"
        )
        tables = [row[0] for row in cur.fetchall()]
        counts: dict[str, int] = {}
        for table in tables:
            cur.execute(f'SELECT COUNT(*) FROM "{table}"')
            counts[table] = int(cur.fetchone()[0])
        return counts
    finally:
        conn.close()


def integrity_ok(path: Path) -> bool:
    conn = sqlite3.connect(str(path))
    try:
        row = conn.execute("PRAGMA integrity_check").fetchone()
        return bool(row and str(row[0]).lower() == "ok")
    finally:
        conn.close()


def copy_tree(source: Path, destination: Path) -> list[Path]:
    copied: list[Path] = []
    if not source.exists():
        return copied
    for item in sorted(source.rglob("*")):
        if not item.is_file():
            continue
        rel = item.relative_to(source)
        target = destination / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(item, target)
        copied.append(rel)
    return copied


def report_hashes_match(backup: Path, restore: Path) -> bool:
    return sha256_file(backup) == sha256_file(restore)


def build_manifest(entries: dict[str, Path]) -> dict[str, Any]:
    files: dict[str, Any] = {}
    for logical_name, path in sorted(entries.items()):
        if path.is_file():
            files[logical_name] = {
                "sha256": sha256_file(path),
                "bytes": path.stat().st_size,
            }
    return {"files": files, "file_count": len(files)}


def verify_manifest(root: Path, manifest: dict[str, Any]) -> list[str]:
    problems: list[str] = []
    expected = manifest.get("files") or {}
    for rel, entry in expected.items():
        target = root / rel
        if not target.exists():
            problems.append(f"missing: {rel}")
            continue
        actual = sha256_file(target)
        if actual != entry.get("sha256"):
            problems.append(f"hash mismatch: {rel}")
    return problems


def sign_report(report: dict[str, Any], signature_path: Path) -> dict[str, Any]:
    report_bytes = json.dumps(report, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    report_sha256 = hashlib.sha256(report_bytes).hexdigest()
    signing_key = (os.getenv("BACKUP_DRILL_SIGNING_KEY") or "").strip()
    signing_kid = (os.getenv("BACKUP_DRILL_SIGNING_KID") or "backup-drill")
    payload = {
        "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat().replace("+00:00", "Z"),
        "report_path": str(signature_path).replace("report.signature.json", "report.json"),
        "report_sha256": report_sha256,
        "signature_alg": None,
        "signature_kid": None,
        "signature": None,
        "retention_days": int(os.getenv("BACKUP_DRILL_RETENTION_DAYS", "30") or 30),
    }
    if signing_key:
        payload["signature_alg"] = "hmac-sha256"
        payload["signature_kid"] = signing_kid
        payload["signature"] = hmac.new(
            signing_key.encode("utf-8"), report_sha256.encode("utf-8"), hashlib.sha256
        ).hexdigest()
    signature_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return payload


def run_drill(db_path: Path, artifact_dir: Path | None) -> dict[str, Any]:
    stamp = datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out_dir = Path("artifacts") / "backup-drill" / stamp
    out_dir.mkdir(parents=True, exist_ok=True)

    backup_db = out_dir / "geolog.db.backup"
    backup_artifacts = out_dir / "artifacts.backup"
    restore_dir = out_dir / "restore"
    restore_db = restore_dir / "geolog.db"
    restore_artifacts = restore_dir / "artifacts"

    backup_sqlite(db_path, backup_db)
    artifact_files = copy_tree(artifact_dir, backup_artifacts) if artifact_dir else []

    manifest_entries: dict[str, Path] = {"geolog.db": backup_db}
    if artifact_dir:
        for rel in artifact_files:
            manifest_entries[f"artifacts/{rel.as_posix()}"] = backup_artifacts / rel
    manifest = build_manifest(manifest_entries)
    (out_dir / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")

    # Restore into a scratch directory and verify what landed there.
    restore_dir.mkdir(parents=True, exist_ok=True)
    shutil.copy2(backup_db, restore_db)
    if artifact_dir:
        copy_tree(backup_artifacts, restore_artifacts)

    original_counts = table_counts(db_path)
    restore_counts = table_counts(restore_db)
    restore_integrity = integrity_ok(restore_db)
    artifact_problems = verify_manifest(restore_dir, manifest)

    report = {
        "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat().replace("+00:00", "Z"),
        "db_path": str(db_path),
        "artifact_dir": str(artifact_dir) if artifact_dir else "",
        "backup_db": str(backup_db),
        "restore_db": str(restore_db),
        "hashes": {
            "original": sha256_file(db_path),
            "backup": sha256_file(backup_db),
            "restore": sha256_file(restore_db),
            "backup_restore_match": sha256_file(backup_db) == sha256_file(restore_db),
        },
        "row_counts": {
            "original": original_counts,
            "restore": restore_counts,
            "match": original_counts == restore_counts,
        },
        "integrity": {"restore": restore_integrity},
        "artifacts": {
            "file_count": len(artifact_files),
            "manifest_file_count": manifest["file_count"],
            "problems": artifact_problems,
            "ok": not artifact_problems,
        },
        "ok": bool(
            original_counts == restore_counts
            and restore_integrity
            and not artifact_problems
            and report_hashes_match(backup_db, restore_db)
        ),
    }
    report_path = out_dir / "report.json"
    report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    signature = sign_report(report, out_dir / "report.signature.json")

    print(json.dumps({"report": report, "signature": signature}, ensure_ascii=False))
    print(f"Backup drill report: {report_path}")
    print(f"Backup drill signature: {out_dir / 'report.signature.json'}")
    return report


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("db_path", nargs="?", default="backend/data/geolog.db")
    parser.add_argument("artifact_dir", nargs="?", default="")
    args = parser.parse_args()
    db_path = Path(args.db_path)
    if not db_path.is_file():
        print(f"Database file not found: {db_path}", flush=True)
        return 1
    artifact_dir = Path(args.artifact_dir) if args.artifact_dir else None
    report = run_drill(db_path, artifact_dir)
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
