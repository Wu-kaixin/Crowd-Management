"""Visualization helpers for static containment experiments."""
from __future__ import annotations

from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np

from .estimation.boundary import BoundaryEstimate
from .types import Array


def plot_static_containment(
    crowd_points: Array,
    guide_points: Array,
    boundary: BoundaryEstimate,
    output_path: str | Path,
    title: str = "Static crowd containment",
) -> None:
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    fig, ax = plt.subplots(figsize=(7.0, 6.0))
    ax.scatter(crowd_points[:, 0], crowd_points[:, 1], s=12, c="#4c78a8", alpha=0.55, label="crowd points")
    closed_boundary = np.vstack((boundary.boundary_points, boundary.boundary_points[0]))
    closed_safety = np.vstack((boundary.safety_points, boundary.safety_points[0]))
    ax.plot(closed_boundary[:, 0], closed_boundary[:, 1], color="#2f4b7c", linewidth=1.6, label="estimated boundary")
    ax.plot(closed_safety[:, 0], closed_safety[:, 1], color="#f58518", linewidth=1.6, linestyle="--", label="safety boundary")
    ax.scatter(guide_points[:, 0], guide_points[:, 1], s=90, c="#e45756", edgecolors="white", linewidths=0.9, label="guide agents")
    ax.scatter([boundary.center[0]], [boundary.center[1]], marker="x", s=80, c="#333333", label="estimated center")
    ax.set_title(title)
    ax.set_aspect("equal", adjustable="box")
    ax.grid(True, alpha=0.22)
    ax.legend(loc="best", frameon=True)
    fig.tight_layout()
    fig.savefig(output, dpi=180)
    plt.close(fig)
