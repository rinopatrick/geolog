"""Login throttling, hashed user secrets, and upload body limits."""

from __future__ import annotations

from fastapi.testclient import TestClient

from backend.main import SessionLocal, app
from backend.models import User, Well
from backend.passwords import is_hash, verify_secret

client = TestClient(app)
ADMIN = {"X-User-Role": "admin"}
INTERPRETER = {"X-User-Role": "interpreter"}


def _user(username: str, **kwargs) -> User:
    db = SessionLocal()
    try:
        user = db.query(User).filter(User.username == username).first()
        if not user:
            user = User(username=username, **kwargs)
            db.add(user)
            db.commit()
            db.refresh(user)
        return user
    finally:
        db.close()


def test_created_user_stores_only_a_hash(monkeypatch):
    monkeypatch.setenv("AUTH_JWT_SECRET", "test-secret-for-hash-123456789")
    name = "hash_create_user"
    r = client.post("/api/users", json={"username": name, "role": "viewer"}, headers=ADMIN)
    assert r.status_code == 201, r.text
    plaintext = r.json()["token"]
    assert len(plaintext) >= 32

    db = SessionLocal()
    try:
        user = db.query(User).filter(User.username == name).first()
        assert user is not None
        assert user.token == ""
        assert is_hash(user.token_hash)
        assert verify_secret(plaintext, user.token_hash)
    finally:
        db.close()

    login = client.post("/api/users/token", json={"username": name, "token": plaintext})
    assert login.status_code == 200, login.text


def test_legacy_plaintext_token_upgrades_on_login(monkeypatch):
    monkeypatch.setenv("AUTH_JWT_SECRET", "test-secret-for-legacy-12345678")
    name = "legacy_plaintext_user"
    _user(name, role="viewer", token="legacy-secret")

    r = client.post("/api/users/token", json={"username": name, "token": "legacy-secret"})
    assert r.status_code == 200, r.text

    db = SessionLocal()
    try:
        user = db.query(User).filter(User.username == name).first()
        assert user.token == ""
        assert is_hash(user.token_hash)
        assert verify_secret("legacy-secret", user.token_hash)
        assert not verify_secret("wrong", user.token_hash)
    finally:
        db.close()


def test_rotate_token_invalidates_old_secret(monkeypatch):
    monkeypatch.setenv("AUTH_JWT_SECRET", "test-secret-for-rotate-1234567")
    name = "rotate_secret_user"
    _user(name, role="viewer", token="old-secret")

    login = client.post("/api/users/token", json={"username": name, "token": "old-secret"})
    assert login.status_code == 200, login.text

    db = SessionLocal()
    try:
        uid = db.query(User).filter(User.username == name).first().id
    finally:
        db.close()

    rotated = client.post(f"/api/users/{uid}/rotate-token", headers=ADMIN)
    assert rotated.status_code == 200, rotated.text
    new_secret = rotated.json()["token"]

    old_login = client.post("/api/users/token", json={"username": name, "token": "old-secret"})
    assert old_login.status_code == 401, old_login.text
    new_login = client.post("/api/users/token", json={"username": name, "token": new_secret})
    assert new_login.status_code == 200, new_login.text


def test_login_failure_lockout(monkeypatch):
    monkeypatch.setenv("AUTH_JWT_SECRET", "test-secret-for-lockout-123456")
    monkeypatch.setenv("GEOLOG_AUTH_FAILURE_LIMIT", "2")
    monkeypatch.setenv("GEOLOG_AUTH_LOCKOUT_SECONDS", "60")
    monkeypatch.setenv("GEOLOG_AUTH_IP_LIMIT", "100")
    name = "lockout_user"
    _user(name, role="viewer", token="correct-secret")

    first = client.post("/api/users/token", json={"username": name, "token": "wrong"})
    assert first.status_code == 401, first.text
    second = client.post("/api/users/token", json={"username": name, "token": "wrong"})
    assert second.status_code == 429, second.text
    assert int(second.headers["Retry-After"]) > 0

    blocked = client.post("/api/users/token", json={"username": name, "token": "correct-secret"})
    assert blocked.status_code == 429, blocked.text

    from backend.ratelimit import clear_login_failures

    clear_login_failures(name)
    allowed = client.post("/api/users/token", json={"username": name, "token": "correct-secret"})
    assert allowed.status_code == 200, allowed.text


def test_declared_oversized_upload_is_rejected_before_route(monkeypatch):
    monkeypatch.setenv("GEOLOG_MAX_UPLOAD_BYTES", "1024")
    db = SessionLocal()
    try:
        wid = db.query(Well.id).order_by(Well.id.asc()).first()[0]
    finally:
        db.close()

    r = client.post(
        f"/api/wells/{wid}/upload-las",
        files={"file": ("big.las", b"x" * 4096, "text/plain")},
        headers=INTERPRETER,
    )
    assert r.status_code == 413, r.text


def test_declared_oversized_json_is_rejected(monkeypatch):
    monkeypatch.setenv("GEOLOG_MAX_BODY_BYTES", "128")
    r = client.post(
        "/api/wells/1/sensitivity",
        content=b"{" + b'"padding":"' + b"x" * 256 + b'"}',
        headers={**INTERPRETER, "Content-Type": "application/json"},
    )
    assert r.status_code == 413, r.text


def test_streamed_upload_without_content_length_is_capped():
    import asyncio

    from fastapi import HTTPException

    from backend.uploads import read_upload

    class Chunked:
        size = None

        def __init__(self, payload: bytes):
            self.payload = payload
            self.offset = 0

        async def read(self, size: int = -1):
            if self.offset >= len(self.payload):
                return b""
            end = len(self.payload) if size < 0 else self.offset + size
            chunk = self.payload[self.offset:end]
            self.offset = end
            return chunk

    async def _run():
        await read_upload(Chunked(b"x" * 4096), max_bytes=1024)

    try:
        asyncio.run(_run())
    except HTTPException as exc:
        assert exc.status_code == 413
    else:
        raise AssertionError("chunked upload was not capped")
