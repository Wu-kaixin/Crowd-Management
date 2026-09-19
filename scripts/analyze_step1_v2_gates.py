"""Summarize a Step 1 v2 Gate A/B spent-regression records.csv."""

from __future__ import annotations

import argparse
import csv
import json
from collections import Counter
from pathlib import Path


def _bool(value: object) -> bool:
    if isinstance(value, bool):
        return value
    text = str(value).strip().lower()
    return text in {"true", "1", "yes"}


def summarize(records_path: Path) -> dict[str, object]:
    rows = list(csv.DictReader(records_path.open(encoding="utf-8")))
    n = len(rows)
    statuses = Counter(str(row.get("episode_status") or row.get("failure_reason") or "") for row in rows)
    scientific = sum(1 for row in rows if _bool(row.get("scientific_success")))
    boundary_valid = sum(1 for row in rows if _bool(row.get("boundary_valid")))
    timeout = sum(
        1
        for row in rows
        if str(row.get("failure_reason")) == "TIMEOUT" or str(row.get("episode_status")) == "TIMEOUT"
    )
    boundary_invalid = sum(
        1
        for row in rows
        if str(row.get("failure_reason")) == "BOUNDARY_INVALID" or str(row.get("episode_status")) == "BOUNDARY_INVALID"
    )
    by_shape: dict[str, dict[str, int]] = {}
    for row in rows:
        shape = str(row.get("shape", "unknown"))
        bucket = by_shape.setdefault(shape, {"n": 0, "success": 0, "timeout": 0, "boundary_invalid": 0})
        bucket["n"] += 1
        if _bool(row.get("scientific_success")):
            bucket["success"] += 1
        reason = str(row.get("failure_reason") or row.get("episode_status") or "")
        if reason == "TIMEOUT":
            bucket["timeout"] += 1
        if reason == "BOUNDARY_INVALID":
            bucket["boundary_invalid"] += 1
    failures = [
        {
            "environment": row.get("environment"),
            "shape": row.get("shape"),
            "seed": row.get("seed"),
            "failure_reason": row.get("failure_reason") or row.get("episode_status"),
            "boundary_v2_method": row.get("boundary_v2_method"),
            "episode_status": row.get("episode_status"),
            "episode_final_tracking_rmse": row.get("episode_final_tracking_rmse"),
            "safety_projected_steps": row.get("safety_projected_steps"),
            "transit_clearance_used": row.get("transit_clearance_used"),
            "follow_deployment_count": row.get("route_follow_deployment_count"),
            "route_final_approach_count": row.get("route_final_approach_count"),
            "route_follow_boundary_count": row.get("route_follow_boundary_count"),
            "geodesic_replan_count": row.get("geodesic_replan_count"),
            "geodesic_wait_steps": row.get("geodesic_wait_steps"),
            "geodesic_fallback_steps": row.get("geodesic_fallback_steps"),
            "geodesic_mean_path_length": row.get("geodesic_mean_path_length"),
            "geodesic_mean_waypoint_count": row.get("geodesic_mean_waypoint_count"),
            "geodesic_mean_progress": row.get("geodesic_mean_progress"),
            "route_crowd_projection_steps": row.get("route_crowd_projection_steps"),
            "route_guide_pair_projection_steps": row.get("route_guide_pair_projection_steps"),
        }
        for row in rows
        if not _bool(row.get("scientific_success"))
    ]
    gate_a = timeout <= 1
    gate_b = boundary_invalid <= 1
    return {
        "n": n,
        "scientific_success": scientific,
        "scientific_success_rate": None if n == 0 else scientific / n,
        "boundary_valid": boundary_valid,
        "TIMEOUT": timeout,
        "BOUNDARY_INVALID": boundary_invalid,
        "episode_status_counts": dict(statuses),
        "by_shape": by_shape,
        "gate_a_timeout_le_1": gate_a,
        "gate_b_boundary_invalid_le_1": gate_b,
        "gates_passed": bool(gate_a and gate_b and n == 160),
        "failures": failures,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Summarize Step 1 v2 spent-regression gates.")
    parser.add_argument("records", type=Path)
    parser.add_argument("--json-out", type=Path)
    args = parser.parse_args()
    summary = summarize(args.records)
    text = json.dumps(summary, indent=2, default=str)
    print(text)
    if args.json_out is not None:
        args.json_out.parent.mkdir(parents=True, exist_ok=True)
        args.json_out.write_text(text, encoding="utf-8")


if __name__ == "__main__":
    main()
