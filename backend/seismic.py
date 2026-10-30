"""Minimal SEG-Y reader for uploaded 2D/3D lines.

Supports IBM 4-byte float (format 1) and IEEE 4-byte float (format 5). It is a
screening reader: the first `max_traces` traces are kept and the section is
decimated before it is sent to the browser.
"""

from __future__ import annotations

import math
from typing import Any

import numpy as np

try:
    from velocity import time_to_depth_ms
except ImportError:
    from backend.velocity import time_to_depth_ms

try:
    from geostat import krige_grid
except ImportError:
    from backend.geostat import krige_grid

TEXT_HEADER = 3200
BINARY_HEADER = 400
TRACE_HEADER = 240
SUPPORTED_FORMATS = {1: 4, 5: 4}


def ibm_to_ieee(raw: bytes) -> np.ndarray:
    """Convert IBM System/360 4-byte floats to IEEE float32."""
    words = np.frombuffer(raw, dtype=">u4").astype(np.uint32)
    sign = (words >> 31) & 0x1
    exponent = ((words >> 24) & 0x7F).astype(np.int32)
    fraction = (words & 0x00FFFFFF).astype(np.float64) / float(1 << 24)
    value = fraction * (16.0 ** (exponent - 64))
    value = np.where(sign == 1, -value, value)
    return value.astype(np.float32)


def parse_segy(content: bytes, max_traces: int = 2500) -> dict[str, Any]:
    if len(content) < TEXT_HEADER + BINARY_HEADER + TRACE_HEADER:
        raise ValueError("file is too small to be SEG-Y")
    binary = content[TEXT_HEADER:TEXT_HEADER + BINARY_HEADER]
    dt_us = int.from_bytes(binary[16:18], "big")
    binary_ns = int.from_bytes(binary[20:22], "big")
    format_code = int.from_bytes(binary[24:26], "big")
    if format_code not in SUPPORTED_FORMATS:
        raise ValueError(f"unsupported SEG-Y sample format {format_code}; expected 1 or 5")

    offset = TEXT_HEADER + BINARY_HEADER
    traces: list[np.ndarray] = []
    inlines: list[int] = []
    crosslines: list[int] = []
    ns = binary_ns
    while offset + TRACE_HEADER <= len(content) and len(traces) < max_traces:
        header = content[offset:offset + TRACE_HEADER]
        offset += TRACE_HEADER
        trace_ns = int.from_bytes(header[114:116], "big") or ns
        if trace_ns <= 0:
            raise ValueError("trace has no sample count")
        if ns <= 0:
            ns = trace_ns
        nbytes = trace_ns * SUPPORTED_FORMATS[format_code]
        if offset + nbytes > len(content):
            break
        raw = content[offset:offset + nbytes]
        offset += nbytes
        if format_code == 1:
            values = ibm_to_ieee(raw)
        else:
            values = np.frombuffer(raw, dtype=">f4").astype(np.float32)
        if len(values) < ns:
            values = np.pad(values, (0, ns - len(values)), constant_values=np.nan)
        traces.append(values[:ns].copy())
        inlines.append(int.from_bytes(header[188:192], "big"))
        crosslines.append(int.from_bytes(header[192:196], "big"))

    if not traces:
        raise ValueError("no traces could be read")
    matrix = np.vstack(traces)
    finite = matrix[np.isfinite(matrix)]
    return {
        "matrix": matrix,
        "format_code": format_code,
        "sample_interval_ms": float(dt_us) / 1000.0,
        "samples_per_trace": int(ns),
        "trace_count": int(matrix.shape[0]),
        "inline_min": int(min(inlines)) if inlines else None,
        "inline_max": int(max(inlines)) if inlines else None,
        "crossline_min": int(min(crosslines)) if crosslines else None,
        "crossline_max": int(max(crosslines)) if crosslines else None,
        "amplitude_min": float(np.min(finite)) if len(finite) else None,
        "amplitude_max": float(np.max(finite)) if len(finite) else None,
        "trace_inlines": [int(value) for value in inlines],
        "trace_crosslines": [int(value) for value in crosslines],
    }


