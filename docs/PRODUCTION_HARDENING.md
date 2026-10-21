# Production Hardening

GeoLog is pre-production. This page lists the minimum work needed before putting
it behind a real user population.

## 1. Identity provider and token lifecycle

Set `GEOLOG_ENV=prod` and `AUTH_MODE=jwt`. The trusted-header mode is refused
outside dev/test/ci.

Recommended: let an OIDC provider sign tokens and publish a JWKS endpoint.

```bash
AUTH_MODE=jwt
AUTH_JWT_ISSUER=https://idp.example.com/
AUTH_JWT_AUDIENCE=geolog-api
AUTH_JWT_JWKS_URL=https://idp.example.com/.well-known/jwks.json
AUTH_JWT_ALGORITHMS=RS256
AUTH_JWT_TTL_SECONDS=3600
AUTH_JWT_LEEWAY_SECONDS=30
```

- `role` (or `roles[0]`) in the token must be `viewer`, `interpreter` or `admin`.
- A PEM public key is also supported: `AUTH_JWT_PUBLIC_KEY` or
  `AUTH_JWT_PUBLIC_KEY_FILE`. RS256/JWKS needs `cryptography`, installed from
  `backend/requirements.txt` on Python 3.10+.
- HS256 is supported with `AUTH_JWT_SECRET`/`AUTH_JWT_SECRET_FILE`, but a shared
  secret is not an identity provider. Use it only for internal service tokens.
- Local token issuance (`POST /api/users/token`) returns `expires_in` and is
  intended for development or small internal deployments. It is not a refresh
  flow and has no revocation list. Use short TTLs and the IdP for production.
- Rotate secrets/keys through the secret manager, not a commit.

## 2. Secrets

Every supported secret can be supplied directly or via `<NAME>_FILE`, which is
the Docker/Kubernetes secret convention.

| Secret | File form |
| --- | --- |
| `AUTH_JWT_SECRET` | `AUTH_JWT_SECRET_FILE` |
| `AUTH_JWT_PUBLIC_KEY` | `AUTH_JWT_PUBLIC_KEY_FILE` |
| `AUDIT_EXPORT_HMAC_KEYS_JSON` | `AUDIT_EXPORT_HMAC_KEYS_JSON_FILE` |
| `AUDIT_EXPORT_HMAC_KEY` | `AUDIT_EXPORT_HMAC_KEY_FILE` |
| `BACKUP_DRILL_SIGNING_KEY` | `BACKUP_DRILL_SIGNING_KEY_FILE` |

Example Docker Compose:

```yaml
services:
  geolog:
    secrets:
      - auth_jwt_secret
    environment:
      AUTH_JWT_SECRET_FILE: /run/secrets/auth_jwt_secret
secrets:
  auth_jwt_secret:
    file: ./secrets/auth_jwt_secret
```

Non-dev startup also requires `GEOLOG_SECRETS_SOURCE` (a label such as `vault`,
`aws-secrets-manager`, or `docker-secrets`) unless
`GEOLOG_ENFORCE_SECRETS_SOURCE=false`.

## 3. TLS

Terminate TLS at a reverse proxy (Caddy, nginx, an ingress controller) and make
sure the proxy forwards the original scheme:

```nginx
location / {
    proxy_pass http://127.0.0.1:8000;
    proxy_set_header Host $host;
    proxy_set_header X-Forwarded-Proto $scheme;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
}
```

Run uvicorn with proxy headers enabled (default in recent versions, but be
explicit) and only trust the proxy:

```bash
python -m uvicorn backend.main:app --host 127.0.0.1 --port 8000 \
  --proxy-headers --forwarded-allow-ips=127.0.0.1 --workers 2
```

Set `GEOLOG_REQUIRE_HTTPS=true` to redirect plain HTTP with 308 and add HSTS on
HTTPS responses. `/api/health` is exempt so an internal container health check can
use plain HTTP. The application always sends `X-Content-Type-Options`,
`X-Frame-Options`, `Referrer-Policy` and `Permissions-Policy`.

## 4. Persistence and workers

- SQLite is a single-host database. Do not put it on NFS or share it between
  hosts. Use one host (multiple uvicorn workers are fine).
- Set `GEOLOG_DB_PATH` and `GEOLOG_ARTIFACT_DIR` to mounted persistent volumes.
- The audit chain, metrics, jobs, well locks and snapshots use a cross-process
  file lock. The volumes must support file locking.
- Back up the database and `GEOLOG_ARTIFACT_DIR` together. `artifacts/` contains
  snapshots, locks, metrics, jobs and security evidence.

## 5. Backup and restore drill

```bash
bash scripts/backup_restore_drill.sh "$GEOLOG_DB_PATH"
python scripts/security_evidence_attest.py \
  --base-url https://geolog.example.com \
  --artifact-dir artifacts/backup-drill
```

Schedule the drill (for example nightly), keep the signed evidence for the
retention period, and test a restore into a scratch instance. The API gate is:

```bash
GET /api/ops/security-evidence/gate/enforce?max_age_seconds=86400&min_retention_days=30
```

A failed gate returns 503 with a machine-readable reason.

## 6. Monitoring and alerts

Prometheus can scrape:

```yaml
scrape_configs:
  - job_name: geolog
    metrics_path: /api/ops/metrics/prometheus
    static_configs:
      - targets: ["geolog.internal:8000"]
```

Useful endpoints:

- `/api/ops/metrics`, `/api/ops/metrics/prometheus`
- `/api/ops/slo-status`, `/api/ops/alerts`, `/api/ops/runbook`
- `/api/ops/health`, `/api/health`
- `/api/ops/summary`

Create alerts for 5xx rate, average/p95 latency, audit-chain verification
failures, and stale security evidence. The runbook endpoint returns the
machine-readable alert descriptions.

## 7. Release checklist

- [ ] `AUTH_MODE=jwt`, issuer/audience/JWKS configured, header mode off.
- [ ] `AUTH_JWT_TTL_SECONDS` and leeway set for the IdP.
- [ ] Secrets mounted as files; no secrets in the image or Compose file.
- [ ] TLS terminates at the proxy; `GEOLOG_REQUIRE_HTTPS=true`.
- [ ] `GEOLOG_DB_PATH` and `GEOLOG_ARTIFACT_DIR` on persistent volumes.
- [ ] Backup/restore drill passes and evidence is signed.
- [ ] Prometheus scrape, SLO alerts and on-call runbook are live.
- [ ] `pytest`, `alembic check`, browser smoke and the SLO gate pass in CI.
- [ ] A restore has been performed on a scratch instance.
