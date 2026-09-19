"""Multi-crowd known-boundary surround: one ring per static group."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from crowd_management.crowd import (
    StaticCrowdConfig,
    build_crowd_source,
    crowd_component_ids,
)
from crowd_management.estimation import BoundaryEstimateFailure, estimate_boundary_v2
from crowd_management.experiments.static_containment import StaticContainmentConfig, run_static_containment
from crowd_management.experiments.static_containment.known_boundary import (
    estimate_multi_group_surround_pipeline,
)
from crowd_management.crowd.observation import crowd_observation_from_points

REPO = Path(__file__).resolve().parents[2]


def test_multi_crowd_config_parses_two_and_three_groups() -> None:
    two = StaticContainmentConfig.from_yaml(REPO / "configs/step1_known_boundary/square_two_crowds.yaml")
    three = StaticContainmentConfig.from_yaml(REPO / "configs/step1_known_boundary/square_three_crowds.yaml")
    assert two.crowd.is_multi
    assert three.crowd.is_multi
    assert len(two.crowd.groups) == 2
    assert len(three.crowd.groups) == 3
    assert two.crowd.count == 90
    assert three.crowd.count == 105
    labels = crowd_component_ids(two.crowd)
    assert labels.shape == (90,)
    assert set(labels.tolist()) == {0, 1}


def test_jupedsim_multi_crowd_generation_and_truth() -> None:
    cfg = StaticContainmentConfig.from_yaml(REPO / "configs/step1_known_boundary/square_two_crowds.yaml")
    source = build_crowd_source(cfg.crowd)
    points = source.observe()
    assert points.shape == (90, 2)
    truth = source.truth(safety_distance=cfg.safety_distance)
    assert truth.valid is True
    assert truth.status == "valid"
    assert truth.component_count == 2
    assert truth.shape == "multi"


def test_multi_crowd_joint_estimate_still_fails_without_labels() -> None:
    """Blind single-component estimate on all points remains multi-component fail."""
    cfg = StaticContainmentConfig.from_yaml(REPO / "configs/step1_known_boundary/square_two_crowds.yaml")
    points = build_crowd_source(cfg.crowd).observe()
    result = estimate_boundary_v2(points, cfg.boundary_v2, np.random.default_rng(cfg.seed))
    assert isinstance(result, BoundaryEstimateFailure)
    assert result.status == "BOUNDARY_INVALID"
    assert result.component_count > 1 or "multiple" in str(result.diagnostics.get("reason", "")).lower()


def test_multi_group_surround_pipeline_builds_two_rings() -> None:
    cfg = StaticContainmentConfig.from_yaml(REPO / "configs/step1_known_boundary/square_two_crowds.yaml")
    points = build_crowd_source(cfg.crowd).observe()
    observation = crowd_observation_from_points(points)
    result = estimate_multi_group_surround_pipeline(observation, cfg)
    from crowd_management.estimation import BoundaryEstimateV2

    assert isinstance(result.boundary_v2, BoundaryEstimateV2)
    assert result.boundary_v2.component_count == 2
    assert result.periodic_plan is not None
    assert result.periodic_plan.status == "VALID"
    assert result.resource_decision is not None
    assert result.resource_decision.status == "VALID"
    assert len(result.group_allocations) == 2
    assert sum(result.group_allocations) == result.resource_decision.active_count
    assert result.crowd_curve_display is not None
    assert np.any(~np.isfinite(result.crowd_curve_display))
    assert result.observed_component_ids is not None
    assert result.boundary_v2.diagnostics.get("used_generator_component_ids") in {False, 0, "false"}


def test_multi_group_rejects_oracle_component_ids() -> None:
    cfg = StaticContainmentConfig.from_yaml(REPO / "configs/step1_known_boundary/square_two_crowds.yaml")
    points = build_crowd_source(cfg.crowd).observe()
    observation = crowd_observation_from_points(points)
    with pytest.raises(ValueError, match="component_ids must not be passed"):
        estimate_multi_group_surround_pipeline(observation, cfg, component_ids=crowd_component_ids(cfg.crowd))


def test_multi_group_surround_pipeline_builds_three_rings() -> None:
    cfg = StaticContainmentConfig.from_yaml(REPO / "configs/step1_known_boundary/square_three_crowds.yaml")
    points = build_crowd_source(cfg.crowd).observe()
    observation = crowd_observation_from_points(points)
    result = estimate_multi_group_surround_pipeline(observation, cfg)
    from crowd_management.estimation import BoundaryEstimateV2

    assert isinstance(result.boundary_v2, BoundaryEstimateV2)
    assert result.boundary_v2.component_count == 3
    assert result.periodic_plan is not None and result.periodic_plan.status == "VALID"
    assert result.resource_decision is not None and result.resource_decision.status == "VALID"
    assert len(result.group_allocations) == 3
    assert all(count >= 1 for count in result.group_allocations)
    assert result.periodic_plan.active_count == sum(result.group_allocations)

def test_multi_crowd_end_to_end_surround(tmp_path: Path) -> None:
    result = run_static_containment(
        REPO / "configs/step1_known_boundary/square_two_crowds.yaml",
        tmp_path / "two",
        methods=["abcg"],
        save_plots=False,
        live=False,
        headless=True,
    )
    assert result["abcg"]["boundary_valid"] is True
    assert result["abcg"]["deployment_valid"] is True
    assert result["abcg"]["plan_valid"] is True
    assert result["abcg"]["assignment_valid"] is True
    assert (tmp_path / "two" / "periodic_plan.npz").is_file()

    three = run_static_containment(
        REPO / "configs/step1_known_boundary/square_three_crowds.yaml",
        tmp_path / "three",
        methods=["abcg"],
        save_plots=False,
        live=False,
        headless=True,
    )
    assert three["abcg"]["boundary_valid"] is True
    assert three["abcg"]["plan_valid"] is True
    assert three["abcg"]["assignment_valid"] is True
    targets = np.load(tmp_path / "three" / "periodic_plan.npz")["target_xy"]
    assert len(targets) >= 3
    ids = np.load(tmp_path / "two" / "crowd_component_ids.npz")
    assert "evaluator_component_ids" in ids.files
    assert "planning_component_ids" in ids.files


def test_synthetic_multi_crowd_groups() -> None:
    raw = {
        "source": "synthetic",
        "groups": [
            {"count": 20, "center": [4.0, 5.0], "radius": 1.2, "seed": 1},
            {"count": 25, "center": [10.0, 5.0], "radius": 1.3, "seed": 2},
            {"count": 15, "center": [7.0, 9.0], "radius": 1.0, "seed": 3},
        ],
    }
    cfg = StaticCrowdConfig.from_dict(raw, seed=0)
    assert cfg.is_multi and cfg.count == 60
    points = build_crowd_source(cfg).observe()
    assert points.shape == (60, 2)
