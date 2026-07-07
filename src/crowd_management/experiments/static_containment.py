"""Static unknown-crowd containment experiment runner."""
from __future__ import annotations

import csv
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import yaml

from ..containment_metrics import containment_summary
from ..containment_visualization import plot_static_containment
from ..controllers import ABCGController, LegacyCenterRadiusController, RandomDeploymentController, StaticCircleController
from ..crowd import StaticCrowdConfig, generate_static_crowd
from ..estimation.boundary import estimate_radial_boundary
from ..types import Array, as_vec2


@dataclass(frozen=True)
class StaticContainmentConfig:
    seed: int
    room_size: Array
    crowd: StaticCrowdConfig
    guide_count: int
    safety_distance: float
    coverage_radius: float
    min_guider_distance: float
    boundary_bins: int

    @classmethod
    def from_yaml(cls, path: str | Path) -> "StaticContainmentConfig":
        with open(path, "r", encoding="utf-8") as f:
            raw = yaml.safe_load(f)
        seed = int(raw.get("seed", 0))
        containment = raw.get("containment", {})
        return cls(
            seed=seed,
            room_size=as_vec2(raw.get("room", {}).get("size", [20.0, 14.0]), "room.size"),
            crowd=StaticCrowdConfig.from_dict(raw["crowd"], seed=seed),
            guide_count=int(raw.get("guiders", {}).get("count", 8)),
            safety_distance=float(containment.get("safety_distance", 0.8)),
            coverage_radius=float(containment.get("coverage_radius", 1.2)),
            min_guider_distance=float(containment.get("min_guider_distance", 0.55)),
            boundary_bins=int(containment.get("boundary_bins", 72)),
        )


def _controller_targets(method: str, cfg: StaticContainmentConfig, crowd_points: Array) -> tuple[Array, Any]:
    method = method.lower()
    if method == "random":
        controller = RandomDeploymentController(cfg.room_size, seed=cfg.seed)
        targets = controller.deploy(cfg.guide_count, crowd_points)
        boundary = estimate_radial_boundary(crowd_points, cfg.boundary_bins, cfg.safety_distance)
        return targets, boundary
    if method == "static_circle":
        radius = cfg.crowd.radius + cfg.safety_distance
        controller = StaticCircleController(radius=radius, center=cfg.crowd.center)
        targets = controller.deploy(cfg.guide_count, crowd_points)
        boundary = estimate_radial_boundary(crowd_points, cfg.boundary_bins, cfg.safety_distance)
        return targets, boundary
    if method == "legacy_center_radius":
        controller = LegacyCenterRadiusController(safety_distance=cfg.safety_distance)
        targets = controller.deploy(cfg.guide_count, crowd_points)
        boundary = estimate_radial_boundary(crowd_points, cfg.boundary_bins, cfg.safety_distance)
        return targets, boundary
    if method == "abcg":
        controller = ABCGController(
            num_bins=cfg.boundary_bins,
            safety_distance=cfg.safety_distance,
            min_guider_distance=cfg.min_guider_distance,
        )
        return controller.deploy(cfg.guide_count, crowd_points, room_size=cfg.room_size)
    raise ValueError(f"Unsupported containment method: {method}")


def run_static_containment(
    config_path: str | Path,
    output_dir: str | Path,
    methods: list[str] | None = None,
    save_plots: bool = True,
) -> dict[str, dict[str, float | int]]:
    cfg = StaticContainmentConfig.from_yaml(config_path)
    crowd_points = generate_static_crowd(cfg.crowd)
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(output / "crowd_points.npz", positions=crowd_points)

    methods = methods or ["random", "static_circle", "legacy_center_radius", "abcg"]
    results: dict[str, dict[str, float | int]] = {}
    for method in methods:
        targets, boundary = _controller_targets(method, cfg, crowd_points)
        summary = containment_summary(targets, crowd_points, boundary, cfg.coverage_radius, cfg.safety_distance)
        results[method] = summary
        method_dir = output / method
        method_dir.mkdir(parents=True, exist_ok=True)
        np.savez_compressed(
            method_dir / "containment_state.npz",
            crowd_points=crowd_points,
            guide_points=targets,
            boundary_points=boundary.boundary_points,
            safety_points=boundary.safety_points,
            center=boundary.center,
        )
        with open(method_dir / "metrics.json", "w", encoding="utf-8") as f:
            json.dump(summary, f, indent=2)
        if save_plots:
            plot_static_containment(crowd_points, targets, boundary, method_dir / "containment.png", title=f"{method}: static containment")

    with open(output / "summary.json", "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2)
    with open(output / "summary.csv", "w", encoding="utf-8", newline="") as f:
        fieldnames = ["method", *next(iter(results.values())).keys()]
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for method, row in results.items():
            writer.writerow({"method": method, **row})
    return results
