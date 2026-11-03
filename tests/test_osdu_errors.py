"""OSDU error contracts at the API seam.

Unconfigured server is a 400 on test, pull, and push. Push without a
wellbore id and without a UWI is a 400. Transport failure is a 502.
"""

from __future__ import annotations

from fastapi.testclient import TestClient

from backend import interop
from backend.main import app

client = TestClient(app)
INTERPRETER = {"X-User-Role": "interpreter"}


def _clear_osdu(monkeypatch):
    monkeypatch.delenv("BORELIA_OSDU_URL", raising=False)
    monkeypatch.delenv("BORELIA_OSDU_TOKEN", raising=False)


def test_osdu_test_unconfigured_is_400(monkeypatch):
    _clear_osdu(monkeypatch)
    r = client.post("/api/interop/osdu/test", headers=INTERPRETER)
    assert r.status_code == 400


def test_osdu_pull_unconfigured_is_400(monkeypatch):
    _clear_osdu(monkeypatch)
    r = client.post("/api/interop/osdu/pull?project_id=1", headers=INTERPRETER)
    assert r.status_code == 400


def test_osdu_pull_logs_needs_wellbore_or_uwi(monkeypatch, make_well):
    monkeypatch.setenv("BORELIA_OSDU_URL", "https://osdu.example")
    wid = make_well("OSDU-NOUWI", {"DEPT": [1000.0], "GR": [10.0]})
    r = client.post(f"/api/interop/osdu/pull-logs?well_id={wid}", headers=INTERPRETER)
    assert r.status_code == 400


def test_osdu_transport_failure_is_502(monkeypatch):
    monkeypatch.setenv("BORELIA_OSDU_URL", "https://osdu.example")
    monkeypatch.setenv("BORELIA_OSDU_PARTITION", "p1")

    def boom(cfg, method, path, body=None):
        raise ConnectionError("refused")
    monkeypatch.setattr(interop, "osdu_request", boom)
    r = client.post("/api/interop/osdu/test", headers=INTERPRETER)
    assert r.status_code == 502
