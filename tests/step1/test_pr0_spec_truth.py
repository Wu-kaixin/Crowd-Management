from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest

from crowd_management.containment_metrics import (
    max_boundary_gap,
    max_euclidean_boundary_distance_to_points,
)
from crowd_management.crowd import StaticCrowdConfig, generate_static_crowd_truth
from crowd_management.estimation import BoundaryEstimate
from crowd_management.experiments.static_containment import run_static_containment


def test_circle_truth_boundary_matches_analytic_contract() -> None:
    cfg = StaticCrowdConfig.from_dict(
        {"shape": "circle", "count": 40, "center": [3.0, 4.0], "radius": 2.0},
        seed=7,
    )

    truth = generate_static_crowd_truth(cfg, safety_distance=0.5, num_samples=64)

    assert truth.valid
    assert truth.status == "valid"
    assert truth.component_count == 1
    assert truth.boundary_points.shape == (64, 2)
    assert np.allclose(np.linalg.norm(truth.boundary_points - cfg.center, axis=1), 2.0)
    assert np.allclose(np.linalg.norm(truth.safety_points - truth.boundary_points, axis=1), 0.5)


def test_rotated_ellipse_truth_boundary_matches_analytic_contract() -> None:
    cfg = StaticCrowdConfig.from_dict(
        {
            "shape": "ellipse",
            "count": 40,
            "center": [8.0, 5.0],
            "axes": [3.0, 1.25],
            "rotation_deg": 31.0,
        },
        seed=8,
    )

    truth = generate_static_crowd_truth(cfg, safety_distance=0.35, num_samples=96)
    theta = np.deg2rad(cfg.rotation_deg)
    rotation = np.array([[np.cos(theta), -np.sin(theta)], [np.sin(theta), np.cos(theta)]])
    local = (truth.boundary_points - cfg.center) @ rotation

    assert truth.valid
    assert np.allclose((local[:, 0] / 3.0) ** 2 + (local[:, 1] / 1.25) ** 2, 1.0)
    assert np.allclose(np.linalg.norm(truth.safety_points - truth.boundary_points, axis=1), 0.35)


def test_two_cluster_truth_is_explicit_out_of_scope_failure() -> None:
    cfg = StaticCrowdConfig.from_dict(
        {"shape": "two_cluster", "count": 40, "center": [10.0, 7.0], "radius": 2.0},
        seed=9,
    )

    truth = generate_static_crowd_truth(cfg, safety_distance=0.4, num_samples=80)

    assert not truth.valid
    assert truth.status == "out_of_scope_multicomponent"
    assert truth.component_count == 2
    assert set(np.unique(truth.component_ids)) == {0, 1}


def test_renamed_euclidean_boundary_metric_and_deprecated_alias() -> None:
    boundary_points = np.array(
        [
            [0.0, 0.0],
            [1.0, 0.0],
            [2.0, 0.0],
            [2.0, 1.0],
            [2.0, 2.0],
            [1.0, 2.0],
            [0.0, 2.0],
            [0.0, 1.0],
        ]
    )
    guides = np.array([[0.0, 0.0], [2.0, 2.0]])

    assert max_euclidean_boundary_distance_to_points(guides, boundary_points) == pytest.approx(2.0)

    radial_boundary = BoundaryEstimate(
        center=np.array([1.0, 1.0]),
        angles=np.linspace(0.0, 2.0 * np.pi, len(boundary_points), endpoint=False),
        radii=np.ones(len(boundary_points)),
        boundary_points=boundary_points,
        safety_points=boundary_points,
        safety_distance=0.0,
        bin_counts=np.ones(len(boundary_points), dtype=int),
    )
    with pytest.warns(DeprecationWarning, match="max_euclidean_boundary_distance"):
        assert max_boundary_gap(guides, radial_boundary) == pytest.approx(2.0)


