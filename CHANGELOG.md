# Changelog

All notable changes to GeoLog are recorded here.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and
the project uses [Semantic Versioning](https://semver.org/spec/v2.0.0.html).
While the major version is `0`, the API is not yet stable.

## [Unreleased]

### Added

- **WITSML/OSDU read-first adapters v1.** WITSML 1.4.1.1 SOAP well/log pull and
  curve import; OSDU Wellbore DDMS well pull and explicit well push; env-based
  credentials, TLS verification, tests and `docs/INTEROP.md`. WITSML 2.1/ETP
  and OSDU log-curve transfer remain out of scope.
- **Borehole images and manual dip picks v1.** Conditioned image upload,
  artifact storage, optional DLIS image-channel extraction, trace-to-sinusoid
  dip fitting, dip quality/approval, migration `f6a7b8c9d0e1`, and
  `docs/IMAGE_LOGS.md`. Automatic picking, vendor conditioning and aperture
  analysis remain out of scope.
- **Geomechanics screening v1.** Versioned well/zone models, calibration-gated
  `Pp`/`Shmin`/`Shmax`, dynamic elastic moduli, generalized-Kirsch screening
  hoop stress, mud window, Mohr-Coulomb/Hoek-Brown/Drucker-Prager flags,
  sanding CDP, optional fracture-slip, JSON/CSV/PDF reports, migration
  `e5f6a7b8c9d0`, and `docs/GEOMECHANICS.md`.
- **Core/SCAL v1.** Core datasets/plugs/measurements, capillary pressure,
  relative permeability, photos/thin-section metadata, CSV import (dry-run and
  conflict reporting), FZI multi-resolution flow units, contacts, and J-function
  saturation-height fit/apply. Adds migration `d4e5f6a7b8c9`, router and
  `docs/CORE_SCAL.md`. Excel import, staged depth matching, extended saturation-
  height models and photo upload are not in this increment.
- **Semantics-aware QC and petrophysics.** Advanced QC, unified saturation,
  permeability, dual-water, VCL models, multimineral and permeability-multi now
  read through the shared semantics layer, so aliases, units and corrected MD
  agree with the viewer.
- **NMR T2 interpretation.** Vendor T2-bin curves are interpreted synchronously;
  raw CPMG echoes use regularized NNLS as a background job. Adds
  `nmr_inversions`/`nmr_distributions`, derived `NMRP`/`BVI`/`FFI`/`T2GM`/
  `KSDR`/`KCOATES` curves, distribution API, SciPy dependency and
  `docs/NMR.md`.
- **Data semantics v1 (`data-semantics-v1`).** Log data now resolves well-level
  curve aliases, converts known units to a per-well field/SI target, applies
  piecewise MD→corrected-depth control points (legacy shift/stretch still maps
  to two points), and emits TVD alongside corrected MD. Responses carry a
  semantics metadata block with an input hash and warnings; stored curves are
  never rewritten. Adds `wells.unit_system`, `depth_control_points`, migration
  `9f2c1a7b4d10`, control-point API endpoints and UI fields.
- **Production hardening.** JWT verification supports JWKS and RS256 public keys,
  token TTL/leeway are configurable, issued tokens carry a `jti` and the token
  endpoint reports `expires_in`.
- **Secrets from files.** Every supported secret can use the `<NAME>_FILE`
  convention for Docker/Kubernetes secret mounts.
- **TLS and response headers.** `GEOLOG_REQUIRE_HTTPS=true` redirects with 308,
  HTTPS responses get HSTS, and all responses carry baseline hardening headers.
- **Deployment guide.** `docs/PRODUCTION_HARDENING.md` covers IdP, secrets, TLS,
  persistence, backup drills, monitoring and a release checklist.
- **Real DLIS/LIS checks.** Opt-in tests accept `GEOLOG_DLIS_SAMPLE` and
  `GEOLOG_LIS_SAMPLE`; no third-party binary fixtures are committed.

## [0.2.0] - 2026-10-21

Security, data-integrity and ingestion hardening release.

### Fixed

- **JWT mode locked out login, health checks, docs and the SPA.** The auth
  middleware now skips public paths (`/api/health`, `/api/users/token`, docs,
  static files and non-API GETs) while still protecting every other API route.
- **Client `X-User-Role` could override a JWT role.** The four well-state routes
  (template lock/unlock, well unlock, snapshot approval) now use the resolved
  role through FastAPI dependencies instead of reading the header directly.
- **Stored XSS through well, project, top and zone names.** Server strings are
  HTML-escaped before they enter the DOM; toasts use `textContent`.
- **QC, correlation and zonation read float64 curves as float32.** They now use
  the stored dtype and the stored DEPT curve instead of inventing depths.
- **`auto-zone-from-tops` crashed without SciPy.** The GR valley picker is now
  NumPy-only.
- **Deleting a well or project left child rows behind.** Annotations, production,
  deviation surveys, aliases, petro params, correlation markers/profiles and
  depth shifts are removed with the well, and its lock/snapshot files are
  deleted. SQLite id reuse can no longer make a new well inherit old data.
- **Viewers could write curve data through `/api/log-runs/*`.** Only the two
  read-only POST query endpoints remain viewer-safe.
- **Frontend calls dropped auth headers.** Deletes, exports, QC, tornado, VCL,
  image-log and correlation requests now use the shared auth helper; blob
  downloads include the bearer token.
- **The collaboration WebSocket accepted anonymous clients and query-string
  roles.** JWT mode now requires a token before `accept()`; header mode keeps the
  development role query but ignores spoofed roles elsewhere.
- **Local token issuance accepted empty user tokens and used a time-based
  token.** Empty tokens are rejected, new tokens use `secrets.token_urlsafe(32)`,
  comparisons are constant-time, and issuance fails with 503 when no JWT secret
  is configured.
- **Security-evidence attestation accepted unknown signature algorithms.** Only
  `hmac-sha256` is accepted now.
- **File-backed state was not safe across workers.** Audit chain, metrics, jobs,
  locks and snapshots use an OS-level file lock; ops endpoints reload shared
  metrics before reporting.
- **Several write endpoints returned 500 on non-numeric input.** Petro params,
  zones, save-picks, depth-shift, production, aliases, trajectory and template
  preview now return 400 with the field name.
- **Core calibration reported the first N core depths instead of the matched
  depths.** Fixed and covered by a regression test.
- **DLIS/LIS temp files could not be reopened on Windows, and the heuristic
  fallback was silent.** Temp files use `delete=False` and are removed in a
  `finally`; fallback parses return a warning that the upload UI shows. `dlisio`
  is now a dependency, and the LIS loader calls its method-based API correctly.
- **Bulk upload was declared as a JSON list, not multipart files.** It now accepts
  `list[UploadFile]`, commits per file and increments run numbers correctly.
- **Curve splice and filter were O(n²)/Python-loop slow.** Splice uses
  `searchsorted`, filters use sliding windows.
- **`np.trapz` is gone in NumPy 2.** EUR uses `np.trapezoid` when available.

## [0.1.0] - 2026-10-14

First tagged release. Pre-production engineering sample: the API is not stable
and the schema may change between 0.x versions.

### Fixed

- **A duplicate route registration made a fix appear not to work.**
  `POST /api/wells/{wid}/apply-template` was registered by both
  `routers/templates.py` and `routers/wells.py`. Starlette matches the first, so
  the second was dead code — and they were not equivalent: different template
  lists (5 vs 6), different lock sources, and only one accepted `custom_params`.
  Fixed, and `tests/test_route_inventory.py` now fails on any duplicate
  registration. (The earlier duplicate, `GET /api/templates`, was found the same
  way.)
- **`routers/templates.py` ignored `GEOLOG_ARTIFACT_DIR`.** It built its own lock
  path from `os.path.dirname(__file__)`, so a deployment that redirected the
  artifact directory had `template-lock` write one file and `apply-template` read
  another, and the lock appeared not to work. It now delegates to
  `well_state.get_template_lock` — one source of truth.
- **A non-finite float in a JSON body returned 500 instead of 422.** Python's
  `json` *parses* `Infinity`, so the value reaches FastAPI, which rejects the
  body; its default handler echoes the offending input, and Starlette serialises
  with `allow_nan=False`, so building the 422 raised. Affected every endpoint with
  a Pydantic body model.
- **Partial updates wrote whatever they were given.** `PUT /api/wells/{wid}` and
  `PUT /api/tops/{tid}` used `for field in (...): setattr(obj, field, data[field])`,
  so `{"depth": "abc"}` reached a FLOAT column and `{"name": null}` hit a NOT
  NULL constraint — both 500s from the driver.
- **The audit chain was broken by its own routes.** `audit_log` is an append-only
  chain, but `log_audit()` inserted rows with no `prev_hash`/`entry_hash`, so the
  row failed verification and the next request-logged row chained onto an empty
  hash. Measured: `POST /api/wells/1/template-lock` produced two chain issues. The
  "immutable provenance chain" broke on every route calling `log_audit()` —
  template lock/unlock, apply-template, save-petro-params. Both writers now go
  through one `append_audit_entry()` that also holds a lock, so concurrent writes
  cannot fork the chain either.
- **Four endpoints returned 500 on missing input instead of 400.**
  `/api/wells/{wid}/annotations` raised `KeyError` from `data["depth"]`; `dst`,
  `rft` and `completion` raised `TypeError` from `float(None)`; `tops`, `wells` and
  `projects` raised `TypeError` when an unknown key reached the model constructor.
  All now return 400 naming the field.
- **Mass assignment: a client could choose the primary key.**
  `POST /api/wells/ {"id": 4242}` created a well with id 4242, and `{"id": 888}`
  did the same for projects. `FormationTop(well_id=wid, **data)` also let a client
  write any column, including `created_at`. All four constructors now take an
  explicit field list.
- **`GET /api/wells/{wid}/export-bundle` returned 500 on every call.** It built its
  CSVs from `t.name`, `z.zone_name`, `z.sw_avg` and `z.net_to_gross` — none of
  which are columns. It had never worked.
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
- **`backend/validation.py`**, giving write endpoints 400 with the field named
  instead of a 500 from `float(None)` or a missing key.
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
- `tests/test_router_integrity.py`, which checks that every name a handler
  references is actually bound in its module — the class of bug that made the QC
  report section fail silently.

### Changed

- Test suite is isolated per run and order-independent, and no longer writes to
  `backend/geolog.db`.
- `requirements.txt` includes `backend/requirements.txt` as a single source, with
  a separate `requirements-dev.txt`.
- `AUTH_MODE=header` is a development convenience and is refused outside
  `dev`/`local`/`test`/`ci`.
- `backend/main.py` reduced from 9,624 to ~1,300 lines. Extracted: `backend/deps.py`
  (shared HTTP primitives), `backend/jobs.py` (job registry), `backend/audit.py`
  (audit chain and signing), `backend/observability.py` (request counters),
  `backend/schema.py` (migrations), `backend/validation.py` (body validation),
  `backend/timeutils.py` (UTC clock), and routers for wells, log-runs, projects,
  audit-log, ops and users.
- `scripts/regression_harness.py` asserts on response shape and values (100 checks)
  instead of status codes alone, records transport errors as failures rather than
  crashing, and defaults to `127.0.0.1` rather than `localhost`.
- Deleted `backend/schemas.py`: 108 lines of Pydantic schemas that nothing
  imported — an abandoned attempt at the validation layer `validation.py` now
  provides.

### Known limitations

- `backend/main.py` still holds a few routes (correlation markers and profile,
  health, bulk tops update, the tops export) plus the middleware.
- Coverage of `backend/main.py` is low; many endpoints have no numeric
  verification beyond a status code. The petrophysics that do have golden-value
  tests are `/compute-sw` and the density-porosity path.
- No auth provider integration: `AUTH_MODE=jwt` verifies tokens but issues none.
- `template-unlock` requires the admin role while `template-lock` accepts an
  interpreter, so an interpreter can sign off a template that only an admin can
  reopen. Deliberate, but worth confirming it matches your process.

[Unreleased]: https://github.com/rinopatrick/geolog/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/rinopatrick/geolog/releases/tag/v0.1.0
