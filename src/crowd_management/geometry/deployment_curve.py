r"""Robust deployment-curve construction from an estimated crowd region.

ROLE: CORE MATH — \(\widehat{\Omega}_d = \widehat{\Omega}_c \oplus B_{d_s}\), \(\Gamma_d = \partial\widehat{\Omega}_d\).

This module is intentionally separate from crowd-boundary estimation.
It never reads spawn polygons, evaluator truth, or room polygons as a
substitute crowd contour. The known environment is used only as the
guide workspace \(\Omega_g = \Omega_{\mathrm{env}} \ominus B_{m_w}\).
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
from shapely.geometry import LineString, MultiPolygon, Polygon
from shapely.validation import explain_validity

from ..scenarios.rectangular import RectangularScenario
from ..types import Array
from .arclength import has_self_intersections, resample_closed_curve_by_arclength


@dataclass(frozen=True)
class DeploymentCurve:
    """Valid sampled deployment curve Gamma_d."""

    curve_points: Array
    arc_s: Array
    length: float
    tangents: Array
    outward_normals: Array
    polygon_vertices: Array
    status: str = "VALID"
    diagnostics: dict[str, object] = field(default_factory=dict)


@dataclass(frozen=True)
class DeploymentCurveFailure:
    """Explicit deployment failure. No silent geometry repair."""

    status: str
    reason: str
    diagnostics: dict[str, object] = field(default_factory=dict)


DeploymentCurveResult = DeploymentCurve | DeploymentCurveFailure


def _failure(status: str, reason: str, **diagnostics: object) -> DeploymentCurveFailure:
    return DeploymentCurveFailure(status=status, reason=reason, diagnostics={"reason": reason, **diagnostics})


def _closed_vertices(polygon: Polygon) -> Array:
    coords = np.asarray(polygon.exterior.coords, dtype=float)
    if len(coords) >= 2 and np.allclose(coords[0], coords[-1]):
        coords = coords[:-1]
    return coords


def build_deployment_curve(
    crowd_curve: Array,
    safety_distance: float,
    *,
    crowd_points: Array | None = None,
    workspace: RectangularScenario | None = None,
    wall_margin: float = 0.0,
    sample_spacing: float = 0.08,
    min_crowd_clearance: float | None = None,
) -> DeploymentCurveResult:
    """Buffer the estimated crowd polygon and sample the deployment curve.

    Failures are explicit. The environment polygon is never returned as
    the crowd or deployment curve.
    """
    if not np.isfinite(safety_distance) or safety_distance < 0.0:
        raise ValueError("safety_distance must be finite and non-negative.")
    if not np.isfinite(sample_spacing) or sample_spacing <= 0.0:
        raise ValueError("sample_spacing must be finite and positive.")
    if not np.isfinite(wall_margin) or wall_margin < 0.0:
        raise ValueError("wall_margin must be finite and non-negative.")

    points = np.asarray(crowd_curve, dtype=float)
    if points.ndim != 2 or points.shape[1:] != (2,) or len(points) < 3 or not np.all(np.isfinite(points)):
        return _failure("OFFSET_INVALID", "crowd_curve_invalid")

    crowd_polygon = Polygon(points)
    if crowd_polygon.is_empty or not crowd_polygon.is_valid or crowd_polygon.area <= 1.0e-12:
        return _failure(
            "OFFSET_INVALID",
            "crowd_polygon_invalid",
            shapely_validity=explain_validity(crowd_polygon),
        )

    buffered = crowd_polygon.buffer(float(safety_distance), join_style=1, cap_style=1)
    if buffered.is_empty:
        return _failure("OFFSET_INVALID", "buffer_empty")
    if isinstance(buffered, MultiPolygon) or getattr(buffered, "geom_type", "") != "Polygon":
        component_count = len(getattr(buffered, "geoms", ()))
        return _failure(
            "OFFSET_INVALID",
            "buffer_topology_invalid",
            component_count=int(component_count),
            geom_type=str(getattr(buffered, "geom_type", type(buffered).__name__)),
        )
    if not buffered.is_valid or buffered.area <= 1.0e-12:
        return _failure(
            "OFFSET_INVALID",
            "buffer_invalid",
            shapely_validity=explain_validity(buffered),
        )
    if len(buffered.interiors) > 0:
        return _failure("OFFSET_INVALID", "buffer_has_holes", hole_count=len(buffered.interiors))

    vertices = _closed_vertices(buffered)
    try:
        self_intersection = has_self_intersections(vertices)
    except ValueError:
        self_intersection = True
    exterior = LineString(np.vstack((vertices, vertices[0])))
    if self_intersection or not exterior.is_simple:
        return _failure("OFFSET_INVALID", "offset_self_intersection")

    try:
        curve, arc_s, length, tangents, normals = resample_closed_curve_by_arclength(
            vertices,
            spacing=sample_spacing,
        )
    except ValueError as error:
        return _failure("OFFSET_INVALID", str(error))

    min_observed_clearance = None
    required_clearance = None if min_crowd_clearance is None else float(min_crowd_clearance)
    if crowd_points is not None and len(np.asarray(crowd_points, dtype=float)):
        observed = np.asarray(crowd_points, dtype=float)
        distances = np.linalg.norm(curve[:, None, :] - observed[None, :, :], axis=2)
        min_observed_clearance = float(np.min(distances))
        if required_clearance is not None and min_observed_clearance + 1.0e-9 < required_clearance:
            # Arclength resampling of a convex offset chords inward.  Push the
            # sampled curve back out when the deficit is a sampling sag, not a
            # leaked crowd estimate.
            for _ in range(3):
                if min_observed_clearance + 1.0e-9 >= required_clearance:
                    break
                deficit = required_clearance - min_observed_clearance
                if deficit > 2.0 * float(sample_spacing) + 1.0e-9:
                    return _failure(
                        "OFFSET_INVALID",
                        "deployment_too_close_to_crowd",
                        min_observed_clearance=min_observed_clearance,
                        required_clearance=required_clearance,
                    )
                pushed = curve + (deficit + 1.0e-4) * normals
                try:
                    curve, arc_s, length, tangents, normals = resample_closed_curve_by_arclength(
                        pushed,
                        spacing=sample_spacing,
                    )
                except ValueError as error:
                    return _failure("OFFSET_INVALID", str(error))
                distances = np.linalg.norm(curve[:, None, :] - observed[None, :, :], axis=2)
                min_observed_clearance = float(np.min(distances))
            if min_observed_clearance + 1.0e-9 < required_clearance:
                return _failure(
                    "OFFSET_INVALID",
                    "deployment_too_close_to_crowd",
                    min_observed_clearance=min_observed_clearance,
                    required_clearance=required_clearance,
                )

    if workspace is not None:
        guide_workspace = workspace.feasible_workspace_polygon(wall_margin)
        if guide_workspace.is_empty:
            return _failure(
                "DEPLOYMENT_INFEASIBLE",
                "workspace_empty",
                wall_margin=float(wall_margin),
            )
        if not guide_workspace.buffer(1.0e-9).covers(buffered):
            inside = workspace.contains(curve, margin=wall_margin)
            if not bool(np.all(inside)):
                return _failure(
                    "OFFSET_OUTSIDE_WORKSPACE",
                    "offset_outside_room",
                    outside_count=int(np.count_nonzero(~inside)),
                    wall_margin=float(wall_margin),
                    environment_is_not_crowd_boundary=True,
                )
        inside = workspace.contains(curve, margin=wall_margin)
        if not bool(np.all(inside)):
            return _failure(
                "OFFSET_OUTSIDE_WORKSPACE",
                "offset_outside_room",
                outside_count=int(np.count_nonzero(~inside)),
                wall_margin=float(wall_margin),
                environment_is_not_crowd_boundary=True,
            )

    return DeploymentCurve(
        curve_points=curve,
        arc_s=arc_s,
        length=float(length),
        tangents=tangents,
        outward_normals=normals,
        polygon_vertices=vertices,
        diagnostics={
            "status": "VALID",
            "construction": "shapely_minkowski_buffer",
            "safety_distance": float(safety_distance),
            "sample_count": int(len(curve)),
            "min_observed_clearance": min_observed_clearance,
            "wall_margin": float(wall_margin),
            "used_environment_as_crowd_boundary": False,
        },
    )
