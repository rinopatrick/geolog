"""Frozen /api/v1 read contract for representative endpoints."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from backend.main import SessionLocal, app
from backend.models import LogRun, Project, Well

client = TestClient(app)
VIEWER = {"X-User-Role": "viewer"}


def _ids() -> tuple[int, int]:
    db = SessionLocal()
    try:
        well = db.query(Well.id).order_by(Well.id.asc()).first()
        project = db.query(Project.id).order_by(Project.id.asc()).first()
        assert well and project
        return int(well[0]), int(project[0])
    finally:
        db.close()


@pytest.mark.parametrize(
    "suffix",
    [
        "/health",
        "/version",
        "/wells/",
        "/projects/",
        "/jobs",
        "/audit-log?limit=5",
    ],
)
def test_v1_read_contract_matches_legacy(suffix):
    legacy = client.get("/api" + suffix, headers=VIEWER)
    versioned = client.get("/api/v1" + suffix, headers=VIEWER)
    assert versioned.status_code == legacy.status_code, versioned.text
    assert versioned.headers["x-api-version"] == "v1"


def test_v1_well_scoped_contract_matches_legacy():
    wid, pid = _ids()
    for suffix in (
        f"/wells/{wid}",
        f"/wells/{wid}/tops",
        f"/wells/{wid}/zones",
        f"/wells/{wid}/log-runs",
        f"/wells/{wid}/petro-params",
        f"/wells/{wid}/export-las",
        f"/projects/{pid}/summary",
    ):
        legacy = client.get("/api" + suffix, headers=VIEWER)
        versioned = client.get("/api/v1" + suffix, headers=VIEWER)
        assert versioned.status_code == legacy.status_code, (suffix, versioned.text)
        assert versioned.headers["x-api-version"] == "v1"
