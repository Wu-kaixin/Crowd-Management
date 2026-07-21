from __future__ import annotations

import json

from crowd_management.runtime import detect_hardware, hardware_metadata

PRIVACY_FORBIDDEN_KEYS = {"hostname", "username", "user", "node", "ip", "mac", "serial", "home"}


def test_detect_hardware_returns_consistent_counts() -> None:
    info = detect_hardware()
    assert info.logical_cpus is None or info.logical_cpus >= 1
    if info.physical_cores is not None and info.logical_cpus is not None:
        assert info.physical_cores <= info.logical_cpus
    if info.affinity_cpus is not None and info.logical_cpus is not None:
        assert 1 <= info.affinity_cpus <= info.logical_cpus
    assert info.multiprocessing_start_method in {"spawn", "fork", "forkserver", "unknown"}


def test_hardware_metadata_is_json_serializable_and_privacy_safe() -> None:
    metadata = hardware_metadata()
    encoded = json.dumps(metadata)
    assert encoded
    assert set(metadata.keys()).isdisjoint(PRIVACY_FORBIDDEN_KEYS)
    for value in metadata.values():
        if isinstance(value, str):
            assert "\\Users\\" not in value and "/home/" not in value
