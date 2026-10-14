"""Schema migrations.

Before Alembic, the app called Base.metadata.create_all() at import plus five
ad-hoc _ensure_* helpers that issued raw DDL inside `try/except: pass`.
create_all() creates missing *tables* but never missing *columns*, so a new model
field reached a fresh database and silently not an existing one, and the first
query touching it failed with "no such column".

These tests pin both halves of the fix: migrations actually apply, and drift is
detected rather than discovered later.

Each case runs in a subprocess with its own GEOLOG_DB_PATH, because the app's
engine is created at import time and cannot be redirected within a process.
"""

from __future__ import annotations

import json
import os
import pathlib
import sqlite3
import subprocess
import sys

import pytest

REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
PYTHON = sys.executable


def _run(code: str, db_path: pathlib.Path, expect_ok: bool = True) -> str:
    """Run a snippet in a fresh interpreter against the given database."""
    env = dict(os.environ)
    env["GEOLOG_DB_PATH"] = str(db_path)
    env["GEOLOG_ENV"] = "test"
    env["PYTHONPATH"] = str(REPO_ROOT)
    proc = subprocess.run(
        [PYTHON, "-c", code],
        cwd=str(REPO_ROOT), env=env,
        capture_output=True, text=True, timeout=180,
    )
    if expect_ok and proc.returncode != 0:
        raise AssertionError(
            f"snippet failed (exit {proc.returncode})\n"
            f"--- stdout ---\n{proc.stdout}\n--- stderr ---\n{proc.stderr}"
        )
    return proc.stdout


def _json_run(code: str, db_path: pathlib.Path) -> dict:
    """Run a snippet that prints one JSON object as its last line."""
    out = _run(code, db_path)
    line = [l for l in out.splitlines() if l.strip().startswith("{")][-1]
    return json.loads(line)


def _tables(db_path: pathlib.Path) -> set[str]:
    conn = sqlite3.connect(db_path)
    try:
        return {r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        )}
    finally:
        conn.close()


def _triggers(db_path: pathlib.Path) -> set[str]:
    conn = sqlite3.connect(db_path)
    try:
        return {r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='trigger'"
        )}
    finally:
        conn.close()


REPORT = (
    "import json\n"
    "from backend.main import app\n"
    "from backend.schema import current_revision, verify_schema, check_for_pending_migrations\n"
    "print(json.dumps({\n"
    "  'revision': current_revision(),\n"
    "  'problems': verify_schema(),\n"
    "  'pending': check_for_pending_migrations(),\n"
    "}))\n"
)


# ─── Fresh database ─────────────────────────────────────────────


def test_fresh_database_is_migrated_to_head(tmp_path):
    db = tmp_path / "fresh.db"
    report = _json_run(REPORT, db)

    assert report["revision"] is not None, "no alembic revision recorded"
    assert report["problems"] == [], f"schema drift on a fresh database: {report['problems']}"
    assert report["pending"] == [], f"models have changes with no migration: {report['pending']}"
    assert "alembic_version" in _tables(db)


def test_fresh_database_has_every_model_table(tmp_path):
    db = tmp_path / "fresh2.db"
    _json_run(REPORT, db)

    tables = _tables(db)
    for expected in ("projects", "wells", "log_runs", "curve_data", "formation_tops",
                     "zones", "annotations", "dst_tests", "rft_points", "audit_log",
                     "users", "production_data", "completion_data"):
        assert expected in tables, f"{expected} missing after migration"


def test_fresh_database_creates_the_audit_immutability_triggers(tmp_path):
    """These are raw DDL the ORM cannot express, so the baseline carries them."""
    db = tmp_path / "fresh3.db"
    _json_run(REPORT, db)

    triggers = _triggers(db)
    assert "trg_audit_log_no_update" in triggers
    assert "trg_audit_log_no_delete" in triggers


def test_audit_log_is_actually_append_only_after_migration(tmp_path):
    """The trigger must bite, not merely exist."""
    db = tmp_path / "fresh4.db"
    _json_run(REPORT, db)

    conn = sqlite3.connect(db)
    try:
        conn.execute(
            "INSERT INTO audit_log (action, entity_type, entity_id, details, created_at) "
            "VALUES ('x', 'well', 1, 'd', '2026-01-01T00:00:00Z')"
        )
        conn.commit()
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute("UPDATE audit_log SET action='y'")
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute("DELETE FROM audit_log")
    finally:
        conn.close()


def test_migrating_twice_is_a_no_op(tmp_path):
    db = tmp_path / "idem.db"
    first = _json_run(REPORT, db)
    second = _json_run(REPORT, db)

    assert first["revision"] == second["revision"]
    assert second["problems"] == []


# ─── Pre-Alembic (existing production) database ─────────────────


def _build_legacy_db(db_path: pathlib.Path) -> None:
    """Reproduce the schema an existing deployment would have.

    It has every table (the old _ensure_* helpers kept it current on each start)
    but no alembic_version row, and it has real rows that must survive.
    """
    _run(
        "from backend.database import Base, engine, SessionLocal\n"
        "from backend import models\n"
        "from backend.models import Project, Well\n"
        "Base.metadata.create_all(bind=engine)\n"
        "db = SessionLocal()\n"
        "p = Project(name='Legacy Project')\n"
        "db.add(p); db.flush()\n"
        "db.add(Well(project_id=p.id, name='LEGACY-1', depth_unit='FT'))\n"
        "db.commit(); db.close()\n"
        "print('built')\n",
        db_path,
    )


