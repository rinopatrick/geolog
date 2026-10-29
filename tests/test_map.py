"""Project map endpoint."""

from fastapi.testclient import TestClient

from backend.main import SessionLocal, app
from backend.models import Project

client = TestClient(app)
ADMIN = {"X-User-Role": "admin"}


def _project_id() -> int:
    db = SessionLocal()
    try:
        return int(db.query(Project.id).order_by(Project.id.asc()).first()[0])
    finally:
        db.close()


def test_project_map_returns_wells_and_feature_buckets():
    pid = _project_id()
    response = client.get(f"/api/projects/{pid}/map", headers=ADMIN)
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["project_id"] == pid
    assert len(body["wells"]) >= 2
    for key in ("lines", "ties", "faults", "surfaces", "prospects"):
        assert isinstance(body[key], list)
