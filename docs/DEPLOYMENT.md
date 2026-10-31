# Production deployment runbook

Target: single host, Docker Compose, Caddy TLS, SQLite on a persistent
volume. For multi-host, see `docs/POSTGRES.md`.

## 1. Prerequisites

- Host with Docker + Compose plugin, public DNS pointing at it.
- `AUTH_JWT_ISSUER`, `AUTH_JWT_AUDIENCE`, `AUTH_JWT_JWKS_URL` from the IdP.
- A file `./secrets/auth_jwt_secret` (HS256 fallback only) with 0600 perms.
- Replace `geolog.example.com` in `deploy/Caddyfile` with the real hostname.

## 2. First deploy

```bash
cp docker-compose.prod.yml docker-compose.yml   # or: docker compose -f docker-compose.prod.yml up
export AUTH_JWT_ISSUER=https://idp.example.com/
export AUTH_JWT_AUDIENCE=geolog-api
export AUTH_JWT_JWKS_URL=https://idp.example.com/.well-known/jwks.json
mkdir -p secrets && openssl rand -hex 32 > secrets/auth_jwt_secret && chmod 600 secrets/auth_jwt_secret
docker compose -f docker-compose.prod.yml up -d --build
docker compose -f docker-compose.prod.yml ps
curl -sf https://HOSTNAME/api/health
```

Order matters: the `migrate` service runs `alembic upgrade head` once and
must complete before `geolog` starts (Compose `depends_on` enforces this).
Never run the app container with a pending migration — startup fails fast
by design.

## 3. Updates

```bash
git pull
docker compose -f docker-compose.prod.yml up -d --build
docker compose -f docker-compose.prod.yml exec geolog python -m alembic upgrade head  # safety: no-op if migrate ran
curl -sf https://HOSTNAME/api/version
```

Checklist (mirrors `docs/PRODUCTION_HARDENING.md` release checklist): auth
mode jwt, TLS live, secrets mounted as files, docs endpoint off or proxied,
persistent volumes attached, backup cron active.

## 4. Backup (nightly cron)

On the host (not in a container — it needs the volume path):

```cron
15 2 * * * /srv/geolog/scripts/nightly_backup.sh >> /var/log/geolog-backup.log 2>&1
```

Required env in the cron environment (or `/etc/geolog/backup.env` sourced
by the wrapper): `GEOLOG_DB_PATH`, `GEOLOG_ARTIFACT_DIR`, `BACKUP_DIR`,
`BACKUP_DRILL_SIGNING_KEY`. Each run executes the full restore drill into
a scratch directory, verifies `PRAGMA integrity_check` plus every manifest
hash, signs the report, and prunes drills older than 30 days.

Verify a restore manually after any storage change:

```bash
bash scripts/backup_restore_drill.sh "$GEOLOG_DB_PATH" "$GEOLOG_ARTIFACT_DIR"
python scripts/security_evidence_attest.py \
  --base-url https://HOSTNAME --artifact-dir artifacts/backup-drill
```

## 5. Restore

1. Stop the stack: `docker compose -f docker-compose.prod.yml stop geolog`.
2. Copy the signed `geolog.db.backup` over `GEOLOG_DB_PATH` and the
   `artifacts.backup` tree over `GEOLOG_ARTIFACT_DIR`.
3. Start and verify: `docker compose -f docker-compose.prod.yml start geolog`
   then `curl -sf https://HOSTNAME/api/health` and the security-evidence
   gate from `docs/PRODUCTION_HARDENING.md` §5.

## 6. Rollback

Releases are tags. To roll back the app (not the data):

```bash
git checkout <previous-tag>
docker compose -f docker-compose.prod.yml up -d --build
```

Never downgrade the database: Alembic migrations here are forward-only.
If a release included a migration, restoring the old code against the new
schema is unsupported — restore the matching backup instead (step 5).

## 7. What is NOT covered

- Multi-host / failover (needs Postgres + shared object store).
- Log shipping, metrics retention, paging (wire Prometheus + on-call).
- Secret rotation automation (manual via secret manager).
