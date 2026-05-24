"""DLIS/LIS parsers for GeoLog.

Primary path uses dlisio. Fallback path performs minimal binary scanning to
extract numeric channels with depth-like index.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from types import SimpleNamespace
from typing import Dict, List, Optional, Tuple
import io
import re
import tempfile
import numpy as np

try:
    from dlisio import dlis as dlis_mod
except Exception:
    dlis_mod = None

try:
    from dlisio import lis as lis_mod
except Exception:
    lis_mod = None

try:
    from las_parser import CURVE_ALIASES
except Exception:
    from backend.las_parser import CURVE_ALIASES


@dataclass
class ParsedCurve:
    mnemonic: str
    unit: str = ""
    description: str = ""


@dataclass
class ParsedRun:
    source_format: str
    run_name: str
    version: str
    start_depth: float
    stop_depth: float
    step: float
    null_value: float
    curves: List[ParsedCurve] = field(default_factory=list)
    data: Dict[str, np.ndarray] = field(default_factory=dict)
    parameters: List[dict] = field(default_factory=list)
    depth_key: str = "DEPT"

    @property
    def depth(self) -> np.ndarray:
        return self.data.get(self.depth_key, np.array([], dtype=np.float64))


@dataclass
class ParsedFile:
    source_format: str
    well_name: str
    uwi: str
    runs: List[ParsedRun]


DEPTH_KEYS = ("DEPT", "DEPTH", "MD", "TDEP", "TVD")


def _canon(m: str) -> str:
    key = (m or "").strip().upper()
    return CURVE_ALIASES.get(key, key)


def _to_float_array(values) -> np.ndarray:
    out = []
    for v in values:
        try:
            fv = float(v)
            if np.isfinite(fv):
                out.append(fv)
            else:
                out.append(np.nan)
        except Exception:
            out.append(np.nan)
    return np.array(out, dtype=np.float64)


def _choose_depth_key(keys: List[str]) -> str:
    keyset = {k.upper() for k in keys}
    for k in DEPTH_KEYS:
        if k in keyset:
            return k
    return keys[0] if keys else "DEPT"


def _derive_step(depth: np.ndarray) -> float:
    if depth.size < 2:
        return 0.0
    d = np.diff(depth)
    d = d[np.isfinite(d)]
    if d.size == 0:
        return 0.0
    return float(np.nanmedian(d))


def _as_string(value) -> str:
    if value is None:
        return ""
    try:
        return str(value).strip()
    except Exception:
        return ""


def parse_dlis_content(content: bytes, filename: str = "upload.dlis") -> ParsedFile:
    if dlis_mod is not None:
        try:
            return _parse_dlis_dlisio(content, filename)
        except Exception:
            pass
    return _parse_dlis_binary_fallback(content, filename)


def parse_lis_content(content: bytes, filename: str = "upload.lis") -> ParsedFile:
    if lis_mod is not None:
        try:
            return _parse_lis_dlisio(content, filename)
        except Exception:
            pass
    return _parse_lis_binary_fallback(content, filename)


def _parse_dlis_dlisio(content: bytes, filename: str) -> ParsedFile:
    runs: List[ParsedRun] = []
    well_name = ""
    uwi = ""

    with tempfile.NamedTemporaryFile(suffix=".dlis", delete=True) as tf:
        tf.write(content)
        tf.flush()
        with dlis_mod.load(tf.name) as physical:
            for lf_idx, logical in enumerate(physical):
                if not well_name:
                    for origin in getattr(logical, "origins", []) or []:
                        wn = _as_string(getattr(origin, "well_name", ""))
                        if wn:
                            well_name = wn
                        uv = _as_string(getattr(origin, "uwi", "")) or _as_string(getattr(origin, "well_id", ""))
                        if uv:
                            uwi = uv

                for frame_idx, frame in enumerate(getattr(logical, "frames", []) or []):
                    try:
                        arr = frame.curves()
                    except Exception:
                        continue
                    if arr is None or len(arr) == 0 or not getattr(arr, "dtype", None):
                        continue

                    names = list(arr.dtype.names or [])
                    if not names:
                        continue

                    data: Dict[str, np.ndarray] = {}
                    curves: List[ParsedCurve] = []
                    used = set()

                    frame_channels = {(_as_string(getattr(ch, "name", "")) or _as_string(getattr(ch, "mnemonic", ""))).upper(): ch for ch in (getattr(frame, "channels", []) or [])}

                    for raw_name in names:
                        canon = _canon(raw_name)
                        if canon in used:
                            suffix = 2
                            while f"{canon}_{suffix}" in used:
                                suffix += 1
                            canon = f"{canon}_{suffix}"
                        used.add(canon)

                        col = arr[raw_name]
                        if getattr(col, "dtype", None) is not None and col.dtype.fields:
                            flat = []
                            for row in col:
                                try:
                                    vals = [float(x) for x in row.tolist()]
                                    flat.append(float(np.nanmean(vals)))
                                except Exception:
                                    flat.append(np.nan)
                            data[canon] = np.array(flat, dtype=np.float64)
                        else:
                            data[canon] = _to_float_array(col)

                        unit = ""
                        desc = _as_string(raw_name)
                        ch = frame_channels.get(_as_string(raw_name).upper())
                        if ch is not None:
                            unit = _as_string(getattr(ch, "units", ""))
                            desc = _as_string(getattr(ch, "long_name", "")) or _as_string(getattr(ch, "name", "")) or desc

                        curves.append(ParsedCurve(mnemonic=canon, unit=unit, description=desc))

                    depth_key = _choose_depth_key(list(data.keys()))
                    depth = data.get(depth_key, np.array([], dtype=np.float64))
                    finite = depth[np.isfinite(depth)] if depth.size else np.array([], dtype=np.float64)
                    start = float(finite[0]) if finite.size else 0.0
                    stop = float(finite[-1]) if finite.size else 0.0
                    step = _derive_step(depth)

                    run_name = f"LF{lf_idx+1}_FRAME{frame_idx+1}"
                    runs.append(ParsedRun(
                        source_format="DLIS",
                        run_name=run_name,
                        version="DLIS",
                        start_depth=start,
                        stop_depth=stop,
                        step=step,
                        null_value=-999.25,
                        curves=curves,
                        data=data,
                        parameters=[{"mnemonic": "FRAME", "unit": "", "value": run_name}],
                        depth_key=depth_key,
                    ))

    if not runs:
        raise ValueError("No frame data found in DLIS")

    return ParsedFile(
        source_format="DLIS",
        well_name=well_name or filename.rsplit('.', 1)[0],
        uwi=uwi,
        runs=runs,
    )


def _parse_lis_dlisio(content: bytes, filename: str) -> ParsedFile:
    runs: List[ParsedRun] = []
    well_name = ""
    uwi = ""

    with tempfile.NamedTemporaryFile(suffix=".lis", delete=True) as tf:
        tf.write(content)
        tf.flush()
        with lis_mod.load(tf.name) as physical:
            for lf_idx, logical in enumerate(physical):
                header = getattr(logical, "header", None)
                if header is not None and not well_name:
                    well_name = _as_string(getattr(header, "well_name", ""))
                    uwi = _as_string(getattr(header, "well_id", ""))

                for dfs_idx, dfsr in enumerate(getattr(logical, "data_format_specs", []) or []):
                    try:
                        arr = lis_mod.curves(logical, dfsr, strict=False)
                        meta = lis_mod.curves_metadata(dfsr, strict=False)
                    except Exception:
                        continue
                    if arr is None or len(arr) == 0:
                        continue

                    names = list(arr.dtype.names or [])
                    if not names:
                        continue

                    data: Dict[str, np.ndarray] = {}
                    curves: List[ParsedCurve] = []
                    used = set()

                    for raw_name in names:
                        canon = _canon(raw_name)
                        if canon in used:
                            suffix = 2
                            while f"{canon}_{suffix}" in used:
                                suffix += 1
                            canon = f"{canon}_{suffix}"
                        used.add(canon)

                        data[canon] = _to_float_array(arr[raw_name])

                        md = (meta or {}).get(raw_name)
                        unit = _as_string(getattr(md, "units", "")) if md is not None else ""
                        desc = _as_string(getattr(md, "name", "")) if md is not None else _as_string(raw_name)
                        curves.append(ParsedCurve(mnemonic=canon, unit=unit, description=desc))

                    depth_key = _choose_depth_key(list(data.keys()))
                    depth = data.get(depth_key, np.array([], dtype=np.float64))
                    finite = depth[np.isfinite(depth)] if depth.size else np.array([], dtype=np.float64)
                    start = float(finite[0]) if finite.size else 0.0
                    stop = float(finite[-1]) if finite.size else 0.0
                    step = _derive_step(depth)

                    run_name = f"LIS_LF{lf_idx+1}_SET{dfs_idx+1}"
                    runs.append(ParsedRun(
                        source_format="LIS",
                        run_name=run_name,
                        version="LIS79",
                        start_depth=start,
                        stop_depth=stop,
                        step=step,
                        null_value=-999.25,
                        curves=curves,
                        data=data,
                        parameters=[{"mnemonic": "SET", "unit": "", "value": run_name}],
                        depth_key=depth_key,
                    ))

    if not runs:
        raise ValueError("No data records found in LIS")

    return ParsedFile(
        source_format="LIS",
        well_name=well_name or filename.rsplit('.', 1)[0],
        uwi=uwi,
        runs=runs,
    )


def _extract_ascii_tokens(content: bytes) -> List[float]:
    text = content.decode("latin1", errors="ignore")
    vals = []
    for m in re.finditer(r"[-+]?\d+(?:\.\d+)?(?:[eE][-+]?\d+)?", text):
        try:
            vals.append(float(m.group(0)))
        except Exception:
            continue
    return vals


def _build_minimal_run_from_tokens(tokens: List[float], fmt: str, filename: str) -> ParsedRun:
    if len(tokens) < 20:
        raise ValueError(f"{fmt} fallback parser could not extract enough numeric samples")

    arr = np.array(tokens, dtype=np.float64)
    depth = arr[0::3]
    c1 = arr[1::3][: len(depth)]
    c2 = arr[2::3][: len(depth)]

    data = {
        "DEPT": depth,
        "CURVE1": c1,
        "CURVE2": c2,
    }
    curves = [
        ParsedCurve("DEPT", "", "Depth"),
        ParsedCurve("CURVE1", "", "Extracted channel 1"),
        ParsedCurve("CURVE2", "", "Extracted channel 2"),
    ]
    finite = depth[np.isfinite(depth)]
    start = float(finite[0]) if finite.size else 0.0
    stop = float(finite[-1]) if finite.size else 0.0
    step = _derive_step(depth)

    return ParsedRun(
        source_format=fmt,
        run_name=f"{fmt}_BINARY_FALLBACK",
        version=fmt,
        start_depth=start,
        stop_depth=stop,
        step=step,
        null_value=-999.25,
        curves=curves,
        data=data,
        parameters=[{"mnemonic": "PARSER", "unit": "", "value": "binary-fallback"}],
        depth_key="DEPT",
    )


def _parse_dlis_binary_fallback(content: bytes, filename: str) -> ParsedFile:
    tokens = _extract_ascii_tokens(content)
    run = _build_minimal_run_from_tokens(tokens, "DLIS", filename)
    return ParsedFile(source_format="DLIS", well_name=filename.rsplit('.', 1)[0], uwi="", runs=[run])


def _parse_lis_binary_fallback(content: bytes, filename: str) -> ParsedFile:
    tokens = _extract_ascii_tokens(content)
    run = _build_minimal_run_from_tokens(tokens, "LIS", filename)
    return ParsedFile(source_format="LIS", well_name=filename.rsplit('.', 1)[0], uwi="", runs=[run])
