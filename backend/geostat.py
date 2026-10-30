"""Ordinary kriging for sparse horizon and fault picks."""

from __future__ import annotations

import math
from typing import Any

import numpy as np


def _variogram(distance, range_m, sill, nugget, model):
    distance = np.asarray(distance, dtype=float)
    span = max(float(range_m), 1e-9)
    scaled = np.clip(distance / span, 0.0, 1.0)
    if model == "exponential":
        shape = 1.0 - np.exp(-3.0 * scaled)
    elif model == "gaussian":
        shape = 1.0 - np.exp(-3.0 * scaled ** 2)
    else:
        shape = 1.5 * scaled - 0.5 * scaled ** 3
    return float(nugget) + (float(sill) - float(nugget)) * shape


def _transform(points: np.ndarray, ratio: float, azimuth_deg: float) -> np.ndarray:
    angle = math.radians(float(azimuth_deg))
    cos_angle, sin_angle = math.cos(angle), math.sin(angle)
    x = points[:, 0]
    y = points[:, 1]
    rotated_x = x * cos_angle + y * sin_angle
    rotated_y = (-x * sin_angle + y * cos_angle) * float(ratio)
    return np.column_stack([rotated_x, rotated_y, points[:, 2]])


def _covariance_matrix(distances: np.ndarray, range_m: float, sill: float, nugget: float, model: str) -> np.ndarray:
    """Stationary covariance between sample pairs from inter-sample distances."""
    return float(sill) - _variogram(distances, range_m, sill, nugget, model)

def _covariance_vector(distances: np.ndarray, range_m: float, sill: float, nugget: float, model: str) -> np.ndarray:
    """Covariance between one estimation node and each neighbour sample."""
    return np.asarray(float(sill) - _variogram(distances, range_m, sill, nugget, model), dtype=float)

def krige_grid(
    points: np.ndarray,
    grid_inlines: list[float],
    grid_crosslines: list[float],
    variogram_model: str = "spherical",
    range_m: float | None = None,
    sill: float | None = None,
    nugget: float = 0.0,
    anisotropy_ratio: float = 1.0,
    azimuth_deg: float = 0.0,
    max_neighbors: int = 16,
) -> tuple[list[list[float]], dict[str, Any]]:
    values = np.asarray(points, dtype=float)
    if values.ndim != 2 or values.shape[1] != 3 or len(values) < 3:
        raise ValueError("kriging needs at least three 2D picks with values")
    if variogram_model not in {"spherical", "exponential", "gaussian"}:
        raise ValueError("variogram model must be spherical, exponential or gaussian")
    ratio = max(0.05, float(anisotropy_ratio))
    transformed = _transform(values, ratio, azimuth_deg)
    coordinates = transformed[:, :2]
    z_values = transformed[:, 2]
    if range_m is None:
        span = max(
            float(np.ptp(coordinates[:, 0])),
            float(np.ptp(coordinates[:, 1])),
        )
        range_m = max(span / 3.0, 1.0)
    if sill is None:
        sill = float(np.var(z_values))
    sill = max(float(sill), 1e-9)
    nugget = max(0.0, min(float(nugget), sill * 0.99))
    # Local neighborhood: each node solves ordinary kriging against its
    # nearest samples only, so sparse far-field picks cannot distort the
    # local estimate. Distances are measured in the anisotropy-transformed
    # frame, matching the covariance model below.
    neighbors = max(1, min(int(max_neighbors), len(values)))
    node_coordinates = np.asarray(
        [[inline, crossline] for inline in grid_inlines for crossline in grid_crosslines],
        dtype=float,
    )
    node_transformed = _transform(
        np.column_stack([node_coordinates, np.zeros(len(node_coordinates))]),
        ratio,
        azimuth_deg,
    )[:, :2]
    estimates = np.zeros(len(node_coordinates), dtype=float)
    kriging_variance = np.zeros(len(node_coordinates), dtype=float)
    for node_index, node in enumerate(node_transformed):
        distances = np.sqrt(np.sum((coordinates - node) ** 2, axis=1))
        if len(distances) > neighbors:
            chosen = np.argpartition(distances, neighbors - 1)[:neighbors]
        else:
            chosen = np.arange(len(distances))
        local_coords = coordinates[chosen]
        local_distances = distances[chosen]
        local_values = z_values[chosen]
        pair = np.sqrt(
            np.sum((local_coords[:, None, :] - local_coords[None, :, :]) ** 2, axis=-1)
        )
        pair_cov = _covariance_matrix(pair, range_m, sill, nugget, variogram_model)
        pair_cov = np.asarray(pair_cov, dtype=float)
        node_cov = _covariance_vector(local_distances, range_m, sill, nugget, variogram_model)
        system = np.ones((len(chosen) + 1, len(chosen) + 1), dtype=float)
        system[:-1, :-1] = pair_cov + np.eye(len(chosen)) * 1e-9
        system[-1, -1] = 0.0
        target = np.ones(len(chosen) + 1, dtype=float)
        target[:-1] = node_cov
        try:
            weights = np.linalg.solve(system, target)
            estimates[node_index] = float(weights[:-1] @ local_values)
            kriging_variance[node_index] = max(0.0, float(pair_cov[0, 0] - weights[:-1] @ node_cov))
        except np.linalg.LinAlgError:
            weights = 1.0 / (local_distances + 1e-9)
            weights /= weights.sum()
            estimates[node_index] = float(weights @ local_values)
    grid = [
        [round(float(estimates[row * len(grid_crosslines) + column]), 4) for column in range(len(grid_crosslines))]
        for row in range(len(grid_inlines))
    ]
    return grid, {
        "reader": "ordinary_kriging",
        "variogram_model": variogram_model,
        "range": round(float(range_m), 4),
        "sill": round(float(sill), 6),
        "nugget": round(float(nugget), 6),
        "anisotropy_ratio": ratio,
        "azimuth_deg": float(azimuth_deg),
        "max_neighbors": neighbors,
        "mean_kriging_variance": round(float(np.mean(kriging_variance)), 6),
    }
