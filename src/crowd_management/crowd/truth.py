"""Independent analytic truth boundaries for Step 1 synthetic scenarios.

The controller must never receive these objects.  They exist only for
evaluation and reproducibility, so estimator output cannot be used as its own
ground truth.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np

from ..types import Array
from .static_crowd import StaticCrowdConfig


@dataclass(frozen=True)
class StaticCrowdTruth:
    """Analytic synthetic boundary and its safety offset.

    All point arrays use metres in the configured world frame.  Points are
    ordered counter-clockwise within each component and do not repeat the
    first point at the end.  ``valid`` means the scenario satisfies the Step 1
    single-component truth contract; out-of-scope pressure cases may still
    carry component-wise points for diagnostic metrics.
    """

    shape: str
    boundary_points: Array
    safety_points: Array
    component_ids: Array
    component_count: int
    valid: bool
    status: str
    diagnostics: dict[str, Any]


def _rotation_matrix(rotation_deg: float) -> Array:
    theta = np.deg2rad(rotation_deg)
    c, s = np.cos(theta), np.sin(theta)
    return np.array([[c, -s], [s, c]], dtype=float)


def _ellipse_component(
    center: Array,
    axes: Array,
    rotation_deg: float,
    safety_distance: float,
    num_samples: int,
) -> tuple[Array, Array]:
    theta = np.linspace(0.0, 2.0 * np.pi, num_samples, endpoint=False)
    axes_arr = np.asarray(axes, dtype=float)
    if axes_arr.shape != (2,) or np.any(axes_arr <= 0.0):
        raise ValueError("ellipse axes must be a positive (2,) array.")
    rotation = _rotation_matrix(rotation_deg)
    local = np.column_stack((axes_arr[0] * np.cos(theta), axes_arr[1] * np.sin(theta)))
    boundary = local @ rotation.T + np.asarray(center, dtype=float)

    normal_local = np.column_stack((np.cos(theta) / axes_arr[0], np.sin(theta) / axes_arr[1]))
    normal_local /= np.linalg.norm(normal_local, axis=1, keepdims=True)
    outward_normals = normal_local @ rotation.T
    safety = boundary + float(safety_distance) * outward_normals
    return boundary, safety


def _nonconvex_component(
    center: Array,
    radius: float,
    safety_distance: float,
    num_samples: int,
) -> tuple[Array, Array]:
    theta = np.linspace(0.0, 2.0 * np.pi, num_samples, endpoint=False)
    radial = float(radius) * (
        1.0
        + 0.22 * np.sin(3.0 * theta + 0.4)
        + 0.14 * np.sin(5.0 * theta - 0.8)
    )
    radial_derivative = float(radius) * (
        0.66 * np.cos(3.0 * theta + 0.4)
        + 0.70 * np.cos(5.0 * theta - 0.8)
    )
    boundary = np.column_stack((radial * np.cos(theta), radial * np.sin(theta)))
    tangent = np.column_stack(
        (
            radial_derivative * np.cos(theta) - radial * np.sin(theta),
            radial_derivative * np.sin(theta) + radial * np.cos(theta),
        )
    )
    outward_normals = np.column_stack((tangent[:, 1], -tangent[:, 0]))
    outward_normals /= np.linalg.norm(outward_normals, axis=1, keepdims=True)
    boundary += np.asarray(center, dtype=float)
    safety = boundary + float(safety_distance) * outward_normals
    return boundary, safety


def generate_static_crowd_truth(
    config: StaticCrowdConfig,
    safety_distance: float = 0.0,
    num_samples: int = 720,
) -> StaticCrowdTruth:
    """Build evaluator-only truth from synthetic generator parameters.

    Observation noise and per-point radial jitter are deliberately excluded:
    they perturb the sampled observation, not the analytic reference shape.
    The two-cluster pressure scenario returns two separate components and an
    explicit out-of-scope status instead of joining them into a fake contour.
    """

    samples = int(num_samples)
    if samples < 8:
        raise ValueError("num_samples must be at least 8.")
    if safety_distance < 0.0:
        raise ValueError("safety_distance must be non-negative.")

    shape = config.shape.lower().replace("-", "_")
    status = "valid"
    valid = True
    if shape == "circle":
        boundary, safety = _ellipse_component(
            config.center,
            np.array([config.radius, config.radius]),
            0.0,
            safety_distance,
            samples,
        )
        components = np.zeros(samples, dtype=int)
        component_count = 1
    elif shape == "ellipse":
        axes = config.axes if config.axes is not None else np.array([config.radius * 1.5, config.radius * 0.75])
        boundary, safety = _ellipse_component(
            config.center,
            axes,
            config.rotation_deg,
            safety_distance,
            samples,
        )
        components = np.zeros(samples, dtype=int)
        component_count = 1
    elif shape in {"nonconvex", "irregular"}:
        boundary, safety = _nonconvex_component(
            config.center,
            config.radius,
            safety_distance,
            samples,
        )
        components = np.zeros(samples, dtype=int)
        component_count = 1
    elif shape in {"two_cluster", "two_clusters"}:
        left_samples = samples // 2
        right_samples = samples - left_samples
        center = np.asarray(config.center, dtype=float)
        left_boundary, left_safety = _ellipse_component(
            center + np.array([-config.lobe_offset, 0.15]),
            np.array([config.radius * 0.72, config.radius * 0.55]),
            -18.0,
            safety_distance,
            left_samples,
        )
        right_boundary, right_safety = _ellipse_component(
            center + np.array([config.lobe_offset, -0.1]),
            np.array([config.radius * 0.78, config.radius * 0.52]),
            20.0,
            safety_distance,
            right_samples,
        )
        boundary = np.vstack((left_boundary, right_boundary))
        safety = np.vstack((left_safety, right_safety))
        components = np.r_[np.zeros(left_samples, dtype=int), np.ones(right_samples, dtype=int)]
        component_count = 2
        valid = False
        status = "out_of_scope_multicomponent"
    else:
        raise ValueError(f"Unsupported static crowd truth shape: {config.shape}")

    return StaticCrowdTruth(
        shape=shape,
        boundary_points=boundary,
        safety_points=safety,
        component_ids=components,
        component_count=component_count,
        valid=valid,
        status=status,
        diagnostics={
            "reference": "analytic_generator_parameters",
            "num_samples": samples,
            "safety_distance": float(safety_distance),
            "observation_noise_included": False,
            "radial_jitter_included": False,
        },
    )
