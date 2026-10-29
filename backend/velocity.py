"""Time-depth conversion for project velocity models."""

from __future__ import annotations

import json
from typing import Any

import numpy as np


def normalize_model(data: dict[str, Any]) -> dict[str, Any]:
    name = str(data.get("name") or "").strip()
    if not name:
        raise ValueError("name is required")
    kind = str(data.get("kind") or "constant").lower()
    if kind == "constant":
        try:
            velocity = float(data.get("velocity_m_s"))
        except (TypeError, ValueError):
            raise ValueError("velocity_m_s is required for constant models")
        if not 500.0 <= velocity <= 8000.0:
            raise ValueError("velocity_m_s must be between 500 and 8000")
        return {"name": name, "kind": kind, "velocity_m_s": velocity, "layers": []}
    if kind == "layers":
        raw = data.get("layers") or []
        if not isinstance(raw, list) or len(raw) < 2:
            raise ValueError("layer models need at least two layers")
        layers = []
        for index, layer in enumerate(raw):
            if not isinstance(layer, dict):
                raise ValueError(f"layers[{index}] must be an object")
            try:
                top_ms = float(layer.get("top_ms"))
                velocity = float(layer.get("velocity_m_s"))
            except (TypeError, ValueError):
                raise ValueError(f"layers[{index}] requires top_ms and velocity_m_s")
            if top_ms < 0:
                raise ValueError(f"layers[{index}].top_ms must be non-negative")
            if not 500.0 <= velocity <= 8000.0:
                raise ValueError(f"layers[{index}].velocity_m_s must be between 500 and 8000")
            layers.append({"top_ms": top_ms, "velocity_m_s": velocity})
        layers.sort(key=lambda item: item["top_ms"])
        if layers[0]["top_ms"] != 0:
            raise ValueError("the first layer must start at top_ms 0")
        for previous, current in zip(layers, layers[1:]):
            if current["top_ms"] <= previous["top_ms"]:
                raise ValueError("layer top_ms values must be strictly increasing")
        return {"name": name, "kind": kind, "velocity_m_s": None, "layers": layers}
    raise ValueError("kind must be constant or layers")


def layers_from_json(raw: str) -> list[dict[str, float]]:
    try:
        value = json.loads(raw or "[]")
    except json.JSONDecodeError:
        return []
    return value if isinstance(value, list) else []


def time_to_depth_ms(
    times_ms: np.ndarray | list[float],
    kind: str,
    velocity_m_s: float | None,
    layers: list[dict[str, float]],
) -> np.ndarray:
    """Convert two-way time in ms to depth in metres."""
    values = np.asarray(times_ms, dtype=float)
    if kind == "constant":
        velocity = float(velocity_m_s or 0.0)
        return velocity * values / 2000.0
    depth = np.zeros_like(values, dtype=float)
    for index, layer in enumerate(layers):
        top = float(layer["top_ms"])
        next_top = float(layers[index + 1]["top_ms"]) if index + 1 < len(layers) else float("inf")
        interval = np.clip(values - top, 0.0, next_top - top)
        depth += float(layer["velocity_m_s"]) * interval / 2000.0
    return depth
