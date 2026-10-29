"""Project membership ACL and list filtering."""

from __future__ import annotations

import datetime

import jwt as pyjwt
import pytest
from fastapi.testclient import TestClient

from backend import main as main_mod
from backend.main import SessionLocal, app
from backend.models import Project, ProjectMember, User, Well

client = TestClient(app)
SECRET = "acl-test-secret-0123456789abcdef"


def _token(subject: str, role: str) -> str:
    now = datetime.datetime.now(datetime.timezone.utc)
    return pyjwt.encode(
        {
            "sub": subject,
            "role": role,
            "iat": int(now.timestamp()),
            "exp": int((now + datetime.timedelta(hours=1)).timestamp()),
        },
        SECRET,
        algorithm="HS256",
    )


def _h(subject: str, role: str) -> dict:
    return {"Authorization": f"Bearer {_token(subject, role)}"}


@pytest.fixture
def jwt_mode(monkeypatch):
    old_mode = main_mod.AUTH_CONFIG.mode
    old_secret = main_mod.AUTH_CONFIG.jwt_secret
    old_algs = main_mod.AUTH_CONFIG.jwt_algorithms
    main_mod.AUTH_CONFIG.mode = "jwt"
    main_mod.AUTH_CONFIG.jwt_secret = SECRET
    main_mod.AUTH_CONFIG.jwt_algorithms = ("HS256",)
    try:
        yield
    finally:
        main_mod.AUTH_CONFIG.mode = old_mode
        main_mod.AUTH_CONFIG.jwt_secret = old_secret
        main_mod.AUTH_CONFIG.jwt_algorithms = old_algs


def _create_project(admin_subject: str = "acl_admin") -> int:
    r = client.post("/api/projects/", json={"name": "ACL Project"}, headers=_h(admin_subject, "admin"))
    assert r.status_code == 201, r.text
    return r.json()["id"]


def test_creator_is_project_admin(jwt_mode):
    pid = _create_project("creator_user")
    db = SessionLocal()
    try:
        member = (
            db.query(ProjectMember)
            .filter(ProjectMember.project_id == pid, ProjectMember.subject == "creator_user")
            .first()
        )
        assert member is not None
        assert member.role == "admin"
    finally:
        db.close()


def test_non_member_is_denied_restricted_project(jwt_mode):
    pid = _create_project("owner_user")
    denied = client.get(f"/api/projects/{pid}/summary", headers=_h("outsider", "viewer"))
    assert denied.status_code == 403, denied.text
    allowed = client.get(f"/api/projects/{pid}/summary", headers=_h("owner_user", "viewer"))
    assert allowed.status_code == 200, allowed.text


def test_member_can_read_and_is_filtered_from_lists(jwt_mode):
    pid = _create_project("owner2")
    added = client.post(
        f"/api/projects/{pid}/members",
        json={"subject": "reader", "role": "viewer"},
        headers=_h("owner2", "admin"),
    )
    assert added.status_code == 201, added.text

    assert client.get(f"/api/projects/{pid}/summary", headers=_h("reader", "viewer")).status_code == 200
    assert client.get(f"/api/projects/{pid}/summary", headers=_h("other", "viewer")).status_code == 403

    projects = client.get("/api/projects/", headers=_h("other", "viewer")).json()
    assert pid not in {p["id"] for p in projects}
    reader_projects = client.get("/api/projects/", headers=_h("reader", "viewer")).json()
    assert pid in {p["id"] for p in reader_projects}


def test_global_admin_bypasses_membership(jwt_mode):
    pid = _create_project("owner3")
    r = client.get(f"/api/projects/{pid}/summary", headers=_h("global_admin", "admin"))
    assert r.status_code == 200, r.text


