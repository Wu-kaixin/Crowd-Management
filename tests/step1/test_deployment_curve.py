"""Deployment-curve buffering and explicit workspace failures."""

from __future__ import annotations

import numpy as np

from crowd_management.geometry.deployment_curve import DeploymentCurve, DeploymentCurveFailure, build_deployment_curve
from crowd_management.scenarios import RectangularScenario


def test_deployment_curve_valid() -> None:
    square = np.array([[8.0, 8.0], [12.0, 8.0], [12.0, 12.0], [8.0, 12.0]])
    crowd = np.array([[9.0, 9.0], [11.0, 9.0], [10.0, 11.0]])
    scene = RectangularScenario(name="square", width=20.0, height=20.0)
    result = build_deployment_curve(
        square,
        0.85,
        crowd_points=crowd,
        workspace=scene,
        wall_margin=0.25,
        sample_spacing=0.2,
    )
    assert isinstance(result, DeploymentCurve)
    assert result.status == "VALID"
    assert result.length > 0.0
    assert not result.diagnostics["used_environment_as_crowd_boundary"]


def test_deployment_curve_no_self_intersection() -> None:
    notch = np.array(
        [
            [0.0, 0.0],
            [4.0, 0.0],
            [4.0, 4.0],
            [2.2, 4.0],
            [2.2, 1.0],
            [1.8, 1.0],
            [1.8, 4.0],
            [0.0, 4.0],
        ]
    )
    result = build_deployment_curve(notch, 0.35, sample_spacing=0.08)
    if isinstance(result, DeploymentCurveFailure):
        assert result.status in {"OFFSET_INVALID", "DEPLOYMENT_INFEASIBLE"}
        assert result.reason != "silent_fallback"
    else:
        from shapely.geometry import LineString

        closed = np.vstack((result.curve_points, result.curve_points[0]))
        assert LineString(closed).is_simple


def test_offset_outside_workspace_is_explicit() -> None:
    near_wall = np.array([[0.4, 9.0], [3.5, 9.0], [3.5, 11.0], [0.4, 11.0]])
    scene = RectangularScenario(name="square", width=20.0, height=20.0)
    result = build_deployment_curve(
        near_wall,
        0.85,
        crowd_points=np.array([[1.5, 10.0], [2.0, 10.2]]),
        workspace=scene,
        wall_margin=0.25,
        sample_spacing=0.1,
        min_crowd_clearance=0.0,
    )
    assert isinstance(result, DeploymentCurveFailure)
    assert result.status == "OFFSET_OUTSIDE_WORKSPACE"
    assert result.diagnostics.get("environment_is_not_crowd_boundary") is True
