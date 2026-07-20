from __future__ import annotations

import json

import numpy as np

from crowd_management.controllers.assignment import (
    AssignmentConfig,
    IdentityPreservingAssigner,
    assign_cyclic_order_preserving,
    assign_guides_to_targets,
)


def test_legacy_squared_euclidean_call_is_exactly_compatible() -> None:
    guides = np.array([[0.0, 0.0], [10.0, 0.0], [20.0, 0.0]])
    targets = np.array([[0.1, 0.0], [19.9, 0.0]])
    config = AssignmentConfig(lambda_switch=0.0, reserve_cost=0.5)

    legacy = assign_guides_to_targets(guides, targets, config)
    explicit = IdentityPreservingAssigner(config).assign(
        guides,
        targets,
        pairwise_cost_matrix=np.sum(
            (guides[:, None, :] - targets[None, :, :]) ** 2,
            axis=2,
        ),
    )

    assert legacy.status == "VALID"
    assert np.array_equal(legacy.guide_to_target, np.array([0, -1, 1]))
    assert np.array_equal(legacy.guide_to_target, explicit.guide_to_target)
    assert np.array_equal(legacy.target_to_guide, explicit.target_to_guide)
    assert np.array_equal(legacy.cost_matrix, explicit.cost_matrix)
    assert legacy.total_cost == explicit.total_cost
    assert legacy.diagnostics["cost_source"] == "squared_euclidean"
    assert explicit.diagnostics["cost_source"] == "external_pairwise"


def test_geodesic_cost_matrix_changes_hungarian_assignment() -> None:
    guides = np.array([[0.0, 0.0], [10.0, 0.0]])
    targets = np.array([[1.0, 0.0], [9.0, 0.0]])
    config = AssignmentConfig(lambda_switch=0.0)

    euclidean = assign_guides_to_targets(guides, targets, config)
    geodesic = assign_guides_to_targets(
        guides,
        targets,
        config,
        pairwise_cost_matrix=np.array([[20.0, 1.0], [1.0, 20.0]]),
    )

    assert np.array_equal(euclidean.guide_to_target, np.array([0, 1]))
    assert np.array_equal(geodesic.guide_to_target, np.array([1, 0]))
    assert geodesic.total_cost == 2.0


def test_partial_infinity_allows_a_finite_perfect_route_matching() -> None:
    guides = np.zeros((3, 2), dtype=float)
    targets = np.zeros((3, 2), dtype=float)
    costs = np.array(
        [
            [1.0, np.inf, np.inf],
            [np.inf, 1.0, 5.0],
            [np.inf, 4.0, 1.0],
        ]
    )

    result = assign_guides_to_targets(
        guides,
        targets,
        AssignmentConfig(lambda_switch=0.0),
        pairwise_cost_matrix=costs,
    )

    assert result.status == "VALID"
    assert np.array_equal(result.guide_to_target, np.array([0, 1, 2]))
    assert np.isfinite(result.total_cost)
    assert np.isposinf(result.cost_matrix[0, 1])


def test_no_finite_perfect_route_matching_is_explicit() -> None:
    guides = np.zeros((2, 2), dtype=float)
    targets = np.zeros((2, 2), dtype=float)
    result = assign_guides_to_targets(
        guides,
        targets,
        AssignmentConfig(),
        pairwise_cost_matrix=np.array([[0.0, np.inf], [1.0, np.inf]]),
    )

    assert result.status == "ROUTE_INFEASIBLE"
    assert result.diagnostics["reason"] == "no_finite_route_matching"
    assert np.all(result.guide_to_target == -1)
    assert np.all(result.target_to_guide == -1)
    payload = result.to_jsonable()
    assert payload["cost_matrix"][0][1] is None
    assert payload["finite_cost_mask"] == [[True, False], [True, False]]
    json.dumps(payload, allow_nan=False)


def test_external_cost_validation_rejects_shape_nan_negative_and_negative_infinity() -> None:
    guides = np.zeros((2, 2), dtype=float)
    targets = np.zeros((2, 2), dtype=float)
    invalid = (
        np.zeros((2, 3)),
        np.array([[0.0, np.nan], [1.0, 0.0]]),
        np.array([[0.0, -np.inf], [1.0, 0.0]]),
        np.array([[0.0, -1.0], [1.0, 0.0]]),
    )

    results = [
        assign_guides_to_targets(
            guides,
            targets,
            AssignmentConfig(),
            pairwise_cost_matrix=costs,
        )
        for costs in invalid
    ]

    assert all(result.status == "ASSIGNMENT_INFEASIBLE" for result in results)
    assert [result.diagnostics["reason"] for result in results] == [
        "pairwise_cost_matrix_shape_mismatch",
        "pairwise_cost_matrix_contains_nan_or_negative_infinity",
        "pairwise_cost_matrix_contains_nan_or_negative_infinity",
        "pairwise_cost_matrix_contains_negative_cost",
    ]


