"""Confidence-ablation helpers shared by G6 and PR6 evaluators."""
from __future__ import annotations

from dataclasses import replace

import numpy as np

from ...estimation import BoundaryEstimateV2


def neutralize_confidence(boundary: BoundaryEstimateV2, *, status_label: str) -> BoundaryEstimateV2:
    """Replace estimated confidence with ones and record an explicit ablation label."""
    return replace(
        boundary,
        confidence=np.ones_like(boundary.confidence),
        diagnostics={
            **boundary.diagnostics,
            "confidence_status": status_label,
        },
    )
