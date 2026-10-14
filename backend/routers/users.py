"""User management router for GeoLog."""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

try:
    from database import get_db
    from deps import require_admin, require_viewer
    from models import User
except ImportError:
    from backend.database import get_db
    from backend.deps import require_admin, require_viewer
    from backend.models import User

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
    import hashlib
    import time

    username = data.get("username", "")
    if not username:
        raise HTTPException(400, "username required")
    if db.query(User).filter(User.username == username).first():
        raise HTTPException(409, "Username already exists")
    token = hashlib.sha256(f"{username}{time.time()}".encode()).hexdigest()[:32]
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
