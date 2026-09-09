import numpy as np

from crowd_management.crowd import (
    StaticHeterogeneityConfig,
    generate_static_agent_attributes,
)


def test_static_heterogeneity_is_reproducible() -> None:
    cfg = StaticHeterogeneityConfig(
        enabled=True
    )

    a = generate_static_agent_attributes(
        100,
        cfg,
        seed=17,
    )

    b = generate_static_agent_attributes(
        100,
        cfg,
        seed=17,
    )

    for key in (
        "radius",
        "desired_speed",
        "time_gap",
    ):
        assert np.allclose(
            a[key],
            b[key],
        )


def test_static_heterogeneity_is_bounded() -> None:
    cfg = StaticHeterogeneityConfig(
        enabled=True
    )

    attributes = (
        generate_static_agent_attributes(
            500,
            cfg,
            seed=21,
        )
    )

    assert np.all(
        attributes["radius"]
        >= cfg.radius_min
    )

    assert np.all(
        attributes["radius"]
        <= cfg.radius_max
    )

    assert np.all(
        attributes["desired_speed"]
        >= cfg.desired_speed_min
    )

    assert np.all(
        attributes["desired_speed"]
        <= cfg.desired_speed_max
    )

    assert np.all(
        attributes["time_gap"]
        >= cfg.time_gap_min
    )

    assert np.all(
        attributes["time_gap"]
        <= cfg.time_gap_max
    )


def test_disabled_heterogeneity_is_homogeneous() -> None:
    cfg = StaticHeterogeneityConfig(
        enabled=False
    )

    attributes = (
        generate_static_agent_attributes(
            50,
            cfg,
            seed=1,
        )
    )

    assert np.allclose(
        attributes["radius"],
        cfg.radius_mean,
    )

    assert np.allclose(
        attributes["desired_speed"],
        cfg.desired_speed_mean,
    )

    assert np.allclose(
        attributes["time_gap"],
        cfg.time_gap_mean,
    )