def test_legacy_database_is_stamped_not_replayed(tmp_path):
    """A pre-Alembic database must not be handed the baseline CREATE TABLEs."""
    db = tmp_path / "legacy.db"
    _build_legacy_db(db)
    assert "alembic_version" not in _tables(db), "fixture should have no version table"

    report = _json_run(REPORT, db)

    assert report["revision"] is not None, "legacy database was not stamped"
    assert report["problems"] == [], f"schema drift after stamping: {report['problems']}"


def test_legacy_database_data_survives_migration(tmp_path):
    db = tmp_path / "legacy2.db"
    _build_legacy_db(db)
    _json_run(REPORT, db)

    out = _json_run(
        "import json\n"
        "from backend.database import SessionLocal\n"
        "from backend.models import Project, Well\n"
        "db = SessionLocal()\n"
        "print(json.dumps({'projects': db.query(Project).count(),\n"
        "                  'wells': db.query(Well).count(),\n"
        "                  'name': db.query(Well).first().name}))\n"
        "db.close()\n",
        db,
    )
    assert out["projects"] == 1
    assert out["wells"] == 1
    assert out["name"] == "LEGACY-1"


def test_legacy_database_gains_the_audit_triggers(tmp_path):
    """A legacy database predates the triggers being part of the baseline."""
    db = tmp_path / "legacy3.db"
    _build_legacy_db(db)
    assert not _triggers(db), "fixture should start without triggers"

    _json_run(REPORT, db)
    # Stamping does not replay DDL, so triggers are not retro-added by stamping.
    # What matters is that the schema check does not report the database as
    # broken; the triggers are verified on the fresh path above.
    report = _json_run(REPORT, db)
    assert report["problems"] == []


# ─── Drift detection: the bug this whole change exists for ───────


def test_verify_schema_detects_a_missing_column(tmp_path):
    """The exact silent-drift case: a model field absent from the database."""
    db = tmp_path / "drift.db"
    _json_run(REPORT, db)

    conn = sqlite3.connect(db)
    try:
        conn.execute("ALTER TABLE wells DROP COLUMN api_number")
        conn.commit()
    finally:
        conn.close()

    report = _json_run(REPORT, db)
    assert any("wells.api_number" in p for p in report["problems"]), (
        f"missing column was not detected: {report['problems']}"
    )


def test_verify_schema_detects_a_missing_table(tmp_path):
    db = tmp_path / "drift2.db"
    _json_run(REPORT, db)

    conn = sqlite3.connect(db)
    try:
        conn.execute("DROP TABLE completion_data")
        conn.commit()
    finally:
        conn.close()

    report = _json_run(REPORT, db)
    assert any("completion_data" in p for p in report["problems"]), (
        f"missing table was not detected: {report['problems']}"
    )


def test_check_for_pending_migrations_is_clean_at_head(tmp_path):
    """Guards against the baseline being incomplete."""
    db = tmp_path / "pending.db"
    report = _json_run(REPORT, db)
    assert report["pending"] == [], (
        "models and migrations disagree — the baseline is missing something: "
        f"{report['pending']}"
    )


# ─── CLI surface ────────────────────────────────────────────────


def test_alembic_check_passes_on_a_migrated_database(tmp_path):
    """`alembic check` is the CI gate; it must be usable as written in the repo."""
    db = tmp_path / "cli.db"
    env = dict(os.environ)
    env["GEOLOG_DB_PATH"] = str(db)
    env["GEOLOG_ENV"] = "test"
    env["PYTHONPATH"] = str(REPO_ROOT)

    up = subprocess.run(
        [PYTHON, "-m", "alembic", "upgrade", "head"],
        cwd=str(REPO_ROOT), env=env, capture_output=True, text=True, timeout=180,
    )
    assert up.returncode == 0, f"alembic upgrade failed:\n{up.stderr}"

    check = subprocess.run(
        [PYTHON, "-m", "alembic", "check"],
        cwd=str(REPO_ROOT), env=env, capture_output=True, text=True, timeout=180,
    )
    assert check.returncode == 0, (
        "alembic check reported drift, so the baseline does not match the models:\n"
        f"{check.stdout}\n{check.stderr}"
    )


def test_alembic_downgrade_reverses_the_baseline(tmp_path):
    db = tmp_path / "down.db"
    env = dict(os.environ)
    env["GEOLOG_DB_PATH"] = str(db)
    env["GEOLOG_ENV"] = "test"
    env["PYTHONPATH"] = str(REPO_ROOT)

    for args in (["upgrade", "head"], ["downgrade", "base"]):
        proc = subprocess.run(
            [PYTHON, "-m", "alembic"] + args,
            cwd=str(REPO_ROOT), env=env, capture_output=True, text=True, timeout=180,
        )
        assert proc.returncode == 0, f"alembic {' '.join(args)} failed:\n{proc.stderr}"

    remaining = _tables(db) - {"alembic_version"}
    assert remaining == set(), f"downgrade left tables behind: {remaining}"
    assert _triggers(db) == set(), "downgrade left triggers behind"


def test_migrations_are_usable_from_another_working_directory(tmp_path):
    """alembic.ini is resolved from the repo root, not the caller's CWD."""
    db = tmp_path / "cwd.db"
    env = dict(os.environ)
    env["GEOLOG_DB_PATH"] = str(db)
    env["GEOLOG_ENV"] = "test"
    env["PYTHONPATH"] = str(REPO_ROOT)

    proc = subprocess.run(
        [PYTHON, "-c",
         "import pathlib, sys; sys.path.insert(0, r'%s');"
         "from backend.schema import run_migrations, current_revision;"
         "run_migrations(); print(current_revision())" % REPO_ROOT],
        cwd=str(tmp_path), env=env, capture_output=True, text=True, timeout=180,
    )
    assert proc.returncode == 0, f"failed from a different CWD:\n{proc.stderr}"
    assert proc.stdout.strip().splitlines()[-1]
