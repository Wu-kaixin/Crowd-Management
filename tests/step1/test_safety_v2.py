from __future__ import annotations

import json

import numpy as np
import pytest

from crowd_management.controllers.safety import VelocitySafetyConfig
from crowd_management.controllers.safety_v2 import (
    VelocityProjectionConfig,
    build_velocity_projection_problem,
    project_velocity_safety_v2,
    solve_velocity_projection,
    zoh_dense_check,
)


EMPTY_CROWD = np.empty((0, 2), dtype=float)
ROOM = np.array([10.0, 10.0], dtype=float)


def _problem(
    positions: np.ndarray,
    nominal: np.ndarray,
    *,
    safety: VelocitySafetyConfig | None = None,
    crowd: np.ndarray = EMPTY_CROWD,
    dt: float = 0.1,
    vmax: float = 2.0,
):
    return build_velocity_projection_problem(
        positions,
        nominal,
        crowd,
        ROOM,
        dt,
        vmax,
        safety
        or VelocitySafetyConfig(
            min_guide_distance=0.0,
            min_crowd_distance=0.0,
            room_margin=0.0,
        ),
    )


def test_problem_is_immutable_hashed_and_shared_by_both_backends() -> None:
    positions = np.array([[2.0, 2.0], [3.0, 2.0]])
    nominal = np.array([[1.0, 0.0], [-1.0, 0.0]])
    safety = VelocitySafetyConfig(
        min_guide_distance=1.0,
        min_crowd_distance=0.0,
        room_margin=0.25,
    )
    first = _problem(positions, nominal, safety=safety)
    second = _problem(positions, nominal, safety=safety)

    assert first.sha256 == second.sha256
    assert len(first.sha256) == 64
    assert np.array_equal(first.u_nom, second.u_nom)
    assert np.array_equal(first.A, second.A)
    assert np.array_equal(first.b, second.b)
    assert np.array_equal(first.kinds, second.kinds)
    assert not first.u_nom.flags.writeable
    assert not first.A.flags.writeable
    assert not first.b.flags.writeable
    assert not first.kinds.flags.writeable

    solutions = {
        backend: solve_velocity_projection(
            first,
            VelocityProjectionConfig(backend=backend, enable_zoh_check=False),
        )
        for backend in ("dykstra", "slsqp_convex_qcqp")
    }
    assert all(solution.success for solution in solutions.values())
    assert np.allclose(
        solutions["dykstra"].vector,
        solutions["slsqp_convex_qcqp"].vector,
        atol=2.0e-6,
    )


@pytest.mark.parametrize("backend", ["dykstra", "slsqp_convex_qcqp"])
def test_safe_nominal_is_identity_for_each_backend(backend: str) -> None:
    nominal = np.array([[0.1, -0.2]])
    result = project_velocity_safety_v2(
        np.array([[5.0, 5.0]]),
        nominal,
        EMPTY_CROWD,
        ROOM,
        0.1,
        1.0,
        VelocitySafetyConfig(
            min_guide_distance=0.0,
            min_crowd_distance=0.0,
            room_margin=0.25,
        ),
        VelocityProjectionConfig(backend=backend),
    )

    assert result.status == "VALID"
    assert result.feasible
    assert np.array_equal(result.candidate_control, nominal)
    assert np.array_equal(result.applied_control, nominal)
    assert result.certificate.problem_class == (
        "strongly_convex_qcqp_socp_representable_projection"
    )
    assert "not_human_safety_certification" in result.certificate.limitations
    assert "not_unconditional_continuous_time_safety_proof" in (
        result.certificate.limitations
    )


@pytest.mark.parametrize("backend", ["dykstra", "slsqp_convex_qcqp"])
def test_analytic_room_halfspace_projection(backend: str) -> None:
    safety = VelocitySafetyConfig(
        min_guide_distance=0.0,
        min_crowd_distance=0.0,
        room_margin=1.0,
    )
    problem = _problem(
        np.array([[1.0, 5.0]]),
        np.array([[-1.0, 0.0]]),
        safety=safety,
        dt=1.0,
        vmax=2.0,
    )
    lower_x = next(
        (row, bound)
        for row, bound, kind in zip(problem.A, problem.b, problem.kinds, strict=True)
        if kind == "room" and np.array_equal(row, np.array([1.0, 0.0]))
    )
    row, bound = lower_x

    solved = solve_velocity_projection(
        problem,
        VelocityProjectionConfig(backend=backend, enable_zoh_check=False),
    )

    assert solved.success
    assert solved.residuals.primal_residual <= 1.0e-8
    assert solved.residuals.kkt_residual <= 2.0e-6
    assert np.isclose(row @ solved.vector, bound, atol=2.0e-7)
    assert np.isclose(solved.vector[1], 0.0, atol=2.0e-7)


