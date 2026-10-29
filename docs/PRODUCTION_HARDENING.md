# Production Hardening

GeoLog is a release candidate for a single-team, single-host deployment. This
page lists the controls to review before putting it behind a real user
population, and the remaining gaps for a multi-tenant/SLA deployment.

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
  intended for development or small internal deployments. It now has refresh
  rotation and jti revocation; still prefer the IdP for production.
- Rotate secrets/keys through the secret manager, not a commit.
- Locally managed user secrets are stored as PBKDF2-HMAC-SHA256 hashes. A
  plaintext row is upgraded and cleared on its first successful login. Tune the
  cost with `GEOLOG_PBKDF2_ITERATIONS` (default 240000).
- Login throttling defaults to 30 attempts per IP per 300s, then 5 failures per
  account lock the account for 900s. Tune with `GEOLOG_AUTH_*`; if a trusted
  reverse proxy is in front, set `GEOLOG_TRUST_PROXY=true` so limits use the
  forwarded client address. Do not enable that on a directly reachable port.

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

## 3. TLS and request limits

Terminate TLS at a reverse proxy (Caddy, nginx, an ingress controller) and make
sure the proxy forwards the original scheme. The application enforces
`GEOLOG_MAX_UPLOAD_BYTES` (default 256 MiB) and `GEOLOG_MAX_BODY_BYTES`
(default 64 MiB), but the proxy should reject oversized bodies too:

```nginx
location / {
    client_max_body_size 256m;
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
use plain HTTP. The application sends `X-Content-Type-Options`, `X-Frame-Options`,
`Referrer-Policy`, `Permissions-Policy`, `Cross-Origin-Resource-Policy`,
`X-API-Version` and a Content-Security-Policy. The CSP still allows inline
handlers because the bundled frontend uses them; remove `'unsafe-inline'` after
that refactor.

## 4. Persistence and workers

- Run migrations as a deploy step, once:
  `GEOLOG_ENV=prod python -m alembic upgrade head`. Production startup verifies
  the schema and fails fast instead of running DDL from every worker.
- SQLite is a single-host database. Do not put it on NFS or share it between
  hosts. Use one host (multiple uvicorn workers are fine).
- Set `GEOLOG_DB_PATH` and `GEOLOG_ARTIFACT_DIR` to mounted persistent volumes.
- The audit chain, metrics, jobs, well locks and snapshots use a cross-process
  file lock. The volumes must support file locking.
- Back up the database and `GEOLOG_ARTIFACT_DIR` together. `artifacts/` contains
  snapshots, locks, metrics, jobs and security evidence.

## 5. Backup and restore drill

```bash
bash scripts/backup_restore_drill.sh "$GEOLOG_DB_PATH" "$GEOLOG_ARTIFACT_DIR"
python scripts/security_evidence_attest.py \
  --base-url https://geolog.example.com \
  --artifact-dir artifacts/backup-drill
```

The drill uses SQLite's backup API, copies the artifact tree, writes a SHA-256
manifest, restores both into a scratch directory, checks `PRAGMA integrity_check`
and every manifest hash, then signs the report. Schedule it nightly, keep the
signed evidence for the retention period, and test a restore into a scratch
instance. The API gate is:

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

For distributed tracing, install the optional stack and point it at an OTLP/HTTP
collector:

```bash
pip install -r requirements-observability.txt
export GEOLOG_OTEL_ENABLED=true
export GEOLOG_OTEL_ENDPOINT=http://otel-collector:4318/v1/traces
export GEOLOG_OTEL_SERVICE_NAME=geolog
```

Without those packages, enabling the flag logs one warning and leaves the app
running. Health and metrics endpoints are excluded by default.

For an external error stream, set `GEOLOG_ERROR_WEBHOOK_URL`. Unhandled 5xx
errors are sent as JSON with request ID, trace ID, role, path and exception
type/message; query strings, bodies, tokens and subjects are excluded.
`GEOLOG_ERROR_WEBHOOK_INCLUDE_TRACE=true` adds a truncated traceback. A local
rate limit suppresses duplicate reports.

## 7. Project membership

Project and per-well ACL are enabled by default. A project or well with no
members remains open for legacy data; adding the first member restricts it.
See [`PROJECT_ACL.md`](PROJECT_ACL.md) for the contract and endpoints. Review
which projects are still open before onboarding external users:

```bash
# Every project with no membership row is open.
python - <<'PY'
from backend.database import SessionLocal
from backend.models import Project, ProjectMember

db = SessionLocal()
try:
    for project in db.query(Project).all():
        if not db.query(ProjectMember).filter_by(project_id=project.id).count():
            print(project.id, project.name)
finally:
    db.close()
PY
```

## 8. Release checklist

- [ ] `AUTH_MODE=jwt`, issuer/audience/JWKS configured, header mode off.
- [ ] `AUTH_JWT_TTL_SECONDS` and leeway set for the IdP.
- [ ] `GEOLOG_TRUST_PROXY=true` only when the proxy is the only reachable path.
- [ ] Login rate limits and upload/body caps reviewed for the expected file sizes.
- [ ] Secrets mounted as files; no secrets in the image or Compose file.
- [ ] TLS terminates at the proxy; `GEOLOG_REQUIRE_HTTPS=true`.
- [ ] Interactive API docs are disabled (`GEOLOG_ENABLE_DOCS` unset in prod) or
      protected by the proxy.
- [ ] `GEOLOG_DB_PATH` and `GEOLOG_ARTIFACT_DIR` on persistent volumes.
- [ ] `alembic upgrade head` runs once as a deploy step, before workers start.
- [ ] Every project or well that must be restricted has at least one member row.
- [ ] Backup/restore drill passes with the artifact directory and evidence is signed.
- [ ] Prometheus scrape, SLO alerts and on-call runbook are live.
- [ ] `coverage_gate.sh`, `alembic check`, browser smoke and the SLO gate pass in CI.
- [ ] A restore has been performed on a scratch instance.
