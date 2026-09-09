"""Generate matched Step-1 benchmark configurations.

Outputs:
    JuPedSim:
        circle
        ellipse
        concave
        irregular

    Synthetic matched references:
        circle
        ellipse
        irregular

Concave is JuPedSim-only because the existing synthetic generator
does not provide an exactly matched concave polygon model.
"""

from __future__ import annotations

import copy
import math
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "configs" / "step1_benchmark"


def polygon_circle(
    center: tuple[float, float],
    radius: float,
    samples: int = 40,
) -> list[list[float]]:
    cx, cy = center

    return [
        [
            cx + radius * math.cos(2.0 * math.pi * i / samples),
            cy + radius * math.sin(2.0 * math.pi * i / samples),
        ]
        for i in range(samples)
    ]


def polygon_ellipse(
    center: tuple[float, float],
    axes: tuple[float, float],
    rotation_deg: float,
    samples: int = 48,
) -> list[list[float]]:
    cx, cy = center
    a, b = axes

    rotation = math.radians(rotation_deg)
    c = math.cos(rotation)
    s = math.sin(rotation)

    vertices: list[list[float]] = []

    for i in range(samples):
        theta = 2.0 * math.pi * i / samples

        x_local = a * math.cos(theta)
        y_local = b * math.sin(theta)

        x = cx + c * x_local - s * y_local
        y = cy + s * x_local + c * y_local

        vertices.append([x, y])

    return vertices


def polygon_irregular(
    center: tuple[float, float],
    radius: float,
    samples: int = 48,
) -> list[list[float]]:
    cx, cy = center

    vertices: list[list[float]] = []

    for i in range(samples):
        theta = 2.0 * math.pi * i / samples

        radial = radius * (
            1.0
            + 0.22 * math.sin(3.0 * theta + 0.4)
            + 0.14 * math.sin(5.0 * theta - 0.8)
        )

        vertices.append(
            [
                cx + radial * math.cos(theta),
                cy + radial * math.sin(theta),
            ]
        )

    return vertices


def common_config() -> dict:
    return {
        "seed": 0,
        "room": {
            "size": [20.0, 14.0],
        },
        "guiders": {
            "count": 12,
        },
        "heterogeneity": {
            "enabled": True,
            "radius_mean": 0.20,
            "radius_std": 0.015,
            "radius_min": 0.17,
            "radius_max": 0.23,
            "desired_speed_mean": 1.25,
            "desired_speed_std": 0.10,
            "desired_speed_min": 0.95,
            "desired_speed_max": 1.55,
            "time_gap_mean": 1.00,
            "time_gap_std": 0.08,
            "time_gap_min": 0.80,
            "time_gap_max": 1.20,
        },
        "containment": {
            "safety_distance": 0.85,
            "coverage_radius": 1.25,
            "min_guider_distance": 0.60,
            "boundary_bins": 72,
            "boundary_sample_spacing": 0.08,
        },
        "boundary": {
            "estimator": "alpha",
            "alpha_scale": 2.5,
            "alpha_growth_factors": [
                1.0,
                1.25,
                1.5,
                2.0,
                3.0,
                4.0,
            ],
            "alpha_smoothing_passes": 5,
            "min_observation_points": 8,
            "min_observation_coverage": 0.8,
            "bootstrap_samples": 8,
            "bootstrap_min_success_fraction": 0.5,
            "bootstrap_confidence_floor": 0.15,
        },
        "resources": {
            "required_arc_gap": 2.5,
            "min_active_guides": 3,
            "increase_hysteresis": 0.1,
            "decrease_hysteresis": 0.1,
        },
        "assignment": {
            "switch_penalty": 0.25,
            "reserve_cost": 0.0,
            "unmet_target_cost": 1_000_000.0,
        },
        "motion": {
            "dt": 0.1,
            "gain": 1.5,
            "max_speed": 1.0,
            "tracking_rmse_tolerance": 0.03,
            "speed_tolerance": 0.03,
            "hold_steps": 10,
            "max_steps": 400,
        },
        "safety": {
            "enabled": True,
            "min_guide_distance": 0.60,
            "min_crowd_distance": 0.85,
            "room_margin": 0.25,
            "residual_tolerance": 1.0e-9,
            "max_projection_sweeps": 200,
        },
    }


