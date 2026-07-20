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

    def to_jsonable(self) -> dict[str, object]:
        """Serialize route ``+inf`` as null with an explicit finite mask."""

        costs = np.asarray(self.cost_matrix, dtype=float)
        finite = np.isfinite(costs)
        return {
            "guide_to_target": self.guide_to_target.tolist(),
            "target_to_guide": self.target_to_guide.tolist(),
            "reserve_guide_ids": self.reserve_guide_ids.tolist(),
            "unmet_target_ids": self.unmet_target_ids.tolist(),
            "cost_matrix": [
                [float(costs[i, j]) if finite[i, j] else None for j in range(costs.shape[1])]
                for i in range(costs.shape[0])
            ],
            "finite_cost_mask": finite.tolist(),
            "total_cost": float(self.total_cost),
            "switch_count": int(self.switch_count),
            "status": self.status,
            "diagnostics": dict(self.diagnostics),
        }


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
        *,
        pairwise_cost_matrix: Array | None = None,
    ) -> AssignmentResult:
        return assign_guides_to_targets(
            guide_positions,
            target_positions,
            self.config,
            previous_assignment,
            pairwise_cost_matrix=pairwise_cost_matrix,
        )


def _point_count_if_shaped(values: Array) -> int:
    array = np.asarray(values)
    return int(array.shape[0]) if array.ndim == 2 else 0


def _failure(
    guide_count: int,
    target_count: int,
    reason: str,
    *,
    status: str = "ASSIGNMENT_INFEASIBLE",
    cost_matrix: Array | None = None,
) -> AssignmentResult:
    costs = (
        np.zeros((guide_count, target_count), dtype=float)
        if cost_matrix is None
        else np.asarray(cost_matrix, dtype=float).copy()
    )
    return AssignmentResult(
        guide_to_target=np.full(guide_count, -1, dtype=int),
        target_to_guide=np.full(target_count, -1, dtype=int),
        reserve_guide_ids=np.arange(guide_count, dtype=int),
        unmet_target_ids=np.arange(target_count, dtype=int),
        cost_matrix=costs,
        total_cost=0.0,
        switch_count=0,
        status=status,
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
    if (
        matrix.ndim != 2
        or matrix.shape[0] != matrix.shape[1]
        or np.any(np.isnan(matrix))
        or np.any(np.isneginf(matrix))
    ):
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


def _pairwise_cost_matrix(
    guides: Array,
    targets: Array,
    supplied: Array | None,
) -> tuple[Array | None, str | None, str]:
    if supplied is None:
        return (
            np.sum((guides[:, None, :] - targets[None, :, :]) ** 2, axis=2),
            None,
            "squared_euclidean",
        )
    matrix = np.asarray(supplied, dtype=float)
    expected = (len(guides), len(targets))
    if matrix.shape != expected:
        return None, "pairwise_cost_matrix_shape_mismatch", "external_pairwise"
    if np.any(np.isnan(matrix)) or np.any(np.isneginf(matrix)):
        return None, "pairwise_cost_matrix_contains_nan_or_negative_infinity", "external_pairwise"
    if np.any(matrix < 0.0):
        return None, "pairwise_cost_matrix_contains_negative_cost", "external_pairwise"
    return matrix.copy(), None, "external_pairwise"


def _finite_cardinality_matching_exists(cost: Array) -> bool:
    matrix = np.asarray(cost, dtype=float)
    if min(matrix.shape, default=0) == 0:
        return True
    try:
        rows, columns = linear_sum_assignment(matrix)
    except ValueError:
        return False
    return bool(
        len(rows) == min(matrix.shape)
        and np.all(np.isfinite(matrix[rows, columns]))
    )


def assign_guides_to_targets(
    guide_positions: Array,
    target_positions: Array,
    config: AssignmentConfig,
    previous_assignment: Array | None = None,
    *,
    pairwise_cost_matrix: Array | None = None,
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

    real_cost, matrix_error, cost_source = _pairwise_cost_matrix(
        guides,
        targets,
        pairwise_cost_matrix,
    )
    if real_cost is None:
        return _failure(guide_count, target_count, str(matrix_error))
    if has_previous and target_count:
        real_cost += config.lambda_switch * (previous[:, None] != np.arange(target_count)[None, :])

    if not _finite_cardinality_matching_exists(real_cost):
        return _failure(
            guide_count,
            target_count,
            "no_finite_route_matching",
            status="ROUTE_INFEASIBLE",
            cost_matrix=real_cost,
        )

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
            diagnostics={
                "reason": "empty_assignment",
                "cost_source": cost_source,
                "config": asdict(config),
            },
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
            "cost_source": cost_source,
            "previous_assignment_provided": has_previous,
            "config": asdict(config),
        },
    )