def _section_view(
    matrix: np.ndarray,
    labels: list[int] | None = None,
    max_traces: int = 500,
    max_samples: int = 500,
    sample_interval_ms: float = 0.0,
) -> dict[str, Any]:
    nt, ns = matrix.shape
    trace_step = max(1, math.ceil(nt / max(1, max_traces)))
    sample_step = max(1, math.ceil(ns / max(1, max_samples)))
    view = matrix[::trace_step, ::sample_step]
    finite = view[np.isfinite(view)]
    if labels is None:
        out_labels = list(range(0, nt, trace_step))
    else:
        out_labels = [int(labels[index]) for index in range(0, len(labels), trace_step)]
    return {
        "trace_count": int(view.shape[0]),
        "sample_count": int(view.shape[1]),
        "trace_step": int(trace_step),
        "sample_step": int(sample_step),
        "original_trace_count": int(nt),
        "original_sample_count": int(ns),
        "sample_interval_ms": sample_interval_ms,
        "amplitude_min": float(np.min(finite)) if len(finite) else 0.0,
        "amplitude_max": float(np.max(finite)) if len(finite) else 0.0,
        "labels": out_labels,
        "data": np.round(view, 6).tolist(),
    }

def section_payload(parsed: dict[str, Any], max_traces: int = 500, max_samples: int = 500) -> dict[str, Any]:
    return _section_view(
        parsed["matrix"],
        max_traces=max_traces,
        max_samples=max_samples,
        sample_interval_ms=parsed["sample_interval_ms"],
    )

def index_segy(content: bytes, max_traces: int = 500000) -> dict[str, Any]:
    """Scan trace headers and offsets without decoding trace samples."""
    if len(content) < TEXT_HEADER + BINARY_HEADER + TRACE_HEADER:
        raise ValueError("file is too small to be SEG-Y")
    binary = content[TEXT_HEADER:TEXT_HEADER + BINARY_HEADER]
    dt_us = int.from_bytes(binary[16:18], "big")
    binary_ns = int.from_bytes(binary[20:22], "big")
    format_code = int.from_bytes(binary[24:26], "big")
    if format_code not in SUPPORTED_FORMATS:
        raise ValueError(f"unsupported SEG-Y sample format {format_code}; expected 1 or 5")

    offset = TEXT_HEADER + BINARY_HEADER
    offsets: list[int] = []
    sample_counts: list[int] = []
    inlines: list[int] = []
    crosslines: list[int] = []
    while offset + TRACE_HEADER <= len(content) and len(offsets) < max_traces:
        header = content[offset:offset + TRACE_HEADER]
        trace_ns = int.from_bytes(header[114:116], "big") or binary_ns
        if trace_ns <= 0:
            break
        nbytes = trace_ns * SUPPORTED_FORMATS[format_code]
        if offset + TRACE_HEADER + nbytes > len(content):
            break
        offsets.append(offset + TRACE_HEADER)
        sample_counts.append(int(trace_ns))
        inlines.append(int.from_bytes(header[188:192], "big"))
        crosslines.append(int.from_bytes(header[192:196], "big"))
        offset += TRACE_HEADER + nbytes
    if not offsets:
        raise ValueError("no traces could be read")
    ns = max(sample_counts) if sample_counts else binary_ns
    return {
        "format_code": format_code,
        "sample_interval_ms": float(dt_us) / 1000.0,
        "samples_per_trace": int(ns),
        "trace_count": len(offsets),
        "trace_offsets": offsets,
        "trace_sample_counts": sample_counts,
        "trace_inlines": inlines,
        "trace_crosslines": crosslines,
        "inline_min": int(min(inlines)),
        "inline_max": int(max(inlines)),
        "crossline_min": int(min(crosslines)),
        "crossline_max": int(max(crosslines)),
    }

def read_indexed_traces(content: bytes, index: dict[str, Any], positions: list[int]) -> np.ndarray:
    """Decode only the requested trace positions from an indexed SEG-Y file."""
    if not positions:
        raise ValueError("no traces selected")
    fmt = int(index["format_code"])
    ns = int(index["samples_per_trace"])
    width = SUPPORTED_FORMATS[fmt]
    traces = []
    for position in positions:
        offset = int(index["trace_offsets"][int(position)])
        count = int(index["trace_sample_counts"][int(position)])
        raw = content[offset:offset + count * width]
        if fmt == 1:
            values = ibm_to_ieee(raw)
        else:
            values = np.frombuffer(raw, dtype=">f4").astype(np.float32)
        if len(values) < ns:
            values = np.pad(values, (0, ns - len(values)), constant_values=np.nan)
        traces.append(values[:ns])
    return np.vstack(traces)