@pytest.mark.parametrize("backend", ["dykstra", "slsqp_convex_qcqp"])
def test_analytic_speed_ball_projection(backend: str) -> None:
    problem = _problem(
        np.array([[5.0, 5.0]]),
        np.array([[3.0, 4.0]]),
        vmax=2.0,
    )

    solved = solve_velocity_projection(
        problem,
        VelocityProjectionConfig(backend=backend, enable_zoh_check=False),
    )

    assert solved.success
    assert np.allclose(solved.vector, [1.2, 1.6], atol=2.0e-6)
    assert solved.residuals.primal_residual <= 1.0e-8
    assert solved.residuals.kkt_residual <= 2.0e-6


def test_seeded_random_speed_ball_problems_agree_between_backends() -> None:
    rng = np.random.default_rng(7102026)
    for nominal in rng.normal(size=(8, 2)) * 3.0:
        problem = _problem(
            np.array([[5.0, 5.0]]),
            nominal.reshape((1, 2)),
            vmax=1.25,
        )
        dykstra = solve_velocity_projection(
            problem,
            VelocityProjectionConfig(backend="dykstra", enable_zoh_check=False),
        )
        slsqp = solve_velocity_projection(
            problem,
            VelocityProjectionConfig(
                backend="slsqp_convex_qcqp", enable_zoh_check=False
            ),
        )

        assert dykstra.success
        assert slsqp.success
        assert np.allclose(dykstra.vector, slsqp.vector, atol=2.0e-6)
        assert dykstra.residuals.kkt_residual <= 2.0e-6
        assert slsqp.residuals.kkt_residual <= 2.0e-6


@pytest.mark.parametrize(
    ("positions", "crowd", "safety", "expected_kind"),
    [
        (
            np.array([[2.0, 2.0], [2.5, 2.0]]),
            EMPTY_CROWD,
            VelocitySafetyConfig(
                min_guide_distance=1.0,
                min_crowd_distance=0.0,
                room_margin=0.25,
            ),
            "guide_pair",
        ),
        (
            np.array([[2.0, 2.0]]),
            np.array([[2.25, 2.0]]),
            VelocitySafetyConfig(
                min_guide_distance=0.0,
                min_crowd_distance=0.8,
                room_margin=0.25,
            ),
            "crowd",
        ),
        (
            np.array([[0.5, 2.0]]),
            EMPTY_CROWD,
            VelocitySafetyConfig(
                min_guide_distance=0.0,
                min_crowd_distance=0.0,
                room_margin=1.0,
            ),
            "room",
        ),
    ],
)
def test_all_initial_unsafe_state_types_fail_explicitly(
    positions: np.ndarray,
    crowd: np.ndarray,
    safety: VelocitySafetyConfig,
    expected_kind: str,
) -> None:
    nominal = np.zeros_like(positions)
    result = project_velocity_safety_v2(
        positions,
        nominal,
        crowd,
        ROOM,
        0.1,
        1.0,
        safety,
    )

    assert result.status == "INITIAL_STATE_UNSAFE"
    assert not result.feasible
    assert result.emergency_stop
    assert np.array_equal(result.applied_control, np.zeros_like(nominal))
    assert result.certificate.diagnostics[
        "emergency_zero_control_repairs_initial_state"
    ] is False
    assert result.certificate.solver_message == (
        "projection_not_attempted_for_unsafe_initial_state"
    )
    problem = _problem(positions, nominal, safety=safety, crowd=crowd)
    assert problem.context["initial_worst_kind"] == expected_kind


def test_single_halfspace_support_produces_mathematical_infeasibility_certificate() -> None:
    safety = VelocitySafetyConfig(
        min_guide_distance=0.0,
        min_crowd_distance=0.0,
        room_margin=1.0,
        residual_tolerance=0.1,
    )
    result = project_velocity_safety_v2(
        np.array([[1.0, 5.0]]),
        np.array([[0.0, 0.0]]),
        EMPTY_CROWD,
        ROOM,
        0.1,
        0.1,
        safety,
    )

    assert result.status == "PROJECTION_INFEASIBLE"
    assert not result.feasible
    assert result.emergency_stop
    assert result.certificate.diagnostics["reason"] == (
        "single_halfspace_exceeds_product_speed_ball_support"
    )
    assert result.certificate.diagnostics["required_bound"] > (
        result.certificate.diagnostics["maximum_support"]
    )