def _cycle_order(values: Array, count: int, name: str) -> Array | None:
    order = np.asarray(values)
    if order.shape != (count,) or not np.all(np.isfinite(order)):
        return None
    integer = order.astype(int)
    if not np.array_equal(order, integer) or not np.array_equal(np.sort(integer), np.arange(count)):
        return None
    return integer


def _reserve_penalties(previous: Array, has_previous: bool, config: AssignmentConfig) -> Array:
    penalties = np.full(len(previous), config.reserve_cost, dtype=float)
    if has_previous:
        penalties += config.lambda_switch * (previous != -1)
    return penalties


def _mapping_tie_code(guide_id: int, target_id: int, guide_count: int, target_count: int) -> int:
    base = target_count + 2
    return (target_id + 1) * base ** (guide_count - 1 - guide_id)


def _better_state(
    candidate: tuple[float, int, tuple[tuple[int, int], ...]],
    current: tuple[float, int, tuple[tuple[int, int], ...]] | None,
    tolerance: float,
) -> bool:
    if current is None:
        return True
    if candidate[0] < current[0] - tolerance:
        return True
    if abs(candidate[0] - current[0]) <= tolerance:
        if candidate[1] != current[1]:
            return candidate[1] < current[1]
        return candidate[2] < current[2]
    return False


def _cyclic_sequence_dp(
    guide_order: Array,
    target_order: Array,
    real_cost: Array,
    reserve_penalty: Array,
    config: AssignmentConfig,
) -> tuple[float, Array, Array] | None:
    guide_count = len(guide_order)
    target_count = len(target_order)
    required_matches = min(guide_count, target_count)
    State = tuple[float, int, tuple[tuple[int, int], ...]]
    states: dict[tuple[int, int, int], State] = {(0, 0, 0): (0.0, 0, ())}

    def update(key: tuple[int, int, int], value: State) -> None:
        current = states.get(key)
        if _better_state(value, current, config.tie_tolerance):
            states[key] = value

    for guide_index in range(guide_count + 1):
        for target_index in range(target_count + 1):
            for match_count in range(required_matches + 1):
                state = states.get((guide_index, target_index, match_count))
                if state is None:
                    continue
                cost, tie_code, matches = state
                if guide_index < guide_count:
                    guide_id = int(guide_order[guide_index])
                    update(
                        (guide_index + 1, target_index, match_count),
                        (cost + float(reserve_penalty[guide_id]), tie_code, matches),
                    )
                if target_index < target_count:
                    update(
                        (guide_index, target_index + 1, match_count),
                        (cost + float(config.unmet_target_cost), tie_code, matches),
                    )
                if (
                    guide_index < guide_count
                    and target_index < target_count
                    and match_count < required_matches
                ):
                    guide_id = int(guide_order[guide_index])
                    target_id = int(target_order[target_index])
                    pair_cost = float(real_cost[guide_id, target_id])
                    if np.isfinite(pair_cost):
                        update(
                            (guide_index + 1, target_index + 1, match_count + 1),
                            (
                                cost + pair_cost,
                                tie_code
                                + _mapping_tie_code(
                                    guide_id,
                                    target_id,
                                    guide_count,
                                    target_count,
                                ),
                                matches + ((guide_id, target_id),),
                            ),
                        )
    final = states.get((guide_count, target_count, required_matches))
    if final is None:
        return None
    guide_to_target = np.full(guide_count, -1, dtype=int)
    target_to_guide = np.full(target_count, -1, dtype=int)
    for guide_id, target_id in final[2]:
        guide_to_target[guide_id] = target_id
        target_to_guide[target_id] = guide_id
    return float(final[0]), guide_to_target, target_to_guide


