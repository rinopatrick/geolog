# Changelog

All notable changes to GeoLog are recorded here.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and
the project uses [Semantic Versioning](https://semver.org/spec/v2.0.0.html).
While the major version is `0`, the API is not yet stable.

## [Unreleased]

## [0.1.0] - 2026-10-14

First tagged release. Pre-production engineering sample: the API is not stable
and the schema may change between 0.x versions.

### Fixed

- **`GET /api/ops/security-evidence/gate` returned 500**, and it is the endpoint the
  security-evidence CI gate depends on. Its response model declared
  `attest_reason_code` as `ATTEST_VALID | ATTEST_INVALID | ATTEST_ERROR`, but the
  handler returns `MISSING_REPORT` when nothing has been attested — the normal
  state of a fresh deployment — so response validation failed.
- **Section 8 "QC Snapshot" of every PDF report printed "QC data unavailable".**
  It called `run_qc_autofix()`, which is defined nowhere in the codebase, and a
  bare `except Exception` swallowed the resulting `NameError`. It now reports the
  real QC summary.
- **Silent LAS column corruption.** The parser dropped a `~C` definition whenever
  two vendor mnemonics mapped to the same canonical name, while `~A` data stayed
  positional, so every curve after the collision read its neighbour's column. On
  the project's own regression fixtures this produced a GR of 0.068 GAPI where
  the file said 83.376, a RHOB of 8.936 where it said 2.594, and a DT of 2.876
  where it said 69.239. Duplicate canonical names now keep their vendor mnemonic
  so the column count is preserved.
- **Aliases that crossed physical quantities.** `DPRL` (limestone *density*
  porosity) was aliased to `NPHI`, `SPRL` (sonic porosity) to `SP` in millivolts,
  `SPOR` to `DT` in transit time, `FEFE` (shallow resistivity) to `PE`, and
  `CILD`/`CILM` (conductivity) to resistivity without the `R = 1000/C`
  conversion. `PERC`-unit porosity curves are now normalised to fractions.
- **`DRHO` was never applied.** It was parsed and plotted but no compute path
  consulted it, and six endpoints each carried their own copy of the
  density-porosity formula fed raw `RHOB`. Bad-hole density flowed straight into
  porosity. The formula now exists once, and `compute-sw` reports bad-hole
  intervals from the tool correction and caliper, with optional filtering.
- **Net-to-gross could exceed 1.0.** The inclusive zone mask counted one sample
  more than the zone's gross thickness.
- **`GET /api/templates` was registered twice** with different payloads; the
  copy in `main.py` was dead code shadowed by the router's.
- **Demo seeding could not run on a Windows console.** Emoji in a startup
  `print` raised `UnicodeEncodeError` under cp1252 and aborted boot.
- **`docker-compose.yml` mounted a volume at a directory the app never wrote to**,
  so all data was lost on restart, and its healthcheck used `curl`, absent from
  `python:3.11-slim`.
- **The Dockerfile did not copy `alembic.ini`**, so the container crashed at
  startup once migrations were introduced.

### Security

- **`AUTH_MODE` defaulted to trusted-header auth**, so the caller's role came from
  a client-supplied header and anyone reaching the port was an admin.
  `DELETE /api/projects/1` with `X-User-Role: admin` returned 204. Non-dev
  environments now default to `jwt` and refuse header mode outright.
- **CORS used `allow_origins=["*"]` with credentials enabled**, reflecting any
  origin, so any page a logged-in user visited could read the whole database. It
  is now opt-in via `GEOLOG_CORS_ORIGINS`.
- Dependency pins for `pyjwt`, `python-multipart` and `starlette` carried known
  vulnerabilities and now resolve clean under `pip-audit`.
- A SHA1 use in the ETag helper is marked `usedforsecurity=False`; it is
  cache-busting, not a security primitive.

### Added

- **Alembic migrations** with a baseline covering all tables and the `audit_log`
  immutability triggers, replacing `Base.metadata.create_all()` and five ad-hoc
  `_ensure_*` helpers. Those could not be trusted: `create_all()` creates missing
  tables but never missing columns, so a new model field reached a fresh database
  and silently not an existing one.
- **A schema drift gate.** `verify_schema()` reports missing tables and columns at
  startup, and CI runs `alembic check`, so a model change without a migration
  fails the build instead of breaking someone else's database.
- **`scripts/audit_stored_curves.py`**, which finds stored wells whose curve
  values are physically impossible and therefore came from the parser bug. The
  raw upload is not retained, so affected wells must be re-uploaded.
- **`GEOLOG_DB_PATH` and `GEOLOG_ARTIFACT_DIR`** so the database and the
  interpretation snapshot/lock files can be redirected. Without the latter, the
  test suite left wells locked for the running app.
- Golden-value tests for the petrophysics compute path, hand-computed from the
  published Archie, Larionov, Clavier and Stieber equations.
- `tests/test_route_inventory.py`, pinning all 186 API endpoints so moving routes
  between modules cannot silently drop one.

### Changed

- Test suite is isolated per run and order-independent, and no longer writes to
  `backend/geolog.db`.
- `requirements.txt` includes `backend/requirements.txt` as a single source, with
  a separate `requirements-dev.txt`.
- `AUTH_MODE=header` is a development convenience and is refused outside
  `dev`/`local`/`test`/`ci`.
- `backend/main.py` reduced from 9,624 to ~6,200 lines. Extracted: `backend/deps.py`
  (shared HTTP primitives), `backend/jobs.py` (job registry), `backend/audit.py`
  (audit chain and signing), `backend/observability.py` (request counters),
  `backend/schema.py` (migrations), and routers for users, log-runs, projects,
  audit-log and ops.

### Known limitations

- `backend/main.py` still holds the `/api/wells` routes (87 endpoints, the least
  tested part of the app) plus the petrophysics helpers they depend on. That is
  the remaining piece of the split.
- Coverage of `backend/main.py` is low; many endpoints have no numeric
  verification beyond a status code. The petrophysics that do have golden-value
  tests are `/compute-sw` and the density-porosity path.
- No auth provider integration: `AUTH_MODE=jwt` verifies tokens but issues none.

[Unreleased]: https://github.com/rinopatrick/geolog/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/rinopatrick/geolog/releases/tag/v0.1.0