def test_cyclic_assignment_prevents_a_noncyclic_crossing() -> None:
    guides = np.zeros((3, 2), dtype=float)
    targets = np.zeros((3, 2), dtype=float)
    costs = np.array(
        [
            [0.0, 10.0, 10.0],
            [10.0, 10.0, 0.0],
            [10.0, 0.0, 10.0],
        ]
    )
    config = AssignmentConfig(lambda_switch=0.0)

    crossing = assign_guides_to_targets(
        guides,
        targets,
        config,
        pairwise_cost_matrix=costs,
    )
    cyclic = assign_cyclic_order_preserving(
        guides,
        targets,
        config,
        guide_cycle_order=np.array([0, 1, 2]),
        target_cycle_order=np.array([0, 1, 2]),
        pairwise_cost_matrix=costs,
    )

    assert np.array_equal(crossing.guide_to_target, np.array([0, 2, 1]))
    assert crossing.total_cost == 0.0
    assert cyclic.status == "VALID"
    assert tuple(cyclic.guide_to_target) in {
        (0, 1, 2),
        (1, 2, 0),
        (2, 0, 1),
    }
    assert cyclic.total_cost > crossing.total_cost


def test_cyclic_assignment_is_invariant_to_cycle_start_rotation() -> None:
    guides = np.zeros((4, 2), dtype=float)
    targets = np.zeros((3, 2), dtype=float)
    costs = np.array(
        [
            [5.0, 9.0, 1.0],
            [1.0, 7.0, 8.0],
            [8.0, 1.0, 7.0],
            [7.0, 8.0, 1.0],
        ]
    )
    config = AssignmentConfig(lambda_switch=0.0, reserve_cost=0.25)

    first = assign_cyclic_order_preserving(
        guides,
        targets,
        config,
        guide_cycle_order=np.array([0, 1, 2, 3]),
        target_cycle_order=np.array([0, 1, 2]),
        pairwise_cost_matrix=costs,
    )
    rotated = assign_cyclic_order_preserving(
        guides,
        targets,
        config,
        guide_cycle_order=np.array([2, 3, 0, 1]),
        target_cycle_order=np.array([1, 2, 0]),
        pairwise_cost_matrix=costs,
    )

    assert first.status == rotated.status == "VALID"
    assert np.array_equal(first.guide_to_target, rotated.guide_to_target)
    assert first.total_cost == rotated.total_cost


def test_cyclic_dp_selects_surplus_guides_and_is_deterministic_on_ties() -> None:
    guides = np.zeros((4, 2), dtype=float)
    targets = np.zeros((2, 2), dtype=float)
    costs = np.array(
        [
            [9.0, 9.0],
            [0.0, 8.0],
            [8.0, 8.0],
            [8.0, 0.0],
        ]
    )
    kwargs = {
        "guide_cycle_order": np.arange(4),
        "target_cycle_order": np.arange(2),
        "pairwise_cost_matrix": costs,
    }
    first = assign_cyclic_order_preserving(
        guides,
        targets,
        AssignmentConfig(lambda_switch=0.0),
        **kwargs,
    )
    second = assign_cyclic_order_preserving(
        guides,
        targets,
        AssignmentConfig(lambda_switch=0.0),
        **kwargs,
    )

    assert np.array_equal(first.guide_to_target, np.array([-1, 0, -1, 1]))
    assert np.array_equal(first.reserve_guide_ids, np.array([0, 2]))
    assert np.array_equal(first.guide_to_target, second.guide_to_target)
    assert first.total_cost == second.total_cost

    tied = assign_cyclic_order_preserving(
        np.zeros((3, 2)),
        np.zeros((2, 2)),
        AssignmentConfig(lambda_switch=0.0),
        guide_cycle_order=np.arange(3),
        target_cycle_order=np.arange(2),
        pairwise_cost_matrix=np.zeros((3, 2)),
    )
    repeated = assign_cyclic_order_preserving(
        np.zeros((3, 2)),
        np.zeros((2, 2)),
        AssignmentConfig(lambda_switch=0.0),
        guide_cycle_order=np.array([1, 2, 0]),
        target_cycle_order=np.array([1, 0]),
        pairwise_cost_matrix=np.zeros((3, 2)),
    )
    assert np.array_equal(tied.guide_to_target, repeated.guide_to_target)


def test_cyclic_capacity_shortfall_and_serializable_result(tmp_path) -> None:
    guides = np.zeros((2, 2), dtype=float)
    targets = np.zeros((3, 2), dtype=float)
    result = assign_cyclic_order_preserving(
        guides,
        targets,
        AssignmentConfig(lambda_switch=0.0, unmet_target_cost=100.0),
        guide_cycle_order=np.arange(2),
        target_cycle_order=np.arange(3),
        pairwise_cost_matrix=np.array([[0.0, 4.0, 8.0], [8.0, 0.0, 4.0]]),
    )

    assert result.status == "CAPACITY_SHORTFALL"
    assert len(result.unmet_target_ids) == 1
    record = {
        "status": result.status,
        "guide_to_target": result.guide_to_target.tolist(),
        "target_to_guide": result.target_to_guide.tolist(),
        "reserve_guide_ids": result.reserve_guide_ids.tolist(),
        "unmet_target_ids": result.unmet_target_ids.tolist(),
        "total_cost": result.total_cost,
        "switch_count": result.switch_count,
        "diagnostics": result.diagnostics,
    }
    path = tmp_path / "cyclic_assignment.json"
    path.write_text(json.dumps(record, sort_keys=True), encoding="utf-8")
    restored = json.loads(path.read_text(encoding="utf-8"))
    assert restored["status"] == "CAPACITY_SHORTFALL"
    assert len(restored["unmet_target_ids"]) == 1
