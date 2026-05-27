#!/usr/bin/env bash
set -euo pipefail

DB_PATH="${1:-backend/data/geolog.db}"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
OUT_DIR="artifacts/backup-drill/${STAMP}"
BACKUP_PATH="${OUT_DIR}/geolog.db.backup"
RESTORE_PATH="${OUT_DIR}/geolog.db.restore"
REPORT_PATH="${OUT_DIR}/report.json"
SIGNATURE_PATH="${OUT_DIR}/report.signature.json"

mkdir -p "${OUT_DIR}"

if [[ ! -f "${DB_PATH}" ]]; then
  echo "Database file not found: ${DB_PATH}" >&2
  exit 1
fi

cp "${DB_PATH}" "${BACKUP_PATH}"
cp "${BACKUP_PATH}" "${RESTORE_PATH}"

orig_sha="$(sha256sum "${DB_PATH}" | awk '{print $1}')"
backup_sha="$(sha256sum "${BACKUP_PATH}" | awk '{print $1}')"
restore_sha="$(sha256sum "${RESTORE_PATH}" | awk '{print $1}')"

python3 - <<'PY' "${DB_PATH}" "${RESTORE_PATH}" "${REPORT_PATH}" "${orig_sha}" "${backup_sha}" "${restore_sha}"
import json, sqlite3, sys, datetime, hashlib, hmac, os

db_path, restore_path, report_path, orig_sha, backup_sha, restore_sha = sys.argv[1:]

def count_tables(path):
    conn = sqlite3.connect(path)
    try:
        cur = conn.cursor()
        cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name")
        tables = [r[0] for r in cur.fetchall()]
        counts = {}
        for t in tables:
            cur.execute(f'SELECT COUNT(*) FROM "{t}"')
            counts[t] = int(cur.fetchone()[0])
        return counts
    finally:
        conn.close()

orig_counts = count_tables(db_path)
restore_counts = count_tables(restore_path)

report = {
    "timestamp": datetime.datetime.utcnow().isoformat() + "Z",
    "db_path": db_path,
    "backup_path": restore_path.replace('.restore', '.backup'),
    "restore_path": restore_path,
    "hashes": {
        "original": orig_sha,
        "backup": backup_sha,
        "restore": restore_sha,
        "hash_match": bool(orig_sha == backup_sha == restore_sha),
    },
    "row_counts": {
        "original": orig_counts,
        "restore": restore_counts,
        "row_count_match": bool(orig_counts == restore_counts),
    },
    "ok": bool((orig_sha == backup_sha == restore_sha) and (orig_counts == restore_counts)),
}

with open(report_path, "w", encoding="utf-8") as f:
    json.dump(report, f, ensure_ascii=False, indent=2)

report_bytes = json.dumps(report, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
report_sha256 = hashlib.sha256(report_bytes).hexdigest()

sig_payload = {
    "timestamp": datetime.datetime.utcnow().isoformat() + "Z",
    "report_path": report_path,
    "report_sha256": report_sha256,
    "signature_alg": None,
    "signature_kid": None,
    "signature": None,
    "retention_days": int(os.getenv("BACKUP_DRILL_RETENTION_DAYS", "30") or 30),
}

signing_key = (os.getenv("BACKUP_DRILL_SIGNING_KEY") or "").strip()
signing_kid = (os.getenv("BACKUP_DRILL_SIGNING_KID") or "backup-drill")
if signing_key:
    sig_payload["signature_alg"] = "hmac-sha256"
    sig_payload["signature_kid"] = signing_kid
    sig_payload["signature"] = hmac.new(signing_key.encode("utf-8"), report_sha256.encode("utf-8"), hashlib.sha256).hexdigest()

with open(report_path.replace("report.json", "report.signature.json"), "w", encoding="utf-8") as f:
    json.dump(sig_payload, f, ensure_ascii=False, indent=2)

print(json.dumps({"report": report, "signature": sig_payload}, ensure_ascii=False))
PY

echo "Backup drill report: ${REPORT_PATH}"
echo "Backup drill signature: ${SIGNATURE_PATH}"