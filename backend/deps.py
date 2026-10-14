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


class SafeJSONResponse(JSONResponse):
    """JSONResponse that sanitizes NaN/Inf to null for JSON compliance."""

    def render(self, content):
        def _sanitize(obj):
            if isinstance(obj, float):
                if math.isnan(obj) or math.isinf(obj):
                    return None
                return obj
            if isinstance(obj, dict):
                return {k: _sanitize(v) for k, v in obj.items()}
            if isinstance(obj, (list, tuple)):
                return [_sanitize(v) for v in obj]
            if isinstance(obj, np.floating):
                v = float(obj)
                return None if (math.isnan(v) or math.isinf(v)) else v
            if isinstance(obj, np.integer):
                return int(obj)
            if isinstance(obj, np.ndarray):
                return _sanitize(obj.tolist())
            return obj

        return super().render(_sanitize(content))


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
