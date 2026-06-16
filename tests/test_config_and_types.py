from pathlib import Path

import numpy as np
import pytest

from crowd_management.types import SimulationConfig, as_vec2, limit_norm, unit


def test_config_loads():
    cfg = SimulationConfig.from_yaml(Path(__file__).resolve().parents[1] / "configs" / "simple_room.yaml")
    assert cfg.pedestrians.count == 160
    assert cfg.guiders.count == 4
    assert cfg.room.width > 0


def test_vector_helpers():
    assert np.allclose(unit(np.array([3.0, 4.0])), np.array([0.6, 0.8]))
    assert np.linalg.norm(limit_norm(np.array([3.0, 4.0]), 2.0)) <= 2.0 + 1e-9
    with pytest.raises(ValueError):
        as_vec2([1.0, 2.0, 3.0])