def test_pr0_run_writes_truth_manifest_and_compatibility_metric(tmp_path: Path) -> None:
    repo = Path(__file__).resolve().parents[2]

    result = run_static_containment(
        repo / "configs" / "static_crowd_circle.yaml",
        tmp_path,
        methods=["abcg"],
        save_plots=False,
    )

    manifest = json.loads((tmp_path / "manifest.json").read_text(encoding="utf-8"))
    metrics = result["abcg"]
    assert (tmp_path / "config_resolved.yaml").is_file()
    assert (tmp_path / "crowd_truth.npz").is_file()
    assert (tmp_path / "boundary_v2.npz").is_file()
    assert (tmp_path / "boundary_v2_status.json").is_file()
    assert (tmp_path / "periodic_plan.npz").is_file()
    assert (tmp_path / "periodic_plan_status.json").is_file()
    assert (tmp_path / "resource_decision.json").is_file()
    assert (tmp_path / "abcg" / "assignment.npz").is_file()
    assert (tmp_path / "abcg" / "assignment_status.json").is_file()
    assert (tmp_path / "abcg" / "episode.npz").is_file()
    assert (tmp_path / "abcg" / "episode_status.json").is_file()
    assert manifest["schema_version"] == "step1-pr6-v1"
    assert manifest["run_scope"] == "alpha_bootstrap_safety_filtered_episode_with_pr6_evidence"
    assert manifest["closed_loop"]
    assert manifest["run_status"] == "timeout"
    assert manifest["truth_boundary"]["status"] == "valid"
    assert manifest["config"]["sha256"]
    assert manifest["environment"]["python"]
    assert manifest["repository"]["commit"]
    assert manifest["boundary_v2"]["status"] == "VALID"
    assert manifest["boundary_v2"]["method"] == "alpha_shape"
    assert manifest["boundary_v2"]["confidence_status"] == "bootstrap_estimated_pr6"
    assert manifest["boundary_v2"]["uncertainty_mean"] > 0.0
    assert manifest["periodic_plan"]["status"] == "VALID"
    assert manifest["periodic_plan"]["converged"]
    assert manifest["periodic_plan"]["h_final"] <= manifest["periodic_plan"]["h_initial"]
    assert manifest["periodic_plan"]["max_arc_gap"] > 0.0
    assert manifest["resource_decision"]["status"] == "VALID"
    assert manifest["resource_decision"]["active_count"] == 6
    assert manifest["resource_decision"]["reserve_count"] == 2
    assert manifest["assignments"]["abcg"]["status"] == "VALID"
    assert manifest["assignments"]["abcg"]["reserve_count"] == 2
    assert manifest["episodes"]["abcg"]["status"] == "TIMEOUT"
    assert manifest["episodes"]["abcg"]["control_steps"] > 0
    assert manifest["episodes"]["abcg"]["safety_filter_status"] == "ENABLED_PR5"
    assert manifest["episodes"]["abcg"]["safety_projected_steps"] > 0
    assert manifest["episodes"]["abcg"]["safety_infeasible_steps"] == 0
    trace = np.load(tmp_path / "abcg" / "episode.npz")
    assert len(trace["positions"]) == len(trace["applied_controls"]) + 1
    assert trace["tracking_rmse"][-1] < trace["tracking_rmse"][0]
    assert trace["state_history"][-1] == "TIMEOUT"
    assert len(trace["safety_status_history"]) == len(trace["applied_controls"])
    assert len(trace["safety_constraint_count"]) == len(trace["applied_controls"])
    assert len(trace["safety_crowd_constraint_count"]) == len(trace["applied_controls"])
    assert np.all(np.isfinite(trace["safety_max_residual_after"]))
    assert np.all(np.isfinite(trace["safety_max_crowd_residual_after"]))
    assert metrics["evaluation_boundary_source"] == "analytic_truth_safety_offset"
    assert metrics["max_boundary_gap"] == metrics["max_euclidean_boundary_distance"]
    assert metrics["periodic_plan_status"] == "VALID"
    assert metrics["boundary_v2_method"] == "alpha_shape"
    assert metrics["boundary_confidence_status"] == "bootstrap_estimated_pr6"
    assert metrics["resource_status"] == "VALID"
    assert metrics["assignment_status"] == "VALID"
    assert metrics["episode_status"] == "TIMEOUT"
    assert metrics["metrics_position_source"] == "episode_final_frame"
    state = np.load(tmp_path / "abcg" / "containment_state.npz")
    assert np.allclose(state["guide_points"], trace["positions"][-1])
    assert np.allclose(state["guide_initial_points"], trace["positions"][0])


