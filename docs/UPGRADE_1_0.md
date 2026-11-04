# Upgrade to Borelia 1.0

Breaking rename from GeoLog. Three lines, no aliases.

## 1. Env vars

Rename every `GEOLOG_*` to `BORELIA_*`:

```bash
env | grep '^GEOLOG_' || true
```

Startup aborts with `Stale GEOLOG_ env vars present` until all are renamed.
There is no backward compat alias.

## 2. DB file

Default moved from `geolog.db` to `borelia.db`.

```bash
cp geolog.db borelia.db
```

Or point `BORELIA_DB_PATH` at the old file. Fresh installs write `borelia.db`.

## 3. Compose volume

Volume `geolog-data` is now `borelia-data`:

```bash
docker volume create borelia-data
```

## Verify before cutover

Run the restore drill on a copy, never on production directly:

```bash
cp "$BORELIA_DB_PATH" /tmp/drill-copy.db
BORELIA_DB_PATH=/tmp/drill-copy.db bash scripts/backup_restore_drill.sh /tmp/drill-copy.db "$BORELIA_ARTIFACT_DIR"
```

The drill copies through the SQLite backup API, restores into scratch, and
verifies `PRAGMA integrity_check` plus every manifest hash and row count.
Cut over only when the signed report passes.
