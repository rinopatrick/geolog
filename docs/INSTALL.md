# Borelia installation guide (operator)

Three paths, pick one. Developers wanting the fast loop should use Path A;
a shared team deployment wants Path C.

## Prerequisites

| Requirement | Version | Notes |
|---|---|---|
| Python | 3.10–3.12 (3.11 in Docker) | `scipy` needs ≥ 3.11; `dlisio` needs ≥ 3.10 |
| Node.js | 20+ | frontend smoke tests + asset build only |
| Docker + Compose plugin | recent | Paths B and C |
| Disk | ≥ 2 GB free | SQLite DB + SEG-Y artifacts + backups |

No internet is needed at runtime once dependencies are installed, except
for OIDC JWKS discovery (Path C) and optional OTLP tracing.

## Path A — local evaluation (5 minutes)

```bash
chmod +x run.sh
./run.sh
```

Open `http://localhost:8000`. Swagger at `/docs`. The SQLite database is
created on first start; demo data is seeded from `backend/demo.las` when
the database is empty.

Verify:

```bash
curl -sf http://localhost:8000/api/health
curl -sf http://localhost:8000/api/version
```

## Path B — single-host demo via Compose

```bash
docker compose up -d --build
curl -sf http://localhost:8000/api/health
```

Same as Path A but containerised. Data persists in the `borelia-data`
volume. **Do not expose this to a network**: it runs `BORELIA_ENV=dev`
with trusted-header auth. For anything beyond localhost, use Path C.

## Path C — production single host

Follow `docs/DEPLOYMENT.md` (migrate-first Compose, Caddy TLS, secrets as
files, nightly backup cron). Minimum checklist before going live:

- [ ] `AUTH_MODE=jwt` with issuer/audience/JWKS; header mode off.
- [ ] `docker compose -f docker-compose.prod.yml config` validates.
- [ ] `curl -sf https://HOSTNAME/api/health` returns 200.
- [ ] Security-evidence gate passes (see `docs/PRODUCTION_HARDENING.md` §5).
- [ ] Backup cron installed and the first drill report is signed.
- [ ] At least one project has a membership row (see §7 of the hardening doc).

## Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| `AUTH_MODE=header ... not allowed with BORELIA_ENV=prod` | Header auth blocked outside dev | Set `AUTH_MODE=jwt` + IdP vars |
| Alembic `FAILED: version ... is not a valid revision` | Stale `backend/borelia.db` from an older checkout | Delete the DB file (dev only) or restore a matching backup |
| `port 8000 already in use` | Old server still running | Stop it, or use `--port 8001` and set `BORELIA_BASE_URL` for e2e scripts |
| Playwright `ERR_CONNECTION_REFUSED` | API not up before browser tests | Wait for `/api/health` first; CI does this in the Start API step |
| `dlisio` import error on Python < 3.10 | Optional dep version guard | Use Python 3.11 (matches Docker) |
| Slow `prospect-maps` (> seconds) | Too many cells × iterations | Reduce grid resolution or iterations; the endpoint caps at 2M draws |

## Upgrade

```bash
git pull
docker compose -f docker-compose.prod.yml up -d --build   # or re-run run.sh
curl -sf http://localhost:8000/api/version   # confirm the new version
```

Migrations run automatically via the `migrate` service (prod) or at
startup (dev). They are forward-only: never downgrade; restore a backup
instead (see `docs/DEPLOYMENT.md` §5–6).
