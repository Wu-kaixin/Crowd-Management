"""Geometry helpers for README media scenes."""

from __future__ import annotations

import numpy as np

from crowd_management.estimation import BoundaryV2Config


def closed_curve(points: np.ndarray) -> np.ndarray:
    return np.vstack([points, points[0]])


def polygon_for_shape(shape: str) -> np.ndarray:
    if shape == "u_shape":
        return np.array(
            [[2.0, 2.0], [8.0, 2.0], [8.0, 7.5], [6.6, 7.5], [6.6, 3.7], [3.4, 3.7], [3.4, 7.5], [2.0, 7.5]],
            dtype=float,
        )
    if shape == "c_shape":
        return np.array(
            [[2.0, 2.0], [8.0, 2.0], [8.0, 3.4], [4.0, 3.4], [4.0, 6.1], [8.0, 6.1], [8.0, 7.5], [2.0, 7.5]],
            dtype=float,
        )
    raise ValueError(f"unsupported polygon shape: {shape}")


def inside_polygon(points: np.ndarray, polygon: np.ndarray) -> np.ndarray:
    x, y = points[:, 0], points[:, 1]
    inside = np.zeros(len(points), dtype=bool)
    previous = polygon[-1]
    for current in polygon:
        crosses = (current[1] > y) != (previous[1] > y)
        denominator = previous[1] - current[1]
        if abs(denominator) > 1.0e-15:
            crossing_x = (previous[0] - current[0]) * (y - current[1]) / denominator + current[0]
            inside ^= crosses & (x < crossing_x)
        previous = current
    return inside


def sample_polygon(polygon: np.ndarray, count: int, rng: np.random.Generator) -> np.ndarray:
    accepted: list[np.ndarray] = []
    total = 0
    while total < count:
        candidates = rng.uniform(np.min(polygon, axis=0), np.max(polygon, axis=0), size=(max(count, 64), 2))
        batch = candidates[inside_polygon(candidates, polygon)]
        accepted.append(batch)
        total += len(batch)
    return np.vstack(accepted)[:count]


def g6_observation(scenario: str, seed: int = 0, count: int = 120) -> np.ndarray:
    scenario_index = ("circle", "ellipse", "u_shape", "c_shape").index(scenario)
    rng = np.random.default_rng(1_000_003 + 1009 * int(seed) + 65_537 * scenario_index)
    if scenario == "circle":
        angles = rng.uniform(0.0, 2.0 * np.pi, count)
        radii = 2.0 * np.sqrt(rng.uniform(0.0, 1.0, count))
        return np.column_stack((5.0 + radii * np.cos(angles), 5.0 + radii * np.sin(angles)))
    if scenario == "ellipse":
        angles = rng.uniform(0.0, 2.0 * np.pi, count)
        radii = np.sqrt(rng.uniform(0.0, 1.0, count))
        return np.column_stack((5.0 + 2.5 * radii * np.cos(angles), 5.0 + 1.35 * radii * np.sin(angles)))
    return sample_polygon(polygon_for_shape(scenario), count, rng)


def boundary_config() -> BoundaryV2Config:
    return BoundaryV2Config(
        estimator="alpha",
        safety_distance=0.8,
        sample_spacing=0.08,
        room_size=(10.0, 10.0),
        room_margin=0.2,
        alpha_scale=2.5,
        bootstrap_samples=0,
    )
