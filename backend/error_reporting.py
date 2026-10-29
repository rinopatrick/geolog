"""Optional error reporting to an operator-configured webhook.

The request path only formats a small payload and hands it to a daemon thread.
No third-party SDK is required, and an unset `GEOLOG_ERROR_WEBHOOK_URL` makes
every call a no-op. The payload deliberately excludes query strings, request
bodies, tokens and user subjects.
"""

from __future__ import annotations

import json
import os
import threading
import time
import traceback
import urllib.request
from typing import Any

try:
    from timeutils import utcnow
    from version import __version__
except ImportError:
    from backend.timeutils import utcnow
    from backend.version import __version__

_LOCK = threading.Lock()
_RECENT: dict[str, float] = {}
_WINDOW_SECONDS = 60.0
_MAX_PER_WINDOW = 30


def _webhook_url() -> str:
    return (os.getenv("GEOLOG_ERROR_WEBHOOK_URL") or "").strip()


def _include_trace() -> bool:
    return (os.getenv("GEOLOG_ERROR_WEBHOOK_INCLUDE_TRACE") or "").strip().lower() in {
        "1", "true", "yes", "on"
    }


def _environment() -> str:
    return (os.getenv("GEOLOG_ENV") or os.getenv("ENV") or "dev").strip().lower()


def _state(request: Any, name: str, default: str = "") -> str:
    return str(getattr(getattr(request, "state", None), name, default) or "")


def _request_id(request: Any) -> str:
    header = ""
    try:
        header = request.headers.get("X-Request-ID") or ""
    except Exception:
        pass
    return _state(request, "request_id") or str(header)


def _allow(key: str) -> bool:
    now = time.monotonic()
    with _LOCK:
        for stale in [k for k, ts in _RECENT.items() if now - ts > _WINDOW_SECONDS]:
            _RECENT.pop(stale, None)
        if len(_RECENT) >= _MAX_PER_WINDOW and key not in _RECENT:
            return False
        last = _RECENT.get(key)
        if last is not None and now - last < 5.0:
            return False
        _RECENT[key] = now
        return True


def build_payload(request: Any, exc: BaseException) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "event": "unhandled_exception",
        "timestamp": utcnow().isoformat() + "Z",
        "environment": _environment(),
        "app_version": __version__,
        "request_id": _request_id(request),
        "trace_id": _state(request, "trace_id"),
        "method": str(getattr(request, "method", "")),
        "path": str(getattr(getattr(request, "url", None), "path", "")),
        "role": _state(request, "user_role", "viewer"),
        "exception_type": type(exc).__name__,
        "exception": str(exc)[:500],
    }
    if _include_trace():
        payload["traceback"] = "".join(
            traceback.format_exception(type(exc), exc, exc.__traceback__)
        )[-4000:]
    return payload


def _post(url: str, payload: dict[str, Any]) -> None:
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    request = urllib.request.Request(
        url,
        data=body,
        headers={"Content-Type": "application/json", "User-Agent": "GeoLog/error-report"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=3.0):
            pass
    except Exception:
        # Reporting must never break the request or spawn noisy retries here.
        pass


def _dispatch(url: str, payload: dict[str, Any]) -> None:
    threading.Thread(target=_post, args=(url, payload), daemon=True).start()


def report_exception(request: Any, exc: BaseException) -> bool:
    """Queue one error report. Returns False when disabled or rate-limited."""
    url = _webhook_url()
    if not url:
        return False
    path = str(getattr(getattr(request, "url", None), "path", ""))
    key = f"{path}:{type(exc).__name__}"
    if not _allow(key):
        return False
    _dispatch(url, build_payload(request, exc))
    return True
