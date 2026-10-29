# Project access control

GeoLog roles (`viewer`, `interpreter`, `admin`) are global. Project membership
adds a second, narrower layer without changing those roles.

## Contract

- A project with **no rows** in `project_members` is open: any authenticated
  caller keeps the existing global-role behavior. This keeps pre-existing data
  usable after upgrade.
- Adding the first member turns the project into a **restricted** project.
  From that moment:
  - `admin` callers still bypass membership (platform administrators).
  - A member with `viewer` may read the project, its wells and its log runs.
  - A member with `interpreter` may also write.
  - A caller with no membership gets `403` on project/well/log-run paths and
    does not see the project in list responses.
- Creating a project adds the creator as its `admin` member, so new projects are
  restricted by default.
- Removing the last member requires `force=true`; without it the API returns
  `400` rather than silently reopening the project.

The middleware resolves `/api/projects/{pid}`, `/api/wells/{wid}` and
`/api/log-runs/{id}` to a project. Routes that take well IDs in a query string or
JSON body (`/api/correlation/*`, `/api/correlation-markers`, `/api/interop/*`)
apply the same check explicitly in the route. The audit log and job list are
filtered to visible projects, and the collaboration WebSocket checks membership
before joining a well room.

## Endpoints

```http
GET    /api/projects/{pid}/members
POST   /api/projects/{pid}/members       {"subject": "alice", "role": "interpreter"}
DELETE /api/projects/{pid}/members/alice?force=false
```

`subject` is the JWT `sub` claim. With the trusted-header development shim there
is no identity, so every request uses the subject `local`.

## Deployment

The layer is enabled by default. To disable it during a migration window:

```bash
GEOLOG_ENFORCE_PROJECT_ACL=false
```

Do not leave it disabled for a multi-user deployment. Disabling it restores the
old behavior where every `viewer` can read every project.

## Limits

- Membership is per project, not per well. A well inherits its project.
- Membership does not replace an identity provider. The JWT signature and role
  claim still decide the global role.
- Audit records are written after the request and do not currently include the
  membership check result. Use the request log plus `/api/audit-log` for
  correlation.
