"""Project-level access control.

A project with no rows in `project_members` is treated as an open legacy
project. The first membership added turns it into a restricted project; from
then on a caller must be a member (or a global admin) to reach its projects,
wells and log runs. That keeps existing installations working while allowing an
administrator to lock a project down without a risky bulk backfill.

This is deliberately project-level. Well-level overrides would need a separate
table and are not part of the current contract.
"""

from __future__ import annotations

import os

from fastapi import HTTPException, Request
from starlette.middleware.base import BaseHTTPMiddleware

try:
    from database import SessionLocal
    from deps import SafeJSONResponse
    from models import LogRun, ProjectMember, Well, WellMember
except ImportError:
    from backend.database import SessionLocal
    from backend.deps import SafeJSONResponse
    from backend.models import LogRun, ProjectMember, Well, WellMember

ROLE_RANK = {"viewer": 1, "interpreter": 2, "admin": 3}
MEMBER_ROLES = {"viewer", "interpreter", "admin"}


def _env_truthy(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None or not raw.strip():
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def enforcement_enabled() -> bool:
    return _env_truthy("GEOLOG_ENFORCE_PROJECT_ACL", True)


def project_is_restricted(db, project_id: int) -> bool:
    return (
        db.query(ProjectMember.id)
        .filter(ProjectMember.project_id == project_id)
        .first()
        is not None
    )


def well_is_restricted(db, well_id: int) -> bool:
    return (
        db.query(WellMember.id)
        .filter(WellMember.well_id == well_id)
        .first()
        is not None
    )


def well_membership_role(db, well_id: int, subject: str) -> str | None:
    if not subject:
        return None
    row = (
        db.query(WellMember.role)
        .filter(WellMember.well_id == well_id, WellMember.subject == subject)
        .first()
    )
    return str(row[0]) if row else None


def membership_role(db, project_id: int, subject: str) -> str | None:
    if not subject:
        return None
    row = (
        db.query(ProjectMember.role)
        .filter(ProjectMember.project_id == project_id, ProjectMember.subject == subject)
        .first()
    )
    return str(row[0]) if row else None


def can_access_project(
    db,
    project_id: int,
    subject: str,
    role: str,
    *,
    write: bool = False,
) -> bool:
    if not enforcement_enabled():
        return True
    if (role or "").strip().lower() == "admin":
        return True
    if not project_is_restricted(db, project_id):
        return True
    member = membership_role(db, project_id, subject)
    if not member:
        return False
    required = "interpreter" if write else "viewer"
    return ROLE_RANK.get(member, 0) >= ROLE_RANK.get(required, 99)


def can_access_well(
    db,
    well_id: int,
    subject: str,
    role: str,
    *,
    write: bool = False,
) -> bool:
    if not enforcement_enabled():
        return True
    if (role or "").strip().lower() == "admin":
        return True
    if well_is_restricted(db, well_id):
        member = well_membership_role(db, well_id, subject)
        if not member:
            return False
        required = "interpreter" if write else "viewer"
        return ROLE_RANK.get(member, 0) >= ROLE_RANK.get(required, 99)
    row = db.query(Well.project_id).filter(Well.id == well_id).first()
    if row is None:
        return True  # the route owns the 404
    return can_access_project(db, int(row[0]), subject, role, write=write)


def visible_project_ids(db, subject: str, role: str, all_ids) -> set[int] | None:
    """Return the project ids the caller may see; None means all of them."""
    if not enforcement_enabled() or (role or "").strip().lower() == "admin":
        return None
    restricted = {
        int(row[0])
        for row in db.query(ProjectMember.project_id).distinct().all()
        if row[0] is not None
    }
    if not restricted:
        return set(all_ids)
    member_of = {
        int(row[0])
        for row in db.query(ProjectMember.project_id)
        .filter(ProjectMember.subject == subject)
        .all()
        if row[0] is not None
    }
    return (set(all_ids) - restricted) | member_of


def can_see_project(db, project_id: int, subject: str, role: str) -> bool:
    return can_access_project(db, project_id, subject, role, write=False)


def resolve_project_id(db, path: str) -> int | None:
    """Resolve an API path to the project whose data it touches."""
    parts = [p for p in path.split("/") if p]
    if len(parts) < 2 or parts[0] != "api":
        return None
    if parts[1] == "projects" and len(parts) >= 3 and parts[2].isdigit():
        return int(parts[2])
    if parts[1] == "wells" and len(parts) >= 3 and parts[2].isdigit():
        row = db.query(Well.project_id).filter(Well.id == int(parts[2])).first()
        return int(row[0]) if row else None
    if parts[1] == "log-runs" and len(parts) >= 3 and parts[2].isdigit():
        row = (
            db.query(Well.project_id)
            .join(LogRun, LogRun.well_id == Well.id)
            .filter(LogRun.id == int(parts[2]))
            .first()
        )
        return int(row[0]) if row else None
    return None


def request_subject(request: Request) -> str:
    try:
        from http_utils import request_subject as _subject
    except ImportError:
        from backend.http_utils import request_subject as _subject
    return _subject(request)


def request_role(request: Request) -> str:
    return str(getattr(request.state, "user_role", "") or "viewer").strip().lower()


class ProjectAccessMiddleware(BaseHTTPMiddleware):
    """Deny access to a restricted project before the route runs."""

    async def dispatch(self, request: Request, call_next):
        allowed, project_id = check_request_access(request)
        if not allowed:
            return SafeJSONResponse(
                status_code=403,
                content={"detail": "project membership required"},
            )
        if project_id is not None:
            request.state.project_id = project_id
        return await call_next(request)


def require_project_access(db, request: Request, project_id: int, *, write: bool = False) -> None:
    """Route-level check for paths whose IDs live in a body or query string."""
    if not can_access_project(
        db, project_id, request_subject(request), request_role(request), write=write
    ):
        raise HTTPException(403, "project membership required")


def require_well_access(db, request: Request, well_id: int, *, write: bool = False) -> None:
    if not can_access_well(
        db, well_id, request_subject(request), request_role(request), write=write
    ):
        raise HTTPException(403, "well membership required")


def check_request_access(request: Request) -> tuple[bool, int | None]:
    """Return (allowed, project_id) for the current request path."""
    if not enforcement_enabled():
        return True, None
    path = request.url.path
    if not path.startswith("/api/"):
        return True, None
    db = SessionLocal()
    try:
        parts = [p for p in path.split("/") if p]
        write = request.method.upper() not in {"GET", "HEAD", "OPTIONS"}
        subject = request_subject(request)
        role = request_role(request)
        if len(parts) >= 3 and parts[0] == "api" and parts[1] == "wells" and parts[2].isdigit():
            well_id = int(parts[2])
            row = db.query(Well.project_id).filter(Well.id == well_id).first()
            project_id = int(row[0]) if row else None
            # A project admin must be able to manage a restricted well's
            # membership even when they are not a well member themselves.
            if (
                project_id is not None
                and len(parts) >= 4
                and parts[3] == "members"
                and (role or "").strip().lower() != "admin"
                and membership_role(db, project_id, subject) == "admin"
            ):
                return True, project_id
            allowed = can_access_well(db, well_id, subject, role, write=write)
            return allowed, project_id
        if len(parts) >= 3 and parts[0] == "api" and parts[1] == "log-runs" and parts[2].isdigit():
            row = (
                db.query(LogRun.well_id, Well.project_id)
                .join(Well, LogRun.well_id == Well.id)
                .filter(LogRun.id == int(parts[2]))
                .first()
            )
            if row is None:
                return True, None
            allowed = can_access_well(db, int(row[0]), subject, role, write=write)
            return allowed, int(row[1])
        project_id = resolve_project_id(db, path)
        if project_id is None:
            return True, None
        allowed = can_access_project(db, project_id, subject, role, write=write)
        return allowed, project_id
    finally:
        db.close()
