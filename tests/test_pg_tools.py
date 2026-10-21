"""SQLite->SQLite exercise of the Postgres copy/verify/rollback path."""

from __future__ import annotations

import numpy as np
from sqlalchemy import select
from sqlalchemy.orm import sessionmaker

from backend.models import Base, CurveData, LogRun, Project, Well
from backend.pg_tools import copy_database, rollback, verify_database, _engine
from backend.database import DATABASE_DIALECT


def _make_db(path, with_data=True):
    url = f"sqlite:///{path}"
    engine = _engine(url)
    Base.metadata.create_all(engine)
    if with_data:
        Session = sessionmaker(bind=engine)
        db = Session()
        project = Project(name="P")
        db.add(project)
        db.flush()
        well = Well(project_id=project.id, name="W", uwi="U")
        db.add(well)
        db.flush()
        run = LogRun(well_id=well.id, run_number=1, filename="w.las", num_points=3)
        db.add(run)
        db.flush()
        arr = np.array([1.0, 2.0, 3.0])
        db.add(CurveData(log_run_id=run.id, mnemonic="GR", num_points=3, data_binary=arr.tobytes()))
        db.commit()
        db.close()
    return url


def test_copy_verify_rollback(tmp_path):
    assert DATABASE_DIALECT == "sqlite"
    src = _make_db(tmp_path / "src.db")
    dst = f"sqlite:///{tmp_path / 'dst.db'}"
    report = copy_database(src, dst)
    assert report["ok"] is True
    assert report["copied"]["wells"] == 1
    assert verify_database(src, dst)["ok"] is True

    target = _engine(dst)
    Session = sessionmaker(bind=target)
    db = Session()
    try:
        raw = db.execute(select(CurveData.data_binary)).scalar_one()
        assert np.frombuffer(raw, dtype=np.float64).tolist() == [1.0, 2.0, 3.0]
    finally:
        db.close()

    try:
        copy_database(src, dst)
        raise AssertionError("copy into a non-empty target must fail")
    except RuntimeError:
        pass

    rollback(dst, confirm=True)
    with target.connect() as conn:
        assert conn.execute(select(Well)).all() == []
