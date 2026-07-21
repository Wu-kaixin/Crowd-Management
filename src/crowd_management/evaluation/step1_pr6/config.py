"""PR6 paired held-out evaluation configuration."""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True)
class PR6EvaluationConfig:
    """Paired-seed PR6 evaluation configuration."""

    seeds: tuple[int, ...] = tuple(range(30))
    shapes: tuple[str, ...] = ("u_shape", "c_shape")
    observation_count: int = 280
    bootstrap_samples: int = 12
    confidence_interval_resamples: int = 2000
    alpha_scale: float = 2.5
    alpha_smoothing_passes: int = 5
    sample_spacing: float = 0.06
    required_arc_gap: float = 1.5
    max_guides: int = 12
    workers: int = 4

    def __post_init__(self) -> None:
        if len(self.seeds) == 0 or len(set(self.seeds)) != len(self.seeds):
            raise ValueError("seeds must be a non-empty unique tuple.")
        if any(isinstance(seed, bool) or int(seed) != seed for seed in self.seeds):
            raise ValueError("seeds must contain integers.")
        allowed = {"u_shape", "c_shape"}
        if len(self.shapes) == 0 or not set(self.shapes).issubset(allowed):
            raise ValueError("shapes must select u_shape and/or c_shape.")
        for name in ("observation_count", "confidence_interval_resamples", "max_guides", "workers"):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, (int, np.integer)) or value < 1:
                raise ValueError(f"{name} must be a positive integer.")
        if self.bootstrap_samples < 1:
            raise ValueError("bootstrap_samples must be positive for PR6 evaluation.")
        for name in ("alpha_scale", "sample_spacing", "required_arc_gap"):
            value = float(getattr(self, name))
            if not np.isfinite(value) or value <= 0.0:
                raise ValueError(f"{name} must be finite and positive.")
        if self.alpha_smoothing_passes < 0:
            raise ValueError("alpha_smoothing_passes must be non-negative.")
