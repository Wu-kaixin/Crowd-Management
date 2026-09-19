"""Centralized gather-then-surround controller (Step 2 CURRENT)."""

from __future__ import annotations

from dataclasses import dataclass, field, replace

import numpy as np
from scipy.optimize import linear_sum_assignment

from ..assignment import assign_guides_to_targets
from ..periodic_arc_cvt import PeriodicArcCVTConfig, plan_periodic_arc_coverage
from ..resources import ResourcePolicy
from ...crowd.observation import crowd_observation_from_points
from ...estimation import BoundaryEstimateV2
from ...geometry.deployment_curve import DeploymentCurve, build_deployment_curve
from ...scenarios.rectangular import RectangularScenario
from ...types import Array
from .motion import AttractiveRendezvousMotion
from .protocols import GatherTarget, GatherThenSurroundPlan


@dataclass(frozen=True)
class GatherThenSurroundConfig:
    """Tunables for the two-phase dispersed gather → surround pipeline."""

    gather_radius: float = 2.8
    gather_fraction: float = 0.88
    max_gather_steps: int = 450
    max_surround_steps: int = 500
    guide_standoff: float = 4.0
    guide_gain: float = 1.6
    guide_max_speed: float = 1.2
    surround_rmse_tol: float = 0.12
    surround_hold_steps: int = 15
    safety_distance: float = 0.85
    wall_margin: float = 0.25
    pedestrian_speed: float = 0.95
    # Outer ring sits outside the current crowd extent during gather.
    gather_ring_margin: float = 1.25


