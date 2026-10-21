"""Production hardening: secret files, JWKS/RS256, TLS headers, token TTL."""

from __future__ import annotations

import datetime
from types import SimpleNamespace

import jwt
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi.testclient import TestClient

from backend import main as main_mod
from backend import security
from backend.audit import resolve_audit_export_signing_key
from backend.main import SessionLocal, app
from backend.models import User
from backend.security import AuthConfig, create_access_token, resolve_auth_context

KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)
PUBLIC_PEM = KEY.public_key().public_bytes(
    serialization.Encoding.PEM,
    serialization.PublicFormat.SubjectPublicKeyInfo,
).decode("utf-8")

class Req:
    def __init__(self, token: str):
        self.headers = {"Authorization": f"Bearer {token}"}

def _rs256(role: str = "interpreter", key=None) -> str:
    now = datetime.datetime.now(datetime.timezone.utc)
    return jwt.encode(
        {
            "sub": "u1",
            "role": role,
            "iat": int(now.timestamp()),
            "exp": int((now + datetime.timedelta(hours=1)).timestamp()),
        },
        key or KEY,
        algorithm="RS256",
    )

def test_auth_config_reads_secret_file(tmp_path, monkeypatch):
    path = tmp_path / "jwt_secret"
    path.write_text("from-a-file\n", encoding="utf-8")
    monkeypatch.setenv("AUTH_JWT_SECRET_FILE", str(path))
    monkeypatch.delenv("AUTH_JWT_SECRET", raising=False)
    cfg = AuthConfig.from_env()
    assert cfg.jwt_secret == "from-a-file"

def test_audit_signing_key_reads_secret_file(tmp_path, monkeypatch):
    path = tmp_path / "audit_key"
    path.write_text("audit-from-file\n", encoding="utf-8")
    monkeypatch.setenv("AUDIT_EXPORT_HMAC_KEY_FILE", str(path))
    monkeypatch.delenv("AUDIT_EXPORT_HMAC_KEY", raising=False)
    monkeypatch.delenv("AUDIT_EXPORT_HMAC_KEYS_JSON", raising=False)
    monkeypatch.delenv("AUDIT_EXPORT_HMAC_ACTIVE_KID", raising=False)
    kid, key = resolve_audit_export_signing_key()
    assert kid == "legacy"
    assert key == "audit-from-file"

def test_token_ttl_and_jti():
    cfg = AuthConfig(mode="jwt", jwt_secret="x" * 40, jwt_ttl_seconds=120)
    token = create_access_token("u1", "viewer", cfg)
    claims = jwt.decode(token, cfg.jwt_secret, algorithms=["HS256"])
    assert claims["exp"] - claims["iat"] == 120
    assert claims["jti"]

def test_rs256_public_key_verification():
    cfg = AuthConfig(
        mode="jwt",
        jwt_public_key=PUBLIC_PEM,
        jwt_algorithms=("RS256",),
    )
    ctx = resolve_auth_context(Req(_rs256()), cfg)
    assert ctx.role == "interpreter"
    assert ctx.subject == "u1"

def test_rs256_rejects_a_different_key():
    other = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    cfg = AuthConfig(
        mode="jwt",
        jwt_public_key=PUBLIC_PEM,
        jwt_algorithms=("RS256",),
    )
    with pytest.raises(Exception):
        resolve_auth_context(Req(_rs256(key=other)), cfg)

def test_jwks_client_path(monkeypatch):
    class FakeClient:
        def get_signing_key_from_jwt(self, token):
            return SimpleNamespace(key=PUBLIC_PEM)

    monkeypatch.setattr(security, "_get_jwks_client", lambda url: FakeClient())
    cfg = AuthConfig(
        mode="jwt",
        jwt_jwks_url="https://idp.example.com/jwks",
        jwt_algorithms=("RS256",),
    )
    ctx = resolve_auth_context(Req(_rs256("admin")), cfg)
    assert ctx.role == "admin"

def test_security_headers_and_hsts():
    http = TestClient(app)
    r = http.get("/api/health")
    assert r.headers["x-content-type-options"] == "nosniff"
    assert r.headers["x-frame-options"] == "DENY"
    assert r.headers["referrer-policy"] == "strict-origin-when-cross-origin"
    assert "strict-transport-security" not in r.headers

    https = TestClient(app, base_url="https://testserver")
    r = https.get("/api/health")
    assert r.headers["strict-transport-security"].startswith("max-age=")

def test_require_https_redirects_api_but_not_health(monkeypatch):
    monkeypatch.setenv("GEOLOG_REQUIRE_HTTPS", "true")
    client = TestClient(app)
    r = client.get("/api/wells", follow_redirects=False)
    assert r.status_code == 308
    assert r.headers["location"].startswith("https://")
    r = client.get("/api/health", follow_redirects=False)
    assert r.status_code == 200

def test_token_endpoint_reports_ttl(monkeypatch):
    monkeypatch.setenv("AUTH_JWT_SECRET", "x" * 40)
    monkeypatch.setenv("AUTH_JWT_TTL_SECONDS", "120")
    db = SessionLocal()
    try:
        user = db.query(User).filter(User.username == "ttl_user").first()
        if not user:
            user = User(username="ttl_user", role="viewer", token="ttl-secret")
            db.add(user)
            db.commit()
    finally:
        db.close()

    client = TestClient(app)
    r = client.post("/api/users/token", json={"username": "ttl_user", "token": "ttl-secret"})
    assert r.status_code == 200, r.text
    assert r.json()["expires_in"] == 120
