"""Shared data semantics: aliases, units, depth correction and TVD.

The viewer, compute endpoints and exports must read the same corrected values.
This module is the one place that resolves:

* explicit curve aliases (well-level),
* units to the well's target system,
* piecewise MD -> corrected-depth control points (legacy shift/stretch fallback),
* deviation-derived TVD.

Nothing here rewrites stored curves. Callers receive copies plus a metadata block
so a response can be reproduced and audited.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any, Iterable, Optional

import numpy as np

try:
    from models import CurveAlias, CurveData, DepthControlPoint, DeviationSurvey, LogRunDepthShift
except ImportError:
    from backend.models import CurveAlias, CurveData, DepthControlPoint, DeviationSurvey, LogRunDepthShift

SEMANTICS_VERSION = "data-semantics-v1"

# Unit definitions: dimension -> {unit: factor to the dimension's base}.
# Temperature is handled separately because it has an offset.
_UNIT_DEFS: dict[str, dict[str, float]] = {
    "length": {"m": 1.0, "ft": 0.3048, "in": 0.0254, "mm": 0.001},
    "slowness": {"us/m": 1.0, "us/ft": 1.0 / 0.3048},
    "density": {"kg/m3": 1.0, "g/cc": 1000.0},
    "fraction": {"v/v": 1.0, "%": 0.01},
    "resistivity": {"ohm.m": 1.0, "ohm.ft": 0.3048},
    "pressure": {"pa": 1.0, "kpa": 1000.0, "mpa": 1_000_000.0, "bar": 100_000.0, "psi": 6894.757293},
    "permeability": {"m2": 1.0, "md": 9.869233e-16},
}

_UNIT_ALIASES = {
    "ft": "ft", "feet": "ft", "foot": "ft",
    "m": "m", "meter": "m", "meters": "m", "metre": "m", "metres": "m",
    "in": "in", "inch": "in", "inches": "in",
    "mm": "mm",
    "us/ft": "us/ft", "us/f": "us/ft", "usec/ft": "us/ft", "usec/f": "us/ft",
    "us/m": "us/m", "usec/m": "us/m",
    "g/cc": "g/cc", "g/c3": "g/cc", "g/cm3": "g/cc", "g/cm^3": "g/cc",
    "kg/m3": "kg/m3", "kg/m^3": "kg/m3",
    "v/v": "v/v", "fraction": "v/v", "frac": "v/v",
    "%": "%", "perc": "%", "percent": "%", "pu": "%",
    "ohmm": "ohm.m", "ohm.m": "ohm.m", "ohm-m": "ohm.m", "ohm m": "ohm.m",
    "ohmft": "ohm.ft", "ohm.ft": "ohm.ft", "ohm-ft": "ohm.ft",
    "pa": "pa", "kpa": "kpa", "mpa": "mpa", "bar": "bar", "psi": "psi",
    "m2": "m2", "m^2": "m2", "md": "md", "millidarcy": "md",
    "degf": "degf", "°f": "degf", "f": "degf",
    "degc": "degc", "°c": "degc", "c": "degc",
}

_FAMILY_BY_MNEMONIC = {
    "length": {"DEPT", "DEPTH", "MD", "TVD", "TVDSS", "MDSS"},
    "slowness": {"DT", "DTC", "DTS", "DTCO", "DTSM", "AC", "SONIC"},
    "density": {"RHOB", "RHOZ", "DEN", "ZDEN", "DGA", "RHOC"},
    "fraction": {"NPHI", "PHIE", "PHIT", "PHID", "DPOR", "SPOR", "SW", "SWT", "BVW", "VSH", "VCL"},
    "resistivity": {
        "RT", "RILD", "RILM", "RMED", "RXO", "RES", "RLL3", "RLLS", "MSFL",
        "ILD", "LLD", "LLS", "AHT90", "AT90", "RLA1", "RT_HRLT",
    },
    "pressure": {"PRES", "PRESSURE", "BHP", "WHP", "PP", "PORE_PRESSURE"},
    "permeability": {"PERM", "K", "KLOG", "KD", "KH"},
    "temperature": {"TEMP", "TEMPERATURE", "TEMP_DEGF", "TEMP_DEGC"},
    "caliper": {"CAL", "CALI", "HCAL", "DCAL", "BS", "BIT", "BIT_SIZE", "CLDC"},
}

_TARGET_UNITS = {
    "field": {
        "length": "ft", "slowness": "us/ft", "density": "g/cc",
        "fraction": "v/v", "resistivity": "ohm.m", "pressure": "psi",
        "permeability": "md", "temperature": "degf", "caliper": "in",
    },
    "si": {
        "length": "m", "slowness": "us/m", "density": "kg/m3",
        "fraction": "v/v", "resistivity": "ohm.m", "pressure": "mpa",
        "permeability": "m2", "temperature": "degc", "caliper": "mm",
    },
}

def normalize_unit(unit: str | None) -> str:
    raw = (unit or "").strip().lower().replace(" ", "")
    return _UNIT_ALIASES.get(raw, raw)

def curve_family(mnemonic: str) -> Optional[str]:
    key = (mnemonic or "").strip().upper()
    for family, names in _FAMILY_BY_MNEMONIC.items():
        if key in names:
            return family
    return None

def _temperature_convert(values: np.ndarray, from_u: str, to_u: str) -> np.ndarray:
    if from_u == to_u:
        return values
    celsius = (values - 32.0) * 5.0 / 9.0 if from_u == "degf" else values
    return celsius * 9.0 / 5.0 + 32.0 if to_u == "degf" else celsius

def convert_array(values: np.ndarray, from_unit: str | None, to_unit: str | None) -> tuple[np.ndarray, Optional[str]]:
    """Convert values or return the original array plus a warning."""
    src = normalize_unit(from_unit)
    dst = normalize_unit(to_unit)
    if not src or not dst:
        return values, "unit missing; conversion skipped"
    if src == dst:
        return values, None
    if src in {"degf", "degc"} and dst in {"degf", "degc"}:
        return _temperature_convert(values, src, dst), None

    for units in _UNIT_DEFS.values():
        if src in units and dst in units:
            return values * (units[src] / units[dst]), None
    return values, f"cannot convert {from_unit!r} to {to_unit!r}; left unchanged"

def piecewise_linear(target: np.ndarray, x: np.ndarray, y: np.ndarray) -> np.ndarray:
    """Linear interpolation with linear extrapolation outside the control range."""
    tx = np.asarray(x, dtype=np.float64)
    ty = np.asarray(y, dtype=np.float64)
    t = np.asarray(target, dtype=np.float64)
    order = np.argsort(tx)
    tx, ty = tx[order], ty[order]
    if tx.size == 0:
        return t.copy()
    if tx.size == 1:
        return ty[0] + (t - tx[0])
    out = np.interp(t, tx, ty)
    left = t < tx[0]
    right = t > tx[-1]
    if np.any(left):
        slope = (ty[1] - ty[0]) / (tx[1] - tx[0])
        out[left] = ty[0] + (t[left] - tx[0]) * slope
    if np.any(right):
        slope = (ty[-1] - ty[-2]) / (tx[-1] - tx[-2])
        out[right] = ty[-1] + (t[right] - tx[-1]) * slope
    return out

def _alias_map(db, well_id: int) -> dict[str, str]:
    rows = db.query(CurveAlias).filter(CurveAlias.well_id == well_id).all()
    return {
        (r.original_mnemonic or "").strip().upper(): (r.alias_mnemonic or "").strip().upper()
        for r in rows
        if (r.original_mnemonic or "").strip() and (r.alias_mnemonic or "").strip()
    }

def _resolve_names(rows: Iterable[CurveData], aliases: dict[str, str]) -> tuple[list[dict[str, Any]], list[str]]:
    resolved = []
    for cd in rows:
        raw = (cd.mnemonic or "").strip()
        canonical = aliases.get(raw.upper(), raw)
        resolved.append({"row": cd, "raw": raw, "canonical": canonical, "name": canonical})
    groups: dict[str, list[dict[str, Any]]] = {}
    for item in resolved:
        groups.setdefault(item["canonical"].upper(), []).append(item)
    warnings = []
    for canonical, items in groups.items():
        if len(items) > 1:
            raws = ", ".join(i["raw"] for i in items)
            warnings.append(f"alias collision for {canonical}: keeping raw names ({raws})")
            for item in items:
                item["name"] = item["raw"]
    return resolved, warnings

def _depth_control_points(db, log_run_id: int) -> list[tuple[float, float]]:
    rows = (
        db.query(DepthControlPoint)
        .filter(DepthControlPoint.log_run_id == log_run_id)
        .order_by(DepthControlPoint.sort_order.asc(), DepthControlPoint.md.asc())
        .all()
    )
    return [(float(r.md), float(r.corrected_depth)) for r in rows]

def _legacy_shift(db, log_run_id: int) -> tuple[float, float] | None:
    row = db.query(LogRunDepthShift).filter(LogRunDepthShift.log_run_id == log_run_id).first()
    if not row:
        return None
    return float(row.shift or 0.0), float(row.stretch if row.stretch is not None else 1.0)

def _tvd_curve(db, well_id: int, md: np.ndarray) -> tuple[np.ndarray, list[str]]:
    rows = (
        db.query(DeviationSurvey)
        .filter(DeviationSurvey.well_id == well_id)
        .order_by(DeviationSurvey.md.asc())
        .all()
    )
    survey = [(float(r.md), float(r.tvd)) for r in rows if r.md is not None and r.tvd is not None]
    if len(survey) >= 2:
        x = np.array([p[0] for p in survey], dtype=np.float64)
        y = np.array([p[1] for p in survey], dtype=np.float64)
        return piecewise_linear(md, x, y), []
    return md.copy(), ["no deviation-derived TVD; TVD set equal to MD"]

def _hash_payload(payload: dict[str, Any]) -> str:
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()

def apply_run_semantics(
    db,
    log_run,
    requested: Optional[Iterable[str]] = None,
    start: Optional[float] = None,
    stop: Optional[float] = None,
    step: int = 1,
    as_arrays: bool = False,
) -> dict[str, Any]:
    """Return corrected curves, depth/TVD and provenance metadata for one run."""
    well = log_run.well
    unit_system = (getattr(well, "unit_system", None) or "field").lower()
    if unit_system not in _TARGET_UNITS:
        unit_system = "field"
    aliases = _alias_map(db, well.id)
    rows = db.query(CurveData).filter(CurveData.log_run_id == log_run.id).all()
    named, warnings = _resolve_names(rows, aliases)

    depth_row = next(
        (n["row"] for n in named if n["canonical"].upper() in {"DEPT", "DEPTH", "MD", "TVD"}),
        None,
    )
    if depth_row is not None and depth_row.data_binary:
        md = np.frombuffer(depth_row.data_binary, dtype=np.float64).copy()
    else:
        start_d = float(log_run.start_depth or 0.0)
        stop_d = float(log_run.stop_depth or start_d + max(0, int(log_run.num_points or 0) - 1))
        md = np.linspace(start_d, stop_d, int(log_run.num_points or 1))

    points = _depth_control_points(db, log_run.id)
    legacy = _legacy_shift(db, log_run.id)
    legacy_payload = None
    if len(points) >= 2:
        x = np.array([p[0] for p in points], dtype=np.float64)
        y = np.array([p[1] for p in points], dtype=np.float64)
        corrected = piecewise_linear(md, x, y)
        if legacy and (legacy[0] or legacy[1] != 1.0):
            warnings.append("control points override legacy shift/stretch")
        depth_source = "control_points"
    elif legacy:
        shift, stretch = legacy
        base = float(log_run.start_depth if log_run.start_depth is not None else md[0])
        corrected = base + (md - base) * stretch + shift
        legacy_payload = {"shift": shift, "stretch": stretch, "base": base}
        depth_source = "legacy_shift"
        warnings.append("legacy shift/stretch applied; add control points for piecewise correction")
    else:
        corrected = md.copy()
        depth_source = "raw"
        if len(points) == 1:
            warnings.append("one control point is not enough; depth correction skipped")

    tvd, tvd_warnings = _tvd_curve(db, well.id, corrected)
    warnings.extend(tvd_warnings)

    depth_unit_from = (depth_row.unit if depth_row is not None and depth_row.unit else (well.depth_unit or "ft"))
    depth_unit_to = _TARGET_UNITS[unit_system]["length"]
    corrected, depth_unit_warning = convert_array(corrected, depth_unit_from, depth_unit_to)
    if depth_unit_warning:
        warnings.append(f"depth: {depth_unit_warning}")
    tvd, tvd_unit_warning = convert_array(tvd, depth_unit_from, depth_unit_to)
    if tvd_unit_warning:
        warnings.append(f"TVD: {tvd_unit_warning}")

    mask = np.ones(len(corrected), dtype=bool)
    if start is not None:
        mask &= corrected >= float(start)
    if stop is not None:
        mask &= corrected <= float(stop)

    step = max(1, int(step or 1))
    wanted = {str(x).strip().upper() for x in (requested or []) if str(x).strip()}
    curves: dict[str, Any] = {}
    curve_meta = []
    for item in named:
        cd = item["row"]
        if wanted and item["raw"].upper() not in wanted and item["canonical"].upper() not in wanted:
            continue
        arr = np.frombuffer(cd.data_binary, dtype=np.float64).copy() if cd.data_binary else np.array([], dtype=np.float64)
        if len(arr) == len(corrected):
            arr = arr[mask]
            arr = arr[::step]
        family = curve_family(item["canonical"])
        target = _TARGET_UNITS[unit_system].get(family) if family else None
        arr, unit_warning = convert_array(arr, cd.unit, target) if target else (arr, None)
        if unit_warning:
            warnings.append(f"{item['name']}: {unit_warning}")
        curves[item["name"]] = arr if as_arrays else [
            None if np.isnan(v) else round(float(v), 6) for v in arr
        ]
        curve_meta.append({
            "raw": item["raw"],
            "name": item["name"],
            "canonical": item["canonical"],
            "unit_from": cd.unit or "",
            "unit_to": target or (cd.unit or ""),
        })

    depth_out = corrected[mask][::step]
    tvd_out = tvd[mask][::step]
    if depth_out.size:
        curves["DEPTH"] = depth_out if as_arrays else [round(float(v), 4) for v in depth_out]
        curves["TVD"] = tvd_out if as_arrays else [round(float(v), 4) for v in tvd_out]

    payload = {
        "version": SEMANTICS_VERSION,
        "unit_system": unit_system,
        "aliases": sorted(aliases.items()),
        "control_points": points,
        "legacy": legacy_payload,
        "depth_unit_from": depth_unit_from,
        "depth_unit_to": depth_unit_to,
    }
    return {
        "curves": curves,
        "depth": depth_out,
        "tvd": tvd_out,
        "metadata": {
            "version": SEMANTICS_VERSION,
            "unit_system": unit_system,
            "depth_source": depth_source,
            "depth_unit_from": depth_unit_from,
            "depth_unit_to": depth_unit_to,
            "input_hash": _hash_payload(payload),
            "aliases": curve_meta,
            "warnings": warnings,
        },
    }
