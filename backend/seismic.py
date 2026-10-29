"""Minimal SEG-Y reader for uploaded 2D/3D lines.

Supports IBM 4-byte float (format 1) and IEEE 4-byte float (format 5). It is a
screening reader: the first `max_traces` traces are kept and the section is
decimated before it is sent to the browser.
"""

from __future__ import annotations

import math
from typing import Any

import numpy as np

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
    }


def section_payload(parsed: dict[str, Any], max_traces: int = 500, max_samples: int = 500) -> dict[str, Any]:
    matrix = parsed["matrix"]
    nt, ns = matrix.shape
    trace_step = max(1, math.ceil(nt / max(1, max_traces)))
    sample_step = max(1, math.ceil(ns / max(1, max_samples)))
    view = matrix[::trace_step, ::sample_step]
    finite = view[np.isfinite(view)]
    return {
        "trace_count": int(view.shape[0]),
        "sample_count": int(view.shape[1]),
        "trace_step": int(trace_step),
        "sample_step": int(sample_step),
        "original_trace_count": int(nt),
        "original_sample_count": int(ns),
        "sample_interval_ms": parsed["sample_interval_ms"],
        "amplitude_min": float(np.min(finite)) if len(finite) else 0.0,
        "amplitude_max": float(np.max(finite)) if len(finite) else 0.0,
        "data": np.round(view, 6).tolist(),
    }