def assign_cyclic_order_preserving(
    guide_positions: Array,
    target_positions: Array,
    config: AssignmentConfig,
    *,
    guide_cycle_order: Array,
    target_cycle_order: Array,
    pairwise_cost_matrix: Array | None = None,
    previous_assignment: Array | None = None,
) -> AssignmentResult:
    """Assign along two explicit cycles without order crossings.

    Every cyclic rotation of the target order is evaluated.  A sequence DP
    handles surplus guides as reserve slots and guide shortages as explicit
    unmet targets.  Equal-cost solutions use the natural guide-id mapping as a
    rotation-independent deterministic tie-break.
    """

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
    guides_ordered = _cycle_order(guide_cycle_order, guide_count, "guide_cycle_order")
    targets_ordered = _cycle_order(target_cycle_order, target_count, "target_cycle_order")
    if guides_ordered is None:
        return _failure(guide_count, target_count, "invalid_guide_cycle_order")
    if targets_ordered is None:
        return _failure(guide_count, target_count, "invalid_target_cycle_order")
    previous_result = _previous_assignment(previous_assignment, guide_count)
    if previous_result is None:
        return _failure(guide_count, target_count, "invalid_previous_assignment")
    previous, has_previous = previous_result
    real_cost, matrix_error, cost_source = _pairwise_cost_matrix(
        guides,
        targets,
        pairwise_cost_matrix,
    )
    if real_cost is None:
        return _failure(guide_count, target_count, str(matrix_error))
    if has_previous and target_count:
        real_cost += config.lambda_switch * (
            previous[:, None] != np.arange(target_count)[None, :]
        )
    if not _finite_cardinality_matching_exists(real_cost):
        return _failure(
            guide_count,
            target_count,
            "no_finite_route_matching",
            status="ROUTE_INFEASIBLE",
            cost_matrix=real_cost,
        )

    reserve_penalty = _reserve_penalties(previous, has_previous, config)
    best: tuple[float, Array, Array] | None = None
    rotation_count = max(target_count, 1)
    for rotation in range(rotation_count):
        rotated_targets = (
            np.roll(targets_ordered, -rotation)
            if target_count
            else targets_ordered
        )
        candidate = _cyclic_sequence_dp(
            guides_ordered,
            rotated_targets,
            real_cost,
            reserve_penalty,
            config,
        )
        if candidate is None:
            continue
        if best is None:
            best = candidate
            continue
        candidate_key = tuple(int(value) for value in candidate[1])
        best_key = tuple(int(value) for value in best[1])
        if candidate[0] < best[0] - config.tie_tolerance or (
            abs(candidate[0] - best[0]) <= config.tie_tolerance
            and candidate_key < best_key
        ):
            best = candidate
    if best is None:
        return _failure(
            guide_count,
            target_count,
            "no_finite_cyclic_route_matching",
            status="ROUTE_INFEASIBLE",
            cost_matrix=real_cost,
        )

    total_cost, guide_to_target, target_to_guide = best
    reserve_ids = np.flatnonzero(guide_to_target < 0).astype(int)
    unmet_ids = np.flatnonzero(target_to_guide < 0).astype(int)
    switch_count = (
        int(np.count_nonzero(guide_to_target != previous))
        if has_previous
        else 0
    )
    return AssignmentResult(
        guide_to_target=guide_to_target,
        target_to_guide=target_to_guide,
        reserve_guide_ids=reserve_ids,
        unmet_target_ids=unmet_ids,
        cost_matrix=real_cost,
        total_cost=total_cost,
        switch_count=switch_count,
        status="CAPACITY_SHORTFALL" if len(unmet_ids) else "VALID",
        diagnostics={
            "reason": "unmet_targets" if len(unmet_ids) else "assignment_complete",
            "solver": "cyclic_sequence_dynamic_programming",
            "cost_source": cost_source,
            "rotation_invariant": True,
            "previous_assignment_provided": has_previous,
            "config": asdict(config),
        },
    )
