"""Small HTTP helpers shared by middleware, auth and upload paths."""

from __future__ import annotations

import os

from fastapi import Request


def _truthy(value: str | None) -> bool:
    return (value or "").strip().lower() in {"1", "true", "yes", "on"}


def trust_proxy_headers() -> bool:
    """Only honour X-Forwarded-* when an operator explicitly trusts the proxy.

    Trusting the header by default lets any direct client forge its source IP,
    which would defeat per-IP rate limiting.
    """
    return _truthy(os.getenv("GEOLOG_TRUST_PROXY"))


def client_ip(request: Request) -> str:
    if trust_proxy_headers():
        forwarded = (request.headers.get("x-forwarded-for") or "").strip()
        if forwarded:
            return forwarded.split(",")[0].strip() or "unknown"
        real_ip = (request.headers.get("x-real-ip") or "").strip()
        if real_ip:
            return real_ip
    return request.client.host if request.client else "unknown"


def request_subject(request: Request) -> str:
    """Stable ACL subject for the request.

    JWT callers use their `sub`; the trusted-header shim has no identity, so it
    uses a single local subject. An empty subject is never treated as a member.
    """
    subject = str(getattr(request.state, "auth_subject", "") or "").strip()
    return subject or "local"
