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
    spawn = raw.get("spawn", {})
    region = raw.get("region", {})
    vertices = spawn.get("vertices")
    if vertices is None:
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


def circle_spawn_vertices(
    center: Array,
    radius: float,
    *,
    samples: int = 36,
) -> tuple[tuple[float, float], ...]:
    """Build a regular polygon spawn region from centre + radius."""
    if samples < 3:
        raise ValueError("samples must be at least 3.")
    if not np.isfinite(radius) or radius <= 0.0:
        raise ValueError("radius must be finite and positive.")
    centre = as_vec2(center, "center")
    angles = np.linspace(0.0, 2.0 * np.pi, samples, endpoint=False)
    return tuple(
        (float(centre[0] + radius * np.cos(theta)), float(centre[1] + radius * np.sin(theta)))
        for theta in angles
    )


def sample_dispersed_centers(
    workspace: Array,
    count: int,
    *,
    margin: float,
    min_separation: float,
    seed: int,
    max_attempts: int = 5000,
) -> Array:
    """Sample separated cluster centres inside an axis-aligned workspace."""
    size = as_vec2(workspace, "workspace")
    if count < 1:
        raise ValueError("dispersed cluster count must be positive.")
    if not np.isfinite(margin) or margin < 0.0:
        raise ValueError("margin must be finite and non-negative.")
    if not np.isfinite(min_separation) or min_separation < 0.0:
        raise ValueError("min_separation must be finite and non-negative.")
    low = np.array([margin, margin], dtype=float)
    high = size - margin
    if np.any(high <= low):
        raise ValueError("workspace margin leaves an empty region for dispersed centres.")
    rng = np.random.default_rng(int(seed))
    centres = np.zeros((count, 2), dtype=float)
    placed = 0
    attempts = 0
    while placed < count and attempts < max_attempts:
        attempts += 1
        candidate = rng.uniform(low, high)
        if placed > 0 and min_separation > 0.0:
            if np.any(np.linalg.norm(centres[:placed] - candidate, axis=1) < min_separation):
                continue
        centres[placed] = candidate
        placed += 1
    if placed < count:
        raise RuntimeError(
            f"Could not place {count} dispersed centres with min_separation={min_separation} "
            f"in workspace {size.tolist()} (placed {placed}). Reduce cluster_count or separation."
        )
    return centres


