#!/usr/bin/env python
"""Run analytic and field-fixture physics checks without the API server."""

from __future__ import annotations

import json
import math
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.las_parser import LASParser
from backend.seismic import _link_geometry, ibm_to_ieee
from backend.saturation import saturation
from backend.synthetic import _depth_scale, _dt_scale, compute_synthetic_seismogram
from backend.velocity import time_to_depth_ms
from backend.volumetrics import grv_from_depth_grid

CHECKS = []


def check(name, function):
    try:
        value = function()
        CHECKS.append({"name": name, "ok": True, "value": value})
    except Exception as exc:  # noqa: BLE001 - this is a diagnostic script
        CHECKS.append({"name": name, "ok": False, "error": str(exc)})


def ibm_check():
    values = ibm_to_ieee(bytes.fromhex("41100000c1100000"))
    assert values[0] == 1.0 and values[1] == -1.0
    return values.tolist()


def depth_check():
    constant = time_to_depth_ms([2000], "constant", 2500, []).tolist()
    layers = time_to_depth_ms(
        [1500],
        "layers",
        None,
        [{"top_ms": 0, "velocity_m_s": 2000}, {"top_ms": 1000, "velocity_m_s": 3000}],
    ).tolist()
    assert constant == [2500.0] and layers == [1750.0]
    return {"constant": constant, "layers": layers}


def grv_check():
    top = [[2000.0, 2000.0], [2000.0, 2000.0]]
    base = [[2050.0, 2050.0], [2050.0, 2050.0]]
    result = grv_from_depth_grid(top, 2100, 25, 25, [0, 1], [0, 1], base_depth_grid=base)
    assert result["grv_m3"] == 125000.0
    return result


def fault_check():
    points = [
        {"inline": 0, "crossline": 0, "sample": 100},
        {"inline": 0, "crossline": 1, "sample": 100},
        {"inline": 1, "crossline": 0, "sample": 108},
        {"inline": 1, "crossline": 1, "sample": 108},
    ]
    geometry, _ = _link_geometry(
        points,
        [{"sample": 100, "throw": {"lag_ms": 8.0, "throw_ms": 8.0}}],
        2.0,
        25.0,
        25.0,
        velocity_m_s=2500.0,
    )
    expected = math.degrees(math.atan(10.0 / 25.0))
    assert geometry["throw_m"] == 10.0
    assert abs(geometry["dip_angle_deg"] - expected) < 0.001
    return geometry


def saturation_check():
    archie = saturation("archie", 10, 0.2, 0, a=1, m=2, n=2, rw=0.1)
    simandoux = saturation("simandoux", 10, 0.2, 0, a=1, m=2, n=2, rw=0.1, rsh=4)
    indonesian = saturation("indonesian", 10, 0.2, 0, a=1, m=2, n=2, rw=0.1, rsh=4)
    assert abs(archie - simandoux) < 1e-12 and abs(archie - indonesian) < 1e-12
    return {"archie": archie, "simandoux": simandoux, "indonesian": indonesian}


def field_check(path):
    las = LASParser.parse_file(str(path))
    depth = np.asarray(las.data["DEPT"], dtype=float)
    dt = np.asarray(las.data["DT"], dtype=float)
    rhob = np.asarray(las.data["RHOB"], dtype=float)
    result = compute_synthetic_seismogram(dt, rhob, depth, dt_unit="US/F", depth_unit="FT", max_points=5000)
    valid = np.isfinite(dt) & np.isfinite(rhob) & np.isfinite(depth) & (dt > 0) & (rhob > 1.5) & (rhob < 3.5)
    expected = 2.0 * np.sum(dt[valid][:-1] * _dt_scale("US/F") * np.abs(np.diff(depth[valid] * _depth_scale("FT"))))
    assert abs(result["stats"]["twt_max_s"] - expected) < 1e-4
    assert np.all(np.diff(result["twt"]) >= 0)
    return {
        "fixture": path.name,
        "samples": result["params"]["n_points"],
        "twt_max_s": result["stats"]["twt_max_s"],
        "expected_twt_s": round(float(expected), 6),
    }


check("ibm_float", ibm_check)
check("depth_conversion", depth_check)
check("grv_with_base", grv_check)
check("fault_depth_geometry", fault_check)
check("shaly_sand_clean_sand", saturation_check)
check("field_hawkins", lambda: field_check(ROOT / "data" / "hawkins_01.las"))
check(
    "field_kgs",
    lambda: field_check(ROOT / "test_data" / "kgs_culwell_unit4_32_density_neutron_resistivity.las"),
)

report = {"ok": all(item["ok"] for item in CHECKS), "checks": CHECKS}
print(json.dumps(report, indent=2))
raise SystemExit(0 if report["ok"] else 1)