def test_open_project_stays_visible_until_first_member(jwt_mode):
    db = SessionLocal()
    try:
        project = Project(name="Open Legacy Project")
        db.add(project)
        db.commit()
        db.refresh(project)
        pid = project.id
    finally:
        db.close()

    assert client.get(f"/api/projects/{pid}/summary", headers=_h("anyone", "viewer")).status_code == 200

    client.post(
        f"/api/projects/{pid}/members",
        json={"subject": "owner_open", "role": "admin"},
        headers=_h("global_admin", "admin"),
    )
    assert client.get(f"/api/projects/{pid}/summary", headers=_h("anyone", "viewer")).status_code == 403


def test_last_member_removal_requires_force(jwt_mode):
    pid = _create_project("last_owner")
    blocked = client.delete(
        f"/api/projects/{pid}/members/last_owner",
        headers=_h("last_owner", "admin"),
    )
    assert blocked.status_code == 400, blocked.text
    forced = client.delete(
        f"/api/projects/{pid}/members/last_owner?force=true",
        headers=_h("last_owner", "admin"),
    )
    assert forced.status_code == 204, forced.text
    # The project becomes open again, matching the legacy-data contract.
    assert client.get(f"/api/projects/{pid}/summary", headers=_h("anyone", "viewer")).status_code == 200


def test_well_list_filters_restricted_projects(jwt_mode):
    pid = _create_project("well_owner")
    db = SessionLocal()
    try:
        well = Well(project_id=pid, name="Restricted Well")
        db.add(well)
        db.commit()
        db.refresh(well)
        wid = well.id
    finally:
        db.close()

    hidden = client.get("/api/wells", headers=_h("outsider", "viewer")).json()
    assert wid not in {w["id"] for w in hidden}
    visible = client.get("/api/wells", headers=_h("well_owner", "viewer")).json()
    assert wid in {w["id"] for w in visible}


def test_body_and_query_well_routes_enforce_acl(jwt_mode):
    pid = _create_project("query_owner")
    db = SessionLocal()
    try:
        restricted = Well(project_id=pid, name="Restricted Query Well")
        db.add(restricted)
        db.commit()
        db.refresh(restricted)
        restricted_id = restricted.id
        other_id = db.query(Well.id).filter(Well.project_id != pid).order_by(Well.id.asc()).first()[0]
    finally:
        db.close()

    cross = client.get(
        f"/api/correlation/cross-section?well_ids={restricted_id},{other_id}&curve=GR",
        headers=_h("outsider", "viewer"),
    )
    assert cross.status_code == 403, cross.text

    ties = client.get(
        f"/api/correlation/tie-lines?well_a_id={restricted_id}&well_b_id={other_id}",
        headers=_h("outsider", "viewer"),
    )
    assert ties.status_code == 403, ties.text

    auto = client.post(
        "/api/correlation/auto-correlate",
        json={"well_a_id": restricted_id, "well_b_id": other_id},
        headers=_h("outsider", "interpreter"),
    )
    assert auto.status_code == 403, auto.text

    markers = client.post(
        "/api/correlation-markers",
        json={"well_a_id": restricted_id, "well_b_id": other_id, "markers": []},
        headers=_h("outsider", "interpreter"),
    )
    assert markers.status_code == 403, markers.text


def test_job_list_hides_restricted_project_payloads(jwt_mode):
    from backend.jobs import create_job

    pid = _create_project("job_owner")
    job_id = create_job("acl-test-job", {"pid": pid})

    outsider = client.get("/api/jobs", headers=_h("outsider", "viewer")).json()
    assert job_id not in {j["id"] for j in outsider["jobs"]}

    owner = client.get("/api/jobs", headers=_h("job_owner", "viewer")).json()
    assert job_id in {j["id"] for j in owner["jobs"]}

    assert client.get(f"/api/jobs/{job_id}", headers=_h("outsider", "viewer")).status_code == 403


def _add_project_member(pid: int, subject: str, role: str = "viewer") -> None:
    r = client.post(
        f"/api/projects/{pid}/members",
        json={"subject": subject, "role": role},
        headers=_h("acl_admin", "admin"),
    )
    assert r.status_code == 201, r.text


