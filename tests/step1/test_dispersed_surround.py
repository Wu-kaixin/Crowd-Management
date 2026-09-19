"""Dispersed static surround (Option A) and Step 2 gather stubs."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from crowd_management.controllers.step2_gather import NotImplementedGatherThenSurroundController
from crowd_management.crowd import build_crowd_source, crowd_component_ids
from crowd_management.estimation import BoundaryEstimateV2, estimate_boundary_v2
from crowd_management.experiments.static_containment import StaticContainmentConfig, run_static_containment

REPO = Path(__file__).resolve().parents[2]


def test_dispersed_config_expands_clusters() -> None:
    cfg = StaticContainmentConfig.from_yaml(REPO / "configs/step1_known_boundary/square_dispersed.yaml")
    assert cfg.crowd.is_dispersed
    assert len(cfg.crowd.groups) == 10
    assert cfg.crowd.count == 50
    labels = crowd_component_ids(cfg.crowd)
    assert labels.shape == (50,)
    assert len(set(labels.tolist())) == 10


def test_dispersed_jupedsim_and_envelope_truth() -> None:
    cfg = StaticContainmentConfig.from_yaml(REPO / "configs/step1_known_boundary/square_dispersed.yaml")
    source = build_crowd_source(cfg.crowd)
    points = source.observe()
    assert points.shape == (50, 2)
    truth = source.truth(safety_distance=cfg.safety_distance)
    assert truth.valid is True
    assert truth.status == "valid"
    assert truth.shape == "dispersed"
    assert truth.component_count == 1


def test_dispersed_boundary_forms_single_envelope() -> None:
    cfg = StaticContainmentConfig.from_yaml(REPO / "configs/step1_known_boundary/square_dispersed.yaml")
    points = build_crowd_source(cfg.crowd).observe()
    result = estimate_boundary_v2(points, cfg.boundary_v2, np.random.default_rng(cfg.seed))
    assert isinstance(result, BoundaryEstimateV2)
    assert result.component_count == 1


def test_dispersed_end_to_end_surround(tmp_path: Path) -> None:
    result = run_static_containment(
        REPO / "configs/step1_known_boundary/square_dispersed.yaml",
        tmp_path,
        methods=["abcg"],
        save_plots=False,
        live=False,
        headless=True,
    )
    status = result["abcg"]["episode_status"]
    assert status in {"CONVERGED", "TIMEOUT", "DEGRADED", "BOUNDARY_INVALID", "CAPACITY_SHORTFALL"}
    assert (tmp_path / "crowd_component_ids.npz").is_file()
    # Prefer successful surround when geometry is feasible.
    if result["abcg"]["boundary_valid"]:
        assert result["abcg"]["deployment_valid"] is True


def test_step2_gather_stub_is_explicit() -> None:
    controller = NotImplementedGatherThenSurroundController()
    with pytest.raises(NotImplementedError, match="CentralGatherThenSurroundController"):
        controller.reset(np.zeros((4, 2)), np.zeros((3, 2)))
