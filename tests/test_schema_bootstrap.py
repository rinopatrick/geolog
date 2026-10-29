"""Startup migration policy: dev migrates, production verifies and fails fast."""

from __future__ import annotations

import pytest

from backend import schema


def _patch(monkeypatch, *, migrate_calls, problems, pending=None):
    monkeypatch.setattr(schema, "run_migrations", lambda: migrate_calls.append("migrate"))
    monkeypatch.setattr(schema, "verify_schema", lambda: list(problems))
    monkeypatch.setattr(schema, "check_for_pending_migrations", lambda: list(pending or []))
    monkeypatch.setattr(schema, "current_revision", lambda: "test-rev")


def test_dev_migrates_by_default(monkeypatch):
    calls: list[str] = []
    _patch(monkeypatch, migrate_calls=calls, problems=[])
    monkeypatch.setenv("GEOLOG_ENV", "dev")
    monkeypatch.delenv("GEOLOG_RUN_MIGRATIONS_ON_STARTUP", raising=False)
    schema.bootstrap_schema()
    assert calls == ["migrate"]


def test_production_does_not_migrate_by_default(monkeypatch):
    calls: list[str] = []
    _patch(monkeypatch, migrate_calls=calls, problems=[])
    monkeypatch.setenv("GEOLOG_ENV", "prod")
    monkeypatch.delenv("GEOLOG_RUN_MIGRATIONS_ON_STARTUP", raising=False)
    schema.bootstrap_schema()
    assert calls == []


def test_production_can_opt_in_to_startup_migration(monkeypatch):
    calls: list[str] = []
    _patch(monkeypatch, migrate_calls=calls, problems=[])
    monkeypatch.setenv("GEOLOG_ENV", "prod")
    monkeypatch.setenv("GEOLOG_RUN_MIGRATIONS_ON_STARTUP", "true")
    schema.bootstrap_schema()
    assert calls == ["migrate"]


def test_production_fails_fast_on_schema_mismatch(monkeypatch):
    calls: list[str] = []
    _patch(monkeypatch, migrate_calls=calls, problems=["column users.token_hash missing"])
    monkeypatch.setenv("GEOLOG_ENV", "prod")
    monkeypatch.delenv("GEOLOG_FAIL_ON_SCHEMA_MISMATCH", raising=False)
    with pytest.raises(RuntimeError, match="does not match the models"):
        schema.bootstrap_schema()


def test_dev_only_warns_on_schema_mismatch(monkeypatch):
    calls: list[str] = []
    _patch(monkeypatch, migrate_calls=calls, problems=["column x missing"])
    monkeypatch.setenv("GEOLOG_ENV", "test")
    monkeypatch.delenv("GEOLOG_FAIL_ON_SCHEMA_MISMATCH", raising=False)
    schema.bootstrap_schema()
    assert calls == ["migrate"]


def test_production_mismatch_can_be_downgraded_to_warning(monkeypatch):
    calls: list[str] = []
    _patch(monkeypatch, migrate_calls=calls, problems=["column x missing"])
    monkeypatch.setenv("GEOLOG_ENV", "prod")
    monkeypatch.setenv("GEOLOG_FAIL_ON_SCHEMA_MISMATCH", "false")
    schema.bootstrap_schema()
    assert calls == []
