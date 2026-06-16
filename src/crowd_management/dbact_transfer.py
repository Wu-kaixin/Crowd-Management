"""Minimal transfer of DBACT/cargo-guidance logic to crowd guidance.

The cargo algorithm is not copied literally. Instead, this module transfers the
structural idea: estimate a group-level state, place mobile guiders around the
rear/side boundary of that group, and let their guidance field influence the
active crowd toward the target exit.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from .types import GuiderConfig, GuiderState, RoomConfig, limit_norm, perpendicular, unit


@dataclass(frozen=True)
class CrowdEstimate:
    center: np.ndarray
    radius: float
    target_direction: np.ndarray
    active_count: int


class DBACTTransferController:
    """Group-level controller that assigns guider target positions."""

    def __init__(self, room: RoomConfig, config: GuiderConfig) -> None:
        self.room = room
        self.config = config

    def estimate_crowd(self, positions: np.ndarray, evacuated: np.ndarray) -> CrowdEstimate:
        active_positions = positions[~evacuated]
        if len(active_positions) == 0:
            center = self.room.exit_center.copy()
            direction = np.array([1.0, 0.0], dtype=float)
            return CrowdEstimate(center=center, radius=0.1, target_direction=direction, active_count=0)
        center = active_positions.mean(axis=0)
        spread = np.linalg.norm(active_positions - center, axis=1)
        radius = max(float(np.percentile(spread, 65)), 0.6)
        direction = unit(self.room.exit_center - center, fallback=np.array([1.0, 0.0]))
        return CrowdEstimate(center=center, radius=radius, target_direction=direction, active_count=len(active_positions))


    def estimate_crowd_state(self, positions: np.ndarray, evacuated: np.ndarray) -> CrowdEstimate:
        return self.estimate_crowd(positions, evacuated)

    @staticmethod
    def compute_crowd_center(positions: np.ndarray, evacuated: np.ndarray | None = None) -> np.ndarray:
        active = positions if evacuated is None else positions[~evacuated]
        if len(active) == 0:
            return np.zeros(2, dtype=float)
        return np.asarray(active, dtype=float).mean(axis=0)

    @staticmethod
    def compute_crowd_radius(positions: np.ndarray, center: np.ndarray, evacuated: np.ndarray | None = None) -> float:
        active = positions if evacuated is None else positions[~evacuated]
        if len(active) == 0:
            return 0.1
        spread = np.linalg.norm(active - center, axis=1)
        return max(float(np.percentile(spread, 65)), 0.6)

    def compute_target_direction(self, center: np.ndarray) -> np.ndarray:
        return unit(self.room.exit_center - center, fallback=np.array([1.0, 0.0]))

    def compute_guider_target_positions(self, estimate: CrowdEstimate, n_guiders: int) -> tuple[np.ndarray, np.ndarray]:
        return self.compute_targets(estimate, n_guiders)

    def compute_targets(self, estimate: CrowdEstimate, n_guiders: int) -> tuple[np.ndarray, np.ndarray]:
        if n_guiders <= 0:
            return np.zeros((0, 2), dtype=float), np.zeros((0, 2), dtype=float)
        direction = estimate.target_direction
        lateral = perpendicular(direction)
        rear_distance = self.config.target_distance_gain * estimate.radius
        rear_center = estimate.center - rear_distance * direction

        # Offsets are symmetric around the rear center; this is the crowd analog
        # of positioning robots around a cargo boundary.
        if n_guiders == 1:
            offsets = [0.0]
        else:
            raw = np.linspace(-(n_guiders - 1) / 2.0, (n_guiders - 1) / 2.0, n_guiders)
            offsets = (raw * self.config.side_spacing).tolist()

        targets = []
        desired_dirs = []
        for offset in offsets:
            target = rear_center + offset * lateral
            # Keep guiders inside the room and not too close to the exit opening.
            target = self.room.clip_inside(target, margin=0.25)
            if target[0] > self.room.width - self.config.min_distance_from_exit:
                target[0] = self.room.width - self.config.min_distance_from_exit
            targets.append(target)
            desired_dirs.append(direction)
        return np.asarray(targets, dtype=float), np.asarray(desired_dirs, dtype=float)

    def update_guiders(self, guiders: list[GuiderState], positions: np.ndarray, evacuated: np.ndarray) -> CrowdEstimate:
        estimate = self.estimate_crowd(positions, evacuated)
        targets, desired_dirs = self.compute_targets(estimate, len(guiders))
        for guider, target, desired_dir in zip(guiders, targets, desired_dirs):
            guider.target_position = target
            guider.desired_direction = unit(desired_dir, fallback=np.array([1.0, 0.0]))
        return estimate

    @staticmethod
    def emergency_slowdown_velocity(velocity: np.ndarray, max_speed: float) -> np.ndarray:
        """Small reusable safety helper for future CBF-style extensions."""
        return limit_norm(velocity, max_speed)
