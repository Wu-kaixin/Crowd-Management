"""Simple microscopic crowd model for the two-week crowd-management sprint."""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from .dbact_transfer import DBACTTransferController
from .density_dbact import DensityDBACTController
from .guidance_controller import GuidanceController
from .guider_model import GuiderModel, initialize_guiders
from ...types import (
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

    ROUTE_ONLY_MODES = {"nearest_exit", "balanced_exit_static", "density_only", "exit_pressure_only", "split_flow_only"}

    def __init__(self, config: SimulationConfig, guided: bool = False, guidance_mode: str = "dbact") -> None:
        self.config = config
        self.guided = bool(guided)
        self.guidance_mode = guidance_mode if self.guided else "none"
        if self.guidance_mode not in {"none", "dbact", "static", "random", "density_dbact", *self.ROUTE_ONLY_MODES}:
            raise ValueError(f"Unsupported guidance_mode: {guidance_mode}")
        self.rng = np.random.default_rng(config.seed)
        self.random_target_interval = 40
        self.step_index = 0
        self.time = 0.0
        self.pedestrians = self._initialize_pedestrians()
        self._configure_initial_exit_choices()
        use_guiders = guided and self.guidance_mode not in self.ROUTE_ONLY_MODES
        self.guiders: list[GuiderState] = initialize_guiders(config.guiders, config.room) if use_guiders else []
        self.guider_model = GuiderModel(config.guiders, config.room)
        self.guidance_controller = GuidanceController(config.guiders.guidance_strength)
        self.transfer_controller = DBACTTransferController(config.room, config.guiders)
        self.density_controller = DensityDBACTController(config.room, config.guiders, pressure_radius=config.metrics.exit_pressure_radius)
        self.route_switch_count = 0
        self.history = SimulationHistory()
        if self.guided:
            if self.guidance_mode == "static":
                self._configure_static_guiders()
            elif self.guidance_mode == "random":
                self._assign_random_guider_targets()
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

    def _configure_initial_exit_choices(self) -> None:
        if len(self.config.room.all_exits) <= 1:
            return
        if self.guidance_mode == "nearest_exit":
            for p in self.pedestrians:
                distances = [np.linalg.norm(exit_cfg.center(self.config.room.width) - p.position) for exit_cfg in self.config.room.all_exits]
                p.target_exit_id = int(np.argmin(distances))
        elif self.guidance_mode in {"balanced_exit_static", "split_flow_only"}:
            for p in self.pedestrians:
                p.target_exit_id = p.pid % len(self.config.room.all_exits)
        elif self.guidance_mode == "density_only":
            ys = np.asarray([p.position[1] for p in self.pedestrians], dtype=float)
            threshold = float(np.quantile(ys, 0.58))
            for p in self.pedestrians:
                p.target_exit_id = 1 if p.position[1] >= threshold else 0

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
        desired_dir = unit(self.config.room.exit_center_by_index(p.target_exit_id) - p.position, fallback=np.array([1.0, 0.0]))
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
        if p.position[0] > room.width - margin and room.exit_index_for_y(p.position[1]) is None:
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
        exit_idx = room.exit_index_for_y(p.position[1])
        if p.position[0] >= room.width and exit_idx is not None:
            p.evacuated = True
            p.evacuation_time = self.time
            p.evacuated_exit_id = exit_idx
            p.velocity[:] = 0.0
            return

        # Regular wall constraints. Right wall is open only at the exit.
        if p.position[0] < radius:
            p.position[0] = radius
            p.velocity[0] = max(0.0, p.velocity[0])
        if p.position[0] > room.width - radius and room.exit_index_for_y(p.position[1]) is None:
            p.position[0] = room.width - radius
            p.velocity[0] = min(0.0, p.velocity[0])
        p.position[1] = float(np.clip(p.position[1], radius, room.height - radius))
        if p.position[1] <= radius:
            p.velocity[1] = max(0.0, p.velocity[1])
        elif p.position[1] >= room.height - radius:
            p.velocity[1] = min(0.0, p.velocity[1])

    def _configure_static_guiders(self) -> None:
        if not self.guiders:
            return
        center = self.transfer_controller.compute_crowd_center(self.positions, self.evacuated)
        direction = self.transfer_controller.compute_target_direction(center)
        lateral = np.array([-direction[1], direction[0]], dtype=float)
        anchor = center + 0.35 * (self.config.room.exit_center - center)
        if len(self.guiders) == 1:
            offsets = [0.0]
        else:
            raw = np.linspace(-(len(self.guiders) - 1) / 2.0, (len(self.guiders) - 1) / 2.0, len(self.guiders))
            offsets = (raw * self.config.guiders.side_spacing).tolist()
        for guider, offset in zip(self.guiders, offsets):
            pos = self.config.room.clip_inside(anchor + offset * lateral, margin=0.25)
            guider.position = pos
            guider.target_position = pos.copy()
            guider.velocity[:] = 0.0
            guider.desired_direction = direction

    def _assign_random_guider_targets(self) -> None:
        for guider in self.guiders:
            target = np.array(
                [
                    self.rng.uniform(0.5, self.config.room.width - 0.8),
                    self.rng.uniform(0.5, self.config.room.height - 0.5),
                ],
                dtype=float,
            )
            guider.target_position = target
            guider.desired_direction = unit(self.config.room.exit_center - target, fallback=np.array([1.0, 0.0]))

    def _update_guiders(self) -> None:
        if not self.guided:
            return
        if self.guidance_mode == "density_only":
            self._update_density_only_targets()
            return
        if self.guidance_mode == "exit_pressure_only":
            self.route_switch_count += self.density_controller.update_pedestrian_targets(self.pedestrians)
            return
        if self.guidance_mode in {"nearest_exit", "balanced_exit_static", "split_flow_only"}:
            return
        if not self.guiders:
            return
        if self.guidance_mode == "dbact":
            self.transfer_controller.update_guiders(self.guiders, self.positions, self.evacuated)
            self.guider_model.step(self.guiders, self.config.dt)
        elif self.guidance_mode == "random":
            if self.step_index % self.random_target_interval == 0:
                self._assign_random_guider_targets()
            self.guider_model.step(self.guiders, self.config.dt)
        elif self.guidance_mode == "static":
            for guider in self.guiders:
                guider.velocity[:] = 0.0
        elif self.guidance_mode == "density_dbact":
            self.route_switch_count += self.density_controller.update_pedestrian_targets(self.pedestrians)
            self.density_controller.update_guiders(self.guiders, self.pedestrians)
            self.guider_model.step(self.guiders, self.config.dt)

    def _update_density_only_targets(self) -> None:
        if len(self.config.room.all_exits) <= 1:
            return
        active = [p for p in self.pedestrians if not p.evacuated]
        if not active:
            return
        positions = np.asarray([p.position for p in active], dtype=float)
        local_counts = np.zeros(len(active), dtype=float)
        radius = max(1.2, self.config.metrics.congestion_radius * 2.2)
        for i, pos in enumerate(positions):
            dist = np.linalg.norm(positions - pos, axis=1)
            local_counts[i] = float(np.sum((dist < radius) & (dist > 1e-9)))
        dense_threshold = float(np.quantile(local_counts, 0.56))
        y_threshold = float(np.quantile(positions[:, 1], 0.55))
        for p, density in zip(active, local_counts):
            if density >= dense_threshold and p.position[1] >= y_threshold and p.compliance > 0.2:
                p.target_exit_id = 1

    def step(self) -> StepInfo:
        cfg = self.config.pedestrians
        dt = self.config.dt
        self._update_guiders()

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
        self.step_index += 1
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
        guider_targets = None
        if self.guiders:
            guider_positions = np.vstack([g.position for g in self.guiders])
            guider_targets = np.vstack([g.target_position for g in self.guiders])
        target_exit_ids = np.asarray([p.target_exit_id for p in self.pedestrians], dtype=int)
        evacuation_exit_ids = np.asarray([p.evacuated_exit_id for p in self.pedestrians], dtype=int)
        self.history.append(
            self.time,
            self.positions,
            self.velocities,
            self.evacuated,
            guider_positions,
            guider_targets,
            target_exit_ids,
            evacuation_exit_ids,
        )


def run_simulation(
    config: SimulationConfig,
    guided: bool = False,
    steps: int | None = None,
    guidance_mode: str = "dbact",
) -> SimulationHistory:
    env = CrowdEnvironment(config=config, guided=guided, guidance_mode=guidance_mode)
    return env.run(steps=steps)
