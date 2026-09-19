"""Step 2 gather-then-surround tests."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from crowd_management.controllers.step2_gather import (
    AttractiveRendezvousMotion,
    CentralGatherThenSurroundController,
    GatherThenSurroundConfig,
    NotImplementedGatherThenSurroundController,
)
from crowd_management.crowd import build_crowd_source
from crowd_management.experiments.static_containment import StaticContainmentConfig
from crowd_management.experiments.step2_gather import run_gather_then_surround
from crowd_management.scenarios import RectangularScenario

REPO = Path(__file__).resolve().parents[2]


def test_step2_stub_still_explicit() -> None:
    controller = NotImplementedGatherThenSurroundController()
    with pytest.raises(NotImplementedError, match="CentralGatherThenSurroundController"):
        controller.reset(np.zeros((4, 2)), np.zeros((3, 2)))


def test_attractive_motion_moves_toward_center() -> None:
    motion = AttractiveRendezvousMotion(speed=1.0, soft_strength=0.0, guide_influence_strength=0.0)
    scene = RectangularScenario.from_size(np.array([20.0, 20.0]))
    crowd = np.array([[2.0, 10.0], [18.0, 10.0], [10.0, 2.0]], dtype=float)
    nxt = motion.step(crowd, np.zeros((0, 2)), 0.2, rendezvous=np.array([10.0, 10.0]), scene=scene)
    assert float(np.linalg.norm(nxt[0] - np.array([10.0, 10.0]))) < float(
        np.linalg.norm(crowd[0] - np.array([10.0, 10.0]))
    )


def test_controller_reaches_surround_or_done() -> None:
    cfg = StaticContainmentConfig.from_yaml(REPO / "configs/step2_gather/square_dispersed_gather.yaml")
    crowd = build_crowd_source(cfg.crowd).observe()
    guides = np.array([[2.0, 2.0], [18.0, 2.0], [2.0, 18.0], [18.0, 18.0], [10.0, 1.5], [1.5, 10.0]], dtype=float)
    gather_cfg = GatherThenSurroundConfig(
        gather_radius=3.2,
        gather_fraction=0.85,
        max_gather_steps=350,
        max_surround_steps=200,
        pedestrian_speed=1.2,
        guide_standoff=3.5,
        safety_distance=cfg.safety_distance,
        wall_margin=cfg.safety.room_margin,
    )
    controller = CentralGatherThenSurroundController(
        scene=cfg.scene,
        containment_cfg=cfg,
        gather_cfg=gather_cfg,
    )
    plan = controller.reset(crowd, guides)
    assert plan.phase == "gather"
    dt = 0.1
    saw_surround = False
    for _ in range(gather_cfg.max_gather_steps + gather_cfg.max_surround_steps):
        velocities, plan = controller.step(crowd, guides, dt)
        guides = guides + velocities * dt
        crowd = controller.advance_crowd(crowd, guides, dt)
        if plan.phase == "surround":
            saw_surround = True
        if plan.phase == "done":
            break
    assert saw_surround or plan.status in {"GATHER_TIMEOUT", "DONE", "SURROUND_TIMEOUT"}
    if saw_surround:
        assert controller.boundary is not None


def test_end_to_end_gather_then_surround(tmp_path: Path) -> None:
    summary = run_gather_then_surround(
        REPO / "configs/step2_gather/square_dispersed_gather.yaml",
        tmp_path,
        live=False,
        headless=True,
        save_plots=False,
    )
    assert summary["steps"] > 0
    assert summary["phase_final"] in {"gather", "surround", "done"}
    assert (tmp_path / "episode.npz").is_file()
    episode = np.load(tmp_path / "episode.npz")
    # Crowd should move during gather (not static Step 1).
    crowd = episode["crowd_positions"]
    assert crowd.shape[0] > 1
    displacement = float(np.max(np.linalg.norm(crowd[-1] - crowd[0], axis=1)))
    assert displacement > 0.5
