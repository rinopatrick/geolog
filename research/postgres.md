# GeoLog #17: SQLite to Postgres
## Recommendation
**Conditional go: dual-dialect, Postgres opt-in, SQLite default.** No hard cutover. Postgres removes SQLite's single-writer limit, not the single-host limit: locks, snapshots, jobs, metrics and audit lock stay on disk [5][6][7]. Move them first. Keep `data_binary` as `LargeBinary`/`BYTEA` and the JSON columns as `Text`; nothing queries JSON operators [1][9][10].
## Migration steps
1. **Config.** `database.py` hardcodes `sqlite:///` and `check_same_thread=False` [1]. Read `GEOLOG_DATABASE_URL`, fall back to `GEOLOG_DB_PATH`; apply `connect_args` only to SQLite; add `pool_pre_ping` and pool sizing for Postgres [8]. `env.py` imports the URL, so Alembic follows [2].
2. **Triggers.** Baseline uses SQLite `RAISE(ABORT)` triggers, invalid on Postgres [3]. Skip that block off-SQLite; add one revision installing a PL/pgSQL `RAISE EXCEPTION` trigger (`BEFORE UPDATE OR DELETE`) on Postgres, no-op on SQLite [11]. Existing SQLite DBs are stamped, so baseline will not re-run.
3. **Audit status.** `/api/audit-log/immutability-status` queries `sqlite_master`; use `pg_trigger` on Postgres [4].
4. **Audit chain.** `append_audit_entry` uses a filesystem lock [5], useless across hosts. On Postgres take `pg_advisory_xact_lock(<constant>)` before reading the last hash and hold it to commit [12]. Keep that lock for SQLite.
5. **Schema and copy.** Stop writes; `alembic upgrade head` on an empty Postgres DB. Keep `render_as_batch=True`; it only rewrites on SQLite [2][8]. Snapshot SQLite with `.backup`, not `cp` on a live file [13]. Copy in FK order, preserving IDs and bytes; batch inserts. Python copy beats pgloader, which needs `create no tables` and cascades on `include drop` [14].
6. **Sequences and verify.** `setval(pg_get_serial_sequence(...), max(id))` per table; empty tables use `setval(..., 1, false)` [15]. Compare counts, SHA-256 per `data_binary`, JSON parse counts, audit-chain report and a sample read, then cut over.
7. **Rollback.** Keep the T0 SQLite file and artifacts. Rollback is repointing the URL before new writes; after Postgres writes, those are lost. State RPO. No dual-write in phase 1.
Backups: keep the SQLite drill but use the backup API [13], not `cp` [17]; add `pg_dump -Fc` + `pg_restore` restore tests [16]; back up artifacts separately.
## What stays file-backed
Snapshots stay (versioned JSON duplicating tops/zones/params [6]); metrics/jobs stay for single-host phase 1 (`jobs.json` plus process-local executor [7]); well/template locks stay until multi-host; the audit lock is replaced by the advisory lock and audit rows move.
## Compatibility
Existing installs keep env and SQLite file; baseline is not re-run. New installs default to SQLite; `GEOLOG_DATABASE_URL` opts in. One Alembic head, dialect branches only for trigger DDL. Docker gains an optional `postgres` profile. Tests/drill must stop assuming `sqlite3` [17][18].
## Risks
- Baseline edits do not re-run on stamped DBs, but test fresh SQLite and fresh Postgres [3][18].
- A stale file lock forks the audit chain across hosts [5]; a missed sequence reset duplicates keys [15].
- `ORDER BY Well.name` can shift under Postgres collation; pin it.
- Curve edits remain read-modify-write; row locks do not prevent lost updates.
- `.backup` can restart under writes; quiesce first [13].
## Test matrix
| Layer | Cases |
|---|---|
| Dialect | fresh SQLite/Postgres, pre-Alembic stamp, upgrade twice, downgrade |
| Audit | triggers bite on both, status endpoint both, 100 concurrent appends one chain |
| Data | float64 round-trip, nulls, Unicode, empty tables, JSON, checksums |
| Copy | rerun, sequence reset, FK order, rollback |
| Concurrency | 2 Postgres workers, curve edits, shared-dir jobs/metrics |
| Backup | backup API restore, pg_dump/pg_restore, full pytest both backends |
## Staged release
v0.3.0 portability + Postgres CI; v0.3.x opt-in beta; v0.4.0 supported Postgres for servers, SQLite default for desktop; v0.5.0 move locks/jobs to DB, then multi-host.
## Evidence
| # | Source | URL | Key claim | Type | Confidence |
|---|---|---|---|---|---|
| 1 | `backend/database.py` | https://github.com/rinopatrick/geolog/blob/main/backend/database.py | Hardcoded SQLite URL/args | primary | high |
| 2 | `migrations/env.py` | https://github.com/rinopatrick/geolog/blob/main/backend/migrations/env.py | URL source; `render_as_batch` | primary | high |
| 3 | baseline | https://github.com/rinopatrick/geolog/blob/main/backend/migrations/versions/20261014_1233_4b064cf3e9be_baseline_schema.py | SQLite trigger DDL | primary | high |
| 4 | `routers/audit.py` | https://github.com/rinopatrick/geolog/blob/main/backend/routers/audit.py | `sqlite_master` query | primary | high |
| 5 | `backend/audit.py` | https://github.com/rinopatrick/geolog/blob/main/backend/audit.py | File lock around chain | primary | high |
| 6 | `backend/well_state.py` | https://github.com/rinopatrick/geolog/blob/main/backend/well_state.py | Locks/snapshots on disk | primary | high |
| 7 | `backend/jobs.py` | https://github.com/rinopatrick/geolog/blob/main/backend/jobs.py | `jobs.json` + file lock | primary | high |
| 8 | SQLAlchemy SQLite | https://docs.sqlalchemy.org/en/20/dialects/sqlite.html | `check_same_thread`, lock errors | primary | high |
| 9 | SQLAlchemy PostgreSQL | https://docs.sqlalchemy.org/en/20/dialects/postgresql.html | `psycopg`; JSON/JSONB | primary | high |
| 10 | `LargeBinary` | https://docs.sqlalchemy.org/en/20/core/type_basics.html | Maps to `BYTEA` | primary | high |
| 11 | PG trigger | https://www.postgresql.org/docs/current/sql-createtrigger.html | Trigger function semantics | primary | high |
| 12 | PG locks | https://www.postgresql.org/docs/current/functions-admin.html | `pg_advisory_xact_lock` | primary | high |
| 13 | SQLite backup | https://www.sqlite.org/backup.html | Online backup; `cp` caveat | primary | high |
| 14 | pgloader | https://pgloader.readthedocs.io/en/latest/ref/sqlite.html | Source; `include drop` | primary | high |
| 15 | PG `setval` | https://www.postgresql.org/docs/current/functions-sequence.html | Sequence reset | primary | high |
| 16 | `pg_dump` | https://www.postgresql.org/docs/current/app-pgdump.html | Consistent logical backup | primary | high |
| 17 | backup drill | https://github.com/rinopatrick/geolog/blob/main/scripts/backup_restore_drill.sh | Uses `cp` | primary | high |
| 18 | `tests/test_migrations.py` | https://github.com/rinopatrick/geolog/blob/main/tests/test_migrations.py | Tests use `sqlite3` | primary | high |
## Coverage
Direct: repo, issue #17, docs. Uncertain: production volume, host count, Postgres version. Blocked: no Postgres for copy/concurrency tests.
Skipped: executing migration/concurrency tests. Risk: production data volume and host topology may change the recommendation from opt-in to mandatory.
