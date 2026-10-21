"""Data semantics: aliases, units, depth control points and TVD."""

from __future__ import annotations

import numpy as np
import pytest
from fastapi.testclient import TestClient

from backend.main import SessionLocal, app
from backend.models import (
    CurveAlias,
    CurveData,
    DepthControlPoint,
    DeviationSurvey,
    LogRun,
    LogRunDepthShift,
    Well,
)
from backend.semantics import apply_run_semantics, convert_array, piecewise_linear

client = TestClient(app)
INTERPRETER = {"X-User-Role": "interpreter"}
ADMIN = {"X-User-Role": "admin"}

def _well_and_run(wid: int):
    db = SessionLocal()
    try:
        well = db.query(Well).filter(Well.id == wid).first()
        lr = db.query(LogRun).filter(LogRun.well_id == wid).first()
        return well, lr
    finally:
        db.close()

def test_piecewise_linear_interpolates_and_extrapolates():
    x = np.array([0.0, 10.0, 20.0])
    y = np.array([0.0, 20.0, 50.0])
    out = piecewise_linear(np.array([-5.0, 5.0, 15.0, 25.0]), x, y)
    assert np.allclose(out, [-10.0, 10.0, 35.0, 65.0])

def test_convert_array_families():
    assert np.allclose(convert_array(np.array([2.65]), "G/C3", "kg/m3")[0], [2650.0])
    assert np.allclose(convert_array(np.array([100.0]), "US/F", "us/m")[0], [328.0839895])
    assert np.allclose(convert_array(np.array([50.0]), "%", "v/v")[0], [0.5])
    assert np.allclose(convert_array(np.array([32.0]), "degF", "degC")[0], [0.0])
    out, warning = convert_array(np.array([1.0]), "mystery", "ft")
    assert np.allclose(out, [1.0]) and warning

def test_semantics_alias_unit_depth_and_tvd(make_well):
    wid = make_well("SEM", {
        "DEPT": np.array([1000.0, 1001.0, 1002.0, 1003.0, 1004.0]),
        "RHO": np.array([2.65, 2.66, 2.67, 2.68, 2.69]),
    })
    db = SessionLocal()
    try:
        well = db.query(Well).filter(Well.id == wid).first()
        lr = db.query(LogRun).filter(LogRun.well_id == wid).first()
        well.unit_system = "si"
        dept = db.query(CurveData).filter_by(log_run_id=lr.id, mnemonic="DEPT").first()
        rho = db.query(CurveData).filter_by(log_run_id=lr.id, mnemonic="RHO").first()
        dept.unit = "FT"
        rho.unit = "G/C3"
        db.add(CurveAlias(well_id=wid, original_mnemonic="RHO", alias_mnemonic="RHOB"))
        db.add_all([
            DepthControlPoint(log_run_id=lr.id, md=1000.0, corrected_depth=1000.0, sort_order=0),
            DepthControlPoint(log_run_id=lr.id, md=1002.0, corrected_depth=1003.0, sort_order=1),
            DepthControlPoint(log_run_id=lr.id, md=1004.0, corrected_depth=1006.0, sort_order=2),
            DeviationSurvey(well_id=wid, md=1000.0, inc=0.0, azi=0.0, tvd=1000.0),
            DeviationSurvey(well_id=wid, md=1010.0, inc=0.0, azi=0.0, tvd=1010.0),
        ])
        db.commit()
        result = apply_run_semantics(db, lr, ["RHOB"])
    finally:
        db.close()

    # Corrected depth is converted FT -> m.
    assert np.allclose(result["depth"], [304.8, 304.8 + 1.5 * 0.3048, 304.8 + 3 * 0.3048, 304.8 + 4.5 * 0.3048, 304.8 + 6 * 0.3048])
    assert result["tvd"].shape == result["depth"].shape
    assert np.allclose(result["tvd"], result["depth"])
    assert "RHOB" in result["curves"]
    assert np.allclose(result["curves"]["RHOB"], [2650.0, 2660.0, 2670.0, 2680.0, 2690.0])
    assert result["metadata"]["version"] == "data-semantics-v1"
    assert result["metadata"]["depth_source"] == "control_points"
    assert len(result["metadata"]["input_hash"]) == 64
    assert any(a["raw"] == "RHO" and a["name"] == "RHOB" for a in result["metadata"]["aliases"])