def test_pr5_run_records_safety_infeasible_and_emergency_trace(tmp_path: Path) -> None:
    repo = Path(__file__).resolve().parents[2]

    result = run_static_containment(
        repo / "configs" / "static_crowd_safety_infeasible.yaml",
        tmp_path,
        methods=["abcg"],
        save_plots=False,
    )

    manifest = json.loads((tmp_path / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["run_status"] == "safety_infeasible"
    assert manifest["stop_reason"] == "SAFETY_INFEASIBLE"
    assert manifest["episodes"]["abcg"]["status"] == "SAFETY_INFEASIBLE"
    assert manifest["episodes"]["abcg"]["safety_infeasible_steps"] == 1
    trace = np.load(tmp_path / "abcg" / "episode.npz")
    assert len(trace["applied_controls"]) == 1
    assert trace["state_history"][-1] == "SAFETY_INFEASIBLE"
    assert trace["safety_emergency_stop_history"].tolist() == [True]
    assert np.array_equal(trace["applied_controls"][0], np.zeros_like(trace["applied_controls"][0]))
    assert np.all(np.isfinite(trace["safety_max_residual_after"]))
    assert result["abcg"]["method_status"] == "diagnostic_only"


def test_pr0_run_records_multicomponent_failure_without_hiding_metrics(tmp_path: Path) -> None:
    repo = Path(__file__).resolve().parents[2]

    result = run_static_containment(
        repo / "configs" / "static_crowd_two_clusters.yaml",
        tmp_path,
        methods=["abcg"],
        save_plots=False,
    )

    manifest = json.loads((tmp_path / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["truth_boundary"]["status"] == "out_of_scope_multicomponent"
    assert manifest["truth_boundary"]["component_count"] == 2
    assert manifest["boundary_v2"]["status"] in {"BOUNDARY_INVALID", "OFFSET_INVALID"}
    assert not manifest["boundary_v2"]["valid"]
    assert (tmp_path / "boundary_v2_status.json").is_file()
    assert not (tmp_path / "boundary_v2.npz").exists()
    assert (tmp_path / "periodic_plan_status.json").is_file()
    assert not (tmp_path / "periodic_plan.npz").exists()
    assert (tmp_path / "resource_decision.json").is_file()
    assert (tmp_path / "abcg" / "assignment_status.json").is_file()
    assert not (tmp_path / "abcg" / "assignment.npz").exists()
    assert (tmp_path / "abcg" / "episode_status.json").is_file()
    assert not (tmp_path / "abcg" / "episode.npz").exists()
    assert manifest["periodic_plan"]["status"] == "PLAN_SKIPPED_BOUNDARY_INVALID"
    assert manifest["resource_decision"]["status"] == "RESOURCE_SKIPPED_BOUNDARY_INVALID"
    assert manifest["assignments"]["abcg"]["status"] == "ASSIGNMENT_SKIPPED_PLAN_INVALID"
    assert manifest["episodes"]["abcg"]["status"] == manifest["boundary_v2"]["status"]
    assert not manifest["closed_loop"]
    assert manifest["run_status"] == "evaluation_scope_failure"
    assert manifest["stop_reason"] == "out_of_scope_multicomponent"
    assert result["abcg"]["evaluation_status"] == "out_of_scope_multicomponent"
    assert result["abcg"]["method_status"] == "diagnostic_only"
    assert np.isfinite(result["abcg"]["max_euclidean_boundary_distance"])


def test_pr3_run_records_capacity_shortfall_without_hiding_active_clip(tmp_path: Path) -> None:
    repo = Path(__file__).resolve().parents[2]

    result = run_static_containment(
        repo / "configs" / "static_crowd_capacity_shortfall.yaml",
        tmp_path,
        methods=["abcg"],
        save_plots=False,
    )

    manifest = json.loads((tmp_path / "manifest.json").read_text(encoding="utf-8"))
    resource = manifest["resource_decision"]
    assert resource["status"] == "CAPACITY_SHORTFALL"
    assert resource["requested_count"] == 6
    assert resource["desired_count"] == 6
    assert resource["active_count"] == 2
    assert resource["unmet_target_count"] == 4
    assert manifest["periodic_plan"]["active_count"] == 2
    assert manifest["run_status"] == "capacity_shortfall"
    assert manifest["stop_reason"] == "CAPACITY_SHORTFALL"
    assert result["abcg"]["resource_status"] == "CAPACITY_SHORTFALL"
    assert result["abcg"]["episode_status"] == "CAPACITY_SHORTFALL"
    assert (tmp_path / "abcg" / "episode.npz").is_file()
    assert result["abcg"]["method_status"] == "diagnostic_only"


def test_pr4_run_records_timeout_with_complete_trace(tmp_path: Path) -> None:
    repo = Path(__file__).resolve().parents[2]

    result = run_static_containment(
        repo / "configs" / "static_crowd_timeout.yaml",
        tmp_path,
        methods=["abcg"],
        save_plots=False,
    )

    manifest = json.loads((tmp_path / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["run_status"] == "timeout"
    assert manifest["stop_reason"] == "TIMEOUT"
    assert manifest["closed_loop"]
    assert manifest["episodes"]["abcg"]["status"] == "TIMEOUT"
    trace = np.load(tmp_path / "abcg" / "episode.npz")
    assert len(trace["applied_controls"]) == 2
    assert len(trace["positions"]) == 3
    assert trace["state_history"][-1] == "TIMEOUT"
    assert result["abcg"]["episode_status"] == "TIMEOUT"
    assert result["abcg"]["method_status"] == "diagnostic_only"
