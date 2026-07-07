from pathlib import Path
import os
import subprocess
import sys

import numpy as np

from crowd_management.containment_metrics import containment_summary
from crowd_management.controllers import ABCGController, LegacyCenterRadiusController
from crowd_management.crowd import StaticCrowdConfig, generate_static_crowd
from crowd_management.estimation import estimate_radial_boundary
from crowd_management.experiments.static_containment import run_static_containment


def test_static_crowd_generators_are_reproducible():
    cfg = StaticCrowdConfig.from_dict(
        {"shape": "ellipse", "count": 64, "center": [5.0, 4.0], "axes": [2.0, 1.0], "rotation_deg": 20.0},
        seed=11,
    )
    a = generate_static_crowd(cfg)
    b = generate_static_crowd(cfg)
    assert a.shape == (64, 2)
    assert np.allclose(a, b)
    assert np.isfinite(a).all()


def test_boundary_estimation_returns_closed_samples():
    points = generate_static_crowd(StaticCrowdConfig.from_dict({"shape": "circle", "count": 80, "center": [0, 0], "radius": 2.0}, seed=4))
    boundary = estimate_radial_boundary(points, num_bins=36, safety_distance=0.75)
    assert boundary.boundary_points.shape == (36, 2)
    assert boundary.safety_points.shape == (36, 2)
    assert np.all(boundary.radii > 0)


def test_abcg_improves_boundary_gap_over_center_radius_on_ellipse():
    points = generate_static_crowd(
        StaticCrowdConfig.from_dict(
            {"shape": "ellipse", "count": 160, "center": [10, 7], "axes": [3.2, 1.2], "rotation_deg": 30.0},
            seed=8,
        )
    )
    abc_targets, boundary = ABCGController(num_bins=72, safety_distance=0.8).deploy(8, points)
    legacy_targets = LegacyCenterRadiusController(safety_distance=0.8).deploy(8, points)
    abc = containment_summary(abc_targets, points, boundary, coverage_radius=1.25, min_crowd_distance=0.8)
    legacy = containment_summary(legacy_targets, points, boundary, coverage_radius=1.25, min_crowd_distance=0.8)
    assert abc["max_boundary_gap"] <= legacy["max_boundary_gap"]
    assert abc["guide_crowd_safety_violation_count"] == 0


def test_static_containment_runner_outputs_metrics(tmp_path):
    repo = Path(__file__).resolve().parents[1]
    result = run_static_containment(repo / "configs" / "static_crowd_circle.yaml", tmp_path, methods=["legacy_center_radius", "abcg"], save_plots=False)
    assert "abcg" in result
    assert (tmp_path / "summary.json").is_file()
    assert (tmp_path / "summary.csv").is_file()
    assert (tmp_path / "abcg" / "metrics.json").is_file()


def test_static_containment_cli_runs(tmp_path):
    repo = Path(__file__).resolve().parents[1]
    env = os.environ.copy()
    env["PYTHONPATH"] = str(repo / "src")
    result = subprocess.run(
        [
            sys.executable,
            str(repo / "scripts" / "run_static_containment.py"),
            "--config",
            str(repo / "configs" / "static_crowd_circle.yaml"),
            "--output",
            str(tmp_path / "run"),
            "--methods",
            "abcg",
            "--skip-plots",
        ],
        cwd=repo,
        env=env,
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    assert (tmp_path / "run" / "abcg" / "metrics.json").is_file()
