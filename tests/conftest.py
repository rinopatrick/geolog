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


@pytest.fixture
def make_well():
    """Factory for a well whose curves are exactly the supplied values.

    Returns the new well id. All curves must be the same length.
    """
    import numpy as np

    from backend.main import CurveData, LogRun, Project, SessionLocal, Well

    created: list[int] = []

    def _make(name: str, curves: dict) -> int:
        db = SessionLocal()
        try:
            project = db.query(Project).order_by(Project.id.asc()).first()
            assert project is not None, "conftest should have seeded a project"

            lengths = {len(v) for v in curves.values()}
            assert len(lengths) == 1, f"all curves must be the same length, got {lengths}"
            n = lengths.pop()

            well = Well(project_id=project.id, name=name, depth_unit="FT")
            db.add(well)
            db.flush()

            run = LogRun(
                well_id=well.id, run_number=1, filename=f"{name}.las",
                start_depth=1000.0, stop_depth=1000.0 + n, step=1.0,
                null_value=-999.25, num_points=n,
            )
            db.add(run)
            db.flush()

            for mnemonic, values in curves.items():
                arr = np.asarray(values, dtype=np.float64)
                valid = arr[~np.isnan(arr)]
                db.add(CurveData(
                    log_run_id=run.id, mnemonic=mnemonic, unit="",
                    num_points=n,
                    min_value=float(np.min(valid)) if len(valid) else None,
                    max_value=float(np.max(valid)) if len(valid) else None,
                    data_binary=arr.tobytes(),
                ))
            db.commit()
            created.append(well.id)
            return well.id
        finally:
            db.close()

    yield _make

    if created:
        db = SessionLocal()
        try:
            for wid in created:
                well = db.query(Well).filter(Well.id == wid).first()
                if well is not None:
                    db.delete(well)
            db.commit()
        finally:
            db.close()


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


@pytest.fixture(autouse=True)
def reset_well_locks():
    """Clear interpretation locks before each test.

    Locks are global file state, not rows. A test that approves a snapshot locks
    its well, and every later test that writes to that well then correctly gets
    423 Locked — so tests passed or failed depending on execution order. Found
    via tests/test_router_integrity.py, which borrowed the first seeded well.

    Tests that exercise locking do so within themselves, so starting from no
    locks is the correct baseline rather than a convenience.
    """
    lock_file = pathlib.Path(_TMP_DIR) / "artifacts" / "locks.json"
    lock_file.unlink(missing_ok=True)
    yield
    lock_file.unlink(missing_ok=True)
