"""JuPedSim-backed static crowd source for Step 1.

JuPedSim is used only to generate physically spaced pedestrian
center positions.

No pedestrian dynamics are advanced in Step 1.

The returned observation is therefore a static N x 2 point cloud.

The evaluator-only truth is constructed from the feasible support
region of pedestrian centres and is never provided to ABCG.
"""

from __future__ import annotations

from importlib.metadata import PackageNotFoundError
from importlib.metadata import version as package_version

import jupedsim as jps
import numpy as np
from shapely.geometry import LineString
from shapely.geometry import Polygon

from ..types import Array
from .static_crowd import StaticCrowdConfig
from .truth import StaticCrowdTruth


def _jupedsim_version() -> str:
    try:
        return package_version(
            "jupedsim"
        )
    except PackageNotFoundError:
        return "unknown"


def build_spawn_polygon(
    config: StaticCrowdConfig,
) -> Polygon:
    """Construct the JuPedSim spawn polygon."""

    if config.region_vertices is None:
        raise ValueError(
            "JuPedSim source requires "
            "region_vertices."
        )

    polygon = Polygon(
        config.region_vertices
    )

    if polygon.is_empty:
        raise ValueError(
            "JuPedSim spawn polygon is empty."
        )

    if not polygon.is_valid:
        raise ValueError(
            "JuPedSim spawn polygon is invalid."
        )

    if polygon.area <= 0.0:
        raise ValueError(
            "JuPedSim spawn polygon "
            "must have positive area."
        )

    if len(polygon.interiors) > 0:
        raise ValueError(
            "Step 1 currently requires "
            "a hole-free crowd polygon."
        )

    return polygon


def build_center_support_polygon(
    config: StaticCrowdConfig,
) -> Polygon:
    """Region in which pedestrian centres may exist.

    JuPedSim's distance_to_polygon keeps generated pedestrian
    centres away from the original spawn boundary.

    Therefore the evaluator truth is based on the inward-offset
    support polygon rather than the original spawn polygon.
    """

    spawn_polygon = build_spawn_polygon(
        config
    )

    margin = float(
        config.distance_to_polygon
    )

    if margin == 0.0:
        support = spawn_polygon
    else:
        support = spawn_polygon.buffer(
            -margin
        )

    if support.is_empty:
        raise ValueError(
            "distance_to_polygon is too large: "
            "the centre-support region is empty."
        )

    if support.geom_type != "Polygon":
        raise ValueError(
            "The centre-support region became "
            "multi-component after inward offset. "
            "This violates Step 1's single-crowd "
            "assumption."
        )

    support_polygon = Polygon(
        support.exterior.coords
    )

    if not support_polygon.is_valid:
        raise ValueError(
            "Centre-support polygon is invalid."
        )

    return support_polygon


def generate_jupedsim_static_crowd(
    config: StaticCrowdConfig,
) -> Array:
    """Generate static pedestrian centre positions using JuPedSim."""

    if config.source != "jupedsim":
        raise ValueError(
            "generate_jupedsim_static_crowd() "
            "requires source='jupedsim'."
        )

    polygon = build_spawn_polygon(
        config
    )

    positions = jps.distribute_by_number(
        polygon=polygon,
        number_of_agents=int(
            config.count
        ),
        distance_to_agents=float(
            config.distance_to_agents
        ),
        distance_to_polygon=float(
            config.distance_to_polygon
        ),
        seed=int(
            config.seed
        ),
    )

    points = np.asarray(
        positions,
        dtype=float,
    )

    expected_shape = (
        config.count,
        2,
    )

    if points.shape != expected_shape:
        raise RuntimeError(
            "JuPedSim did not generate the "
            "requested number of pedestrians: "
            f"expected {expected_shape}, "
            f"received {points.shape}. "
            "Reduce count or spacing constraints."
        )

    if not np.isfinite(points).all():
        raise RuntimeError(
            "JuPedSim returned non-finite "
            "pedestrian coordinates."
        )

    return points


def _sample_polygon_exterior(
    polygon: Polygon,
    num_samples: int,
) -> Array:
    """Arc-length sample a polygon exterior."""

    samples = int(
        num_samples
    )

    if samples < 8:
        raise ValueError(
            "num_samples must be at least 8."
        )

    line = LineString(
        polygon.exterior.coords
    )

    length = float(
        line.length
    )

    if length <= 0.0:
        raise ValueError(
            "Polygon exterior has zero length."
        )

    distances = np.linspace(
        0.0,
        length,
        samples,
        endpoint=False,
    )

    points = np.asarray(
        [
            line.interpolate(
                float(distance)
            ).coords[0]
            for distance in distances
        ],
        dtype=float,
    )

    return points


def generate_jupedsim_static_truth(
    config: StaticCrowdConfig,
    safety_distance: float = 0.0,
    num_samples: int = 720,
) -> StaticCrowdTruth:
    """Build evaluator-only truth for a JuPedSim static crowd.

    Truth definition:

        Omega_c^* = feasible support region of pedestrian centres.

    ABCG never receives this polygon. It receives only sampled
    pedestrian positions.
    """

    if config.source != "jupedsim":
        raise ValueError(
            "JuPedSim truth requires "
            "source='jupedsim'."
        )

    if safety_distance < 0.0:
        raise ValueError(
            "safety_distance must be non-negative."
        )

    support_polygon = (
        build_center_support_polygon(
            config
        )
    )

    boundary_points = (
        _sample_polygon_exterior(
            support_polygon,
            num_samples,
        )
    )

    if safety_distance == 0.0:
        safety_polygon = (
            support_polygon
        )
    else:
        safety_geometry = (
            support_polygon.buffer(
                float(
                    safety_distance
                )
            )
        )

        if (
            safety_geometry.is_empty
            or safety_geometry.geom_type
            != "Polygon"
        ):
            raise ValueError(
                "Unable to construct a "
                "single-component safety offset."
            )

        safety_polygon = Polygon(
            safety_geometry.exterior.coords
        )

    safety_points = (
        _sample_polygon_exterior(
            safety_polygon,
            num_samples,
        )
    )

    samples = int(
        num_samples
    )

    return StaticCrowdTruth(
        shape="jupedsim_polygon",
        boundary_points=boundary_points,
        safety_points=safety_points,
        component_ids=np.zeros(
            samples,
            dtype=int,
        ),
        component_count=1,
        valid=True,
        status="valid",
        diagnostics={
            "reference": (
                "jupedsim_center_support_polygon"
            ),
            "source": "jupedsim",
            "jupedsim_version": (
                _jupedsim_version()
            ),
            "num_samples": samples,
            "spawn_polygon_area": float(
                build_spawn_polygon(
                    config
                ).area
            ),
            "center_support_area": float(
                support_polygon.area
            ),
            "distance_to_agents": float(
                config.distance_to_agents
            ),
            "distance_to_polygon": float(
                config.distance_to_polygon
            ),
            "safety_distance": float(
                safety_distance
            ),
            "truth_exposed_to_controller": False,
        },
    )