def test_iteration_limit_is_numerical_failure_not_infeasibility() -> None:
    result = project_velocity_safety_v2(
        np.array([[1.0, 5.0]]),
        np.array([[-1.0, 0.0]]),
        EMPTY_CROWD,
        ROOM,
        1.0,
        2.0,
        VelocitySafetyConfig(
            min_guide_distance=0.0,
            min_crowd_distance=0.0,
            room_margin=1.0,
        ),
        VelocityProjectionConfig(
            backend="dykstra",
            max_iterations=1,
            iterate_tolerance=0.0,
            enable_zoh_check=False,
        ),
    )

    assert result.status == "NUMERICAL_RESIDUAL_FAILURE"
    assert not result.feasible
    assert result.emergency_stop
    assert result.certificate.diagnostics["mathematical_infeasibility_claimed"] is False
    assert result.certificate.iterations == 1
    assert result.certificate.residuals.primal_residual <= 1.0e-8


def test_zoh_dense_check_finds_middle_of_interval_pair_collision() -> None:
    problem = _problem(
        np.array([[2.0, 5.0], [8.0, 5.0]]),
        np.zeros((2, 2)),
        safety=VelocitySafetyConfig(
            min_guide_distance=1.0,
            min_crowd_distance=0.0,
            room_margin=0.0,
        ),
        dt=1.0,
        vmax=10.0,
    )
    certificate = zoh_dense_check(
        problem,
        np.array([[6.0, 0.0], [-6.0, 0.0]]),
        sample_count=4,
    )

    assert not certificate.safe
    assert certificate.worst_kind == "guide_pair"
    assert np.isclose(certificate.worst_time, 0.5)
    assert np.isclose(certificate.minimum_guide_clearance, -1.0)
    assert np.any(np.isclose(certificate.checked_times, 0.5))


def test_zoh_dense_check_accepts_safe_parallel_motion() -> None:
    problem = _problem(
        np.array([[2.0, 3.0], [2.0, 7.0]]),
        np.zeros((2, 2)),
        safety=VelocitySafetyConfig(
            min_guide_distance=1.0,
            min_crowd_distance=0.0,
            room_margin=0.25,
        ),
        dt=0.5,
        vmax=2.0,
    )
    certificate = zoh_dense_check(
        problem,
        np.array([[1.0, 0.0], [1.0, 0.0]]),
        sample_count=3,
    )

    assert certificate.safe
    assert certificate.minimum_guide_clearance == pytest.approx(3.0)
    assert certificate.minimum_room_clearance > 0.0
    assert certificate.minimum_speed_margin == pytest.approx(1.0)


def test_result_certificate_is_strict_json_serializable() -> None:
    result = project_velocity_safety_v2(
        np.array([[2.0, 2.0], [3.0, 2.0]]),
        np.array([[1.0, 0.0], [-1.0, 0.0]]),
        EMPTY_CROWD,
        ROOM,
        0.1,
        2.0,
        VelocitySafetyConfig(
            min_guide_distance=1.0,
            min_crowd_distance=0.0,
            room_margin=0.25,
        ),
        VelocityProjectionConfig(backend="dykstra"),
    )

    encoded = json.dumps(result.certificate.to_dict(), allow_nan=False, sort_keys=True)
    decoded = json.loads(encoded)
    assert decoded["schema"] == "abcg-v2.1-velocity-projection-certificate-v1"
    assert decoded["problem_sha256"] == result.certificate.problem_sha256
    assert decoded["zoh"]["safe"] is True


def test_dykstra_candidate_and_residuals_are_deterministic() -> None:
    kwargs = dict(
        positions=np.array([[2.0, 2.0], [3.0, 2.0]]),
        nominal_control=np.array([[1.0, 0.0], [-1.0, 0.0]]),
        crowd_points=EMPTY_CROWD,
        room_size=ROOM,
        dt=0.1,
        vmax=2.0,
        safety_config=VelocitySafetyConfig(
            min_guide_distance=1.0,
            min_crowd_distance=0.0,
            room_margin=0.25,
        ),
        projection_config=VelocityProjectionConfig(backend="dykstra"),
    )

    first = project_velocity_safety_v2(**kwargs)
    second = project_velocity_safety_v2(**kwargs)

    assert first.status == second.status == "PROJECTED"
    assert np.array_equal(first.candidate_control, second.candidate_control)
    assert np.array_equal(
        first.certificate.residuals.halfspace_residuals,
        second.certificate.residuals.halfspace_residuals,
    )
    assert first.certificate.residuals.kkt_residual == (
        second.certificate.residuals.kkt_residual
    )
    assert first.certificate.iterations == second.certificate.iterations
