"""compute-sw save=true persists SW/PHIE/VSH as curves (opt-in).

Default (no save flag) stays stateless: no CurveData rows added.
With save=true, SW/PHIE/VSH are stored on the same log run and readable via
GET /api/log-runs/{id}/curves. Re-running overwrites (one row per mnemonic).
"""

from __future__ import annotations

import numpy as np
from fastapi.testclient import TestClient

from backend.main import SessionLocal, app
from backend.models import CurveData, LogRun, Project, Well

client = TestClient(app)
HEADERS = {"X-User-Role": "interpreter"}

N = 10
DEPTH = [1000.0 + 0.5 * i for i in range(N)]
GR = [50.0 + i for i in range(N)]
RT = [20.0 - 0.5 * i for i in range(N)]
NPHI = [0.25 - 0.005 * i for i in range(N)]
RHOB = [2.2 + 0.005 * i for i in range(N)]


def _make_well_with_run() -> tuple[int, int]:
    db = SessionLocal()
    try:
        project = db.query(Project).order_by(Project.id.asc()).first()
        assert project is not None
        well = Well(project_id=project.id, name="sw-save-well", depth_unit="FT")
        db.add(well)
        db.flush()
        lr = LogRun(well_id=well.id, run_number=1, filename="sw-save-well.las",
                    start_depth=DEPTH[0], stop_depth=DEPTH[-1], step=0.5,
                    null_value=-999.25, num_points=N)
        db.add(lr)
        db.flush()
        for mnemonic, vals in (("DEPT", DEPTH), ("GR", GR), ("RT", RT),
                               ("NPHI", NPHI), ("RHOB", RHOB)):
            arr = np.asarray(vals, dtype=np.float64)
            db.add(CurveData(log_run_id=lr.id, mnemonic=mnemonic,
                             unit="", description="",
                             num_points=N,
                             min_value=float(np.min(arr)),
                             max_value=float(np.max(arr)),
                             data_binary=arr.tobytes()))
        db.commit()
        return well.id, lr.id
    finally:
        db.close()


def _count_curves(lr_id: int) -> int:
    db = SessionLocal()
    try:
        return db.query(CurveData).filter(CurveData.log_run_id == lr_id).count()
    finally:
        db.close()


def test_compute_sw_default_is_stateless():
    wid, lr_id = _make_well_with_run()
    before = _count_curves(lr_id)
    r = client.post(f"/api/wells/{wid}/compute-sw", json={"model": "archie"},
                    headers=HEADERS)
    assert r.status_code == 200
    assert _count_curves(lr_id) == before


def test_compute_sw_save_persists_curves():
    wid, lr_id = _make_well_with_run()
    r = client.post(f"/api/wells/{wid}/compute-sw",
                    json={"model": "archie", "save": True}, headers=HEADERS)
    assert r.status_code == 200
    body = r.json()
    assert body["saved"]["log_run_id"] == lr_id
    assert set(body["saved"]["mnemonics"]) == {"SW", "PHIE", "VSH"}
    curves = client.get(f"/api/log-runs/{lr_id}/curves", headers=HEADERS).json()
    names = {c["mnemonic"] for c in curves} if isinstance(curves, list) \
        else set(curves.keys())
    assert {"SW", "PHIE", "VSH"} <= names


def test_compute_sw_save_is_idempotent():
    wid, lr_id = _make_well_with_run()
    payload = {"model": "archie", "save": True}
    assert client.post(f"/api/wells/{wid}/compute-sw", json=payload,
                       headers=HEADERS).status_code == 200
    assert client.post(f"/api/wells/{wid}/compute-sw", json=payload,
                       headers=HEADERS).status_code == 200
    db = SessionLocal()
    try:
        for mnemonic in ("SW", "PHIE", "VSH"):
            n = db.query(CurveData).filter(
                CurveData.log_run_id == lr_id,
                CurveData.mnemonic == mnemonic).count()
            assert n == 1, mnemonic
    finally:
        db.close()
