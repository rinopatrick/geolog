"""User management router for GeoLog."""

import hmac
import secrets

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

try:
    from database import get_db
    from deps import require_admin, require_viewer
    from http_utils import client_ip
    from models import User
    from passwords import hash_secret, needs_rehash, verify_secret
    from ratelimit import (
        check_login_allowed, clear_login_failures, record_login_failure,
    )
    from security import (
        AuthConfig, create_access_token, create_refresh_token, decode_token,
        is_token_revoked, revoke_token,
    )
except ImportError:
    from backend.database import get_db
    from backend.deps import require_admin, require_viewer
    from backend.http_utils import client_ip
    from backend.models import User
    from backend.passwords import hash_secret, needs_rehash, verify_secret
    from backend.ratelimit import (
        check_login_allowed, clear_login_failures, record_login_failure,
    )
    from backend.security import (
        AuthConfig, create_access_token, create_refresh_token, decode_token,
        is_token_revoked, revoke_token,
    )

VALID_ROLES = {"viewer", "interpreter", "admin"}

# Spend the same PBKDF2 work for an unknown username so response timing does not
# reveal whether an account exists.
DUMMY_HASH = hash_secret(secrets.token_urlsafe(32))


def _set_secret(user: User, secret: str) -> None:
    """Store only the hash. The plaintext column is cleared on purpose."""
    user.token_hash = hash_secret(secret)
    user.token = ""


def _valid_role(value: str) -> str:
    role = (value or "interpreter").strip().lower()
    if role not in VALID_ROLES:
        raise HTTPException(400, "role must be viewer, interpreter or admin")
    return role

router = APIRouter(prefix="/api/users", tags=["users"])




@router.post("/refresh")
def refresh_user_token(data: dict, db: Session = Depends(get_db)):
    """Exchange a valid refresh token for a new access/refresh pair.

    The old refresh token is revoked (rotation). Refresh tokens are public-path
    requests but still signature- and expiry-verified.
    """
    raw = (data.get("refresh_token") or "").strip()
    if not raw:
        raise HTTPException(400, "refresh_token required")
    cfg = AuthConfig.from_env()
    try:
        claims = decode_token(raw, cfg)
    except HTTPException as exc:
        raise HTTPException(401, exc.detail)
    if claims.get("typ") != "refresh":
        raise HTTPException(401, "not a refresh token")
    if is_token_revoked(claims.get("jti")):
        raise HTTPException(401, "refresh token revoked")
    username = claims.get("sub")
    user = db.query(User).filter(User.username == username).first()
    if not user:
        raise HTTPException(401, "user no longer exists")
    revoke_token(raw, cfg, "refresh_rotation")
    return {
        "access_token": create_access_token(subject=user.username, role=user.role, cfg=cfg),
        "refresh_token": create_refresh_token(subject=user.username, role=user.role, cfg=cfg),
        "token_type": "bearer",
        "expires_in": cfg.jwt_ttl_seconds,
        "refresh_expires_in": cfg.jwt_refresh_ttl_seconds,
        "username": user.username,
        "role": user.role,
    }

@router.post("/revoke")
def revoke_user_token(data: dict, _role: str = Depends(require_viewer)):
    raw = (data.get("token") or "").strip()
    if not raw:
        raise HTTPException(400, "token required")
    cfg = AuthConfig.from_env()
    try:
        result = revoke_token(raw, cfg, str(data.get("reason") or "logout"))
    except HTTPException as exc:
        raise HTTPException(401, exc.detail)
    return {"status": "revoked", **result}

@router.get("")
def list_users(db: Session = Depends(get_db), _role: str = Depends(require_admin)):
    users = db.query(User).all()
    return [
        {
            "id": u.id,
            "username": u.username,
            "display_name": u.display_name,
            "role": u.role,
            "created_at": u.created_at.isoformat() if u.created_at else "",
        }
        for u in users
    ]


