"""Arbitrary seismic lines and fence segments."""

from __future__ import annotations

import math
from typing import Any

import numpy as np

try:
    from seismic import _section_view, read_indexed_traces
except ImportError:
    from backend.seismic import _section_view, read_indexed_traces


def arbitrary_line(
    content: bytes,
    index: dict[str, Any],
    start: tuple[float, float],
    end: tuple[float, float],
    max_traces: int = 600,
    max_samples: int = 600,
    inline_spacing_m: float | None = None,
    crossline_spacing_m: float | None = None,
) -> dict[str, Any]:
    inlines = np.asarray(index.get("trace_inlines") or [], dtype=float)
    crosslines = np.asarray(index.get("trace_crosslines") or [], dtype=float)
    if len(inlines) == 0 or len(inlines) != len(crosslines):
        raise ValueError("SEG-Y trace headers are incomplete")
    start_inline, start_crossline = float(start[0]), float(start[1])
    end_inline, end_crossline = float(end[0]), float(end[1])
    span = max(abs(end_inline - start_inline), abs(end_crossline - start_crossline))
    steps = max(2, min(int(max_traces), int(math.ceil(span)) + 1))
    positions: list[int] = []
    for fraction in np.linspace(0.0, 1.0, steps):
        target_inline = start_inline + (end_inline - start_inline) * fraction
        target_crossline = start_crossline + (end_crossline - start_crossline) * fraction
        position = int(np.argmin((inlines - target_inline) ** 2 + (crosslines - target_crossline) ** 2))
        if not positions or positions[-1] != position:
            positions.append(position)
    if len(positions) < 2:
        raise ValueError("arbitrary line does not cross enough traces")
    matrix = read_indexed_traces(content, index, positions)
    labels: list[int] = []
    if inline_spacing_m and crossline_spacing_m:
        distance = 0.0
        for index_position, position in enumerate(positions):
            if index_position:
                previous = positions[index_position - 1]
                di = (float(inlines[position]) - float(inlines[previous])) * float(inline_spacing_m)
                dx = (float(crosslines[position]) - float(crosslines[previous])) * float(crossline_spacing_m)
                distance += math.hypot(di, dx)
            labels.append(int(round(distance)))
        label_name = "distance_m"
    else:
        labels = list(range(len(positions)))
        label_name = "trace_index"
    section = _section_view(
        matrix,
        labels=labels,
        max_traces=max(2, int(max_traces)),
        max_samples=max(2, int(max_samples)),
        sample_interval_ms=index["sample_interval_ms"],
    )
    section["labels"] = [int(value) for value in labels[:: int(section["trace_step"])]]
    section["label_name"] = label_name
    section["start"] = {"inline": start_inline, "crossline": start_crossline}
    section["end"] = {"inline": end_inline, "crossline": end_crossline}
    section["trace_positions"] = positions
    return section
