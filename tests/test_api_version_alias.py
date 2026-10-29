"""The /api/v1 prefix is a stable alias for the current handlers."""

from __future__ import annotations

from fastapi.testclient import TestClient

from backend.main import app

client = TestClient(app)
VIEWER = {"X-User-Role": "viewer"}


def test_v1_alias_serves_the_same_wells():
    legacy = client.get("/api/wells", headers=VIEWER)
    versioned = client.get("/api/v1/wells", headers=VIEWER)
    assert legacy.status_code == 200
    assert versioned.status_code == 200
    assert {w["id"] for w in legacy.json()} == {w["id"] for w in versioned.json()}


def test_v1_response_reports_v1_and_legacy_reports_v0():
    v1 = client.get("/api/v1/health")
    v0 = client.get("/api/health")
    assert v1.status_code == 200
    assert v1.headers["x-api-version"] == "v1"
    assert v0.headers["x-api-version"] == "v0"


def test_version_endpoint_reports_prefix():
    v1 = client.get("/api/v1/version")
    assert v1.status_code == 200
    assert v1.json()["api_version"] == "v1"
    assert v1.json()["version"]
    v0 = client.get("/api/version")
    assert v0.json()["api_version"] == "v0"


def test_v1_keeps_public_auth_paths_public():
    r = client.post("/api/v1/users/token", json={"username": "missing"})
    assert r.status_code == 401, r.text
    assert r.headers["x-api-version"] == "v1"


def test_v1_is_behind_auth():
    from backend import main as main_mod

    old_mode, old_secret, old_algs = (
        main_mod.AUTH_CONFIG.mode,
        main_mod.AUTH_CONFIG.jwt_secret,
        main_mod.AUTH_CONFIG.jwt_algorithms,
    )
    main_mod.AUTH_CONFIG.mode = "jwt"
    main_mod.AUTH_CONFIG.jwt_secret = "alias-test-secret-0123456789"
    main_mod.AUTH_CONFIG.jwt_algorithms = ("HS256",)
    try:
        assert client.get("/api/v1/wells").status_code == 401
    finally:
        main_mod.AUTH_CONFIG.mode = old_mode
        main_mod.AUTH_CONFIG.jwt_secret = old_secret
        main_mod.AUTH_CONFIG.jwt_algorithms = old_algs