def _expand_dispersed_groups(
    raw: dict[str, Any],
    *,
    source: str,
    seed: int,
    distance_to_agents: float,
    distance_to_polygon: float,
) -> list[dict[str, Any]]:
    """Turn a ``dispersed`` block into concrete group dicts."""
    block = dict(raw.get("dispersed") or {})
    cluster_count = int(block.get("cluster_count", raw.get("cluster_count", 8)))
    people_per = int(block.get("people_per_cluster", block.get("per_cluster", 5)))
    cluster_radius = float(block.get("cluster_radius", block.get("radius", 0.9)))
    min_sep = float(block.get("min_center_separation", 2.5))
    margin = float(block.get("margin", 2.5))
    workspace = as_vec2(block.get("workspace", [20.0, 20.0]), "dispersed.workspace")
    if cluster_count < 2:
        raise ValueError("dispersed.cluster_count must be at least 2.")
    if people_per < 1:
        raise ValueError("dispersed.people_per_cluster must be positive.")
    centres = sample_dispersed_centers(
        workspace,
        cluster_count,
        margin=margin + cluster_radius,
        min_separation=min_sep,
        seed=int(block.get("seed", seed + 101)),
    )
    groups: list[dict[str, Any]] = []
    for index, centre in enumerate(centres):
        groups.append(
            {
                "source": source,
                "shape": "circle",
                "count": people_per,
                "center": [float(centre[0]), float(centre[1])],
                "radius": cluster_radius,
                "seed": int(seed + 31 * (index + 1)),
                "noise_std": float(raw.get("noise_std", 0.04)),
                "spacing": {
                    "distance_to_agents": distance_to_agents,
                    "distance_to_polygon": distance_to_polygon,
                },
            }
        )
    return groups



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

    # ---------------------------------------------------------
    # Multi-crowd (same room): 2+ disjoint groups. Step 1 remains
    # single-component for ABCG; multi groups are explicit
    # out-of-scope pressure / visualization scenarios.
    # ---------------------------------------------------------
    groups: tuple["StaticCrowdConfig", ...] = ()

    @property
    def is_multi(self) -> bool:
        return len(self.groups) >= 2

    @property
    def is_dispersed(self) -> bool:
        return self.shape.lower().replace("-", "_") == "dispersed" and self.is_multi

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

        shape_hint = str(raw.get("shape", "circle")).strip().lower().replace("-", "_")
        groups_raw = list(raw.get("groups") or [])
        if (shape_hint == "dispersed" or raw.get("dispersed")) and not groups_raw:
            groups_raw = _expand_dispersed_groups(
                raw,
                source=source,
                seed=seed,
                distance_to_agents=distance_to_agents,
                distance_to_polygon=distance_to_polygon,
            )
            shape_hint = "dispersed"

        if groups_raw:
            if len(groups_raw) < 2:
                raise ValueError("crowd.groups must contain at least two groups.")
            if any(isinstance(item, dict) and item.get("groups") for item in groups_raw):
                raise ValueError("Nested crowd.groups are not supported.")
            parsed_groups: list[StaticCrowdConfig] = []
            for index, item in enumerate(groups_raw):
                if not isinstance(item, dict):
                    raise TypeError(f"crowd.groups[{index}] must be a mapping.")
                group_raw = {
                    "source": source,
                    "shape": str(item.get("shape", "circle")),
                    "count": int(item["count"]),
                    "center": item.get("center", [0.0, 0.0]),
                    "radius": float(item.get("radius", 2.0)),
                    "noise_std": float(item.get("noise_std", raw.get("noise_std", 0.04))),
                    "seed": int(item.get("seed", seed + 17 * (index + 1))),
                    "spacing": {
                        "distance_to_agents": float(
                            item.get("spacing", {}).get("distance_to_agents", distance_to_agents)
                        ),
                        "distance_to_polygon": float(
                            item.get("spacing", {}).get("distance_to_polygon", distance_to_polygon)
                        ),
                    },
                }
                if "axes" in item:
                    group_raw["axes"] = item["axes"]
                if "rotation_deg" in item:
                    group_raw["rotation_deg"] = item["rotation_deg"]
                if "spawn" in item or "region" in item:
                    if "spawn" in item:
                        group_raw["spawn"] = item["spawn"]
                    if "region" in item:
                        group_raw["region"] = item["region"]
                elif source == "jupedsim":
                    centre = as_vec2(item.get("center", [0.0, 0.0]), f"crowd.groups[{index}].center")
                    radius = float(item.get("radius", 2.0))
                    group_raw["spawn"] = {
                        "vertices": [
                            [float(x), float(y)]
                            for x, y in circle_spawn_vertices(centre, radius)
                        ]
                    }
                parsed_groups.append(cls.from_dict(group_raw, seed=int(group_raw["seed"])))

            total_count = int(sum(group.count for group in parsed_groups))
            centres = np.vstack([group.center for group in parsed_groups])
            resolved_shape = "dispersed" if shape_hint == "dispersed" else "multi"
            return cls(
                source=source,
                shape=resolved_shape,
                count=total_count,
                center=np.mean(centres, axis=0),
                radius=float(np.mean([group.radius for group in parsed_groups])),
                seed=int(raw.get("seed", seed)),
                distance_to_agents=distance_to_agents,
                distance_to_polygon=distance_to_polygon,
                groups=tuple(parsed_groups),
            )

        region_vertices = _parse_region_vertices(raw)

        if source == "jupedsim" and region_vertices is None:
            raise ValueError(
                "JuPedSim crowd source requires "
                "crowd.spawn.vertices or crowd.region.vertices."
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
            groups=(),
        )


def crowd_component_ids(config: StaticCrowdConfig) -> Array:
    """Return per-person group labels for multi-crowd scenarios."""
    if not config.is_multi:
        return np.zeros(int(config.count), dtype=int)
    parts = [np.full(int(group.count), index, dtype=int) for index, group in enumerate(config.groups)]
    return np.concatenate(parts)



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

    if config.is_multi or shape in {"multi", "dispersed"}:
        if not config.is_multi:
            raise ValueError("shape multi/dispersed requires crowd.groups with at least two entries.")
        parts = [generate_static_crowd(group) for group in config.groups]
        return np.vstack(parts)

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