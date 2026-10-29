# Contributing to GeoLog

## Setup

Requires Python 3.11+, Node 20+ for the browser checks, and Git.

```bash
python -m venv .venv
# Windows: .venv\Scripts\activate
source .venv/bin/activate
pip install -r requirements-dev.txt
npm ci
```

Useful environment for local work:

```bash
export GEOLOG_ENV=dev
export GEOLOG_ENABLE_DEMO_SEED=true
export AUTH_JWT_SECRET=dev-only-secret-change-me
```

## Before changing code

- Read `README.md`, `docs/PROJECT_ACL.md` and `docs/API_VERSIONING.md`.
- Schema changes need an Alembic migration. Never use `create_all()`.
- New routes need a `tests/test_route_inventory.py` entry.
- New access checks need an allow and a deny test.

## Verification

```bash
python -m pytest tests/ -q
bash scripts/coverage_gate.sh
python -m alembic check
python -m compileall -q backend tests scripts
for f in frontend/js/*.js scripts/*.js; do node --check "$f"; done
```

Browser smoke needs a running API:

```bash
GEOLOG_ENV=dev GEOLOG_ENABLE_DEMO_SEED=true \
  python -m uvicorn backend.main:app --port 8000
npm run e2e
```

## Commits and pull requests

- Use Conventional Commits: `feat:`, `fix:`, `test:`, `docs:`, `ci:`, `chore:`.
- Keep the subject at or below 72 characters.
- One concern per commit; one concern per pull request when practical.
- Explain the failure mode in the body, not just the change.
- Include the verification commands you ran.
- Do not commit databases, WAL files, artifacts, logs, secrets or licensed data.

## Production-sensitive changes

Call these out explicitly in the PR:

- Auth, RBAC/ACL, token storage, rate limits.
- Upload/body limits and audit middleware.
- Migrations and startup behavior.
- Backup/restore or security-evidence signing.
- Anything that changes the public API contract.
