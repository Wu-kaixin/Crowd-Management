"""Configuration constants for formal G6 evaluation."""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np

PRIMARY_METHODS = (
    "endpoint_abcg",
    "uniform_angular",
    "uniform_arc",
    "fixed_m_periodic",
    "abcg_v2",
)
PRIMARY_SCENARIOS = ("circle", "ellipse", "u_shape", "c_shape")
NONCONVEX_SCENARIOS = ("u_shape", "c_shape")
ABLATION_VARIANTS = ("radial_no_bootstrap", "alpha_no_bootstrap", "alpha_bootstrap_no_gain", "abcg_v2_full")


@dataclass(frozen=True)
class G6EvaluationConfig:
    """Resolved formal-G6 configuration; distances are metres and time seconds."""

    seeds: tuple[int, ...] = tuple(range(30))
    scenarios: tuple[str, ...] = PRIMARY_SCENARIOS
    methods: tuple[str, ...] = PRIMARY_METHODS
    observation_count: int = 120
    bootstrap_samples: int = 30
    confidence_interval_resamples: int = 2000
    robustness_noise_levels: tuple[float, ...] = (0.0, 0.04, 0.08)
    robustness_dropout_levels: tuple[float, ...] = (0.0, 0.15, 0.30)
    robustness_scales: tuple[float, ...] = (0.75, 1.0, 1.25)
    available_guides: int = 16
    fixed_guide_count: int = 8
    required_arc_gap: float = 2.2
    safety_distance: float = 0.8
    coverage_radius: float = 1.25
    room_size: tuple[float, float] = (10.0, 10.0)
    dt: float = 0.1
    max_steps: int = 160
    workers: int = 4
    alpha_scale: float = 2.5
    sample_spacing: float = 0.08

    def __post_init__(self) -> None:
        if not self.seeds or len(set(self.seeds)) != len(self.seeds):
            raise ValueError("seeds must be a non-empty unique tuple.")
        if any(isinstance(seed, bool) or int(seed) != seed for seed in self.seeds):
            raise ValueError("seeds must contain integers.")
        if not self.scenarios or not set(self.scenarios).issubset(PRIMARY_SCENARIOS):
            raise ValueError(f"scenarios must select from {PRIMARY_SCENARIOS}.")
        if not self.methods or not set(self.methods).issubset(PRIMARY_METHODS):
            raise ValueError(f"methods must select from {PRIMARY_METHODS}.")
        for name in (
            "observation_count",
            "bootstrap_samples",
            "confidence_interval_resamples",
            "available_guides",
            "fixed_guide_count",
            "max_steps",
            "workers",
        ):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, (int, np.integer)) or value < 1:
                raise ValueError(f"{name} must be a positive integer.")
        if self.fixed_guide_count > self.available_guides:
            raise ValueError("fixed_guide_count must not exceed available_guides.")
        for name in (
            "required_arc_gap",
            "safety_distance",
            "coverage_radius",
            "dt",
            "alpha_scale",
            "sample_spacing",
        ):
            value = float(getattr(self, name))
            if not np.isfinite(value) or value <= 0.0:
                raise ValueError(f"{name} must be finite and positive.")
        room = np.asarray(self.room_size, dtype=float)
        if room.shape != (2,) or not np.all(np.isfinite(room)) or np.any(room <= 0.0):
            raise ValueError("room_size must contain two finite positive dimensions.")
        for name in ("robustness_noise_levels", "robustness_dropout_levels", "robustness_scales"):
            values = np.asarray(getattr(self, name), dtype=float)
            if values.ndim != 1 or len(values) < 3 or not np.all(np.isfinite(values)):
                raise ValueError(f"{name} must contain at least three finite levels.")
        if np.any(np.asarray(self.robustness_noise_levels) < 0.0):
            raise ValueError("robustness noise levels must be non-negative.")
        dropout = np.asarray(self.robustness_dropout_levels)
        if np.any((dropout < 0.0) | (dropout >= 1.0)):
            raise ValueError("robustness dropout levels must be in [0, 1).")
        if np.any(np.asarray(self.robustness_scales) <= 0.0):
            raise ValueError("robustness scales must be positive.")


METRIC_DIRECTIONS = {
    "curve_chamfer_m": "lower",
    "curve_hausdorff95_m": "lower",
    "plan_h_final": "lower",
    "plan_max_arc_gap_m": "lower",
    "tracking_rmse_final": "lower",
    "convergence_time_s": "lower",
    "path_length_m": "lower",
    "assignment_switch_count": "lower",
    "trajectory_crossing_count": "lower",
    "coverage_ratio": "higher",
    "max_truth_boundary_distance_m": "lower",
    "min_guide_guide_clearance_m": "higher",
    "min_guide_crowd_clearance_m": "higher",
    "active_count": "lower",
    "total_runtime_ms": "lower",
    "trace_memory_bytes": "lower",
}