@dataclass
class CentralGatherThenSurroundController:
    """Gather dispersed pedestrians to a rendezvous, then ABCG-surround.

    Gather: people walk to the rendezvous disk; guides hold fixed angular slots
    on an *outer* ring (never the empty centre). Surround: re-estimate one
    deployment ring on the gathered cloud and track those targets.
    """

    scene: RectangularScenario
    containment_cfg: object
    gather_cfg: GatherThenSurroundConfig = field(default_factory=GatherThenSurroundConfig)
    motion: AttractiveRendezvousMotion | None = None

    def __post_init__(self) -> None:
        if self.motion is None:
            self.motion = AttractiveRendezvousMotion(
                speed=self.gather_cfg.pedestrian_speed,
                wall_margin=self.gather_cfg.wall_margin,
            )
        self._phase = "gather"
        self._step = 0
        self._phase_step = 0
        self._gather_center: Array | None = None
        self._gather_radius = float(self.gather_cfg.gather_radius)
        self._guide_slot: Array | None = None
        self._gather_ring_targets: Array | None = None
        self._surround_targets: Array | None = None
        self._guide_to_target: Array | None = None
        self._boundary: BoundaryEstimateV2 | None = None
        self._hold = 0
        self._diagnostics: dict[str, object] = {}

    def reset(self, crowd_positions: Array, guide_positions: Array) -> GatherThenSurroundPlan:
        crowd = np.asarray(crowd_positions, dtype=float)
        guides = np.asarray(guide_positions, dtype=float)
        if crowd.ndim != 2 or crowd.shape[1] != 2 or len(crowd) < 3:
            raise ValueError("crowd_positions must be finite (N, 2) with N >= 3.")
        if guides.ndim != 2 or guides.shape[1] != 2 or len(guides) < 1:
            raise ValueError("guide_positions must be finite (M, 2).")
        self._phase = "gather"
        self._step = 0
        self._phase_step = 0
        self._gather_center = np.mean(crowd, axis=0)
        self._gather_radius = float(self.gather_cfg.gather_radius)
        # One-shot Hungarian slots: each guide owns the nearest ring seat for the
        # whole gather phase (no per-step reassignment, no diameter cuts through centre).
        self._guide_slot = self._assign_ring_slots(guides, len(guides))
        self._gather_ring_targets = self._compute_gather_ring(crowd, len(guides))
        self._surround_targets = None
        self._guide_to_target = None
        self._boundary = None
        self._hold = 0
        self._diagnostics = {
            "initial_crowd_count": int(len(crowd)),
            "guide_count": int(len(guides)),
            "gather_center": self._gather_center.tolist(),
        }
        return self._plan(crowd, guides)

    def step(
        self,
        crowd_positions: Array,
        guide_positions: Array,
        dt: float,
    ) -> tuple[Array, GatherThenSurroundPlan]:
        crowd = np.asarray(crowd_positions, dtype=float)
        guides = np.asarray(guide_positions, dtype=float)
        if self._gather_center is None:
            self.reset(crowd, guides)
        assert self._gather_center is not None
        del dt
        self._step += 1
        self._phase_step += 1

        if self._phase == "gather":
            self._gather_ring_targets = self._compute_gather_ring(crowd, len(guides))
            velocities = self._p_control(guides, self._gather_ring_targets)
            plan = self._plan(crowd, guides)
            if self._gathered(crowd):
                if self._begin_surround(crowd, guides):
                    self._phase = "surround"
                    self._phase_step = 0
                    self._hold = 0
                    plan = self._plan(crowd, guides)
            elif self._phase_step >= int(self.gather_cfg.max_gather_steps):
                # Last chance: try surround even if fraction is short.
                if self._begin_surround(crowd, guides):
                    self._phase = "surround"
                    self._phase_step = 0
                    self._hold = 0
                    plan = self._plan(crowd, guides)
                else:
                    self._phase = "done"
                    plan = replace(plan, phase="done", status="GATHER_TIMEOUT")
            return velocities, plan

        if self._phase == "surround":
            velocities = self._surround_guide_velocities(guides)
            rmse = self._tracking_rmse(guides)
            if rmse is not None and rmse <= float(self.gather_cfg.surround_rmse_tol):
                self._hold += 1
            else:
                self._hold = 0
            if self._hold >= int(self.gather_cfg.surround_hold_steps):
                self._phase = "done"
                return velocities, replace(self._plan(crowd, guides), phase="done", status="DONE")
            if self._phase_step >= int(self.gather_cfg.max_surround_steps):
                self._phase = "done"
                return velocities, replace(self._plan(crowd, guides), phase="done", status="SURROUND_TIMEOUT")
            return velocities, self._plan(crowd, guides)

        return np.zeros_like(guides), replace(self._plan(crowd, guides), phase="done", status="DONE")

    def advance_crowd(self, crowd_positions: Array, guide_positions: Array, dt: float) -> Array:
        assert self._gather_center is not None and self.motion is not None
        freeze = self._phase != "gather"
        return self.motion.step(
            crowd_positions,
            guide_positions,
            dt,
            rendezvous=self._gather_center,
            scene=self.scene,
            freeze=freeze,
        )

    @property
    def boundary(self) -> BoundaryEstimateV2 | None:
        return self._boundary

    def _gathered(self, crowd: Array) -> bool:
        assert self._gather_center is not None
        dist = np.linalg.norm(crowd - self._gather_center[None, :], axis=1)
        fraction = float(np.mean(dist <= self._gather_radius))
        self._diagnostics["gather_fraction"] = fraction
        self._diagnostics["gather_max_radius"] = float(np.max(dist)) if len(dist) else 0.0
        return fraction >= float(self.gather_cfg.gather_fraction)

    def _ring_points(self, ring: float, guide_count: int) -> Array:
        assert self._gather_center is not None
        angles = 2.0 * np.pi * np.arange(guide_count) / float(guide_count)
        return self._gather_center[None, :] + ring * np.column_stack((np.cos(angles), np.sin(angles)))

    def _assign_ring_slots(self, guides: Array, guide_count: int) -> Array:
        """Return guide_index → slot_index minimizing travel (Hungarian, once)."""
        assert self._gather_center is not None
        # Provisional radius for matching only; real radius updates each gather step.
        provisional = max(
            float(self.gather_cfg.guide_standoff),
            float(self.gather_cfg.gather_radius) + float(self.gather_cfg.safety_distance),
        )
        seats = self._ring_points(provisional, guide_count)
        cost = np.linalg.norm(guides[:, None, :] - seats[None, :, :], axis=2)
        rows, cols = linear_sum_assignment(cost)
        slot = np.empty(guide_count, dtype=int)
        slot[rows] = cols
        return slot

    def _compute_gather_ring(self, crowd: Array, guide_count: int) -> Array:
        assert self._gather_center is not None and self._guide_slot is not None
        crowd_radius = float(np.max(np.linalg.norm(crowd - self._gather_center[None, :], axis=1)))
        # Keep guides OUTSIDE the people; never collapse to the empty centre.
        ring = max(
            float(self.gather_cfg.guide_standoff),
            float(self.gather_cfg.gather_radius) + float(self.gather_cfg.safety_distance),
            crowd_radius + float(self.gather_cfg.gather_ring_margin),
        )
        # Clip ring so targets stay inside the workspace.
        lower, upper = self.scene.feasible_workspace_bounds(self.gather_cfg.wall_margin)
        max_fit = float(
            min(
                self._gather_center[0] - lower[0],
                upper[0] - self._gather_center[0],
                self._gather_center[1] - lower[1],
                upper[1] - self._gather_center[1],
            )
        )
        ring = min(ring, max(max_fit - 0.05, float(self.gather_cfg.gather_radius) + 0.5))
        self._diagnostics["gather_ring_radius"] = ring
        ring_points = self._ring_points(ring, guide_count)
        # Map guide i → its fixed seat (identity preserved; radial shrink only).
        assigned = ring_points[self._guide_slot]
        assigned = np.clip(assigned, lower, upper)
        return assigned

    def _disk_polyline(self, radius: float, samples: int = 64) -> Array:
        assert self._gather_center is not None
        angles = np.linspace(0.0, 2.0 * np.pi, samples, endpoint=False)
        return self._gather_center[None, :] + radius * np.column_stack((np.cos(angles), np.sin(angles)))

    def _radial_crowd_curve(self, crowd: Array, sample_spacing: float) -> Array:
        """Circle covering every observed point (post-gather compact blob)."""
        center = np.mean(crowd, axis=0)
        radius = float(np.max(np.linalg.norm(crowd - center[None, :], axis=1))) + 0.05
        count = max(48, int(np.ceil(2.0 * np.pi * radius / max(sample_spacing, 0.05))))
        angles = np.linspace(0.0, 2.0 * np.pi, count, endpoint=False)
        return center[None, :] + radius * np.column_stack((np.cos(angles), np.sin(angles)))

    def _begin_surround(self, crowd: Array, guides: Array) -> bool:
        cfg = self.containment_cfg
        observation = crowd_observation_from_points(crowd)
        sample_spacing = float(cfg.boundary_v2.sample_spacing)
        # Radial envelope covering EVERY observed point. Alpha-shape after a
        # partial gather often hugs the dense core and leaves outliers outside.
        crowd_curve = self._radial_crowd_curve(observation.positions, sample_spacing)
        method = "radial_post_gather"
        deployment = build_deployment_curve(
            crowd_curve,
            float(self.gather_cfg.safety_distance),
            crowd_points=observation.positions,
            workspace=self.scene,
            wall_margin=float(self.gather_cfg.wall_margin),
            sample_spacing=sample_spacing,
            min_crowd_clearance=None,
        )
        if not isinstance(deployment, DeploymentCurve):
            self._diagnostics["surround_boundary_status"] = deployment.status
            return False
        count = len(deployment.curve_points)
        boundary = BoundaryEstimateV2(
            curve_points=np.asarray(crowd_curve, dtype=float),
            offset_points=deployment.curve_points,
            arc_s=deployment.arc_s,
            length=deployment.length,
            tangents=deployment.tangents,
            outward_normals=deployment.outward_normals,
            uncertainty=np.zeros(count, dtype=float),
            confidence=np.ones(count, dtype=float),
            component_count=1,
            topology_valid=True,
            method=method,
            version=2,
            diagnostics={"deployment_status": "VALID", "phase": "surround", "method": method},
        )
        resource = ResourcePolicy(cfg.resource_policy).decide(boundary.length, len(guides))
        active = max(int(resource.active_count), min(len(guides), int(cfg.resource_policy.m_min)))
        plan = plan_periodic_arc_coverage(boundary, active, PeriodicArcCVTConfig())
        if plan.status != "VALID" or not plan.converged:
            self._diagnostics["surround_plan_status"] = plan.status
            return False
        assignment = assign_guides_to_targets(guides, plan.target_xy, cfg.assignment)
        if assignment.status != "VALID":
            self._diagnostics["surround_assignment_status"] = assignment.status
            return False
        self._boundary = boundary
        self._surround_targets = np.asarray(plan.target_xy, dtype=float)
        self._guide_to_target = np.asarray(assignment.guide_to_target, dtype=int)
        self._diagnostics.update(
            {
                "surround_boundary_status": "VALID",
                "surround_resource_status": resource.status,
                "surround_plan_status": plan.status,
                "surround_assignment_status": assignment.status,
                "surround_active_count": int(active),
                "deployment_length": float(boundary.length),
            }
        )
        return True

    def _surround_guide_velocities(self, guides: Array) -> Array:
        if self._surround_targets is None or self._guide_to_target is None:
            return np.zeros_like(guides)
        targets = np.zeros_like(guides)
        active = self._guide_to_target >= 0
        targets[active] = self._surround_targets[self._guide_to_target[active]]
        # Idle reserves hold last gather-ring slot if present.
        if np.any(~active) and self._gather_ring_targets is not None:
            targets[~active] = self._gather_ring_targets[~active]
        velocities = self._p_control(guides, targets)
        return velocities

    def _p_control(self, guides: Array, targets: Array) -> Array:
        err = np.asarray(targets, dtype=float) - np.asarray(guides, dtype=float)
        vel = float(self.gather_cfg.guide_gain) * err
        speed = np.linalg.norm(vel, axis=1, keepdims=True)
        max_speed = float(self.gather_cfg.guide_max_speed)
        too_fast = speed[:, 0] > max_speed
        vel[too_fast] = vel[too_fast] / np.maximum(speed[too_fast], 1.0e-9) * max_speed
        lower, upper = self.scene.feasible_workspace_bounds(self.gather_cfg.wall_margin)
        for i in range(len(guides)):
            trial = guides[i] + vel[i] * 0.1
            if np.any(trial < lower) or np.any(trial > upper):
                clipped = np.clip(trial, lower, upper)
                direction = clipped - guides[i]
                vel[i] = direction / 0.1 if np.linalg.norm(direction) > 1.0e-9 else 0.0
        return vel

    def _tracking_rmse(self, guides: Array) -> float | None:
        if self._surround_targets is None or self._guide_to_target is None:
            return None
        active = self._guide_to_target >= 0
        if not np.any(active):
            return None
        err = self._surround_targets[self._guide_to_target[active]] - guides[active]
        return float(np.sqrt(np.mean(np.sum(err**2, axis=1))))

    def _plan(self, crowd: Array, guides: Array) -> GatherThenSurroundPlan:
        assert self._gather_center is not None
        target = GatherTarget(
            group_id=0,
            center=self._gather_center.copy(),
            radius=self._gather_radius,
            status="ACTIVE" if self._phase == "gather" else "COMPLETE",
        )
        status = {
            "gather": "GATHERING",
            "surround": "SURROUNDING",
            "done": "DONE",
        }.get(self._phase, "UNKNOWN")
        if self._phase == "gather":
            active_targets = None if self._gather_ring_targets is None else self._gather_ring_targets.copy()
            disk = self._disk_polyline(self._gather_radius)
        else:
            active_targets = None if self._surround_targets is None else self._surround_targets.copy()
            disk = self._disk_polyline(self._gather_radius)
        diagnostics = {
            **self._diagnostics,
            "step": int(self._step),
            "phase": self._phase,
            "tracking_rmse": self._tracking_rmse(guides),
            "crowd_count": int(len(crowd)),
            "gather_center": self._gather_center.tolist(),
        }
        return GatherThenSurroundPlan(
            phase=self._phase,
            gather_targets=(target,),
            surround_targets=None if self._surround_targets is None else self._surround_targets.copy(),
            active_guide_targets=active_targets,
            gather_disk_polyline=disk,
            diagnostics=diagnostics,
            status=status,
        )