@router.post("", status_code=201)
def create_user(data: dict, db: Session = Depends(get_db), _role: str = Depends(require_admin)):
    username = data.get("username", "")
    if not username:
        raise HTTPException(400, "username required")
    if db.query(User).filter(User.username == username).first():
        raise HTTPException(409, "Username already exists")
    # When creating user, if client specifies an initial token/secret, preserve it; otherwise auto-generate
    token = (data.get("token") or "").strip()
    if not token:
        token = secrets.token_urlsafe(32)
    u = User(
        username=username,
        display_name=data.get("display_name", username),
        role=_valid_role(data.get("role", "interpreter")),
    )
    _set_secret(u, token)
    db.add(u)
    db.commit()
    db.refresh(u)
    # The plaintext is returned exactly once; only its hash is persisted.
    return {"id": u.id, "username": u.username, "role": u.role, "token": token}


@router.put("/{uid}")
def update_user(uid: int, data: dict, db: Session = Depends(get_db), _role: str = Depends(require_admin)):
    u = db.query(User).filter(User.id == uid).first()
    if not u:
        raise HTTPException(404, "User not found")
    if "display_name" in data:
        u.display_name = data["display_name"]
    if "role" in data:
        u.role = _valid_role(data["role"])
    db.commit()
    return {"id": u.id, "username": u.username, "role": u.role}


@router.post("/{uid}/rotate-token")
def rotate_user_token(uid: int, db: Session = Depends(get_db), _role: str = Depends(require_admin)):
    """Issue a new one-time plaintext secret and persist only its hash."""
    user = db.query(User).filter(User.id == uid).first()
    if not user:
        raise HTTPException(404, "User not found")
    token = secrets.token_urlsafe(32)
    _set_secret(user, token)
    db.commit()
    return {"id": user.id, "username": user.username, "token": token}


@router.delete("/{uid}", status_code=204)
def delete_user(uid: int, db: Session = Depends(get_db), _role: str = Depends(require_admin)):
    u = db.query(User).filter(User.id == uid).first()
    if not u:
        raise HTTPException(404, "User not found")
    db.delete(u)
    db.commit()


@router.post("/token")
def issue_user_token(data: dict, request: Request, db: Session = Depends(get_db)):
    """Authenticate user by username and user token/secret, returning signed JWT bearer token."""
    username = (data.get("username") or "").strip()
    token = (data.get("token") or "").strip()
    if not username:
        raise HTTPException(400, "username required")

    retry_after = check_login_allowed(client_ip(request), username)
    if retry_after:
        raise HTTPException(
            429,
            "too many login attempts",
            headers={"Retry-After": str(retry_after)},
        )

    user = db.query(User).filter(User.username == username).first()
    valid = False
    if user is not None:
        if user.token_hash:
            valid = verify_secret(token, user.token_hash)
        elif user.token:
            # One-way upgrade path for rows created before hashing existed.
            valid = hmac.compare_digest(str(user.token), token)

    if not valid:
        if user is None or (not user.token_hash and not user.token):
            verify_secret(token, DUMMY_HASH)
        lockout = record_login_failure(client_ip(request), username)
        if lockout:
            raise HTTPException(
                429,
                "too many failed login attempts",
                headers={"Retry-After": str(lockout)},
            )
        raise HTTPException(401, "Invalid credentials")

    clear_login_failures(username)
    if user.token or needs_rehash(user.token_hash):
        # Upgrade legacy plaintext and raise the cost of old hashes.
        _set_secret(user, token)
        db.commit()

    cfg = AuthConfig.from_env()
    if not cfg.jwt_secret:
        raise HTTPException(503, "JWT secret is not configured (set AUTH_JWT_SECRET)")

    access_token = create_access_token(subject=user.username, role=user.role, cfg=cfg)
    refresh_token = create_refresh_token(subject=user.username, role=user.role, cfg=cfg)
    return {
        "access_token": access_token,
        "refresh_token": refresh_token,
        "token_type": "bearer",
        "expires_in": cfg.jwt_ttl_seconds,
        "refresh_expires_in": cfg.jwt_refresh_ttl_seconds,
        "username": user.username,
        "role": user.role,
    }

