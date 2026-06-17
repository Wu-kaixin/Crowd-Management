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
class ExitConfig:
    id: str
    center_y: float
    width: float
    depth: float = 0.8

    @property
    def y_min(self) -> float:
        return self.center_y - self.width / 2.0

    @property
    def y_max(self) -> float:
        return self.center_y + self.width / 2.0

    def center(self, room_width: float) -> Array:
        return np.array([room_width + self.depth, self.center_y], dtype=float)

    def inside_opening(self, y: float) -> bool:
        return self.y_min <= float(y) <= self.y_max


@dataclass(frozen=True)
class RoomConfig:
    width: float
    height: float
    exit_center_y: float
    exit_width: float
    exit_depth: float = 0.8
    exits: tuple[ExitConfig, ...] = ()

    @property
    def exit_center(self) -> Array:
        return self.exit_by_index(0).center(self.width)

    @property
    def exit_y_min(self) -> float:
        return self.exit_by_index(0).y_min

    @property
    def exit_y_max(self) -> float:
        return self.exit_by_index(0).y_max

    def inside_exit_opening(self, y: float) -> bool:
        return any(exit_cfg.inside_opening(y) for exit_cfg in self.all_exits)

    @property
    def all_exits(self) -> tuple[ExitConfig, ...]:
        if self.exits:
            return self.exits
        return (ExitConfig("main", self.exit_center_y, self.exit_width, self.exit_depth),)

    def exit_by_index(self, index: int) -> ExitConfig:
        exits = self.all_exits
        return exits[int(np.clip(index, 0, len(exits) - 1))]

    def exit_center_by_index(self, index: int) -> Array:
        return self.exit_by_index(index).center(self.width)

    def exit_index_for_y(self, y: float) -> int | None:
        for idx, exit_cfg in enumerate(self.all_exits):
            if exit_cfg.inside_opening(y):
                return idx
        return None

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
    exit_pressure_radius: float = 2.2


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

        if "simulation" in raw:
            return cls._from_sprint_yaml(raw)
        return cls._from_reference_yaml(raw)

    @classmethod
    def _from_reference_yaml(cls, raw: dict[str, Any]) -> "SimulationConfig":
        room_raw = dict(raw["room"])
        exits = _parse_exits(room_raw)
        if exits:
            primary = exits[0]
            room_raw["exit_center_y"] = primary.center_y
            room_raw["exit_width"] = primary.width
            room_raw["exit_depth"] = primary.depth
            room_raw["exits"] = exits
        room = RoomConfig(**room_raw)
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

    @classmethod
    def _from_sprint_yaml(cls, raw: dict[str, Any]) -> "SimulationConfig":
        room_raw = raw["room"]
        exit_raw = room_raw["exit"]
        sim_raw = raw["simulation"]
        crowd_raw = raw["crowd"]
        forces_raw = raw["forces"]
        guiders_raw = raw["guiders"]

        room = RoomConfig(
            width=float(room_raw["width"]),
            height=float(room_raw["height"]),
            exit_center_y=float(exit_raw["center"][1]),
            exit_width=float(exit_raw["width"]),
            exit_depth=float(exit_raw.get("radius", 0.8)),
            exits=_parse_sprint_exits(room_raw),
        )
        pedestrians = PedestrianConfig(
            count=int(sim_raw["pedestrian_count"]),
            spawn_center=as_vec2(crowd_raw["initial_center"], "initial_center"),
            spawn_std=as_vec2(crowd_raw["initial_spread"], "initial_spread"),
            radius=float(sim_raw["pedestrian_radius"]),
            desired_speed_mean=float(sim_raw["desired_speed_mean"]),
            desired_speed_std=float(sim_raw["desired_speed_std"]),
            max_speed=float(sim_raw["max_speed"]),
            compliance_mean=float(crowd_raw["compliance_mean"]),
            compliance_std=float(crowd_raw["compliance_std"]),
            relaxation_time=float(forces_raw.get("relaxation_time", 0.45)),
            interaction_range=float(forces_raw.get("interaction_range", max(0.9, forces_raw["repulsion_range"] * 2.0))),
            repulsion_strength=float(forces_raw.get("repulsion_strength", forces_raw["repulsion_gain"] * 30.0)),
            repulsion_range=float(forces_raw["repulsion_range"]),
            wall_repulsion_strength=float(forces_raw.get("wall_repulsion_strength", forces_raw["wall_gain"] * 18.0)),
            wall_margin=float(forces_raw["wall_range"]),
            noise_std=float(forces_raw.get("noise_std", 0.02)),
        )
        guiders = GuiderConfig(
            count=int(guiders_raw["count"]),
            max_speed=float(guiders_raw["max_speed"]),
            influence_radius=float(guiders_raw["influence_radius"]),
            guidance_strength=float(guiders_raw["influence_strength"]),
            target_distance_gain=float(guiders_raw["rear_distance_scale"]),
            side_spacing=float(guiders_raw["side_spacing"]),
            min_distance_from_exit=float(guiders_raw.get("min_distance_from_exit", 1.0)),
        )
        metrics = MetricsConfig(**raw.get("metrics", {}))
        return cls(
            seed=int(raw.get("seed", 0)),
            steps=int(sim_raw["steps"]),
            dt=float(sim_raw["dt"]),
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
    target_exit_id: int = 0
    evacuated_exit_id: int = -1


@dataclass
class GuiderState:
    gid: int
    position: Array
    velocity: Array
    target_position: Array
    desired_direction: Array
    influence_radius: float
    assigned_exit_id: int = 0


@dataclass
class SimulationHistory:
    positions: list[Array] = field(default_factory=list)
    velocities: list[Array] = field(default_factory=list)
    evacuated: list[Array] = field(default_factory=list)
    guider_positions: list[Array] = field(default_factory=list)
    guider_targets: list[Array] = field(default_factory=list)
    target_exit_ids: list[Array] = field(default_factory=list)
    evacuation_exit_ids: list[Array] = field(default_factory=list)
    times: list[float] = field(default_factory=list)

    def append(
        self,
        time: float,
        ped_positions: Array,
        ped_velocities: Array,
        ped_evacuated: Array,
        guider_positions: Array | None = None,
        guider_targets: Array | None = None,
        target_exit_ids: Array | None = None,
        evacuation_exit_ids: Array | None = None,
    ) -> None:
        self.times.append(float(time))
        self.positions.append(np.asarray(ped_positions, dtype=float).copy())
        self.velocities.append(np.asarray(ped_velocities, dtype=float).copy())
        self.evacuated.append(np.asarray(ped_evacuated, dtype=bool).copy())
        if guider_positions is not None:
            self.guider_positions.append(np.asarray(guider_positions, dtype=float).copy())
        if guider_targets is not None:
            self.guider_targets.append(np.asarray(guider_targets, dtype=float).copy())
        if target_exit_ids is not None:
            self.target_exit_ids.append(np.asarray(target_exit_ids, dtype=int).copy())
        if evacuation_exit_ids is not None:
            self.evacuation_exit_ids.append(np.asarray(evacuation_exit_ids, dtype=int).copy())

    def as_arrays(self) -> dict[str, Array]:
        data = {
            "times": np.asarray(self.times, dtype=float),
            "positions": np.asarray(self.positions, dtype=float),
            "velocities": np.asarray(self.velocities, dtype=float),
            "evacuated": np.asarray(self.evacuated, dtype=bool),
        }
        if self.guider_positions:
            data["guider_positions"] = np.asarray(self.guider_positions, dtype=float)
        if self.guider_targets:
            data["guider_targets"] = np.asarray(self.guider_targets, dtype=float)
        if self.target_exit_ids:
            data["target_exit_ids"] = np.asarray(self.target_exit_ids, dtype=int)
        if self.evacuation_exit_ids:
            data["evacuation_exit_ids"] = np.asarray(self.evacuation_exit_ids, dtype=int)
        return data


def _exit_from_raw(raw: dict[str, Any], index: int) -> ExitConfig:
    return ExitConfig(
        id=str(raw.get("id", raw.get("label", f"exit_{index}"))),
        center_y=float(raw["center"][1] if "center" in raw else raw["center_y"]),
        width=float(raw["width"]),
        depth=float(raw.get("radius", raw.get("depth", 0.8))),
    )


def _parse_sprint_exits(room_raw: dict[str, Any]) -> tuple[ExitConfig, ...]:
    if "exits" in room_raw:
        return tuple(_exit_from_raw(item, idx) for idx, item in enumerate(room_raw["exits"]))
    exits = [_exit_from_raw(room_raw["exit"], 0)]
    for idx, item in enumerate(room_raw.get("alternative_exits", []), start=1):
        exits.append(_exit_from_raw(item, idx))
    return tuple(exits)


def _parse_exits(room_raw: dict[str, Any]) -> tuple[ExitConfig, ...]:
    if "exits" not in room_raw:
        return ()
    exits = tuple(_exit_from_raw(item, idx) for idx, item in enumerate(room_raw.pop("exits")))
    room_raw.pop("alternative_exits", None)
    return exits
