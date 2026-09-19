"""Step 2 gather-then-surround experiment runner."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import numpy as np

from ...controllers.guide_initialization import sample_random_guide_positions
from ...controllers.step2_gather import (
    CentralGatherThenSurroundController,
    GatherThenSurroundConfig,
)
from ...crowd import build_crowd_source, generate_static_agent_attributes
from ...experiments.static_containment.config import StaticContainmentConfig
from ...experiments.static_containment.known_boundary import build_step1_observation
from ...types import Array
from ...visualization.live_step1 import (
    NullStep1Renderer,
    Step1Frame,
    build_renderer,
    display_is_unattended,
)
from ...visualization.static_step1 import save_final_scene


def _gather_config_from_yaml(raw: dict[str, Any], cfg: StaticContainmentConfig) -> GatherThenSurroundConfig:
    section = raw.get("gather") or {}
    return GatherThenSurroundConfig(
        gather_radius=float(section.get("gather_radius", 2.8)),
        gather_fraction=float(section.get("gather_fraction", 0.88)),
        max_gather_steps=int(section.get("max_gather_steps", 450)),
        max_surround_steps=int(section.get("max_surround_steps", 500)),
        guide_standoff=float(section.get("guide_standoff", 4.0)),
        guide_gain=float(section.get("guide_gain", 1.6)),
        guide_max_speed=float(section.get("guide_max_speed", getattr(cfg.motion, "v_max", 1.2))),
        surround_rmse_tol=float(section.get("surround_rmse_tol", 0.08)),
        surround_hold_steps=int(section.get("surround_hold_steps", 12)),
        safety_distance=float(cfg.safety_distance),
        wall_margin=float(cfg.safety.room_margin),
        pedestrian_speed=float(section.get("pedestrian_speed", 0.85)),
    )


def run_gather_then_surround(
    config_path: str | Path,
    output_dir: str | Path,
    *,
    live: bool | None = None,
    headless: bool = False,
    hold_window: bool | None = None,
    save_plots: bool = True,
) -> dict[str, Any]:
    """Run Step 2: disperse → gather pedestrians → surround the gathered blob."""
    import yaml

    config_path = Path(config_path)
    with open(config_path, encoding="utf-8") as handle:
        raw = yaml.safe_load(handle)
    cfg = StaticContainmentConfig.from_yaml(config_path)
    if int(raw.get("step", cfg.step)) < 2 and not bool(raw.get("gather")):
        raise ValueError(
            "Gather-then-surround expects step: 2 (or a gather: section). "
            "Use configs/step2_gather/*.yaml; Step 1 dispersed static surround remains "
            "scripts/run_static_containment.py."
        )
    gather_cfg = _gather_config_from_yaml(raw, cfg)
    max_steps = gather_cfg.max_gather_steps + gather_cfg.max_surround_steps

    if headless:
        live_enabled = False
    elif live is None:
        live_enabled = bool(cfg.visualization.live)
    else:
        live_enabled = bool(live)
    if live_enabled and display_is_unattended():
        live_enabled = False
    hold_enabled = bool(cfg.visualization.hold_window if hold_window is None else hold_window)

    crowd_source = build_crowd_source(cfg.crowd)
    crowd_points = crowd_source.observe()
    attributes = generate_static_agent_attributes(
        count=len(crowd_points),
        config=cfg.heterogeneity,
        seed=cfg.seed + 100003,
        positions=crowd_points,
    )
    crowd_observation = build_step1_observation(crowd_points, attributes)
    guides = sample_random_guide_positions(
        cfg.scene,
        cfg.guide_count,
        seed=cfg.seed + 17,
        wall_margin=cfg.safety.room_margin,
        min_guide_distance=cfg.safety.min_guide_distance,
        crowd_points=crowd_points,
        min_crowd_distance=cfg.safety.min_crowd_distance,
    )
    initial_guides = guides.copy()

    controller = CentralGatherThenSurroundController(
        scene=cfg.scene,
        containment_cfg=cfg,
        gather_cfg=gather_cfg,
    )
    plan = controller.reset(crowd_points, guides)
    dt = float(cfg.motion.dt)

    renderer: Any = NullStep1Renderer()
    if live_enabled:
        renderer = build_renderer(
            live=True,
            render_every=cfg.visualization.render_every,
            max_fps=cfg.visualization.max_fps,
            show_trails=cfg.visualization.show_trails,
            block=hold_enabled,
        )

    trail_frames: list[Array] = [guides.copy()]
    crowd_history: list[Array] = [crowd_points.copy()]
    phase_history: list[str] = [plan.phase]

    start_frame = Step1Frame(
        scenario_name=cfg.scene.name,
        seed=cfg.seed,
        time=0.0,
        step=0,
        environment_vertices=cfg.scene.boundary_vertices(),
        crowd_points=crowd_points,
        crowd_radii=crowd_observation.radii,
        crowd_demand=crowd_observation.demand,
        estimated_crowd_boundary=plan.gather_disk_polyline,
        deployment_curve=None,
        target_positions=plan.active_guide_targets,
        initial_guides=initial_guides,
        current_guides=guides,
        active_ids=tuple(range(len(guides))),
        reserve_ids=(),
        trails=None,
        controller_state="GATHER start · people→disk, guides→outer ring",
        tracking_rmse=None,
        active_guide_count=len(guides),
        max_arc_gap=None,
        min_guide_guide_distance=None,
        min_guide_crowd_distance=None,
        min_guide_wall_distance=None,
        safety_status="step2_kinematic",
        failed=False,
        failure_reason=None,
        title_suffix="Step 2 gather→surround",
        max_steps=max_steps,
        guide_body_radius=0.12,
        guide_halo_radius=0.3,
        min_guide_distance_req=float(cfg.safety.min_guide_distance),
        min_crowd_distance_req=float(cfg.safety.min_crowd_distance),
        min_wall_distance_req=float(cfg.safety.room_margin),
        guide_to_target=None,
        crowd_component_ids=None,
        crowd_group_count=1,
    )
    renderer.start(start_frame)

    status = plan.status
    for step_index in range(1, max_steps + 1):
        velocities, plan = controller.step(crowd_points, guides, dt)
        guides = guides + velocities * dt
        lower, upper = cfg.scene.feasible_workspace_bounds(cfg.safety.room_margin)
        guides = np.clip(guides, lower, upper)
        crowd_points = controller.advance_crowd(crowd_points, guides, dt)
        trail_frames.append(guides.copy())
        crowd_history.append(crowd_points.copy())
        phase_history.append(plan.phase)
        status = plan.status

        boundary = controller.boundary
        crowd_curve = boundary.curve_points if boundary is not None else None
        deploy_curve = boundary.offset_points if boundary is not None else None
        # During gather: show rendezvous disk as "boundary" and outer ring targets.
        if plan.phase == "gather":
            crowd_curve = plan.gather_disk_polyline
            deploy_curve = None
        targets = plan.active_guide_targets
        rmse = plan.diagnostics.get("tracking_rmse")
        gather_frac = plan.diagnostics.get("gather_fraction")
        ring_r = plan.diagnostics.get("gather_ring_radius")
        state = f"{plan.phase.upper()}:{plan.status}"
        if plan.phase == "gather" and gather_frac is not None:
            state = f"GATHER {float(gather_frac):.0%} in disk"
            if ring_r is not None:
                state += f" · ring r={float(ring_r):.1f}"
        frame = Step1Frame(
            scenario_name=cfg.scene.name,
            seed=cfg.seed,
            time=step_index * dt,
            step=step_index,
            environment_vertices=cfg.scene.boundary_vertices(),
            crowd_points=crowd_points,
            crowd_radii=crowd_observation.radii,
            crowd_demand=crowd_observation.demand,
            estimated_crowd_boundary=crowd_curve,
            deployment_curve=deploy_curve,
            target_positions=targets,
            initial_guides=initial_guides,
            current_guides=guides,
            active_ids=tuple(range(len(guides))),
            reserve_ids=(),
            trails=np.stack(trail_frames, axis=0),
            controller_state=state,
            tracking_rmse=None if rmse is None else float(rmse),
            active_guide_count=len(guides),
            max_arc_gap=None,
            min_guide_guide_distance=None,
            min_guide_crowd_distance=None,
            min_guide_wall_distance=None,
            safety_status="step2_kinematic",
            failed=plan.status.endswith("TIMEOUT"),
            failure_reason=plan.status if plan.status.endswith("TIMEOUT") else None,
            title_suffix="Step 2 gather→surround",
            max_steps=max_steps,
            guide_body_radius=0.12,
            guide_halo_radius=0.3,
            min_guide_distance_req=float(cfg.safety.min_guide_distance),
            min_crowd_distance_req=float(cfg.safety.min_crowd_distance),
            min_wall_distance_req=float(cfg.safety.room_margin),
            guide_to_target=None,
            crowd_component_ids=None,
            crowd_group_count=1,
        )
        renderer.update(frame)
        if plan.phase == "done":
            break

    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(
        output / "episode.npz",
        guide_positions=np.stack(trail_frames, axis=0),
        crowd_positions=np.stack(crowd_history, axis=0),
        phase=np.asarray(phase_history),
    )
    # Require a real surround: people gathered + deployment ring tracked + guides outside.
    gather_ok = float(plan.diagnostics.get("gather_fraction") or 0.0) >= 0.75
    surround_ok = plan.diagnostics.get("surround_boundary_status") == "VALID"
    rmse = plan.diagnostics.get("tracking_rmse")
    track_ok = rmse is not None and float(rmse) <= 0.35
    crowd_span = float(np.max(np.linalg.norm(crowd_points - crowd_points.mean(axis=0), axis=1)))
    guide_radii = np.linalg.norm(guides - crowd_points.mean(axis=0), axis=1)
    guides_outside = bool(np.min(guide_radii) >= crowd_span * 0.85)
    summary = {
        "status": status,
        "phase_final": phase_history[-1],
        "steps": len(trail_frames) - 1,
        "gather_fraction": plan.diagnostics.get("gather_fraction"),
        "gather_max_radius": plan.diagnostics.get("gather_max_radius"),
        "gather_ring_radius": plan.diagnostics.get("gather_ring_radius"),
        "surround_boundary_status": plan.diagnostics.get("surround_boundary_status"),
        "surround_plan_status": plan.diagnostics.get("surround_plan_status"),
        "tracking_rmse": rmse,
        "final_crowd_span": crowd_span,
        "final_guide_min_radius": float(np.min(guide_radii)),
        "scientific_success": bool(
            status == "DONE"
            and gather_ok
            and surround_ok
            and track_ok
            and crowd_span <= 4.5
            and guides_outside
        ),
    }
    with open(output / "summary.json", "w", encoding="utf-8") as handle:
        json.dump(summary, handle, indent=2)
    if save_plots:
        final = Step1Frame(
            scenario_name=cfg.scene.name,
            seed=cfg.seed,
            time=(len(trail_frames) - 1) * dt,
            step=len(trail_frames) - 1,
            environment_vertices=cfg.scene.boundary_vertices(),
            crowd_points=crowd_points,
            crowd_radii=crowd_observation.radii,
            crowd_demand=crowd_observation.demand,
            estimated_crowd_boundary=(
                controller.boundary.curve_points if controller.boundary is not None else None
            ),
            deployment_curve=(
                controller.boundary.offset_points if controller.boundary is not None else None
            ),
            target_positions=plan.active_guide_targets,
            initial_guides=initial_guides,
            current_guides=guides,
            active_ids=tuple(range(len(guides))),
            reserve_ids=(),
            trails=np.stack(trail_frames, axis=0),
            controller_state=f"{plan.phase.upper()}:{status}",
            tracking_rmse=(
                None
                if plan.diagnostics.get("tracking_rmse") is None
                else float(plan.diagnostics["tracking_rmse"])
            ),
            active_guide_count=len(guides),
            max_arc_gap=None,
            min_guide_guide_distance=None,
            min_guide_crowd_distance=None,
            min_guide_wall_distance=None,
            safety_status="step2_kinematic",
            failed=not bool(summary["scientific_success"]),
            failure_reason=None if summary["scientific_success"] else status,
            title_suffix="Step 2 gather→surround",
            max_steps=max_steps,
            guide_body_radius=0.12,
            guide_halo_radius=0.3,
            min_guide_distance_req=float(cfg.safety.min_guide_distance),
            min_crowd_distance_req=float(cfg.safety.min_crowd_distance),
            min_wall_distance_req=float(cfg.safety.room_margin),
            guide_to_target=None,
            crowd_component_ids=None,
            crowd_group_count=1,
        )
        save_final_scene(final, output / "final_scene.png")
        renderer.save_final(output / "final_scene.png", final)
    renderer.close()
    return summary
