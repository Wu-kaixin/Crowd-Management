"""Simple projection-based safety helpers for guide deployment."""
from __future__ import annotations

import numpy as np

from ..types import Array, unit


def enforce_minimum_separation(points: Array, min_distance: float, iterations: int = 8) -> Array:
    """Push guide points apart when they are closer than min_distance."""
    out = np.asarray(points, dtype=float).copy()
    for _ in range(max(0, int(iterations))):
        for i in range(len(out)):
            for j in range(i + 1, len(out)):
                delta = out[i] - out[j]
                dist = float(np.linalg.norm(delta))
                if dist >= min_distance or dist < 1e-9:
                    continue
                direction = unit(delta, fallback=np.array([1.0, 0.0]))
                shift = 0.5 * (min_distance - dist) * direction
                out[i] += shift
                out[j] -= shift
    return out


def clip_to_room(points: Array, room_size: Array, margin: float = 0.25) -> Array:
    room = np.asarray(room_size, dtype=float)
    return np.clip(np.asarray(points, dtype=float), margin, room - margin)


def enforce_distance_from_cloud(points: Array, cloud: Array, center: Array, min_distance: float, iterations: int = 12) -> Array:
    """Push guide points outward until they clear the observed crowd cloud."""
    out = np.asarray(points, dtype=float).copy()
    cloud_arr = np.asarray(cloud, dtype=float)
    center_arr = np.asarray(center, dtype=float)
    for _ in range(max(0, int(iterations))):
        changed = False
        for i, point in enumerate(out):
            dist = np.linalg.norm(cloud_arr - point, axis=1)
            nearest = float(dist.min()) if len(dist) else float("inf")
            if nearest >= min_distance:
                continue
            direction = unit(point - center_arr, fallback=point - cloud_arr[int(np.argmin(dist))])
            out[i] = point + direction * (min_distance - nearest + 1e-3)
            changed = True
        if not changed:
            break
    return out
