"""Simple microscopic crowd model for the two-week crowd-management sprint."""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from .dbact_transfer import DBACTTransferController
from .guidance_controller import GuidanceController
from .guider_model import GuiderModel, initialize_guiders
from .types import (
    GuiderState,
    PedestrianState,
    SimulationConfig,
    SimulationHistory,
    limit_norm,
    unit,
)


@dataclass
class StepInfo:
    time: float
    evacuated_count: int
    active_count: int


class CrowdEnvironment:
    """A compact Social-Force-like environment.

    This simulator is intentionally minimal. It is designed to test whether the
    group-level cargo-guidance idea can be transferred to crowd guidance before
    adding hybrid modeling, CBF, LLM planning, or exclusion queues.
    """

    def __init__(self, config: SimulationConfig, guided: bool = False) -> None:
        self.config = config
        self.guided = bool(guided)
        self.rng = np.random.default_rng(config.seed)
        self.time = 0.0
        self.pedestrians = self._initialize_pedestrians()
        self.guiders: list[GuiderState] = initialize_guiders(config.guiders, config.room) if guided else []
        self.guider_model = GuiderModel(config.guiders, config.room)
        self.guidance_controller = GuidanceController(config.guiders.guidance_strength)
        self.transfer_controller = DBACTTransferController(config.room, config.guiders)
        self.history = SimulationHistory()
        self._record()

    def _initialize_pedestrians(self) -> list[PedestrianState]:
        cfg = self.config.pedestrians
        room = self.config.room
        pedestrians: list[PedestrianState] = []
        for pid in range(cfg.count):
            pos = self.rng.normal(cfg.spawn_center, cfg.spawn_std)
            pos = room.clip_inside(pos, margin=cfg.radius + 0.04)
            desired_speed = max(0.3, float(self.rng.normal(cfg.desired_speed_mean, cfg.desired_speed_std)))
            compliance = float(np.clip(self.rng.normal(cfg.compliance_mean, cfg.compliance_std), 0.0, 1.0))
            pedestrians.append(
                PedestrianState(
                    pid=pid,
                    position=pos,
                    velocity=np.zeros(2, dtype=float),
                    desired_speed=desired_speed,
                    radius=cfg.radius,
                    compliance=compliance,
                )
            )
        return pedestrians

    @property
    def positions(self) -> np.ndarray:
        return np.vstack([p.position for p in self.pedestrians])

    @property
    def velocities(self) -> np.ndarray:
        return np.vstack([p.velocity for p in self.pedestrians])

    @property
    def evacuated(self) -> np.ndarray:
        return np.asarray([p.evacuated for p in self.pedestrians], dtype=bool)

    def _goal_force(self, p: PedestrianState) -> np.ndarray:
        ped_cfg = self.config.pedestrians
        desired_dir = unit(self.config.room.exit_center - p.position, fallback=np.array([1.0, 0.0]))
        desired_velocity = p.desired_speed * desired_dir
        return (desired_velocity - p.velocity) / max(ped_cfg.relaxation_time, 1e-6)

    def _pedestrian_repulsion_forces(self) -> np.ndarray:
        cfg = self.config.pedestrians
        positions = self.positions
        evacuated = self.evacuated
        forces = np.zeros_like(positions)
        active_idx = np.where(~evacuated)[0]
        for local_i, i in enumerate(active_idx):
            pi = positions[i]
            for j in active_idx[local_i + 1 :]:
                delta = pi - positions[j]
                dist = float(np.linalg.norm(delta))
                if dist < 1e-9 or dist > cfg.interaction_range:
                    continue
                direction = delta / dist
                overlap_like = max(0.0, 2.0 * cfg.radius - dist)
                magnitude = cfg.repulsion_strength * np.exp((2.0 * cfg.radius - dist) / max(cfg.repulsion_range, 1e-6))
                magnitude += 6.0 * overlap_like
                force = magnitude * direction
                forces[i] += force
                forces[j] -= force
        return forces

    def _wall_force(self, p: PedestrianState) -> np.ndarray:
        room = self.config.room
        cfg = self.config.pedestrians
        force = np.zeros(2, dtype=float)
        margin = cfg.wall_margin

        # Left wall.
        if p.position[0] < margin:
            force[0] += cfg.wall_repulsion_strength * (margin - p.position[0]) / margin

        # Right wall, except the exit opening.
        if p.position[0] > room.width - margin and not room.inside_exit_opening(p.position[1]):
            force[0] -= cfg.wall_repulsion_strength * (p.position[0] - (room.width - margin)) / margin

        # Bottom and top walls.
        if p.position[1] < margin:
            force[1] += cfg.wall_repulsion_strength * (margin - p.position[1]) / margin
        if p.position[1] > room.height - margin:
            force[1] -= cfg.wall_repulsion_strength * (p.position[1] - (room.height - margin)) / margin
        return force

    def _apply_boundary_and_exit(self, p: PedestrianState) -> None:
        room = self.config.room
        radius = p.radius
        # Evacuation occurs after crossing the right wall within the exit opening.
        if p.position[0] >= room.width and room.inside_exit_opening(p.position[1]):
            p.evacuated = True
            p.evacuation_time = self.time
            p.velocity[:] = 0.0
            return

        # Regular wall constraints. Right wall is open only at the exit.
        if p.position[0] < radius:
            p.position[0] = radius
            p.velocity[0] = max(0.0, p.velocity[0])
        if p.position[0] > room.width - radius and not room.inside_exit_opening(p.position[1]):
            p.position[0] = room.width - radius
            p.velocity[0] = min(0.0, p.velocity[0])
        p.position[1] = float(np.clip(p.position[1], radius, room.height - radius))
        if p.position[1] <= radius:
            p.velocity[1] = max(0.0, p.velocity[1])
        elif p.position[1] >= room.height - radius:
            p.velocity[1] = min(0.0, p.velocity[1])

    def step(self) -> StepInfo:
        cfg = self.config.pedestrians
        dt = self.config.dt
        if self.guided and self.guiders:
            self.transfer_controller.update_guiders(self.guiders, self.positions, self.evacuated)
            self.guider_model.step(self.guiders, dt)

        repulsion_forces = self._pedestrian_repulsion_forces()
        for idx, p in enumerate(self.pedestrians):
            if p.evacuated:
                continue
            force = self._goal_force(p)
            force += repulsion_forces[idx]
            force += self._wall_force(p)
            if self.guided:
                force += self.guidance_controller.force_on(p, self.guiders)
            if cfg.noise_std > 0:
                force += self.rng.normal(0.0, cfg.noise_std, size=2)
            p.velocity = limit_norm(p.velocity + dt * force, cfg.max_speed)
            p.position = p.position + dt * p.velocity
            self._apply_boundary_and_exit(p)

        self.time += dt
        self._record()
        return StepInfo(time=self.time, evacuated_count=int(self.evacuated.sum()), active_count=int((~self.evacuated).sum()))

    def run(self, steps: int | None = None) -> SimulationHistory:
        n_steps = self.config.steps if steps is None else int(steps)
        for _ in range(n_steps):
            self.step()
            if self.evacuated.all():
                break
        return self.history

    def _record(self) -> None:
        guider_positions = None
        if self.guiders:
            guider_positions = np.vstack([g.position for g in self.guiders])
        self.history.append(self.time, self.positions, self.velocities, self.evacuated, guider_positions)


def run_simulation(config: SimulationConfig, guided: bool = False, steps: int | None = None) -> SimulationHistory:
    env = CrowdEnvironment(config=config, guided=guided)
    return env.run(steps=steps)