def _add_well_member(pid: int, wid: int, subject: str, role: str = "viewer", admin_subject: str = "acl_admin") -> None:
    r = client.post(
        f"/api/wells/{wid}/members",
        json={"subject": subject, "role": role},
        headers=_h(admin_subject, "admin"),
    )
    assert r.status_code == 201, r.text


def _well(pid: int, name: str = "ACL Well") -> int:
    db = SessionLocal()
    try:
        well = Well(project_id=pid, name=name)
        db.add(well)
        db.commit()
        db.refresh(well)
        return well.id
    finally:
        db.close()


def test_well_member_overrides_project_membership(jwt_mode):
    pid = _create_project("acl_admin")
    _add_project_member(pid, "project_reader", "viewer")
    wid = _well(pid, "Restricted Well")

    # No well members yet: project membership is enough.
    assert client.get(f"/api/wells/{wid}", headers=_h("project_reader", "viewer")).status_code == 200

    _add_well_member(pid, wid, "well_reader", "viewer")

    # The well is now restricted: project membership alone is denied.
    assert client.get(f"/api/wells/{wid}", headers=_h("project_reader", "viewer")).status_code == 403
    assert client.get(f"/api/wells/{wid}", headers=_h("well_reader", "viewer")).status_code == 200
    assert client.get(f"/api/wells/{wid}", headers=_h("acl_admin", "admin")).status_code == 200
    assert client.get(f"/api/wells/{wid}", headers=_h("global_admin", "admin")).status_code == 200


def test_well_member_list_and_filtering(jwt_mode):
    pid = _create_project("filter_owner")
    _add_project_member(pid, "project_reader", "viewer")
    wid = _well(pid, "Hidden Well")
    _add_well_member(pid, wid, "well_reader", "viewer")

    members = client.get(f"/api/wells/{wid}/members", headers=_h("well_reader", "viewer"))
    assert members.status_code == 200, members.text
    assert [m["subject"] for m in members.json()] == ["well_reader"]

    listed = client.get("/api/wells", headers=_h("project_reader", "viewer")).json()
    assert wid not in {w["id"] for w in listed}
    listed = client.get("/api/wells", headers=_h("well_reader", "viewer")).json()
    assert wid in {w["id"] for w in listed}


def test_project_admin_can_manage_well_members_without_well_membership(jwt_mode):
    pid = _create_project("manage_owner")
    wid = _well(pid, "Managed Well")
    _add_well_member(pid, wid, "existing", "viewer")

    # manage_owner is project admin but not a well member; the manager
    # exception must let them add another member.
    added = client.post(
        f"/api/wells/{wid}/members",
        json={"subject": "new_member", "role": "interpreter"},
        headers=_h("manage_owner", "admin"),
    )
    assert added.status_code == 201, added.text


def test_well_member_write_requires_well_role(jwt_mode):
    pid = _create_project("write_owner")
    _add_project_member(pid, "project_writer", "interpreter")
    wid = _well(pid, "Write Well")
    _add_well_member(pid, wid, "well_writer", "interpreter")

    payload = {"depth": 1000.0, "text": "note"}
    denied = client.post(
        f"/api/wells/{wid}/annotations",
        json=payload,
        headers=_h("project_writer", "interpreter"),
    )
    assert denied.status_code == 403, denied.text
    allowed = client.post(
        f"/api/wells/{wid}/annotations",
        json=payload,
        headers=_h("well_writer", "interpreter"),
    )
    assert allowed.status_code == 201, allowed.text


def test_last_well_member_removal_requires_force(jwt_mode):
    pid = _create_project("last_well_owner")
    wid = _well(pid, "Last Member Well")
    _add_well_member(pid, wid, "only_member", "admin", admin_subject="acl_admin")

    blocked = client.delete(
        f"/api/wells/{wid}/members/only_member",
        headers=_h("acl_admin", "admin"),
    )
    assert blocked.status_code == 400, blocked.text
    forced = client.delete(
        f"/api/wells/{wid}/members/only_member?force=true",
        headers=_h("acl_admin", "admin"),
    )
    assert forced.status_code == 204, forced.text
