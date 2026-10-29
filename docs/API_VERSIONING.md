# API versioning

The current public API is **v0**, mounted at `/api`. Responses carry
`X-API-Version: v0`.

`/api/v1/*` is the frozen prefix for the current handlers. Responses on that
prefix carry `X-API-Version: v1`. Future breaking changes go to `/api/v2`; the
v1 routes stay on the contract documented here.
`GET /api/version` (or `/api/v1/version`) reports the app version and the prefix
that served the request.

While the major version in `backend/version.py` is `0`, the schema and request
contracts may change between minor releases. Treat `CHANGELOG.md` as the
compatibility record.

## Compatibility rules

- Existing `/api` and `/api/v1` paths are not renamed in a patch release.
- A breaking request or response change requires a new prefix (for example
  `/api/v2`) with a migration guide. `/api/v1` stays on the current contract.
- New optional response fields are allowed; clients must ignore unknown fields.
- New required request fields are a breaking change.
- Auth and error envelope shapes are part of the contract:
  - `401` missing/invalid/revoked token
  - `403` insufficient global role or missing project membership
  - `413` upload/body over the configured cap
  - `429` login throttled or locked, with `Retry-After`
  - `503` dependency or security-evidence gate unavailable

## Client guidance

- Pin to a release tag, not `main`.
- Branch on the HTTP status and `detail` field; do not parse prose.
- Poll background jobs through `/api/jobs/{job_id}` and treat `done`/`failed` as
  terminal. Jobs are durable across worker restarts.
- Send `X-Request-ID` when you have one; it is echoed and written to the audit
  chain and request log.
