"""Shared evaluation helpers (geometry sampling, confidence, metrics, stats)."""

from .confidence import neutralize_confidence
from .curve_metrics import curve_errors_with_p95, symmetric_curve_errors
from .polygons import points_inside_polygon, sample_polygon
from .stats import bootstrap_metric_summary, percentile_interval

__all__ = [
    "bootstrap_metric_summary",
    "curve_errors_with_p95",
    "neutralize_confidence",
    "percentile_interval",
    "points_inside_polygon",
    "sample_polygon",
    "symmetric_curve_errors",
]
