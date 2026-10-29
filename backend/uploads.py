"""Bounded upload reading.

Starlette has no default request-body size limit and `UploadFile.read()` reads
the whole file into memory. A single authenticated caller could therefore pin a
worker with a multi-gigabyte upload. Every upload route goes through
`read_upload`, and a body-size middleware rejects declared oversized requests
before the route runs.
"""

from __future__ import annotations

import os

from fastapi import HTTPException, UploadFile
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

CHUNK_SIZE = 1024 * 1024
DEFAULT_MAX_UPLOAD_BYTES = 256 * 1024 * 1024
DEFAULT_MAX_BODY_BYTES = 64 * 1024 * 1024


def _env_int(name: str, default: int) -> int:
    try:
        value = int(os.getenv(name, str(default)) or default)
    except ValueError:
        return default
    return value if value > 0 else default


def max_upload_bytes() -> int:
    return _env_int("GEOLOG_MAX_UPLOAD_BYTES", DEFAULT_MAX_UPLOAD_BYTES)


def max_body_bytes() -> int:
    return _env_int("GEOLOG_MAX_BODY_BYTES", DEFAULT_MAX_BODY_BYTES)


def _too_large(limit: int) -> HTTPException:
    return HTTPException(
        status_code=413,
        detail=f"upload exceeds the {limit} byte limit",
    )


async def read_upload(file: UploadFile, max_bytes: int | None = None) -> bytes:
    limit = max_upload_bytes() if max_bytes is None else max_bytes
    declared = getattr(file, "size", None)
    if declared is not None and int(declared) > limit:
        raise _too_large(limit)

    buffer = bytearray()
    while True:
        chunk = await file.read(CHUNK_SIZE)
        if not chunk:
            break
        buffer.extend(chunk)
        if len(buffer) > limit:
            raise _too_large(limit)
    return bytes(buffer)


class BodySizeLimitMiddleware(BaseHTTPMiddleware):
    """Reject declared oversized writes before they enter a route.

    The chunked/no-Content-Length case is still covered by read_upload at the
    endpoint. This layer exists so a normal client cannot make the server read
    a multi-gigabyte body before discovering it is too large.
    """

    async def dispatch(self, request, call_next):
        if request.method in {"POST", "PUT", "PATCH"} and request.url.path.startswith("/api/"):
            content_type = (request.headers.get("content-type") or "").lower()
            limit = max_upload_bytes() if content_type.startswith("multipart/") else max_body_bytes()
            declared = (request.headers.get("content-length") or "").strip()
            if declared:
                try:
                    size = int(declared)
                except ValueError:
                    size = 0
                if size > limit:
                    return JSONResponse(
                        status_code=413,
                        content={"detail": f"request body exceeds the {limit} byte limit"},
                    )
        return await call_next(request)