def make_jupedsim(
    name: str,
    vertices: list[list[float]],
    count: int = 80,
) -> dict:
    config = common_config()

    config["benchmark"] = {
        "name": name,
        "source": "jupedsim",
    }

    config["crowd"] = {
        "source": "jupedsim",
        "shape": name,
        "count": count,
        "center": [10.0, 7.0],
        "radius": 3.0,
        "region": {
            "vertices": vertices,
        },
        "spacing": {
            "distance_to_agents": 0.35,
            "distance_to_polygon": 0.20,
        },
    }

    return config


def make_synthetic_circle() -> dict:
    config = common_config()

    config["benchmark"] = {
        "name": "circle",
        "source": "synthetic",
    }

    config["crowd"] = {
        "source": "synthetic",
        "shape": "circle",
        "count": 80,
        "center": [10.0, 7.0],
        "radius": 3.0,
        "noise_std": 0.04,
    }

    return config


def make_synthetic_ellipse() -> dict:
    config = common_config()

    config["benchmark"] = {
        "name": "ellipse",
        "source": "synthetic",
    }

    config["crowd"] = {
        "source": "synthetic",
        "shape": "ellipse",
        "count": 80,
        "center": [10.0, 7.0],
        "axes": [3.6, 2.2],
        "rotation_deg": 25.0,
        "noise_std": 0.04,
    }

    return config


def make_synthetic_irregular() -> dict:
    config = common_config()

    config["benchmark"] = {
        "name": "irregular",
        "source": "synthetic",
    }

    config["crowd"] = {
        "source": "synthetic",
        "shape": "nonconvex",
        "count": 80,
        "center": [10.0, 7.0],
        "radius": 3.0,
        "noise_std": 0.04,
        "radial_jitter": 0.05,
    }

    return config


def write_yaml(
    path: Path,
    data: dict,
) -> None:
    path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    with open(
        path,
        "w",
        encoding="utf-8",
    ) as file:
        yaml.safe_dump(
            data,
            file,
            sort_keys=False,
            allow_unicode=True,
        )


def main() -> None:
    OUTPUT.mkdir(
        parents=True,
        exist_ok=True,
    )

    circle = polygon_circle(
        (10.0, 7.0),
        3.2,
    )

    ellipse = polygon_ellipse(
        (10.0, 7.0),
        (3.8, 2.4),
        25.0,
    )

    concave = [
        [7.0, 4.5],
        [13.0, 4.5],
        [13.0, 9.5],
        [11.4, 9.5],
        [11.4, 7.4],
        [8.6, 7.4],
        [8.6, 9.5],
        [7.0, 9.5],
    ]

    irregular = polygon_irregular(
        (10.0, 7.0),
        3.2,
    )

    configs = {
        "jupedsim_circle.yaml": make_jupedsim(
            "circle",
            circle,
        ),
        "jupedsim_ellipse.yaml": make_jupedsim(
            "ellipse",
            ellipse,
        ),
        "jupedsim_concave.yaml": make_jupedsim(
            "concave",
            concave,
        ),
        "jupedsim_irregular.yaml": make_jupedsim(
            "irregular",
            irregular,
        ),
        "synthetic_circle.yaml": make_synthetic_circle(),
        "synthetic_ellipse.yaml": make_synthetic_ellipse(),
        "synthetic_irregular.yaml": make_synthetic_irregular(),
    }

    for filename, data in configs.items():
        write_yaml(
            OUTPUT / filename,
            data,
        )

    manifest = {
        "paired_cases": {
            "circle": {
                "synthetic": "synthetic_circle.yaml",
                "jupedsim": "jupedsim_circle.yaml",
            },
            "ellipse": {
                "synthetic": "synthetic_ellipse.yaml",
                "jupedsim": "jupedsim_ellipse.yaml",
            },
            "irregular": {
                "synthetic": "synthetic_irregular.yaml",
                "jupedsim": "jupedsim_irregular.yaml",
            },
        },
        "pressure_cases": {
            "concave": "jupedsim_concave.yaml",
        },
        "pairing_note": (
            "Pairs match nominal geometry, crowd count, room, "
            "controller and evaluation settings. They do not "
            "claim identical point-process distributions."
        ),
    }

    write_yaml(
        OUTPUT / "benchmark_manifest.yaml",
        manifest,
    )

    print(f"Wrote benchmark configs to: {OUTPUT}")


if __name__ == "__main__":
    main()