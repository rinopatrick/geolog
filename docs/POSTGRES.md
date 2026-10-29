# PostgreSQL (opt-in)

SQLite remains the default. PostgreSQL is enabled with:

```bash
export GEOLOG_DATABASE_URL='postgresql+psycopg://geolog:secret@db:5432/geolog'
export GEOLOG_DB_POOL_SIZE=5
export GEOLOG_DB_MAX_OVERFLOW=10
```

`GEOLOG_DATABASE_URL` wins over `GEOLOG_DB_PATH`. Use the `+psycopg` driver.

For more than one app host, also set `GEOLOG_STATE_BACKEND=database`. Rate-limit
counters, metrics, job records, well locks, template locks and snapshots then
live in PostgreSQL, and the audit chain uses a transaction-scoped advisory lock.
Image/core assets and security-evidence files still live under
`GEOLOG_ARTIFACT_DIR`, so a multi-host deployment needs a shared volume or object
store for those files.

## Schema

```bash
cd backend
alembic upgrade head
```

`render_as_batch` is enabled only for SQLite. The app-level audit chain remains
the single writer for `audit_log`; no database trigger is installed on it because
an independent trigger would fork the hash chain. Operational DDL/DML auditing
should use the existing `/api/audit-log` and `/api/ops` evidence instead.

## Copy from SQLite

The target must be empty. The copy creates the schema, inserts in FK order,
verifies every table by count and SHA-256 content hash, and deletes copied rows
if verification fails. PostgreSQL identity sequences are advanced afterwards.

```bash
python -m backend.pg_tools copy \
  --source "sqlite:///backend/geolog.db" \
  --target "postgresql+psycopg://geolog:secret@db:5432/geolog"

python -m backend.pg_tools verify --source ... --target ...
python -m backend.pg_tools rollback --target ... --confirm
```

After a successful copy, run `alembic stamp head` because the copy does not
include Alembic's `alembic_version` table. `rollback` deletes every row in every
GeoLog table in the target; it requires `--confirm`.

## Multi-instance CI

`.github/workflows/postgres-multi-instance.yml` starts PostgreSQL, two uvicorn
instances and runs `scripts/multi_instance_probe.py`. The probe verifies shared
project/well ACL, login lockout, snapshot/well lock state and a job submitted on
one instance and observed on the other.

## Limits

- Multi-host app state requires `GEOLOG_STATE_BACKEND=database` and a shared
  artifact volume for binary assets.
- No online replication or dual-write mode.
- No automatic hash-chain audit triggers (deliberate; see above).
- File-backed state is not copied.
- The copy is offline; stop writers before taking the SQLite source.
