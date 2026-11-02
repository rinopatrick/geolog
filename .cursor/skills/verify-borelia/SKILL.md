---
name: verify-borelia
description: Drive the Borelia well-log interpretation app (FastAPI + bundled SPA) the way a user does via HTTP and Playwright, and prove behavior with captured evidence. Use when verifying any change to viewer, uploads, petrophysics, correlation, or reports.
---

# Verify Borelia

Borelia (this repo, mid-rename from GeoLog) is a FastAPI backend serving a bundled
single-page app from the same origin. Primary surface: web UI at `/` plus JSON API
under `/api/`. Secondary surface: raw HTTP API via curl for headless checks.

## Launch

Start an isolated instance on port 8137 with a throwaway DB (never touch the
developer's `backend/geolog.db`):

```bash
VFY_DIR=$(mktemp -d -t borelia-verify-XXXXXX)
BORELIA_DB_PATH="$VFY_DIR/verify.db" BORELIA_ARTIFACT_DIR="$VFY_DIR/artifacts" \
  BORELIA_ENV=test python3 -m uvicorn backend.main:app --host 127.0.0.1 --port 8137 &
echo $! > "$VFY_DIR/server.pid"
```

Ready means: `curl -sf http://127.0.0.1:8137/api/health` returns 200 AND
`curl -sf http://127.0.0.1:8137/` returns the SPA HTML (not just a socket accept).
Seed demo data loads automatically when the DB is empty (`seed_demo_data` in
`backend/main.py`); if wells list is empty and no demo LAS exists, seed via
`POST /api/wells/` per the feature map instead.

Teardown: kill only the PID you started, then remove the scratch dir. Evidence
stays outside the scratch dir (see Evidence).

```bash
kill "$(cat "$VFY_DIR/server.pid)"
rm -rf "$VFY_DIR"
```

## Doctor

Read-only, run first whenever anything looks off:

```bash
curl -sf http://127.0.0.1:8137/api/health && curl -sf http://127.0.0.1:8137/api/version
ss -ltnp 2>/dev/null | grep 8137   # port owned by our uvicorn, not another dev server
```

Auth: default dev mode trusts the client header (`AUTH_MODE=header`); every
write needs `-H "X-User-Role: admin"`. No login needed on the verify instance.
Do not test against a shared/production instance.

## Drive

Two harnesses, pick by what the feature needs:

- **HTTP (curl):** well/project CRUD, uploads (LAS multipart), curve reads,
  petrophysics compute, reports export. Stable handles: `GET /api/wells/`,
  `POST /api/wells/`, `GET /api/log-runs/{id}/curves`, `POST /api/log-runs/`.
  (No `GET /api/wells/{id}/curves` route exists — curves live under log runs.)
- **Browser (Playwright, `scripts/e2e_*.js` as prior art):** viewer rendering,
  `app.switchView(name)` for each of the 40+ panels, correlation picks.
  Set `BORELIA_BASE_URL` to the verify port:
  `BORELIA_BASE_URL=http://127.0.0.1:8137 node scripts/e2e_panel_smoke.js`.

Prefer route paths and `app.switchView` names over coordinates. Never use
internal setters or test-only endpoints to fake a pass; exercise the real path.

## Evidence

Per run, create `artifacts/verify/<YYYYMMDDTHHMMSSZ>/` containing:

- `health.json` — output of doctor step.
- `drive.log` — full transcript of drive commands and exit codes.
- `proof.*` — screenshots (browser runs) or key response bodies (API runs)
  showing the action AND the resulting state (e.g. uploaded well appears in
  well list; computed curve returned with expected depth range).
- Side effects verified alongside: rows in verify DB (`sqlite3` query) or files
  in artifact dir, not just the visible screen.

Mocks only where a production boundary already isolates the system (none needed
for local verify: all local).

## Cleanup

Kill the PID file's process, remove `$VFY_DIR`. Never `pkill -f uvicorn` (may
kill the developer's server). Never delete `artifacts/verify/` output.
Always run cleanup after failed iterations too.

## Helpers

None shipped; repo scripts are the helpers:

- `node scripts/e2e_panel_smoke.js` — all-panel switch smoke (needs
  `BORELIA_BASE_URL` set to verify port).
- `python scripts/regression_harness.py` — health + app-name contract check.
- `bash scripts/backup_restore_drill.sh <db> <artifacts>` — backup proof.
