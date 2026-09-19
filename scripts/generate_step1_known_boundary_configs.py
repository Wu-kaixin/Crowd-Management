"""Generate canonical Step 1 known-boundary YAML configs."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import yaml

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "configs" / "step1_benchmark"
OUT = ROOT / "configs" / "step1_known_boundary"


def circle(cx: float, cy: float, r: float, n: int = 32) -> list[list[float]]:
    t = np.linspace(0.0, 2.0 * np.pi, n, endpoint=False)
    return np.column_stack((cx + r * np.cos(t), cy + r * np.sin(t))).round(6).tolist()


def ellipse(cx: float, cy: float, a: float, b: float, n: int = 32) -> list[list[float]]:
    t = np.linspace(0.0, 2.0 * np.pi, n, endpoint=False)
    return np.column_stack((cx + a * np.cos(t), cy + b * np.sin(t))).round(6).tolist()


def concave(cx: float, cy: float, sx: float = 1.0, sy: float = 1.0) -> list[list[float]]:
    local = np.array(
        [
            [-3.0, -2.5],
            [3.0, -2.5],
            [3.0, 2.5],
            [1.4, 2.5],
            [1.4, 0.4],
            [-1.4, 0.4],
            [-1.4, 2.5],
            [-3.0, 2.5],
        ]
    )
    return (np.array([cx, cy]) + local * np.array([sx, sy])).round(6).tolist()


def load_irregular() -> np.ndarray:
    raw = yaml.safe_load((SRC / "jupedsim_irregular.yaml").read_text(encoding="utf-8"))
    return np.asarray(raw["crowd"]["region"]["vertices"], dtype=float)


def translate(points: np.ndarray, dx: float, dy: float) -> list[list[float]]:
    return (points + np.array([dx, dy])).round(6).tolist()


def base_cfg(
    *,
    scene_type: str,
    width: float,
    height: float,
    shape: str,
    vertices: list[list[float]],
    center: list[float],
    count: int = 80,
    guides: int = 12,
    demand_std: float = 0.0,
    demand_side_bias: str = "none",
    live: bool = True,
) -> dict[str, object]:
    return {
        "step": 1,
        "seed": 0,
        "scene": {
            "type": scene_type,
            "width": width,
            "height": height,
            "closed": True,
            "openings": [],
        },
        "guiders": {"count": guides},
        "heterogeneity": {
            "enabled": True,
            "radius_mean": 0.2,
            "radius_std": 0.015,
            "radius_min": 0.17,
            "radius_max": 0.23,
            "desired_speed_mean": 1.25,
            "desired_speed_std": 0.1,
            "desired_speed_min": 0.95,
            "desired_speed_max": 1.55,
            "time_gap_mean": 1.0,
            "time_gap_std": 0.08,
            "time_gap_min": 0.8,
            "time_gap_max": 1.2,
            "demand_mean": 1.0,
            "demand_std": demand_std,
            "demand_min": 0.5,
            "demand_max": 2.5,
            "demand_side_bias": demand_side_bias,
        },
        "containment": {
            "safety_distance": 0.85,
            "coverage_radius": 1.25,
            "min_guider_distance": 0.6,
            "boundary_bins": 72,
            "boundary_sample_spacing": 0.08,
        },
        "boundary": {
            "estimator": "alpha",
            "alpha_scale": 2.5,
            "alpha_growth_factors": [1.0, 1.25, 1.5, 2.0, 3.0, 4.0],
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
            "unmet_target_cost": 1000000.0,
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
            "min_guide_distance": 0.6,
            "min_crowd_distance": 0.85,
            "wall_margin": 0.25,
            "residual_tolerance": 1.0e-9,
            "max_projection_sweeps": 200,
        },
        "visualization": {
            "live": live,
            "render_every": 1,
            "max_fps": 20,
            "show_trails": True,
        },
        "crowd": {
            "source": "jupedsim",
            "shape": shape,
            "count": count,
            "center": center,
            "radius": 3.0,
            "spawn": {"vertices": vertices},
            "spacing": {
                "distance_to_agents": 0.35,
                "distance_to_polygon": 0.2,
            },
        },
    }


def dump(name: str, data: dict[str, object]) -> None:
    path = OUT / name
    path.write_text(yaml.safe_dump(data, sort_keys=False, allow_unicode=True), encoding="utf-8")


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    irregular = load_irregular()
    shapes_square = {
        "circle": circle(10.0, 10.0, 3.2),
        "ellipse": ellipse(10.0, 10.0, 4.5, 2.2),
        "concave": concave(10.0, 10.0),
        "irregular": translate(irregular, 0.0, 3.0),
    }
    shapes_rect = {
        "circle": circle(14.0, 8.0, 3.2),
        "ellipse": ellipse(14.0, 8.0, 4.5, 2.2),
        "concave": concave(14.0, 8.0),
        "irregular": translate(irregular, 4.0, 1.0),
    }
    for shape, verts in shapes_square.items():
        dump(
            f"square_{shape}.yaml",
            base_cfg(
                scene_type="square",
                width=20.0,
                height=20.0,
                shape=shape,
                vertices=verts,
                center=[10.0, 10.0],
            ),
        )
    for shape, verts in shapes_rect.items():
        dump(
            f"rectangle_{shape}.yaml",
            base_cfg(
                scene_type="rectangle",
                width=28.0,
                height=16.0,
                shape=shape,
                vertices=verts,
                center=[14.0, 8.0],
            ),
        )
    dump(
        "square_off_center.yaml",
        base_cfg(
            scene_type="square",
            width=20.0,
            height=20.0,
            shape="off_center",
            vertices=[[2.0, 3.0], [9.0, 3.0], [9.0, 10.0], [2.0, 10.0]],
            center=[5.5, 6.5],
        ),
    )
    dump(
        "square_elongated.yaml",
        base_cfg(
            scene_type="square",
            width=20.0,
            height=20.0,
            shape="elongated",
            vertices=[[3.0, 8.0], [17.0, 8.0], [17.0, 12.0], [3.0, 12.0]],
            center=[10.0, 10.0],
        ),
    )
    dump(
        "square_near_wall_feasible.yaml",
        base_cfg(
            scene_type="square",
            width=20.0,
            height=20.0,
            shape="near_wall_feasible",
            vertices=[[2.0, 6.0], [8.0, 6.0], [8.0, 14.0], [2.0, 14.0]],
            center=[5.0, 10.0],
        ),
    )
    dump(
        "square_near_wall_infeasible.yaml",
        base_cfg(
            scene_type="square",
            width=20.0,
            height=20.0,
            shape="near_wall_infeasible",
            vertices=[[0.4, 9.0], [4.0, 9.0], [4.0, 11.0], [0.4, 11.0]],
            center=[2.2, 10.0],
            count=20,
        ),
    )
    dump(
        "square_high_demand_side.yaml",
        base_cfg(
            scene_type="square",
            width=20.0,
            height=20.0,
            shape="circle",
            vertices=circle(10.0, 10.0, 3.2),
            center=[10.0, 10.0],
            demand_std=0.4,
            demand_side_bias="positive_x",
        ),
    )
    dump(
        "square_insufficient_guides.yaml",
        base_cfg(
            scene_type="square",
            width=20.0,
            height=20.0,
            shape="circle",
            vertices=circle(10.0, 10.0, 4.8),
            center=[10.0, 10.0],
            count=120,
            guides=4,
        ),
    )
    dump(
        "homogeneous_square_circle.yaml",
        {
            **base_cfg(
                scene_type="square",
                width=20.0,
                height=20.0,
                shape="circle",
                vertices=circle(10.0, 10.0, 3.2),
                center=[10.0, 10.0],
            ),
            "heterogeneity": {
                **base_cfg(
                    scene_type="square",
                    width=20.0,
                    height=20.0,
                    shape="circle",
                    vertices=circle(10.0, 10.0, 3.2),
                    center=[10.0, 10.0],
                )["heterogeneity"],
                "enabled": False,
                "radius_std": 0.0,
                "desired_speed_std": 0.0,
                "time_gap_std": 0.0,
                "demand_std": 0.0,
            },
        },
    )
    dump(
        "benchmark_manifest.yaml",
        {
            "name": "step1_known_boundary_holdout",
            "environments": ["square", "rectangle"],
            "shapes": ["circle", "ellipse", "concave", "irregular"],
            "development_seeds": list(range(0, 5)),
            "holdout_seeds": list(range(100, 120)),
            "methods": ["abcg"],
            "live_default": True,
        },
    )


if __name__ == "__main__":
    main()
