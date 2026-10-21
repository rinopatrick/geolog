"""Authentication and role-resolution utilities (Sprint 1).

Modes:
- AUTH_MODE=jwt (default outside dev: server-verified bearer JWT, OIDC-ready)
- AUTH_MODE=header (trusted client header; dev/local/test/ci only)

Header mode takes the caller's role from a request header, so it is only safe
where the network boundary is trusted. It is refused outside dev environments
unless AUTH_MODE is set explicitly and GEOLOG_ENV says otherwise.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Dict, Any
import os
import uuid
from threading import Lock

from fastapi import Request, HTTPException

try:
    from secretstore import read_secret
except ImportError:
    from backend.secretstore import read_secret

ROLE_RANK = {"viewer": 1, "interpreter": 2, "admin": 3}

# Environments where the trusted-header shim is acceptable.
DEV_ENVIRONMENTS = {"dev", "local", "test", "ci"}


def current_env() -> str:
    return (os.getenv("GEOLOG_ENV") or os.getenv("ENV") or "dev").strip().lower()


@dataclass
class AuthConfig:
    mode: str = "jwt"
    header_role_name: str = "X-User-Role"
    jwt_issuer: Optional[str] = None
    jwt_audience: Optional[str] = None
    jwt_secret: Optional[str] = None
    jwt_public_key: Optional[str] = None
    jwt_jwks_url: Optional[str] = None
    jwt_algorithms: tuple[str, ...] = ("HS256",)
    jwt_ttl_seconds: int = 86400
    jwt_leeway_seconds: int = 0

    @classmethod
    def from_env(cls) -> "AuthConfig":
        env = current_env()
        mode = (os.getenv("AUTH_MODE") or "").strip().lower()
        if not mode:
            # Secure by default: a real deployment must verify tokens. Local runs
            # keep the header shim so the app is usable without an identity provider.
            mode = "header" if env in DEV_ENVIRONMENTS else "jwt"
        if mode not in ("header", "jwt"):
            raise RuntimeError(f"unsupported AUTH_MODE {mode!r} (expected 'header' or 'jwt')")
        if mode == "header" and env not in DEV_ENVIRONMENTS:
            raise RuntimeError(
                f"AUTH_MODE=header trusts a client-supplied role header, which is not "
                f"allowed with GEOLOG_ENV={env!r}. Set AUTH_MODE=jwt."
            )
        jwks_url = read_secret("AUTH_JWT_JWKS_URL") or None
        public_key = read_secret("AUTH_JWT_PUBLIC_KEY") or None
        secret = read_secret("AUTH_JWT_SECRET") or None

        alg_raw = (os.getenv("AUTH_JWT_ALGORITHMS") or "").strip()
        if not alg_raw:
            # A JWKS/public key means an asymmetric provider; otherwise keep HS256.
            alg_raw = "RS256" if (jwks_url or public_key) else "HS256"
        algs = tuple(a.strip() for a in alg_raw.split(",") if a.strip()) or ("HS256",)

        try:
            ttl = int(os.getenv("AUTH_JWT_TTL_SECONDS", "86400") or 86400)
        except ValueError as exc:
            raise RuntimeError("AUTH_JWT_TTL_SECONDS must be an integer") from exc
        if ttl <= 0:
            raise RuntimeError("AUTH_JWT_TTL_SECONDS must be > 0")
        try:
            leeway = int(os.getenv("AUTH_JWT_LEEWAY_SECONDS", "0") or 0)
        except ValueError as exc:
            raise RuntimeError("AUTH_JWT_LEEWAY_SECONDS must be an integer") from exc
        if leeway < 0:
            raise RuntimeError("AUTH_JWT_LEEWAY_SECONDS must be >= 0")

        return cls(
            mode=mode,
            header_role_name=(os.getenv("AUTH_ROLE_HEADER", "X-User-Role") or "X-User-Role").strip(),
            jwt_issuer=(os.getenv("AUTH_JWT_ISSUER") or "").strip() or None,
            jwt_audience=(os.getenv("AUTH_JWT_AUDIENCE") or "").strip() or None,
            jwt_secret=secret,
            jwt_public_key=public_key,
            jwt_jwks_url=jwks_url,
            jwt_algorithms=algs,
            jwt_ttl_seconds=ttl,
            jwt_leeway_seconds=leeway,
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


_JWKS_CLIENTS: Dict[str, Any] = {}
_JWKS_LOCK = Lock()

def _get_jwks_client(url: str):
    """Cache one PyJWKClient per URL so its key cache survives requests."""
    import jwt

    with _JWKS_LOCK:
        client = _JWKS_CLIENTS.get(url)
        if client is None:
            client = jwt.PyJWKClient(url)
            _JWKS_CLIENTS[url] = client
        return client

def _decode_jwt(token: str, cfg: AuthConfig) -> Dict[str, Any]:
    try:
        import jwt  # PyJWT
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"jwt auth misconfigured: PyJWT missing ({e})")

    options = {"verify_signature": True, "verify_exp": True}
    kwargs: Dict[str, Any] = {
        "algorithms": list(cfg.jwt_algorithms),
        "options": options,
        "leeway": cfg.jwt_leeway_seconds,
    }
    if cfg.jwt_audience:
        kwargs["audience"] = cfg.jwt_audience
    if cfg.jwt_issuer:
        kwargs["issuer"] = cfg.jwt_issuer

    if cfg.jwt_jwks_url:
        try:
            key = _get_jwks_client(cfg.jwt_jwks_url).get_signing_key_from_jwt(token).key
        except Exception as e:
            raise HTTPException(status_code=401, detail=f"invalid bearer token: {e}")
    elif cfg.jwt_public_key:
        key = cfg.jwt_public_key
    elif cfg.jwt_secret:
        key = cfg.jwt_secret
    else:
        raise HTTPException(
            status_code=500,
            detail="jwt auth misconfigured: set AUTH_JWT_SECRET, AUTH_JWT_PUBLIC_KEY or AUTH_JWT_JWKS_URL",
        )

    try:
        return jwt.decode(token, key, **kwargs)
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

    # In header/compat mode: if a Bearer token is present and secret is configured, decode it;
    # otherwise fall back to trusted header.
    token = _extract_bearer_token(request)
    if token and cfg.jwt_secret:
        try:
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
        except Exception:
            pass

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


def create_access_token(
    subject: str,
    role: str,
    cfg: AuthConfig,
    expires_delta_seconds: int | None = None,
) -> str:
    """Generate a signed JWT bearer token matching server auth configuration."""
    try:
        import jwt  # PyJWT
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"jwt auth misconfigured: PyJWT missing ({e})")

    if not cfg.jwt_secret:
        raise HTTPException(status_code=500, detail="jwt auth misconfigured: AUTH_JWT_SECRET missing")

    import datetime
    now = datetime.datetime.now(datetime.timezone.utc)
    ttl = cfg.jwt_ttl_seconds if expires_delta_seconds is None else expires_delta_seconds
    if ttl <= 0:
        raise HTTPException(status_code=500, detail="token TTL must be > 0")
    exp = now + datetime.timedelta(seconds=ttl)

    payload: Dict[str, Any] = {
        "sub": subject,
        "role": _normalize_role(role),
        "iat": int(now.timestamp()),
        "exp": int(exp.timestamp()),
        "jti": uuid.uuid4().hex,
    }
    if cfg.jwt_issuer:
        payload["iss"] = cfg.jwt_issuer
    if cfg.jwt_audience:
        payload["aud"] = cfg.jwt_audience

    algorithm = cfg.jwt_algorithms[0] if cfg.jwt_algorithms else "HS256"
    if not algorithm.upper().startswith("HS"):
        raise HTTPException(
            status_code=500,
            detail="local token issuance requires an HMAC algorithm (HS256/HS384/HS512)",
        )
    return jwt.encode(payload, cfg.jwt_secret, algorithm=algorithm)
