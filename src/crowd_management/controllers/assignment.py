"""PR3 deterministic identity-preserving guide-to-target assignment."""
from __future__ import annotations

from dataclasses import asdict, dataclass, field

import numpy as np
from scipy.optimize import linear_sum_assignment

from ..types import Array


@dataclass(frozen=True)
class AssignmentConfig:
    """Costs for target switches, reserve slots, and unmet target dummies."""

    lambda_switch: float = 0.25
    reserve_cost: float = 0.0
    unmet_target_cost: float = 1.0e6
    tie_tolerance: float = 1.0e-12

    def __post_init__(self) -> None:
        for name in ("lambda_switch", "reserve_cost", "unmet_target_cost", "tie_tolerance"):
            value = float(getattr(self, name))
            if not np.isfinite(value) or value < 0.0:
                raise ValueError(f"{name} must be finite and non-negative.")


@dataclass(frozen=True)
class AssignmentResult:
    """One-to-one assignment with explicit reserve and unmet-target indices."""

    guide_to_target: Array
    target_to_guide: Array
    reserve_guide_ids: Array
    unmet_target_ids: Array
    cost_matrix: Array
    total_cost: float
    switch_count: int
    status: str
    diagnostics: dict[str, object] = field(default_factory=dict)


class IdentityPreservingAssigner:
    """State-free facade; guide-row identities and prior assignments are explicit."""

    def __init__(self, config: AssignmentConfig | None = None) -> None:
        self.config = config or AssignmentConfig()
        if not isinstance(self.config, AssignmentConfig):
            raise TypeError("config must be AssignmentConfig.")

    def assign(
        self,
        guide_positions: Array,
        target_positions: Array,
        previous_assignment: Array | None = None,
    ) -> AssignmentResult:
        return assign_guides_to_targets(
            guide_positions,
            target_positions,
            self.config,
            previous_assignment,
        )


def _point_count_if_shaped(values: Array) -> int:
    array = np.asarray(values)
    return int(array.shape[0]) if array.ndim == 2 else 0


def _failure(guide_count: int, target_count: int, reason: str) -> AssignmentResult:
    return AssignmentResult(
        guide_to_target=np.full(guide_count, -1, dtype=int),
        target_to_guide=np.full(target_count, -1, dtype=int),
        reserve_guide_ids=np.arange(guide_count, dtype=int),
        unmet_target_ids=np.arange(target_count, dtype=int),
        cost_matrix=np.zeros((guide_count, target_count), dtype=float),
        total_cost=0.0,
        switch_count=0,
        status="ASSIGNMENT_INFEASIBLE",
        diagnostics={"reason": reason},
    )


def _valid_points(values: Array) -> bool:
    array = np.asarray(values, dtype=float)
    return bool(array.ndim == 2 and array.shape[1:] == (2,) and np.all(np.isfinite(array)))


def _previous_assignment(values: Array | None, guide_count: int) -> tuple[Array, bool] | None:
    if values is None:
        return np.full(guide_count, -1, dtype=int), False
    array = np.asarray(values)
    if array.shape != (guide_count,) or not np.all(np.isfinite(array)):
        return None
    integer = array.astype(int)
    if not np.array_equal(array, integer) or np.any(integer < -1):
        return None
    return integer, True


def _hungarian_square(cost: Array, tolerance: float) -> Array | None:
    """Return deterministic row-to-column indices through SciPy Hungarian."""
    matrix = np.asarray(cost, dtype=float)
    if matrix.ndim != 2 or matrix.shape[0] != matrix.shape[1] or not np.all(np.isfinite(matrix)):
        return None
    size = len(matrix)
    if size == 0:
        return np.empty(0, dtype=int)
    try:
        rows, columns = linear_sum_assignment(matrix)
    except ValueError:
        return None
    if not np.array_equal(rows, np.arange(size)):
        return None
    assignment = np.asarray(columns, dtype=int)
    return assignment if np.all(assignment >= 0) else None


def assign_guides_to_targets(
    guide_positions: Array,
    target_positions: Array,
    config: AssignmentConfig,
    previous_assignment: Array | None = None,
) -> AssignmentResult:
    """Assign stable guide rows to target rows, reserve, or explicit unmet slots."""
    if not isinstance(config, AssignmentConfig):
        raise TypeError("config must be AssignmentConfig.")
    guide_count = _point_count_if_shaped(guide_positions)
    target_count = _point_count_if_shaped(target_positions)
    if not _valid_points(guide_positions):
        return _failure(guide_count, target_count, "invalid_guide_positions")
    if not _valid_points(target_positions):
        return _failure(guide_count, target_count, "invalid_target_positions")

    guides = np.asarray(guide_positions, dtype=float)
    targets = np.asarray(target_positions, dtype=float)
    previous_result = _previous_assignment(previous_assignment, guide_count)
    if previous_result is None:
        return _failure(guide_count, target_count, "invalid_previous_assignment")
    previous, has_previous = previous_result

    real_cost = np.sum((guides[:, None, :] - targets[None, :, :]) ** 2, axis=2)
    if has_previous and target_count:
        real_cost += config.lambda_switch * (previous[:, None] != np.arange(target_count)[None, :])

    size = max(guide_count, target_count)
    if size == 0:
        return AssignmentResult(
            guide_to_target=np.empty(0, dtype=int),
            target_to_guide=np.empty(0, dtype=int),
            reserve_guide_ids=np.empty(0, dtype=int),
            unmet_target_ids=np.empty(0, dtype=int),
            cost_matrix=real_cost,
            total_cost=0.0,
            switch_count=0,
            status="VALID",
            diagnostics={"reason": "empty_assignment", "config": asdict(config)},
        )

    augmented = np.zeros((size, size), dtype=float)
    if guide_count and target_count:
        augmented[:guide_count, :target_count] = real_cost
    if guide_count > target_count:
        reserve_penalty = np.full(guide_count, config.reserve_cost, dtype=float)
        if has_previous:
            reserve_penalty += config.lambda_switch * (previous != -1)
        augmented[:guide_count, target_count:] = reserve_penalty[:, None]
    elif target_count > guide_count:
        augmented[guide_count:, :target_count] = config.unmet_target_cost

    square_assignment = _hungarian_square(augmented, config.tie_tolerance)
    if square_assignment is None:
        return _failure(guide_count, target_count, "hungarian_solver_failed")

    guide_to_target = np.full(guide_count, -1, dtype=int)
    target_to_guide = np.full(target_count, -1, dtype=int)
    for guide_id in range(guide_count):
        column = int(square_assignment[guide_id])
        if column < target_count:
            guide_to_target[guide_id] = column
            target_to_guide[column] = guide_id

    reserve_ids = np.flatnonzero(guide_to_target < 0).astype(int)
    unmet_ids = np.flatnonzero(target_to_guide < 0).astype(int)
    if has_previous:
        switch_count = int(np.count_nonzero(guide_to_target != previous))
    else:
        switch_count = 0
    status = "CAPACITY_SHORTFALL" if len(unmet_ids) else "VALID"
    return AssignmentResult(
        guide_to_target=guide_to_target,
        target_to_guide=target_to_guide,
        reserve_guide_ids=reserve_ids,
        unmet_target_ids=unmet_ids,
        cost_matrix=real_cost,
        total_cost=float(np.sum(augmented[np.arange(size), square_assignment])),
        switch_count=switch_count,
        status=status,
        diagnostics={
            "reason": "unmet_targets" if len(unmet_ids) else "assignment_complete",
            "solver": "scipy_linear_sum_assignment",
            "previous_assignment_provided": has_previous,
            "config": asdict(config),
        },
    )
