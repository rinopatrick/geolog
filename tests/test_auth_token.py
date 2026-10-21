"""Tests for local token issuance and JWT auth flow."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from backend.main import SessionLocal, app
from backend.models import User
from backend.security import AuthConfig, create_access_token, resolve_auth_context

client = TestClient(app)


def test_create_access_token_and_decode():
    cfg = AuthConfig(
        mode="jwt",
        jwt_secret="super-secret-key-12345",
        jwt_issuer="geolog-auth",
        jwt_audience="geolog-api",
    )
    token = create_access_token(
        subject="petrophysicist",
        role="interpreter",
        cfg=cfg,
        expires_delta_seconds=3600,
    )
    assert isinstance(token, str)

    class DummyRequest:
        def __init__(self, t):
            self.headers = {"Authorization": f"Bearer {t}"}

    req = DummyRequest(token)
    ctx = resolve_auth_context(req, cfg)
    assert ctx.role == "interpreter"
    assert ctx.subject == "petrophysicist"
    assert ctx.source == "jwt"


def test_issue_token_endpoint(monkeypatch):
    monkeypatch.setenv("AUTH_JWT_SECRET", "test-secret-for-token-issuance-12345")
    db = SessionLocal()
    try:
        user = db.query(User).filter(User.username == "auth_test_user").first()
        if not user:
            user = User(
                username="auth_test_user",
                display_name="Auth Tester",
                role="admin",
                token="test-secret-token",
            )
            db.add(user)
            db.commit()
    finally:
        db.close()

    # Invalid user
    r_bad_user = client.post("/api/users/token", json={"username": "non_existent"})
    assert r_bad_user.status_code == 401

    # Invalid secret token
    r_bad_token = client.post("/api/users/token", json={"username": "auth_test_user", "token": "wrong"})
    assert r_bad_token.status_code == 401

    # Valid issuance
    r_ok = client.post("/api/users/token", json={"username": "auth_test_user", "token": "test-secret-token"})
    assert r_ok.status_code == 200
    data = r_ok.json()
    assert data["token_type"] == "bearer"
    assert "access_token" in data
    assert data["role"] == "admin"

def test_issue_token_rejects_empty_registered_token(monkeypatch):
    monkeypatch.setenv("AUTH_JWT_SECRET", "test-secret-for-token-issuance-12345")
    db = SessionLocal()
    try:
        user = db.query(User).filter(User.username == "auth_empty_user").first()
        if not user:
            user = User(username="auth_empty_user", display_name="Empty", role="admin", token="")
            db.add(user)
            db.commit()
    finally:
        db.close()

    r = client.post("/api/users/token", json={"username": "auth_empty_user", "token": "anything"})
    assert r.status_code == 401, r.text

def test_issue_token_requires_configured_secret(monkeypatch):
    monkeypatch.delenv("AUTH_JWT_SECRET", raising=False)
    db = SessionLocal()
    try:
        user = db.query(User).filter(User.username == "auth_no_secret_user").first()
        if not user:
            user = User(username="auth_no_secret_user", role="viewer", token="secret")
            db.add(user)
            db.commit()
    finally:
        db.close()

    r = client.post("/api/users/token", json={"username": "auth_no_secret_user", "token": "secret"})
    assert r.status_code == 503, r.text