def line_section(
    content: bytes,
    index: dict[str, Any],
    max_traces: int = 1200,
    max_samples: int = 800,
) -> dict[str, Any]:
    """Decimate the whole indexed line/volume instead of stopping at a trace count."""
    total = int(index["trace_count"])
    count = max(1, min(total, int(max_traces)))
    if count >= total:
        positions = list(range(total))
    else:
        positions = sorted(set(
            int(value) for value in np.linspace(0, total - 1, count).round().astype(int).tolist()
        ))
    matrix = read_indexed_traces(content, index, positions)
    payload = _section_view(
        matrix,
        labels=positions,
        max_traces=count,
        max_samples=max_samples,
        sample_interval_ms=index["sample_interval_ms"],
    )
    payload["line_trace_count"] = total
    payload["sampled"] = len(positions) < total
    return payload

def volume_index(index: dict[str, Any], limit: int = 5000) -> dict[str, Any]:
    """Return sorted inline/crossline values present in the scanned headers."""
    inlines = sorted(set(int(value) for value in index.get("trace_inlines", [])))
    crosslines = sorted(set(int(value) for value in index.get("trace_crosslines", [])))
    return {
        "inlines": inlines[:limit],
        "crosslines": crosslines[:limit],
        "inline_count": len(inlines),
        "crossline_count": len(crosslines),
        "trace_count": int(index["trace_count"]),
        "is_3d": len(inlines) > 1 and len(crosslines) > 1,
        "truncated": len(inlines) > limit or len(crosslines) > limit,
    }

def volume_section(
    content: bytes,
    index: dict[str, Any],
    mode: str,
    value: int,
    max_traces: int = 500,
    max_samples: int = 500,
) -> dict[str, Any]:
    """Build an inline or crossline section by reading only matching traces."""
    inlines = index.get("trace_inlines", [])
    crosslines = index.get("trace_crosslines", [])
    if mode == "inline":
        positions = [pos for pos, inline in enumerate(inlines) if int(inline) == int(value)]
        labels = [int(crosslines[pos]) for pos in positions]
    elif mode == "crossline":
        positions = [pos for pos, crossline in enumerate(crosslines) if int(crossline) == int(value)]
        labels = [int(inlines[pos]) for pos in positions]
    else:
        raise ValueError("mode must be inline or crossline")
    if not positions:
        raise ValueError(f"no traces for {mode} {value}")
    order = sorted(range(len(positions)), key=lambda pos: labels[pos])
    positions = [positions[pos] for pos in order]
    labels = [labels[pos] for pos in order]
    matrix = read_indexed_traces(content, index, positions)
    payload = _section_view(
        matrix,
        labels=labels,
        max_traces=max_traces,
        max_samples=max_samples,
        sample_interval_ms=index["sample_interval_ms"],
    )
    payload["mode"] = mode
    payload["value"] = int(value)
    payload["label_name"] = "crossline" if mode == "inline" else "inline"
    return payload

