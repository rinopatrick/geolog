"""Auth-mode and CORS defaults.

Header auth takes the caller's role from a request header, so it must not be the
default outside a trusted development environment. CORS must not be a wildcard
with credentials enabled.
"""

from __future__ import annotations

import pytest

from backend.security import AuthConfig, DEV_ENVIRONMENTS


def _clear_auth_env(monkeypatch):
    for key in ("AUTH_MODE", "GEOLOG_ENV", "ENV"):
        monkeypatch.delenv(key, raising=False)


def test_header_auth_is_allowed_in_dev_by_default(monkeypatch):
    _clear_auth_env(monkeypatch)
    assert AuthConfig.from_env().mode == "header"


@pytest.mark.parametrize("env", sorted(DEV_ENVIRONMENTS))
def test_header_auth_is_allowed_in_dev_environments(monkeypatch, env):
    _clear_auth_env(monkeypatch)
    monkeypatch.setenv("GEOLOG_ENV", env)
    assert AuthConfig.from_env().mode == "header"


@pytest.mark.parametrize("env", ["prod", "production", "staging"])
def test_auth_defaults_to_jwt_outside_dev(monkeypatch, env):
    _clear_auth_env(monkeypatch)
    monkeypatch.setenv("GEOLOG_ENV", env)
    assert AuthConfig.from_env().mode == "jwt"


@pytest.mark.parametrize("env", ["prod", "production", "staging"])
def test_header_auth_is_refused_outside_dev(monkeypatch, env):
    _clear_auth_env(monkeypatch)
    monkeypatch.setenv("GEOLOG_ENV", env)
    monkeypatch.setenv("AUTH_MODE", "header")
    with pytest.raises(RuntimeError, match="AUTH_MODE=header"):
        AuthConfig.from_env()


def test_jwt_mode_is_accepted_outside_dev(monkeypatch):
    _clear_auth_env(monkeypatch)
    monkeypatch.setenv("GEOLOG_ENV", "prod")
    monkeypatch.setenv("AUTH_MODE", "jwt")
    monkeypatch.setenv("AUTH_JWT_SECRET", "s3cret")
    assert AuthConfig.from_env().mode == "jwt"


def test_unknown_auth_mode_is_rejected(monkeypatch):
    _clear_auth_env(monkeypatch)
    monkeypatch.setenv("AUTH_MODE", "none")
    with pytest.raises(RuntimeError, match="unsupported AUTH_MODE"):
        AuthConfig.from_env()


def test_cors_is_disabled_by_default():
    """The bundled frontend is same-origin, so no CORS middleware is installed."""
    from starlette.middleware.cors import CORSMiddleware

    from backend.main import app

    assert not any(m.cls is CORSMiddleware for m in app.user_middleware), (
        "wildcard CORS must not be enabled by default"
    )
