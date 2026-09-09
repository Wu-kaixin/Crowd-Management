"""Static unknown-crowd point-cloud generators.

ROLE:
    CORE DATA GENERATORS.

Step 1 treats a crowd as an observed static 2-D point cloud.

Two observation sources are supported:

1. synthetic
2. jupedsim

The ABCG controller must only receive the observed point cloud.
Evaluator-only truth must never be passed to the estimator/controller.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np

from ..types import Array, as_vec2


def _parse_region_vertices(
    raw: dict[str, Any],
) -> tuple[tuple[float, float], ...] | None:
    region = raw.get("region", {})
    vertices = region.get("vertices")

    if vertices is None:
        return None

    arr = np.asarray(vertices, dtype=float)

    if arr.ndim != 2 or arr.shape[1] != 2:
        raise ValueError(
            "crowd.region.vertices must have shape (N, 2)."
        )

    if arr.shape[0] < 3:
        raise ValueError(
            "crowd.region.vertices must contain at least 3 vertices."
        )

    if not np.isfinite(arr).all():
        raise ValueError(
            "crowd.region.vertices must contain only finite values."
        )

    return tuple(
        (float(x), float(y))
        for x, y in arr
    )


@dataclass(frozen=True)
class StaticCrowdConfig:
    # ---------------------------------------------------------
    # Existing synthetic scenario parameters
    # ---------------------------------------------------------
    shape: str
    count: int
    center: Array
    radius: float = 2.0
    axes: Array | None = None
    rotation_deg: float = 0.0
    noise_std: float = 0.04
    radial_jitter: float = 0.08
    lobe_offset: float = 1.2
    seed: int = 0

    # ---------------------------------------------------------
    # Crowd observation source
    # ---------------------------------------------------------
    source: str = "synthetic"

    # ---------------------------------------------------------
    # JuPedSim Step-1 parameters
    # ---------------------------------------------------------
    region_vertices: tuple[tuple[float, float], ...] | None = None
    distance_to_agents: float = 0.45
    distance_to_polygon: float = 0.20

    @classmethod
    def from_dict(
        cls,
        raw: dict[str, Any],
        seed: int = 0,
    ) -> "StaticCrowdConfig":
        source = (
            str(raw.get("source", "synthetic"))
            .strip()
            .lower()
            .replace("-", "_")
        )

        if source not in {"synthetic", "jupedsim"}:
            raise ValueError(
                f"Unsupported crowd source: {source}"
            )

        spacing = raw.get("spacing", {})

        distance_to_agents = float(
            spacing.get(
                "distance_to_agents",
                raw.get("distance_to_agents", 0.45),
            )
        )

        distance_to_polygon = float(
            spacing.get(
                "distance_to_polygon",
                raw.get("distance_to_polygon", 0.20),
            )
        )

        if distance_to_agents <= 0.0:
            raise ValueError(
                "distance_to_agents must be positive."
            )

        if distance_to_polygon < 0.0:
            raise ValueError(
                "distance_to_polygon must be non-negative."
            )

        region_vertices = _parse_region_vertices(raw)

        if source == "jupedsim" and region_vertices is None:
            raise ValueError(
                "JuPedSim crowd source requires "
                "crowd.region.vertices."
            )

        count = int(raw["count"])

        if count <= 0:
            raise ValueError(
                "crowd.count must be positive."
            )

        return cls(
            source=source,
            shape=str(raw.get("shape", "circle")),
            count=count,
            center=as_vec2(
                raw.get("center", [0.0, 0.0]),
                "crowd.center",
            ),
            radius=float(raw.get("radius", 2.0)),
            axes=(
                as_vec2(raw["axes"], "crowd.axes")
                if "axes" in raw
                else None
            ),
            rotation_deg=float(
                raw.get("rotation_deg", 0.0)
            ),
            noise_std=float(
                raw.get("noise_std", 0.04)
            ),
            radial_jitter=float(
                raw.get("radial_jitter", 0.08)
            ),
            lobe_offset=float(
                raw.get("lobe_offset", 1.2)
            ),
            seed=int(raw.get("seed", seed)),
            region_vertices=region_vertices,
            distance_to_agents=distance_to_agents,
            distance_to_polygon=distance_to_polygon,
        )


def _rng(
    seed: int | None,
) -> np.random.Generator:
    return np.random.default_rng(seed)


def _sample_disk(
    n: int,
    rng: np.random.Generator,
) -> tuple[Array, Array]:
    angles = rng.uniform(
        0.0,
        2.0 * np.pi,
        size=n,
    )

    radii = np.sqrt(
        rng.uniform(
            0.0,
            1.0,
            size=n,
        )
    )

    return angles, radii


def _rotation_matrix(
    rotation_deg: float,
) -> Array:
    theta = np.deg2rad(rotation_deg)

    c = np.cos(theta)
    s = np.sin(theta)

    return np.array(
        [
            [c, -s],
            [s, c],
        ],
        dtype=float,
    )


def generate_circle_crowd(
    count: int,
    center: Array,
    radius: float,
    noise_std: float = 0.04,
    seed: int | None = None,
) -> Array:
    """Generate a compact circular crowd point cloud."""

    rng = _rng(seed)

    angles, radii = _sample_disk(
        count,
        rng,
    )

    points = np.column_stack(
        (
            np.cos(angles),
            np.sin(angles),
        )
    )

    points *= radii[:, None] * radius

    if noise_std > 0:
        points += rng.normal(
            0.0,
            noise_std,
            size=points.shape,
        )

    return points + as_vec2(
        center,
        "center",
    )


def generate_ellipse_crowd(
    count: int,
    center: Array,
    axes: Array,
    rotation_deg: float = 0.0,
    noise_std: float = 0.04,
    seed: int | None = None,
) -> Array:
    """Generate an elliptical crowd."""

    rng = _rng(seed)

    angles, radii = _sample_disk(
        count,
        rng,
    )

    unit_points = np.column_stack(
        (
            np.cos(angles),
            np.sin(angles),
        )
    )

    unit_points *= radii[:, None]

    points = unit_points * as_vec2(
        axes,
        "axes",
    )

    points = (
        points
        @ _rotation_matrix(rotation_deg).T
    )

    if noise_std > 0:
        points += rng.normal(
            0.0,
            noise_std,
            size=points.shape,
        )

    return points + as_vec2(
        center,
        "center",
    )


def generate_nonconvex_crowd(
    count: int,
    center: Array,
    radius: float,
    radial_jitter: float = 0.08,
    noise_std: float = 0.04,
    seed: int | None = None,
) -> Array:
    """Generate a star-like irregular crowd."""

    rng = _rng(seed)

    angles, radii = _sample_disk(
        count,
        rng,
    )

    boundary = radius * (
        1.0
        + 0.22 * np.sin(
            3.0 * angles + 0.4
        )
        + 0.14 * np.sin(
            5.0 * angles - 0.8
        )
    )

    boundary *= rng.normal(
        1.0,
        radial_jitter,
        size=count,
    )

    points = np.column_stack(
        (
            np.cos(angles),
            np.sin(angles),
        )
    )

    points *= (
        radii * boundary
    )[:, None]

    if noise_std > 0:
        points += rng.normal(
            0.0,
            noise_std,
            size=points.shape,
        )

    return points + as_vec2(
        center,
        "center",
    )


def generate_two_cluster_crowd(
    count: int,
    center: Array,
    radius: float,
    lobe_offset: float = 1.2,
    noise_std: float = 0.04,
    seed: int | None = None,
) -> Array:
    """Generate two nearby lobes."""

    rng = _rng(seed)

    left_count = count // 2
    right_count = count - left_count

    center = as_vec2(
        center,
        "center",
    )

    left = generate_ellipse_crowd(
        left_count,
        center
        + np.array(
            [-lobe_offset, 0.15]
        ),
        np.array(
            [
                radius * 0.72,
                radius * 0.55,
            ]
        ),
        rotation_deg=-18.0,
        noise_std=noise_std,
        seed=int(
            rng.integers(
                0,
                2**31 - 1,
            )
        ),
    )

    right = generate_ellipse_crowd(
        right_count,
        center
        + np.array(
            [lobe_offset, -0.1]
        ),
        np.array(
            [
                radius * 0.78,
                radius * 0.52,
            ]
        ),
        rotation_deg=20.0,
        noise_std=noise_std,
        seed=int(
            rng.integers(
                0,
                2**31 - 1,
            )
        ),
    )

    return np.vstack(
        (
            left,
            right,
        )
    )


def generate_static_crowd(
    config: StaticCrowdConfig,
) -> Array:
    """Generate a synthetic static crowd.

    This function intentionally remains synthetic-only.

    JuPedSim observations must be created through
    build_crowd_source().
    """

    if config.source != "synthetic":
        raise ValueError(
            "generate_static_crowd() is synthetic-only. "
            "Use build_crowd_source() for JuPedSim."
        )

    shape = (
        config.shape
        .lower()
        .replace("-", "_")
    )

    if shape == "circle":
        return generate_circle_crowd(
            config.count,
            config.center,
            config.radius,
            config.noise_std,
            config.seed,
        )

    if shape == "ellipse":
        axes = (
            config.axes
            if config.axes is not None
            else np.array(
                [
                    config.radius * 1.5,
                    config.radius * 0.75,
                ]
            )
        )

        return generate_ellipse_crowd(
            config.count,
            config.center,
            axes,
            config.rotation_deg,
            config.noise_std,
            config.seed,
        )

    if shape in {
        "nonconvex",
        "irregular",
    }:
        return generate_nonconvex_crowd(
            config.count,
            config.center,
            config.radius,
            config.radial_jitter,
            config.noise_std,
            config.seed,
        )

    if shape in {
        "two_cluster",
        "two_clusters",
    }:
        return generate_two_cluster_crowd(
            config.count,
            config.center,
            config.radius,
            config.lobe_offset,
            config.noise_std,
            config.seed,
        )

    raise ValueError(
        f"Unsupported static crowd shape: "
        f"{config.shape}"
    )