def surface_from_horizons(
    content: bytes,
    index: dict[str, Any],
    horizons: list[dict[str, Any]],
    max_grid: int = 96,
    inline_spacing_m: float | None = None,
    crossline_spacing_m: float | None = None,
    method: str = "idw",
    variogram: dict[str, Any] | None = None,
    anisotropy_ratio: float = 1.0,
    azimuth_deg: float = 0.0,
) -> dict[str, Any]:
    """Grid inline/crossline horizon picks into a time surface with IDW."""
    points: list[tuple[float, float, float]] = []
    cache: dict[tuple[str, int], dict[str, Any]] = {}
    for horizon in horizons:
        mode = str(horizon.get("mode") or "")
        if mode not in {"inline", "crossline"}:
            continue
        value = horizon.get("section_value")
        if value is None:
            continue
        key = (mode, int(value))
        if key not in cache:
            cache[key] = volume_section(
                content,
                index,
                mode,
                int(value),
                max_traces=600,
                max_samples=600,
            )
        section = cache[key]
        labels = section.get("labels") or []
        step = int(section.get("sample_step") or 1)
        for pick in horizon.get("picks") or []:
            try:
                trace = int(pick["trace"])
                sample = int(pick["sample"])
            except (KeyError, TypeError, ValueError):
                continue
            if trace < 0 or trace >= len(labels):
                continue
            if mode == "inline":
                inline_value = float(value)
                crossline_value = float(labels[trace])
            else:
                inline_value = float(labels[trace])
                crossline_value = float(value)
            points.append((inline_value, crossline_value, float(sample * step) * float(index["sample_interval_ms"])))
    if len(points) < 3:
        raise ValueError("need at least three inline/crossline horizon picks")
    if len(points) > 8000:
        positions = np.linspace(0, len(points) - 1, 8000).round().astype(int).tolist()
        points = [points[position] for position in positions]
    points_array = np.asarray(points, dtype=float)
    inline_values = sorted(set(float(value) for value in points_array[:, 0]))
    crossline_values = sorted(set(float(value) for value in points_array[:, 1]))
    if len(inline_values) < 2 or len(crossline_values) < 2:
        raise ValueError("surface needs at least two inlines and two crosslines")

    def axis(values: list[float], limit: int) -> list[float]:
        if len(values) <= limit:
            return values
        positions = np.linspace(0, len(values) - 1, limit).round().astype(int)
        return [values[int(position)] for position in sorted(set(positions.tolist()))]

    grid_inlines = axis(inline_values, max(2, int(max_grid)))
    grid_crosslines = axis(crossline_values, max(2, int(max_grid)))
    point_inlines = points_array[:, 0]
    point_crosslines = points_array[:, 1]
    point_samples = points_array[:, 2]
    interpolation = str(method or "idw").lower()
    variogram = variogram or {}
    kriging_info: dict[str, Any] = {}
    if interpolation == "kriging":
        grid, kriging_info = krige_grid(
            points_array,
            grid_inlines,
            grid_crosslines,
            variogram_model=str(variogram.get("model", "spherical")),
            range_m=variogram.get("range"),
            sill=variogram.get("sill"),
            nugget=float(variogram.get("nugget", 0.0) or 0.0),
            anisotropy_ratio=float(anisotropy_ratio or 1.0),
            azimuth_deg=float(azimuth_deg or 0.0),
            max_neighbors=int(variogram.get("max_neighbors", 16) or 16),
        )
    elif interpolation == "idw":
        grid = []
        for inline in grid_inlines:
            distance_sq = (
                (inline - point_inlines) ** 2
                + (np.asarray(grid_crosslines)[:, None] - point_crosslines[None, :]) ** 2
            )
            weights = 1.0 / (distance_sq + 1e-9)
            values = (weights * point_samples[None, :]).sum(axis=1) / weights.sum(axis=1)
            grid.append([round(float(value), 4) for value in values])
    else:
        raise ValueError("surface method must be idw or kriging")
    flat = [value for row in grid for value in row]
    unique_cells = len({
        (int(round(inline)), int(round(crossline)))
        for inline, crossline in zip(point_inlines, point_crosslines)
    })
    stats = {
        "point_count": len(points),
        "inline_count": len(grid_inlines),
        "crossline_count": len(grid_crosslines),
        "coverage": round(min(1.0, unique_cells / max(1, len(grid_inlines) * len(grid_crosslines))), 4),
        "min_time_ms": round(float(np.min(flat)), 3),
        "max_time_ms": round(float(np.max(flat)), 3),
        "mean_time_ms": round(float(np.mean(flat)), 3),
        "method": interpolation,
        "anisotropy_ratio": float(anisotropy_ratio or 1.0),
        "azimuth_deg": float(azimuth_deg or 0.0),
        **({"kriging": kriging_info} if kriging_info else {}),
    }
    return {
        "grid": grid,
        "inlines": [int(value) for value in grid_inlines],
        "crosslines": [int(value) for value in grid_crosslines],
        "sample_interval_ms": float(index["sample_interval_ms"]),
        "inline_spacing_m": inline_spacing_m,
        "crossline_spacing_m": crossline_spacing_m,
        "stats": stats,
    }

