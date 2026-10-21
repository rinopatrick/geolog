"""User management router for GeoLog."""

import hmac
import secrets

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

try:
    from database import get_db
    from deps import require_admin, require_viewer
    from models import User
    from security import AuthConfig, create_access_token
except ImportError:
    from backend.database import get_db
    from backend.deps import require_admin, require_viewer
    from backend.models import User
    from backend.security import AuthConfig, create_access_token

router = APIRouter(prefix="/api/users", tags=["users"])


@router.get("")
def list_users(db: Session = Depends(get_db), _role: str = Depends(require_viewer)):
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
        role=data.get("role", "interpreter"),
        token=token,
    )
    db.add(u)
    db.commit()
    db.refresh(u)
    return {"id": u.id, "username": u.username, "role": u.role, "token": token}


@router.put("/{uid}")
def update_user(uid: int, data: dict, db: Session = Depends(get_db), _role: str = Depends(require_admin)):
    u = db.query(User).filter(User.id == uid).first()
    if not u:
        raise HTTPException(404, "User not found")
    for field in ("display_name", "role"):
        if field in data:
            setattr(u, field, data[field])
    db.commit()
    return {"id": u.id, "username": u.username, "role": u.role}


@router.delete("/{uid}", status_code=204)
def delete_user(uid: int, db: Session = Depends(get_db), _role: str = Depends(require_admin)):
    u = db.query(User).filter(User.id == uid).first()
    if not u:
        raise HTTPException(404, "User not found")
    db.delete(u)
    db.commit()


@router.post("/token")
def issue_user_token(data: dict, db: Session = Depends(get_db)):
    """Authenticate user by username and user token/secret, returning signed JWT bearer token."""
    username = (data.get("username") or "").strip()
    token = (data.get("token") or "").strip()
    if not username:
        raise HTTPException(400, "username required")

    user = db.query(User).filter(User.username == username).first()
    if not user:
        raise HTTPException(401, "Invalid credentials")

    # A user with no registered secret cannot authenticate. The old form
    # skipped this check when the column was empty, so any legacy row with no
    # token could be logged in as without a credential.
    if not user.token or not hmac.compare_digest(str(user.token), token):
        raise HTTPException(401, "Invalid credentials")

    cfg = AuthConfig.from_env()
    if not cfg.jwt_secret:
        raise HTTPException(503, "JWT secret is not configured (set AUTH_JWT_SECRET)")

    access_token = create_access_token(subject=user.username, role=user.role, cfg=cfg)
    return {
        "access_token": access_token,
        "token_type": "bearer",
        "expires_in": cfg.jwt_ttl_seconds,
        "username": user.username,
        "role": user.role,
    }

