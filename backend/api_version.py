"""Versioned API prefix aliasing.

`/api/v1/*` is served by the same handlers as `/api/*` for now. The alias gives
clients a stable prefix to pin while the legacy prefix stays compatible. A
future breaking change can move the legacy handlers without moving `/api/v1`.
"""

from __future__ import annotations

from starlette.middleware.base import BaseHTTPMiddleware

V1_PREFIX = "/api/v1"
LEGACY_PREFIX = "/api"


class APIVersionAliasMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        path = request.url.path
        if path == V1_PREFIX or path.startswith(V1_PREFIX + "/"):
            suffix = path[len(V1_PREFIX):] or "/"
            new_path = LEGACY_PREFIX + suffix
            request.scope["path"] = new_path
            request.scope["raw_path"] = new_path.encode("utf-8")
            request.state.api_version = "v1"
            response = await call_next(request)
            response.headers["X-API-Version"] = "v1"
            return response
        request.state.api_version = "v0"
        return await call_next(request)
