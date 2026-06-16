import numpy as np

from crowd_management.dbact_transfer import DBACTTransferController
from crowd_management.guider_model import initialize_guiders
from crowd_management.types import GuiderConfig, RoomConfig


def test_dbact_transfer_generates_valid_targets():
    room = RoomConfig(width=10.0, height=6.0, exit_center_y=3.0, exit_width=1.2)
    cfg = GuiderConfig(count=3, max_speed=1.0, influence_radius=2.0, guidance_strength=1.0, target_distance_gain=1.0, side_spacing=1.0)
    controller = DBACTTransferController(room, cfg)
    positions = np.array([[2.0, 2.0], [2.5, 3.0], [2.0, 4.0]])
    evacuated = np.array([False, False, False])
    estimate = controller.estimate_crowd(positions, evacuated)
    targets, directions = controller.compute_targets(estimate, cfg.count)
    assert targets.shape == (3, 2)
    assert directions.shape == (3, 2)
    assert np.all(targets[:, 0] >= 0.0)
    assert np.all(targets[:, 0] <= room.width)
    assert np.all(np.linalg.norm(directions, axis=1) > 0.99)


def test_update_guiders_assigns_targets():
    room = RoomConfig(width=10.0, height=6.0, exit_center_y=3.0, exit_width=1.2)
    cfg = GuiderConfig(count=2, max_speed=1.0, influence_radius=2.0, guidance_strength=1.0, target_distance_gain=1.0, side_spacing=1.0)
    guiders = initialize_guiders(cfg, room)
    controller = DBACTTransferController(room, cfg)
    positions = np.array([[2.0, 2.0], [2.5, 3.0]])
    evacuated = np.array([False, False])
    controller.update_guiders(guiders, positions, evacuated)
    assert not np.allclose(guiders[0].target_position, guiders[1].target_position)