def _convex_hull(points: list[dict[str, Any]]) -> list[dict[str, float]]:
    values = sorted({(float(point["inline"]), float(point["crossline"])) for point in points})
    if len(values) == 1:
        inline, crossline = values[0]
        return [
            {"inline": inline - 0.5, "crossline": crossline - 0.5},
            {"inline": inline + 0.5, "crossline": crossline - 0.5},
            {"inline": inline + 0.5, "crossline": crossline + 0.5},
            {"inline": inline - 0.5, "crossline": crossline + 0.5},
        ]
    if len(values) == 2:
        (inline_a, crossline_a), (inline_b, crossline_b) = values
        length = math.hypot(inline_b - inline_a, crossline_b - crossline_a) or 1.0
        offset_inline = -(crossline_b - crossline_a) / length * 0.5
        offset_crossline = (inline_b - inline_a) / length * 0.5
        return [
            {"inline": inline_a - offset_inline, "crossline": crossline_a - offset_crossline},
            {"inline": inline_b - offset_inline, "crossline": crossline_b - offset_crossline},
            {"inline": inline_b + offset_inline, "crossline": crossline_b + offset_crossline},
            {"inline": inline_a + offset_inline, "crossline": crossline_a + offset_crossline},
        ]

    def cross(origin, a, b):
        return (a[0] - origin[0]) * (b[1] - origin[1]) - (a[1] - origin[1]) * (b[0] - origin[0])

    lower: list[tuple[int, int]] = []
    for value in values:
        while len(lower) >= 2 and cross(lower[-2], lower[-1], value) <= 0:
            lower.pop()
        lower.append(value)
    upper: list[tuple[int, int]] = []
    for value in reversed(values):
        while len(upper) >= 2 and cross(upper[-2], upper[-1], value) <= 0:
            upper.pop()
        upper.append(value)
    hull = lower[:-1] + upper[:-1]
    if len(hull) < 3:
        inline_a, crossline_a = hull[0]
        inline_b, crossline_b = hull[-1]
        length = math.hypot(inline_b - inline_a, crossline_b - crossline_a) or 1.0
        offset_inline = -(crossline_b - crossline_a) / length * 0.5
        offset_crossline = (inline_b - inline_a) / length * 0.5
        return [
            {"inline": inline_a - offset_inline, "crossline": crossline_a - offset_crossline},
            {"inline": inline_b - offset_inline, "crossline": crossline_b - offset_crossline},
            {"inline": inline_b + offset_inline, "crossline": crossline_b + offset_crossline},
            {"inline": inline_a + offset_inline, "crossline": crossline_a + offset_crossline},
        ]
    return [{"inline": float(inline), "crossline": float(crossline)} for inline, crossline in hull]

