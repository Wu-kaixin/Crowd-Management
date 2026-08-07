"""Matplotlib drawing helpers for README media scenes."""

from __future__ import annotations

import numpy as np

from .geometry import closed_curve


def draw_scene(
    ax,
    crowd_points: np.ndarray,
    guide_points: np.ndarray,
    boundary_points: np.ndarray | None = None,
    safety_points: np.ndarray | None = None,
    title: str = "",
    xlim: tuple[float, float] | None = None,
    ylim: tuple[float, float] | None = None,
    legend: bool = False,
) -> None:
    ax.scatter(crowd_points[:, 0], crowd_points[:, 1], s=8, c="#4c78a8", alpha=0.48, label="crowd")
    if boundary_points is not None and len(boundary_points):
        ax.plot(*closed_curve(boundary_points).T, c="#1f4e79", lw=1.3, label="estimated boundary")
    if safety_points is not None and len(safety_points):
        ax.plot(*closed_curve(safety_points).T, c="#f28e2b", lw=1.5, ls="--", label="safety boundary")
    ax.scatter(guide_points[:, 0], guide_points[:, 1], s=70, c="#e15759", edgecolor="white", lw=0.8, label="guides")
    ax.set_title(title, fontsize=10)
    ax.set_aspect("equal")
    if xlim is not None:
        ax.set_xlim(*xlim)
    if ylim is not None:
        ax.set_ylim(*ylim)
    ax.grid(alpha=0.18)
    if legend:
        ax.legend(loc="upper right", fontsize=7)
