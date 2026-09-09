from pathlib import Path

import numpy as np
from shapely.geometry import Point

from crowd_management.crowd import (
    StaticCrowdConfig,
    build_center_support_polygon,
    build_crowd_source,
)
from crowd_management.experiments.static_containment import (
    run_static_containment,
)


def _make_config() -> StaticCrowdConfig:
    return StaticCrowdConfig.from_dict(
        {
            "source": "jupedsim",
            "shape": "polygon",
            "count": 40,
            "center": [5.0, 5.0],
            "radius": 2.0,
            "region": {
                "vertices": [
                    [3.0, 3.0],
                    [7.0, 3.0],
                    [7.0, 7.0],
                    [3.0, 7.0],
                ]
            },
            "spacing": {
                "distance_to_agents": 0.35,
                "distance_to_polygon": 0.20,
            },
        },
        seed=11,
    )


def test_jupedsim_source_returns_n_by_2_points() -> None:
    cfg = _make_config()

    source = build_crowd_source(
        cfg
    )

    points = source.observe()

    assert points.shape == (
        40,
        2,
    )

    assert np.isfinite(
        points
    ).all()


def test_jupedsim_source_is_reproducible() -> None:
    cfg = _make_config()

    source_a = build_crowd_source(
        cfg
    )

    source_b = build_crowd_source(
        cfg
    )

    points_a = (
        source_a.observe()
    )

    points_b = (
        source_b.observe()
    )

    assert np.allclose(
        points_a,
        points_b,
    )


def test_jupedsim_points_lie_in_center_support() -> None:
    cfg = _make_config()

    source = build_crowd_source(
        cfg
    )

    points = source.observe()

    support = (
        build_center_support_polygon(
            cfg
        )
    )

    for x, y in points:
        point = Point(
            float(x),
            float(y),
        )

        assert support.buffer(
            1.0e-9
        ).covers(point)


def test_jupedsim_truth_is_single_component() -> None:
    cfg = _make_config()

    source = build_crowd_source(
        cfg
    )

    truth = source.truth(
        safety_distance=0.8
    )

    assert truth.valid

    assert (
        truth.component_count
        == 1
    )

    assert (
        truth.status
        == "valid"
    )

    assert truth.boundary_points.shape == (
        720,
        2,
    )

    assert truth.safety_points.shape == (
        720,
        2,
    )

    assert (
        truth.diagnostics[
            "truth_exposed_to_controller"
        ]
        is False
    )


def test_jupedsim_static_containment_runner(
    tmp_path: Path,
) -> None:
    repo = (
        Path(__file__)
        .resolve()
        .parents[2]
    )

    config_path = (
        repo
        / "configs"
        / "jupedsim"
        / "static_polygon.yaml"
    )

    result = (
        run_static_containment(
            config_path,
            tmp_path,
            methods=["abcg"],
            save_plots=False,
        )
    )

    assert "abcg" in result

    assert (
        tmp_path
        / "crowd_points.npz"
    ).is_file()

    assert (
        tmp_path
        / "crowd_truth.npz"
    ).is_file()

    assert (
        tmp_path
        / "summary.json"
    ).is_file()

    assert (
        tmp_path
        / "manifest.json"
    ).is_file()

    assert (
        tmp_path
        / "abcg"
        / "metrics.json"
    ).is_file()

def test_disabled_heterogeneity_does_not_write_attribute_artifact(
    tmp_path: Path,
) -> None:
    repo = (
        Path(__file__)
        .resolve()
        .parents[2]
    )

    run_static_containment(
        repo / "configs" / "ci_smoke.yaml",
        tmp_path,
        methods=["abcg"],
        save_plots=False,
    )

    assert not (
        tmp_path / "crowd_attributes.npz"
    ).exists()