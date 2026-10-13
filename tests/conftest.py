"""Test isolation.

Every run gets its own throwaway SQLite file, seeded once per session. Without
this the suite reads and writes backend/geolog.db, so results depend on whatever
is already on disk and tests leak state into each other (one of them deletes
project 1).
"""

from __future__ import annotations

import os
import pathlib
import shutil
import sys
import tempfile

ROOT = pathlib.Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# Must be set before backend.database / backend.main are imported.
_TMP_DIR = tempfile.mkdtemp(prefix="geolog-test-")
os.environ["GEOLOG_DB_PATH"] = str(pathlib.Path(_TMP_DIR) / "test.db")
# Snapshots/locks are files on disk, not rows: without this the suite leaves a
# well locked for the next run.
os.environ["GEOLOG_ARTIFACT_DIR"] = str(pathlib.Path(_TMP_DIR) / "artifacts")
os.environ.setdefault("GEOLOG_ENV", "test")

import pytest  # noqa: E402


@pytest.fixture(scope="session", autouse=True)
def seeded_database():
    """Create the schema and seed demo data once for the whole session."""
    from backend.main import SessionLocal, seed_demo_data

    db = SessionLocal()
    try:
        seed_demo_data(db)
    finally:
        db.close()

    yield

    from backend.database import engine

    engine.dispose()
    shutil.rmtree(_TMP_DIR, ignore_errors=True)