def _throw_estimate(
    matrix: np.ndarray,
    labels: list[int],
    crossline: float,
    sample: float,
    sample_step: int,
    sample_interval_ms: float,
) -> dict[str, float] | None:
    """Estimate vertical offset from cross-correlation across the fault plane."""
    if matrix.shape[0] < 5 or matrix.shape[1] < 9 or not labels:
        return None
    position = min(range(len(labels)), key=lambda index: abs(labels[index] - float(crossline)))
    offset = 2
    left, right = position - offset, position + offset
    if left < 0 or right >= matrix.shape[0]:
        offset = 1
        left, right = position - offset, position + offset
    if left < 0 or right >= matrix.shape[0]:
        return None
    ns = matrix.shape[1]
    center = int(round(float(sample) / max(1, int(sample_step))))
    radius = 6
    start = max(0, center - radius)
    end = min(ns, center + radius + 1)
    if end - start < radius + 2:
        return None
    max_lag = min(12, max(1, ns // 4))
    best_score = -2.0
    best_lag = 0
    for lag in range(-max_lag, max_lag + 1):
        other_start = start + lag
        other_end = end + lag
        if other_start < 0 or other_end > ns:
            continue
        score = _correlation(matrix[left, start:end], matrix[right, other_start:other_end])
        if score > best_score:
            best_score = score
            best_lag = lag
    if best_score < 0.35:
        return None
    step_ms = float(sample_step) * float(sample_interval_ms)
    return {
        "throw_ms": round(abs(best_lag) * step_ms, 3),
        "lag_ms": round(best_lag * step_ms, 3),
        "score": round(float(best_score), 4),
    }

def _link_geometry(
    points: list[dict[str, int]],
    segments: list[dict[str, Any]],
    sample_interval_ms: float,
    inline_spacing_m: float | None,
    crossline_spacing_m: float | None,
    velocity_m_s: float | None = None,
    layers: list[dict[str, float]] | None = None,
    velocity_model_id: int | None = None,
) -> tuple[dict[str, Any], list[dict[str, int]]]:
    inline_values = np.asarray([point["inline"] for point in points], dtype=float)
    crossline_values = np.asarray([point["crossline"] for point in points], dtype=float)
    sample_values = np.asarray([point["sample"] for point in points], dtype=float)
    design = np.column_stack([inline_values, crossline_values, np.ones(len(points))])
    coefficients, *_ = np.linalg.lstsq(design, sample_values, rcond=None)
    prediction = design @ coefficients
    rms_ms = float(np.sqrt(np.mean((prediction - sample_values) ** 2)) * sample_interval_ms)
    throws = [
        float(segment["throw"]["throw_ms"])
        for segment in segments
        if segment.get("throw") is not None
    ]
    def convert(values: np.ndarray) -> np.ndarray:
        if velocity_m_s is not None:
            return time_to_depth_ms(values, "constant", velocity_m_s, [])
        if layers:
            return time_to_depth_ms(values, "layers", None, layers)
        return values

    depth_values = convert(sample_values)
    depth_coefficients, *_ = np.linalg.lstsq(design, depth_values, rcond=None)
    depth_prediction = design @ depth_coefficients
    depth_rms = float(np.sqrt(np.mean((depth_prediction - depth_values) ** 2)))
    depth_throws: list[float] = []
    if velocity_m_s is not None or layers:
        for segment in segments:
            throw = segment.get("throw") or {}
            lag = throw.get("lag_ms")
            if lag is None:
                continue
            center = float(segment["sample"])
            depth_throws.append(abs(float(convert(np.asarray([center + lag]))[0]) - float(convert(np.asarray([center]))[0])))
    geometry: dict[str, Any] = {
        "point_count": len(points),
        "inline_span": int(inline_values.max() - inline_values.min()),
        "crossline_span": int(crossline_values.max() - crossline_values.min()),
        "vertical_extent_ms": round(float(sample_values.max() - sample_values.min()) * sample_interval_ms, 3),
        "throw_ms": round(float(np.median(throws)), 3) if throws else None,
        "throw_range_ms": [round(min(throws), 3), round(max(throws), 3)] if throws else [],
        "throw_sections": len(throws),
        "dip_inline_ms_per_line": round(float(coefficients[0]) * sample_interval_ms, 4),
        "dip_crossline_ms_per_line": round(float(coefficients[1]) * sample_interval_ms, 4),
        "plane_rms_ms": round(rms_ms, 3),
        "dip_basis": "time",
        "dip_angle_deg": None,
        "inline_spacing_m": inline_spacing_m,
        "crossline_spacing_m": crossline_spacing_m,
        "domain": "time",
        "velocity_model_id": velocity_model_id,
        "throw_m": None,
        "throw_range_m": [],
        "dip_inline_m_per_line": None,
        "dip_crossline_m_per_line": None,
        "plane_rms_m": None,
    }
    if velocity_m_s is not None or layers:
        geometry.update({
            "domain": "depth",
            "dip_basis": "depth",
            "throw_m": round(float(np.median(depth_throws)), 3) if depth_throws else None,
            "throw_range_m": [round(min(depth_throws), 3), round(max(depth_throws), 3)] if depth_throws else [],
            "dip_inline_m_per_line": round(float(depth_coefficients[0]), 4),
            "dip_crossline_m_per_line": round(float(depth_coefficients[1]), 4),
            "plane_rms_m": round(depth_rms, 3),
        })
        if inline_spacing_m and crossline_spacing_m:
            gradient_inline = float(depth_coefficients[0]) / float(inline_spacing_m)
            gradient_crossline = float(depth_coefficients[1]) / float(crossline_spacing_m)
            geometry["dip_angle_deg"] = round(
                float(np.degrees(np.arctan(np.hypot(gradient_inline, gradient_crossline)))),
                3,
            )
    return geometry, _convex_hull(points)

def link_faults_3d(
    content: bytes,
    index: dict[str, Any],
    threshold: float = 0.35,
    min_points: int = 8,
    max_faults: int = 20,
    max_sections: int = 12,
    crossline_tolerance: float = 3.0,
    sample_tolerance: float = 16.0,
    inline_spacing_m: float | None = None,
    crossline_spacing_m: float | None = None,
    velocity_m_s: float | None = None,
    layers: list[dict[str, float]] | None = None,
    velocity_model_id: int | None = None,
) -> list[dict[str, Any]]:
    """Detect faults on sampled inline sections and link them across inlines."""
    inlines = index.get("trace_inlines", [])
    crosslines = index.get("trace_crosslines", [])
    unique_inlines = sorted(set(int(value) for value in inlines))
    if len(unique_inlines) < 2:
        return []
    limit = max(1, min(int(max_sections), len(unique_inlines)))
    if len(unique_inlines) > limit:
        positions = np.linspace(0, len(unique_inlines) - 1, limit).round().astype(int)
        sampled = [unique_inlines[int(pos)] for pos in sorted(set(positions.tolist()))]
    else:
        sampled = unique_inlines
    spacing = 1.0
    if len(sampled) > 1:
        gaps = [b - a for a, b in zip(sampled, sampled[1:])]
        spacing = float(np.median(gaps)) if gaps else 1.0

    segments: list[dict[str, Any]] = []
    for inline in sampled:
        positions = [pos for pos, value in enumerate(inlines) if int(value) == inline]
        if len(positions) < 3:
            continue
        order = sorted(range(len(positions)), key=lambda pos: int(crosslines[positions[pos]]))
        positions = [positions[pos] for pos in order]
        labels = [int(crosslines[pos]) for pos in positions]
        matrix = read_indexed_traces(content, index, positions)
        view = _section_view(matrix, labels=labels, max_traces=600, max_samples=600)
        sampled_matrix = np.asarray(view["data"], dtype=float)
        faults = detect_faults(
            sampled_matrix,
            threshold=threshold,
            min_points=min_points,
            max_faults=max_faults,
        )
        for fault in faults:
            points = []
            for pick in fault["picks"]:
                pos = max(0, min(len(view["labels"]) - 1, int(pick["trace"])))
                points.append({
                    "inline": int(inline),
                    "crossline": int(view["labels"][pos]),
                    "sample": int(pick["sample"]) * int(view["sample_step"]),
                })
            if not points:
                continue
            segments.append({
                "inline": int(inline),
                "points": points,
                "crossline": float(np.mean([point["crossline"] for point in points])),
                "sample": float(np.mean([point["sample"] for point in points])),
                "score": float(fault.get("score") or 0.0),
                "size": int(fault.get("size") or len(points)),
                "throw": _throw_estimate(
                    sampled_matrix,
                    view["labels"],
                    float(np.mean([point["crossline"] for point in points])),
                    float(np.mean([point["sample"] for point in points])),
                    int(view["sample_step"]),
                    float(index["sample_interval_ms"]),
                ),
            })

    links: list[dict[str, Any]] = []
    for segment in sorted(segments, key=lambda item: item["inline"]):
        best = None
        best_distance = None
        for link in links:
            last = link["_last"]
            gap = segment["inline"] - last["inline"]
            if gap <= 0 or gap > max(1.0, spacing * 1.6):
                continue
            dx = abs(segment["crossline"] - last["crossline"])
            dy = abs(segment["sample"] - last["sample"])
            if dx > float(crossline_tolerance) or dy > float(sample_tolerance):
                continue
            distance = dx + dy / max(1.0, float(sample_tolerance))
            if best_distance is None or distance < best_distance:
                best, best_distance = link, distance
        if best is None:
            links.append({"_last": segment, "segments": [segment]})
        else:
            best["segments"].append(segment)
            best["_last"] = segment

    results = []
    for link in links:
        points = [point for segment in link["segments"] for point in segment["points"]]
        if len(link["segments"]) < 2 or not points:
            continue
        inline_values = [segment["inline"] for segment in link["segments"]]
        geometry, polygon = _link_geometry(
            points,
            link["segments"],
            float(index["sample_interval_ms"]),
            inline_spacing_m,
            crossline_spacing_m,
            velocity_m_s=velocity_m_s,
            layers=layers,
            velocity_model_id=velocity_model_id,
        )
        results.append({
            "name": "3D Fault",
            "color": "#f85149",
            "points": points,
            "polygon": polygon,
            "geometry": geometry,
            "score": float(np.mean([segment["score"] for segment in link["segments"]])),
            "inline_start": int(min(inline_values)),
            "inline_end": int(max(inline_values)),
            "crossline_center": float(np.mean([point["crossline"] for point in points])),
            "sample_center": float(np.mean([point["sample"] for point in points])),
            "section_count": len(link["segments"]),
        })
    results.sort(key=lambda item: (item["inline_start"], item["crossline_center"]))
    for index, item in enumerate(results):
        item["name"] = f"3D Fault {index + 1}"
    return results

def _window(trace: np.ndarray, center: int, radius: int) -> np.ndarray:
    start = center - radius
    end = center + radius + 1
    if start < 0 or end > len(trace):
        chunk = np.zeros(radius * 2 + 1, dtype=np.float64)
        lo = max(0, start)
        hi = min(len(trace), end)
        chunk[lo - start:hi - start] = trace[lo:hi]
        return chunk
    return np.asarray(trace[start:end], dtype=np.float64)


def _correlation(a: np.ndarray, b: np.ndarray) -> float:
    a = np.nan_to_num(a, nan=0.0)
    b = np.nan_to_num(b, nan=0.0)
    denom = float(np.linalg.norm(a) * np.linalg.norm(b))
    if denom <= 1e-12:
        return -1.0
    return float(np.dot(a, b) / denom)


def auto_track(
    matrix: np.ndarray,
    seed_trace: int,
    seed_sample: int,
    window: int = 8,
    search_radius: int = 12,
) -> dict:
    """Track a reflection across traces with normalized cross-correlation."""
    nt, ns = matrix.shape
    w = max(1, int(window))
    radius = max(1, int(search_radius))
    seed_trace = max(0, min(nt - 1, int(seed_trace)))
    seed_sample = max(w, min(ns - w - 1, int(seed_sample)))
    picks: dict[int, int] = {seed_trace: seed_sample}
    scores: list[float] = []

    def _walk(direction: int) -> None:
        prev_trace, prev_sample = seed_trace, seed_sample
        current = prev_trace + direction
        while 0 <= current < nt:
            a = _window(matrix[prev_trace], prev_sample, w)
            best_score, best_sample = -2.0, prev_sample
            low = max(w, prev_sample - radius)
            high = min(ns - w - 1, prev_sample + radius)
            for cand in range(low, high + 1):
                b = _window(matrix[current], cand, w)
                score = _correlation(a, b)
                if score > best_score:
                    best_score, best_sample = score, cand
            if best_score < 0.05:
                break
            picks[current] = best_sample
            scores.append(best_score)
            prev_trace, prev_sample = current, best_sample
            current += direction

    _walk(1)
    _walk(-1)
    ordered = [{"trace": idx, "sample": picks[idx]} for idx in sorted(picks)]
    return {
        "picks": ordered,
        "confidence": float(np.mean(scores)) if scores else 0.0,
        "trace_count": len(ordered),
    }


def detect_faults(
    matrix: np.ndarray,
    threshold: float = 0.35,
    min_points: int = 8,
    max_faults: int = 20,
) -> list[dict]:
    """Find low-coherence, vertically connected segments as fault candidates."""
    nt, ns = matrix.shape
    if nt < 3 or ns < 3:
        return []
    w = 3
    if ns <= 2 * w:
        return []
    left = np.lib.stride_tricks.sliding_window_view(matrix[:-1], 2 * w + 1, axis=1)
    right = np.lib.stride_tricks.sliding_window_view(matrix[1:], 2 * w + 1, axis=1)
    num = np.sum(left * right, axis=2)
    den = np.sqrt(np.sum(left * left, axis=2) * np.sum(right * right, axis=2))
    coherence = np.divide(num, den, out=np.ones_like(num), where=den > 1e-12)
    energy = np.sqrt(np.sum(left * left, axis=2) + np.sum(right * right, axis=2))
    full = np.ones((nt - 1, ns), dtype=np.float64)
    full[:, w:w + coherence.shape[1]] = coherence
    energy_full = np.zeros((nt - 1, ns), dtype=np.float64)
    energy_full[:, w:w + energy.shape[1]] = energy
    energy_floor = 0.05 * float(np.max(energy)) if energy.size else 0.0
    candidates = (full < float(threshold)) & (energy_full > energy_floor)
    visited = np.zeros_like(candidates, dtype=bool)
    components: list[list[tuple[int, int]]] = []
    for start_t in range(candidates.shape[0]):
        for start_s in range(candidates.shape[1]):
            if not candidates[start_t, start_s] or visited[start_t, start_s]:
                continue
            stack = [(start_t, start_s)]
            visited[start_t, start_s] = True
            points: list[tuple[int, int]] = []
            while stack:
                t, sample = stack.pop()
                points.append((t, sample))
                for dt, ds in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                    nt2, ns2 = t + dt, sample + ds
                    if 0 <= nt2 < candidates.shape[0] and 0 <= ns2 < candidates.shape[1]:
                        if candidates[nt2, ns2] and not visited[nt2, ns2]:
                            visited[nt2, ns2] = True
                            stack.append((nt2, ns2))
            if len(points) >= max(2, int(min_points)):
                components.append(points)

    components.sort(key=len, reverse=True)
    faults = []
    for index, points in enumerate(components[: max(1, int(max_faults))]):
        by_trace: dict[int, list[int]] = {}
        for t, sample in points:
            by_trace.setdefault(t, []).append(sample)
        picks = [
            {"trace": int(t), "sample": int(np.median(samples))}
            for t, samples in sorted(by_trace.items())
        ]
        if not picks:
            continue
        score = float(np.clip(1.0 - np.mean([full[t, s] for t, s in points]), 0.0, 2.0))
        faults.append({
            "name": f"Fault {index + 1}",
            "color": "#f85149",
            "picks": picks,
            "score": score,
            "size": len(points),
        })
    return faults
