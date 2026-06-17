"""Density-aware DBACT-style guidance for visible split-flow experiments."""
from __future__ import annotations

import numpy as np

from .types import GuiderConfig, GuiderState, PedestrianState, RoomConfig, unit


class DensityDBACTController:
    """Heuristic density-aware guider placement for two-exit bottleneck scenes."""

    def __init__(self, room: RoomConfig, config: GuiderConfig, pressure_radius: float = 3.0) -> None:
        self.room = room
        self.config = config
        self.pressure_radius = float(pressure_radius)
        self.switch_margin = 1.2
        self.pressure_weight = 4.0
        self.redirect_fraction = 0.46
        self.smoothing = 0.35

    def exit_pressures(self, pedestrians: list[PedestrianState]) -> np.ndarray:
        active_positions = np.asarray([p.position for p in pedestrians if not p.evacuated], dtype=float)
        exits = self.room.all_exits
        pressures = np.zeros(len(exits), dtype=float)
        if active_positions.size == 0:
            return pressures
        for idx, exit_cfg in enumerate(exits):
            center = exit_cfg.center(self.room.width)
            dist = np.linalg.norm(active_positions - center, axis=1)
            pressures[idx] = float(np.sum(dist < self.pressure_radius) / max(exit_cfg.width, 1e-6))
        return pressures

    def update_pedestrian_targets(self, pedestrians: list[PedestrianState]) -> int:
        exits = self.room.all_exits
        if len(exits) < 2:
            return 0
        pressures = self.exit_pressures(pedestrians)
        overloaded = int(np.argmax(pressures))
        underused = int(np.argmin(pressures))
        if pressures[overloaded] < 1.0:
            overloaded = 0
            underused = 1

        active = [p for p in pedestrians if not p.evacuated]
        if not active:
            return 0
        ys = np.asarray([p.position[1] for p in active], dtype=float)
        threshold = float(np.quantile(ys, 1.0 - self.redirect_fraction))
        switches = 0
        alt_center = exits[underused].center(self.room.width)
        for p in active:
            current = int(np.clip(p.target_exit_id, 0, len(exits) - 1))
            current_center = exits[current].center(self.room.width)
            current_cost = np.linalg.norm(current_center - p.position) + self.pressure_weight * pressures[current]
            alt_cost = np.linalg.norm(alt_center - p.position) + self.pressure_weight * pressures[underused]
            should_switch = p.position[1] >= threshold or alt_cost + self.switch_margin < current_cost
            if should_switch and p.compliance > 0.25:
                if p.target_exit_id != underused:
                    switches += 1
                p.target_exit_id = underused
            elif current != overloaded and p.position[1] < threshold * 0.85:
                p.target_exit_id = overloaded
        return switches

    def update_guiders(self, guiders: list[GuiderState], pedestrians: list[PedestrianState]) -> None:
        exits = self.room.all_exits
        if not guiders:
            return
        if len(exits) < 2:
            target_exit = 0
        else:
            pressures = self.exit_pressures(pedestrians)
            target_exit = int(np.argmin(pressures))
            if target_exit == 0 and len(exits) > 1 and pressures[0] >= pressures[1]:
                target_exit = 1
        active_positions = np.asarray([p.position for p in pedestrians if not p.evacuated], dtype=float)
        if active_positions.size == 0:
            active_positions = np.array([[self.room.width * 0.35, self.room.height * 0.5]], dtype=float)
        center = active_positions.mean(axis=0)
        exit_center = exits[target_exit].center(self.room.width)
        direction = unit(exit_center - center, fallback=np.array([1.0, 0.0]))
        lateral = np.array([-direction[1], direction[0]], dtype=float)

        line_start = center + np.array([1.8, 0.0]) - 1.8 * lateral
        line_end = center + 0.45 * (exit_center - center) + 1.8 * lateral
        for idx, guider in enumerate(guiders):
            t = 0.0 if len(guiders) == 1 else idx / (len(guiders) - 1)
            desired = (1.0 - t) * line_start + t * line_end
            desired = self.room.clip_inside(desired, margin=0.35)
            guider.target_position = (1.0 - self.smoothing) * guider.target_position + self.smoothing * desired
            guider.desired_direction = direction
            guider.assigned_exit_id = target_exit
            guider.influence_radius = max(guider.influence_radius, self.config.influence_radius * 1.35)
