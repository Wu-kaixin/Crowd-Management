"""Shared dataclasses and numerical helpers for the crowd-management sprint."""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np
import yaml

Array = np.ndarray


def as_vec2(value: Any, name: str = "vector") -> Array:
    """Convert an input value to a finite 2D NumPy vector."""
    arr = np.asarray(value, dtype=float)
    if arr.shape != (2,):
        raise ValueError(f"{name} must be a 2D vector, got shape {arr.shape}.")
    if not np.all(np.isfinite(arr)):
        raise ValueError(f"{name} must contain finite values.")
    return arr


def norm(vec: Array) -> float:
    return float(np.linalg.norm(vec))


def unit(vec: Array, fallback: Array | None = None) -> Array:
    """Return a unit vector, using fallback when the vector is too small."""
    n = norm(vec)
    if n < 1e-9:
        if fallback is None:
            return np.zeros(2, dtype=float)
        return unit(fallback)
    return np.asarray(vec, dtype=float) / n


def limit_norm(vec: Array, max_norm: float) -> Array:
    """Clip a vector to a maximum Euclidean norm."""
    n = norm(vec)
    if n <= max_norm or n < 1e-12:
        return np.asarray(vec, dtype=float)
    return np.asarray(vec, dtype=float) * (max_norm / n)


def perpendicular(vec: Array) -> Array:
    return np.array([-vec[1], vec[0]], dtype=float)


@dataclass(frozen=True)
class RoomConfig:
    width: float
    height: float
    exit_center_y: float
    exit_width: float
    exit_depth: float = 0.8

    @property
    def exit_center(self) -> Array:
        return np.array([self.width + self.exit_depth, self.exit_center_y], dtype=float)

    @property
    def exit_y_min(self) -> float:
        return self.exit_center_y - self.exit_width / 2.0

    @property
    def exit_y_max(self) -> float:
        return self.exit_center_y + self.exit_width / 2.0

    def inside_exit_opening(self, y: float) -> bool:
        return self.exit_y_min <= float(y) <= self.exit_y_max

    def clip_inside(self, pos: Array, margin: float = 0.05) -> Array:
        """Clip a point inside the room, leaving the exit side slightly open."""
        x = float(np.clip(pos[0], margin, self.width - margin))
        y = float(np.clip(pos[1], margin, self.height - margin))
        return np.array([x, y], dtype=float)


@dataclass(frozen=True)
class PedestrianConfig:
    count: int
    spawn_center: Array
    spawn_std: Array
    radius: float
    desired_speed_mean: float
    desired_speed_std: float
    max_speed: float
    compliance_mean: float
    compliance_std: float
    relaxation_time: float
    interaction_range: float
    repulsion_strength: float
    repulsion_range: float
    wall_repulsion_strength: float
    wall_margin: float
    noise_std: float = 0.0


@dataclass(frozen=True)
class GuiderConfig:
    count: int
    max_speed: float
    influence_radius: float
    guidance_strength: float
    target_distance_gain: float
    side_spacing: float
    min_distance_from_exit: float = 1.0


@dataclass(frozen=True)
class MetricsConfig:
    congestion_radius: float = 0.55
    near_collision_distance: float = 0.34


@dataclass(frozen=True)
class SimulationConfig:
    seed: int
    steps: int
    dt: float
    room: RoomConfig
    pedestrians: PedestrianConfig
    guiders: GuiderConfig
    metrics: MetricsConfig = field(default_factory=MetricsConfig)

    @classmethod
    def from_yaml(cls, path: str | Path) -> "SimulationConfig":
        with open(path, "r", encoding="utf-8") as f:
            raw = yaml.safe_load(f)
        room = RoomConfig(**raw["room"])
        ped_raw = dict(raw["pedestrians"])
        ped_raw["spawn_center"] = as_vec2(ped_raw["spawn_center"], "spawn_center")
        ped_raw["spawn_std"] = as_vec2(ped_raw["spawn_std"], "spawn_std")
        pedestrians = PedestrianConfig(**ped_raw)
        guiders = GuiderConfig(**raw["guiders"])
        metrics = MetricsConfig(**raw.get("metrics", {}))
        return cls(
            seed=int(raw.get("seed", 0)),
            steps=int(raw["steps"]),
            dt=float(raw["dt"]),
            room=room,
            pedestrians=pedestrians,
            guiders=guiders,
            metrics=metrics,
        )


@dataclass
class PedestrianState:
    pid: int
    position: Array
    velocity: Array
    desired_speed: float
    radius: float
    compliance: float
    evacuated: bool = False
    evacuation_time: float | None = None


@dataclass
class GuiderState:
    gid: int
    position: Array
    velocity: Array
    target_position: Array
    desired_direction: Array
    influence_radius: float


@dataclass
class SimulationHistory:
    positions: list[Array] = field(default_factory=list)
    velocities: list[Array] = field(default_factory=list)
    evacuated: list[Array] = field(default_factory=list)
    guider_positions: list[Array] = field(default_factory=list)
    times: list[float] = field(default_factory=list)

    def append(
        self,
        time: float,
        ped_positions: Array,
        ped_velocities: Array,
        ped_evacuated: Array,
        guider_positions: Array | None = None,
    ) -> None:
        self.times.append(float(time))
        self.positions.append(np.asarray(ped_positions, dtype=float).copy())
        self.velocities.append(np.asarray(ped_velocities, dtype=float).copy())
        self.evacuated.append(np.asarray(ped_evacuated, dtype=bool).copy())
        if guider_positions is not None:
            self.guider_positions.append(np.asarray(guider_positions, dtype=float).copy())

    def as_arrays(self) -> dict[str, Array]:
        data = {
            "times": np.asarray(self.times, dtype=float),
            "positions": np.asarray(self.positions, dtype=float),
            "velocities": np.asarray(self.velocities, dtype=float),
            "evacuated": np.asarray(self.evacuated, dtype=bool),
        }
        if self.guider_positions:
            data["guider_positions"] = np.asarray(self.guider_positions, dtype=float)
        return data
