#!/usr/bin/env bash
# Nightly backup + restore verification for a production GeoLog host.
# Usage (cron): 15 2 * * * /srv/geolog/scripts/nightly_backup.sh >> /var/log/geolog-backup.log 2>&1
# Requires: GEOLOG_DB_PATH, GEOLOG_ARTIFACT_DIR, BACKUP_DIR, BACKUP_DRILL_SIGNING_KEY.
set -euo pipefail

: "${GEOLOG_DB_PATH:?set GEOLOG_DB_PATH}"
: "${GEOLOG_ARTIFACT_DIR:?set GEOLOG_ARTIFACT_DIR}"
: "${BACKUP_DIR:?set BACKUP_DIR}"
: "${BACKUP_DRILL_SIGNING_KEY:?set BACKUP_DRILL_SIGNING_KEY}"

STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
DEST="$BACKUP_DIR/$STAMP"
mkdir -p "$DEST"
cd "$(dirname "$0")/.."

echo "[backup] drill at $STAMP"
bash scripts/backup_restore_drill.sh "$GEOLOG_DB_PATH" "$GEOLOG_ARTIFACT_DIR"
LATEST=$(ls -dt artifacts/backup-drill/*/ | head -1)
cp -r "$LATEST" "$DEST/drill"

echo "[backup] pruning drills older than 30 days"
find artifacts/backup-drill -maxdepth 1 -type d -mtime +30 -print -exec rm -rf {} + || true
find "$BACKUP_DIR" -maxdepth 1 -type d -mtime +30 -print -exec rm -rf {} + || true

echo "[backup] OK $STAMP"
