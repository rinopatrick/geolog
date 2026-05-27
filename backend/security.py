"""Authentication and role-resolution utilities (Sprint 1).

Modes:
- AUTH_MODE=header (default for backward compatibility)
- AUTH_MODE=jwt (server-verified bearer JWT; OIDC-ready via issuer/audience)
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Dict, Any
import os

from fastapi import Request, HTTPException

ROLE_RANK = {"viewer": 1, "interpreter": 2, "admin": 3}


@dataclass
class AuthConfig:
    mode: str = "header"
    header_role_name: str = "X-User-Role"
    jwt_issuer: Optional[str] = None
    jwt_audience: Optional[str] = None
    jwt_secret: Optional[str] = None
    jwt_algorithms: tuple[str, ...] = ("HS256",)

    @classmethod
    def from_env(cls) -> "AuthConfig":
        mode = (os.getenv("AUTH_MODE", "header") or "header").strip().lower()
        alg_raw = (os.getenv("AUTH_JWT_ALGORITHMS", "HS256") or "HS256").strip()
        algs = tuple(a.strip() for a in alg_raw.split(",") if a.strip()) or ("HS256",)
        return cls(
            mode=mode,
            header_role_name=(os.getenv("AUTH_ROLE_HEADER", "X-User-Role") or "X-User-Role").strip(),
            jwt_issuer=(os.getenv("AUTH_JWT_ISSUER") or "").strip() or None,
            jwt_audience=(os.getenv("AUTH_JWT_AUDIENCE") or "").strip() or None,
            jwt_secret=(os.getenv("AUTH_JWT_SECRET") or "").strip() or None,
            jwt_algorithms=algs,
        )


@dataclass
class AuthContext:
    role: str
    subject: Optional[str] = None
    claims: Optional[Dict[str, Any]] = None
    source: str = "header"


def _normalize_role(role: Optional[str]) -> str:
    r = (role or "viewer").strip().lower()
    return r if r in ROLE_RANK else "viewer"


def _extract_bearer_token(request: Request) -> Optional[str]:
    auth = request.headers.get("Authorization") or ""
    if not auth.lower().startswith("bearer "):
        return None
    token = auth[7:].strip()
    return token or None


def _decode_jwt(token: str, cfg: AuthConfig) -> Dict[str, Any]:
    try:
        import jwt  # PyJWT
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"jwt auth misconfigured: PyJWT missing ({e})")

    options = {"verify_signature": True, "verify_exp": True}
    kwargs: Dict[str, Any] = {"algorithms": list(cfg.jwt_algorithms), "options": options}
    if cfg.jwt_audience:
        kwargs["audience"] = cfg.jwt_audience
    if cfg.jwt_issuer:
        kwargs["issuer"] = cfg.jwt_issuer

    if not cfg.jwt_secret:
        raise HTTPException(status_code=500, detail="jwt auth misconfigured: AUTH_JWT_SECRET missing")

    try:
        return jwt.decode(token, cfg.jwt_secret, **kwargs)
    except Exception as e:
        raise HTTPException(status_code=401, detail=f"invalid bearer token: {e}")


def resolve_auth_context(request: Request, cfg: AuthConfig) -> AuthContext:
    """Resolve authenticated role for current request.

    Header mode: trusted header fallback (compat mode).
    JWT mode: requires valid bearer JWT; role from claims['role'] or claims['roles'][0].
    """
    if cfg.mode == "jwt":
        token = _extract_bearer_token(request)
        if not token:
            raise HTTPException(status_code=401, detail="missing bearer token")
        claims = _decode_jwt(token, cfg)
        role = claims.get("role")
        if not role and isinstance(claims.get("roles"), list) and claims["roles"]:
            role = claims["roles"][0]
        return AuthContext(
            role=_normalize_role(role),
            subject=(claims.get("sub") or claims.get("user_id") or None),
            claims=claims,
            source="jwt",
        )

    # compatibility mode
    role = request.headers.get(cfg.header_role_name, "viewer")
    return AuthContext(role=_normalize_role(role), source="header")


def require_min_role(role: str, current_role: str):
    min_rank = ROLE_RANK.get(role, 99)
    cur_rank = ROLE_RANK.get(_normalize_role(current_role), 0)
    if cur_rank < min_rank:
        raise HTTPException(status_code=403, detail=f"{role} role required")


def role_from_request(request: Request) -> str:
    return _normalize_role(getattr(request.state, "user_role", None) or "viewer")