def test_alias_collision_keeps_raw_names(make_well):
    wid = make_well("CLASH", {
        "DEPT": np.array([1000.0, 1001.0]),
        "A": np.array([1.0, 2.0]),
        "B": np.array([3.0, 4.0]),
    })
    db = SessionLocal()
    try:
        lr = db.query(LogRun).filter(LogRun.well_id == wid).first()
        db.add_all([
            CurveAlias(well_id=wid, original_mnemonic="A", alias_mnemonic="GR"),
            CurveAlias(well_id=wid, original_mnemonic="B", alias_mnemonic="GR"),
        ])
        db.commit()
        result = apply_run_semantics(db, lr)
    finally:
        db.close()
    assert "A" in result["curves"] and "B" in result["curves"]
    assert "GR" not in result["curves"]
    assert any("collision" in w for w in result["metadata"]["warnings"])

def test_legacy_shift_maps_to_points(make_well):
    wid = make_well("LEGACY", {
        "DEPT": np.array([1000.0, 1001.0, 1002.0]),
        "GR": np.array([10.0, 20.0, 30.0]),
    })
    db = SessionLocal()
    try:
        lr = db.query(LogRun).filter(LogRun.well_id == wid).first()
        db.add(LogRunDepthShift(log_run_id=lr.id, shift=5.0, stretch=2.0))
        db.commit()
        result = apply_run_semantics(db, lr, ["GR"])
    finally:
        db.close()
    assert result["metadata"]["depth_source"] == "legacy_shift"
    assert np.allclose(result["depth"], [1005.0, 1007.0, 1009.0])

def test_control_point_api_and_data_metadata(make_well):
    wid = make_well("CPAPI", {
        "DEPT": np.array([1000.0, 1001.0, 1002.0]),
        "GR": np.array([10.0, 20.0, 30.0]),
    })
    db = SessionLocal()
    try:
        lrid = db.query(LogRun).filter(LogRun.well_id == wid).first().id
    finally:
        db.close()

    r = client.put(
        f"/api/log-runs/{lrid}/depth-control-points",
        headers=INTERPRETER,
        json={"points": [
            {"md": 1000.0, "corrected_depth": 1000.0},
            {"md": 1002.0, "corrected_depth": 1003.0},
        ]},
    )
    assert r.status_code == 200, r.text
    r = client.get(f"/api/log-runs/{lrid}/depth-control-points")
    assert r.status_code == 200 and len(r.json()) == 2

    r = client.post(
        f"/api/log-runs/{lrid}/data",
        headers=INTERPRETER,
        json={"curve_mnemonics": ["GR"]},
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["semantics"]["version"] == "data-semantics-v1"
    assert data["semantics"]["depth_source"] == "control_points"
    assert np.allclose(data["DEPTH"], [1000.0, 1001.5, 1003.0])

    bad = client.put(
        f"/api/log-runs/{lrid}/depth-control-points",
        headers=INTERPRETER,
        json={"points": [{"md": 1000, "corrected_depth": 1}]},
    )
    assert bad.status_code == 400

def test_well_unit_system_update(make_well):
    wid = make_well("UNIT", {"DEPT": [1000.0], "GR": [10.0]})
    r = client.put(f"/api/wells/{wid}", headers=INTERPRETER, json={"unit_system": "si"})
    assert r.status_code == 200, r.text
    assert r.json()["unit_system"] == "si"
    r = client.put(f"/api/wells/{wid}", headers=INTERPRETER, json={"unit_system": "bad"})
    assert r.status_code == 400

def test_decimated_data_uses_semantics(make_well):
    wid = make_well("DEC", {
        "DEPT": np.arange(1000.0, 1500.0),
        "GR": np.linspace(10.0, 100.0, 500),
    })
    db = SessionLocal()
    try:
        lr = db.query(LogRun).filter(LogRun.well_id == wid).first()
        db.add_all([
            DepthControlPoint(log_run_id=lr.id, md=1000.0, corrected_depth=1002.0, sort_order=0),
            DepthControlPoint(log_run_id=lr.id, md=1499.0, corrected_depth=1501.0, sort_order=1),
        ])
        db.commit()
        lrid = lr.id
    finally:
        db.close()

    r = client.get(f"/api/log-runs/{lrid}/data-decimated?max_points=200", headers=INTERPRETER)
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["semantics"]["depth_source"] == "control_points"
    assert data["depth"][0] == 1002.0
    assert data["depth"][-1] == 1501.0
    assert "GR" in data["curves"]
    assert len(data["depth"]) <= 200
