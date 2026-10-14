"""Demo seeding.

`backend/seed.py` used to run at import time, create its schema with
`Base.metadata.create_all()` (which never adds columns to an existing table) and
put `backend/` on `sys.path` (which gives the models a second SQLAlchemy Base).
It also printed emoji, which aborted under the Windows console codepage. None of
it was covered, because a module that does its work on import cannot be tested.
"""

from __future__ import annotations

import pathlib
import subprocess
import sys

import pytest

REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]


def test_seed_module_imports_without_side_effects():
    """Importing must not touch the database."""
    import backend.seed as seed_module

    assert hasattr(seed_module, "seed")
    assert hasattr(seed_module, "main")
    assert callable(seed_module.find_demo_las)


def test_demo_las_is_found():
    from backend.seed import find_demo_las

    found = find_demo_las()
    assert found is not None, "no demo LAS file in the expected locations"
    assert pathlib.Path(found).is_file()


def test_seed_creates_the_demo_project():
    """Runs against the throwaway database the session fixture created."""
    from backend.database import SessionLocal
    from backend.models import CurveData, FormationTop, LogRun, Project, Well
    from backend.seed import PROJECT_NAME, seed

    db = SessionLocal()
    try:
        # A previous test in the session may have seeded already; that is fine.
        result = seed(db)
        if result.get("created"):
            assert result["curves"] > 0
            assert result["points"] > 0
            assert result["tops"] > 0
        else:
            assert result["reason"] == "already seeded"

        project = db.query(Project).filter(Project.name == PROJECT_NAME).first()
        assert project is not None, "the demo project was not created"

        well = db.query(Well).filter(Well.project_id == project.id).first()
        assert well is not None

        run = db.query(LogRun).filter(LogRun.well_id == well.id).first()
        assert run is not None
        assert run.num_points > 0

        curves = db.query(CurveData).filter(CurveData.log_run_id == run.id).count()
        assert curves > 0

        tops = db.query(FormationTop).filter(FormationTop.well_id == well.id).count()
        assert tops == len(__import__("backend.seed", fromlist=["x"]).STRATIGRAPHY)
    finally:
        db.close()


def test_seeding_twice_does_not_duplicate():
    from backend.database import SessionLocal
    from backend.models import Project
    from backend.seed import PROJECT_NAME, seed

    db = SessionLocal()
    try:
        seed(db)
        first = db.query(Project).filter(Project.name == PROJECT_NAME).count()
        seed(db)
        second = db.query(Project).filter(Project.name == PROJECT_NAME).count()
    finally:
        db.close()

    assert first == second == 1, "seeding twice created a second demo project"


def test_script_runs_as_a_module(tmp_path):
    """`python -m backend.seed` must work from a clean database."""
    db = tmp_path / "seedcli.db"
    env = dict(__import__("os").environ)
    env["GEOLOG_DB_PATH"] = str(db)
    env["GEOLOG_ENV"] = "test"
    env["PYTHONPATH"] = str(REPO_ROOT)

    proc = subprocess.run(
        [sys.executable, "-m", "backend.seed"],
        cwd=str(REPO_ROOT), env=env, capture_output=True, text=True, timeout=180,
    )
    assert proc.returncode == 0, f"seed script failed:\n{proc.stderr}"

    # Output must be ASCII-encodable: emoji used to abort under cp1252.
    proc.stdout.encode("ascii")
    assert "Done." in proc.stdout

    # And the schema must have been created by Alembic, not create_all.
    import sqlite3

    conn = sqlite3.connect(db)
    try:
        tables = {r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        )}
        assert "alembic_version" in tables, "seed did not migrate the database"
        wells = conn.execute("SELECT COUNT(*) FROM wells").fetchone()[0]
        assert wells >= 1
    finally:
        conn.close()
