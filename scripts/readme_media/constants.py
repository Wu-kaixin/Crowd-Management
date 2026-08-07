"""Shared constants for README media generation."""

from pathlib import Path

import numpy as np

MEDIA_DIR = Path("reports/media")
G6_REPORT_DIR = Path("reports/step1_g6_compliance")
ROOM = np.array([20.0, 14.0], dtype=float)
G6_ROOM = np.array([10.0, 10.0], dtype=float)

SCENARIOS = [
    ("Circle", {"shape": "circle", "count": 180, "center": [10, 7], "radius": 2.2, "noise_std": 0.05}, 8, 72, 0),
    (
        "Ellipse",
        {
            "shape": "ellipse",
            "count": 220,
            "center": [10, 7],
            "axes": [3.2, 1.35],
            "rotation_deg": 24,
            "noise_std": 0.05,
        },
        9,
        96,
        1,
    ),
    (
        "Nonconvex",
        {
            "shape": "nonconvex",
            "count": 240,
            "center": [10, 7],
            "radius": 2.35,
            "radial_jitter": 0.09,
            "noise_std": 0.05,
        },
        10,
        108,
        2,
    ),
    (
        "Two clusters",
        {
            "shape": "two_cluster",
            "count": 240,
            "center": [10, 7],
            "radius": 2.0,
            "lobe_offset": 1.25,
            "noise_std": 0.05,
        },
        10,
        108,
        3,
    ),
]

G6_LABELS = {
    "circle": "Circle",
    "ellipse": "Ellipse",
    "u_shape": "Held-out U",
    "c_shape": "Held-out C",
}
