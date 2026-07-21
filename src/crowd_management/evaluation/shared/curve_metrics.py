"""Curve-to-truth distance metrics shared by formal evaluators."""
from __future__ import annotations

import numpy as np

from ...types import Array


def symmetric_curve_errors(estimate: Array, truth: Array) -> tuple[float, float]:
    """Return Chamfer and Hausdorff distances between closed polylines."""
    distances = np.linalg.norm(estimate[:, None, :] - truth[None, :, :], axis=2)
    estimate_to_truth = np.min(distances, axis=1)
    truth_to_estimate = np.min(distances, axis=0)
    chamfer = 0.5 * (float(np.mean(estimate_to_truth)) + float(np.mean(truth_to_estimate)))
    hausdorff = max(float(np.max(estimate_to_truth)), float(np.max(truth_to_estimate)))
    return chamfer, hausdorff


def curve_errors_with_p95(estimate: Array, truth: Array) -> tuple[float, float, float]:
    """Return Chamfer, Hausdorff, and Hausdorff-95 distances."""
    distances = np.linalg.norm(estimate[:, None, :] - truth[None, :, :], axis=2)
    estimate_to_truth = np.min(distances, axis=1)
    truth_to_estimate = np.min(distances, axis=0)
    chamfer = 0.5 * (float(np.mean(estimate_to_truth)) + float(np.mean(truth_to_estimate)))
    hausdorff = max(float(np.max(estimate_to_truth)), float(np.max(truth_to_estimate)))
    hausdorff95 = float(
        max(np.percentile(estimate_to_truth, 95.0), np.percentile(truth_to_estimate, 95.0))
    )
    return chamfer, hausdorff, hausdorff95
