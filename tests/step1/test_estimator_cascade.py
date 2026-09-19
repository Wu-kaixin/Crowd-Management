from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import numpy as np

from crowd_management.crowd import generate_jupedsim_static_crowd
from crowd_management.crowd.observation import CrowdObservation
from crowd_management.estimation import BoundaryEstimateFailure, BoundaryEstimateV2
from crowd_management.experiments.static_containment import StaticContainmentConfig
from crowd_management.experiments.static_containment.known_boundary import (
    estimate_known_boundary_pipeline,
)

REPO = Path(__file__).resolve().parents[2]


def _split_clusters() -> np.ndarray:
    left = np.random.default_rng(0).normal(loc=[5.0, 10.0], scale=0.22, size=(16, 2))
    right = np.random.default_rng(1).normal(loc=[15.0, 10.0], scale=0.22, size=(16, 2))
    return np.vstack((left, right))


def test_frozen_alpha_pipeline_fails_on_two_significant_components() -> None:
    cfg = replace(
        StaticContainmentConfig.from_yaml(REPO / "configs/step1_known_boundary/square_circle.yaml"),
        estimator_cascade=False,
    )
    result, deployment = estimate_known_boundary_pipeline(CrowdObservation(positions=_split_clusters()), cfg)
    assert isinstance(result, BoundaryEstimateFailure)
    assert result.status == "BOUNDARY_INVALID"
    assert result.method != "convex_fallback"
    assert deployment is None


def test_cascade_uses_convex_fallback_and_does_not_relabel_alpha() -> None:
    cfg = replace(
        StaticContainmentConfig.from_yaml(REPO / "configs/step1_known_boundary/square_circle.yaml"),
        estimator_cascade=True,
    )
    result, deployment = estimate_known_boundary_pipeline(CrowdObservation(positions=_split_clusters()), cfg)
    assert isinstance(result, BoundaryEstimateV2)
    assert result.method in {"radial_fallback", "convex_fallback"}
    assert result.diagnostics.get("boundary_method") in {"radial_fallback", "convex_fallback"}
    assert result.method != "alpha_shape"
    assert result.diagnostics.get("boundary_method") != "alpha"
    assert deployment is not None
    assert "spawn" not in result.diagnostics


def test_cascade_keeps_alpha_label_when_alpha_succeeds() -> None:
    cfg = replace(
        StaticContainmentConfig.from_yaml(REPO / "configs/step1_known_boundary/square_circle.yaml"),
        estimator_cascade=True,
    )
    points = generate_jupedsim_static_crowd(cfg.crowd)
    result, deployment = estimate_known_boundary_pipeline(CrowdObservation(positions=points), cfg)
    assert isinstance(result, BoundaryEstimateV2)
    assert result.diagnostics.get("boundary_method") == "alpha"
    assert result.method in {"alpha_shape", "alpha"}
    assert deployment is not None


def test_leaky_radial_candidate_falls_to_covering_convex() -> None:
    rng = np.random.default_rng(4)
    blob = rng.normal(loc=[10.0, 10.0], scale=0.35, size=(40, 2))
    outlier = np.array([[14.5, 10.0]])
    cfg = replace(
        StaticContainmentConfig.from_yaml(REPO / "configs/step1_known_boundary/square_ellipse.yaml"),
        estimator_cascade=True,
    )
    result, deployment = estimate_known_boundary_pipeline(
        CrowdObservation(positions=np.vstack((blob, outlier))),
        cfg,
    )
    assert isinstance(result, BoundaryEstimateV2)
    assert deployment is not None
    distances = np.linalg.norm(
        deployment.curve_points[:, None, :] - np.vstack((blob, outlier))[None, :, :],
        axis=2,
    )
    assert float(np.min(distances)) + 1.0e-9 >= cfg.safety_distance
