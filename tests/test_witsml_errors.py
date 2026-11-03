"""WITSML error contracts at the API seam.

Unconfigured server is a 400. Bad object type is a 400. Transport
failure is a 502, not a 500. Pull of an unknown object type is a 400.
"""

from __future__ import annotations

from fastapi.testclient import TestClient

from backend import interop
from backend.main import app

client = TestClient(app)
INTERPRETER = {"X-User-Role": "interpreter"}


def test_witsml_test_unconfigured_is_400(monkeypatch):
    monkeypatch.delenv("BORELIA_WITSML_URL", raising=False)
    monkeypatch.delenv("BORELIA_WITSML_USER", raising=False)
    monkeypatch.delenv("BORELIA_WITSML_PASSWORD", raising=False)
    monkeypatch.delenv("BORELIA_WITSML_TOKEN", raising=False)
    r = client.post("/api/interop/witsml/test", headers=INTERPRETER)
    assert r.status_code == 400


def test_witsml_pull_bad_object_type_is_400(monkeypatch):
    monkeypatch.setattr(interop, "witsml_query", lambda kind, name="": "")
    r = client.post("/api/interop/witsml/pull?project_id=1&object_type=nope",
                    headers=INTERPRETER)
    assert r.status_code == 400


def test_witsml_transport_failure_is_502(monkeypatch):
    def boom(kind, name=""):
        raise ConnectionError("refused")
    monkeypatch.setattr(interop, "witsml_query", boom)
    r = client.post("/api/interop/witsml/pull?project_id=1&object_type=well",
                    headers=INTERPRETER)
    assert r.status_code == 502
