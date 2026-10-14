"""Shared HTTP primitives used by both `main.py` and the routers.

These live here rather than in `main.py` so that routers can import them without
importing `main` (which imports the routers — that would be circular).
"""

from __future__ import annotations

import math

import numpy as np
from fastapi import Request
from fastapi.responses import JSONResponse

try:
    from security import require_min_role, role_from_request
except ImportError:
    from backend.security import require_min_role, role_from_request


def sanitize_json(obj):
    """Replace NaN/Inf with None, recursively, and make numpy types JSON-safe.

    Starlette's JSONResponse serialises with `allow_nan=False`, so a response
    containing a non-finite float raises rather than emitting `Infinity`. Every
    response path needs this, including FastAPI's own error handlers — its default
    validation handler echoes the offending input, so a client sending
    `{"x": Infinity}` turned a 422 into a 500.
    """
    if isinstance(obj, float):
        return None if (math.isnan(obj) or math.isinf(obj)) else obj
    if isinstance(obj, dict):
        return {k: sanitize_json(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [sanitize_json(v) for v in obj]
    if isinstance(obj, np.floating):
        value = float(obj)
        return None if (math.isnan(value) or math.isinf(value)) else value
    if isinstance(obj, np.integer):
        return int(obj)
    if isinstance(obj, np.ndarray):
        return sanitize_json(obj.tolist())
    return obj


class SafeJSONResponse(JSONResponse):
    """JSONResponse that sanitizes NaN/Inf to null for JSON compliance."""

    def render(self, content):
        return super().render(sanitize_json(content))


def require_role(min_role: str, request: Request) -> str:
    """Raise 403 unless the caller holds at least `min_role`; return the role."""
    current = role_from_request(request)
    require_min_role(min_role, current)
    return current


def require_viewer(request: Request) -> str:
    return require_role("viewer", request)


def require_interpreter(request: Request) -> str:
    return require_role("interpreter", request)


def require_admin(request: Request) -> str:
    return require_role("admin", request)
