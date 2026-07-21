"""Deterministic CI smoke workload tests."""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from crowd_management.evaluation.schema_validation import validate_evaluation_directory


def test_ci_smoke_script_matches_golden(tmp_path: Path) -> None:
    output = tmp_path / "smoke"
    result = subprocess.run(
        [
            sys.executable,
            "scripts/run_ci_smoke.py",
            "--config",
            "configs/ci_smoke.yaml",
            "--output",
            str(output),
            "--expected",
            "tests/golden/ci_smoke_expected.json",
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    validate_evaluation_directory(output, kind="static")
    payload = json.loads(result.stdout)
    assert payload["status"] == "ok"
    assert "stable_fields" in payload


def test_ci_smoke_golden_omits_runtime_metadata() -> None:
    golden = json.loads(Path("tests/golden/ci_smoke_expected.json").read_text(encoding="utf-8"))
    assert "stable_fields" in golden
    for forbidden in ("runtime_ms", "timestamp", "memory_bytes", "wall_time", "/home/", "/Users/"):
        assert forbidden not in json.dumps(golden)
