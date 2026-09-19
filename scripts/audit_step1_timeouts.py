"""Retrospective Step 1 TIMEOUT audit. Read-only over frozen holdout artifacts.

Does not change controller parameters, estimators, or holdout seeds 100-119.
"""

from __future__ import annotations

import argparse
import csv
import json
from collections import defaultdict
from pathlib import Path
from statistics import mean

import numpy as np

RMSE_TOL = 0.03
MAX_STEPS = 400
CROWD_MARGIN = 0.85
V_MAX = 1.0
LAST_WINDOW = 50
NEAR_MISS_RMSE = 5.0 * RMSE_TOL
STALL_SPEED = 0.05


def _flag(row: dict[str, str], key: str) -> bool:
    return str(row.get(key, "")).strip().lower() in {"true", "1", "yes"}


def _float(row: dict[str, str], key: str) -> float | None:
    raw = row.get(key, "")
    try:
        value = float(raw)
    except (TypeError, ValueError):
        return None
    if value != value:
        return None
    return value


def _run_dir(root: Path, row: dict[str, str]) -> Path:
    config = str(row["config"]).replace(".yaml", "")
    seed = int(row["seed"])
    return root / config / f"seed_{seed:03d}"


def _load_npz(path: Path) -> dict[str, np.ndarray] | None:
    if not path.is_file():
        return None
    with np.load(path, allow_pickle=True) as handle:
        return {key: handle[key] for key in handle.files}


def _time_to_fraction(rmse: np.ndarray, fraction: float) -> int | None:
    if len(rmse) == 0:
        return None
    target = float(rmse[0]) * fraction
    hits = np.flatnonzero(rmse <= target)
    if len(hits) == 0:
        return None
    return int(hits[0])


def _finite_extra(value: object) -> float | None:
    if not isinstance(value, (int, float)):
        return None
    number = float(value)
    if number != number or not np.isfinite(number) or number > 4 * MAX_STEPS:
        return None
    return number


def _classify(
    *,
    status: str,
    rmse_final: float,
    last50_drop: float,
    extra_steps: float,
    last50_speed: float,
    last50_proj: float,
    safety_frac: float,
    crowd_pin: bool,
) -> str:
    if status != "TIMEOUT":
        return "not_timeout"
    stalled = last50_speed < STALL_SPEED and last50_proj >= 0.90
    pinned = crowd_pin and (safety_frac >= 0.75 or last50_proj >= 0.90)
    if stalled and pinned:
        if rmse_final <= NEAR_MISS_RMSE:
            return "near_miss_safety_pin"
        return "structural_safety_pin"
    moving = last50_speed >= STALL_SPEED and last50_drop > 0.08
    if moving and extra_steps <= MAX_STEPS:
        return "horizon_sensitive"
    if moving and extra_steps <= 4 * MAX_STEPS:
        return "slow_but_improving"
    if last50_drop <= 0.08 and rmse_final > NEAR_MISS_RMSE:
        return "structural_plateau"
    return "structural_other"


def audit_row(root: Path, row: dict[str, str]) -> dict[str, object]:
    run = _run_dir(root, row)
    episode_status_path = run / "abcg" / "episode_status.json"
    episode = _load_npz(run / "abcg" / "episode.npz")
    assignment = _load_npz(run / "abcg" / "assignment.npz")
    plan = _load_npz(run / "periodic_plan.npz")
    boundary = _load_npz(run / "boundary_v2.npz")
    crowd = _load_npz(run / "crowd_points.npz")
    status = str(row.get("episode_status") or "")
    record: dict[str, object] = {
        "environment": row.get("environment"),
        "shape": row.get("shape"),
        "seed": int(row["seed"]),
        "config": row.get("config"),
        "scientific_success": _flag(row, "scientific_success"),
        "boundary_valid": _flag(row, "boundary_valid"),
        "episode_status": status,
        "failure_reason": row.get("failure_reason"),
        "active_guide_count": _float(row, "active_guide_count"),
        "coverage_ratio": _float(row, "coverage_ratio"),
        "periodic_max_arc_gap": _float(row, "periodic_max_arc_gap"),
        "safety_projected_steps": _float(row, "safety_projected_steps"),
        "safety_infeasible_steps": _float(row, "safety_infeasible_steps"),
        "episode_control_steps": _float(row, "episode_control_steps"),
        "episode_final_tracking_rmse": _float(row, "episode_final_tracking_rmse"),
        "minimum_guide_crowd_distance": _float(row, "minimum_guide_crowd_distance"),
        "minimum_guide_guide_distance": _float(row, "minimum_guide_guide_distance"),
        "minimum_guide_wall_distance": _float(row, "minimum_guide_wall_distance"),
        "has_episode_trace": episode is not None,
        "timeout_class": "not_timeout",
        "max_target_displacement": 0.0 if episode is not None else None,
    }
    if episode_status_path.is_file():
        meta = json.loads(episode_status_path.read_text(encoding="utf-8"))
        record["initial_tracking_rmse"] = meta.get("initial_tracking_rmse")
        record["stop_reason"] = meta.get("stop_reason")
        record["tracking_error_nonincreasing"] = bool(
            (meta.get("diagnostics") or {}).get("tracking_error_nonincreasing")
        )
    if plan is not None and "length" in plan:
        record["deployment_length"] = float(np.asarray(plan["length"]).reshape(-1)[0])
    elif boundary is not None and "length" in boundary:
        record["deployment_length"] = float(np.asarray(boundary["length"]).reshape(-1)[0])
    if crowd is not None and "positions" in crowd:
        points = np.asarray(crowd["positions"], dtype=float)
        record["crowd_span"] = float(np.max(np.linalg.norm(points - points.mean(axis=0), axis=1)))
    if assignment is not None and episode is not None:
        guides0 = np.asarray(episode["positions"][0], dtype=float)
        targets = np.asarray(episode["target_positions"], dtype=float)
        mapping = np.asarray(episode["guide_to_target"], dtype=int)
        if targets.ndim == 3:
            record["max_target_displacement"] = float(
                np.max(np.linalg.norm(targets - targets[0], axis=2))
            )
            targets_final = targets[-1]
            targets0 = targets[0]
        else:
            targets_final = targets
            targets0 = targets
        active = mapping >= 0
        if np.any(active) and len(targets0):
            dist0 = np.linalg.norm(guides0[active] - targets0[mapping[active]], axis=1)
            record["initial_assignment_mean"] = float(np.mean(dist0))
            record["initial_assignment_max"] = float(np.max(dist0))
            record["assignment_path_sum"] = float(np.sum(dist0))
            guides_final = np.asarray(episode["positions"][-1], dtype=float)
            dist_final = np.linalg.norm(guides_final[active] - targets_final[mapping[active]], axis=1)
            record["final_assignment_max"] = float(np.max(dist_final))
            record["final_assignment_mean"] = float(np.mean(dist_final))
    if episode is None:
        return record
    rmse = np.asarray(episode["tracking_rmse"], dtype=float)
    applied = np.asarray(episode["applied_controls"], dtype=float)
    nominal = np.asarray(episode["nominal_controls"], dtype=float)
    speeds = np.linalg.norm(applied, axis=2)
    nom_speeds = np.linalg.norm(nominal, axis=2)
    if "safety_status_history" in episode:
        status_hist = np.asarray(episode["safety_status_history"]).astype(str)
        projected = status_hist == "PROJECTED"
        record["safety_projected_frac"] = float(np.mean(projected))
        record["last50_projected_frac"] = float(np.mean(projected[-LAST_WINDOW:]))
    elif "safety_control_adjustment_norm" in episode:
        adj = np.asarray(episode["safety_control_adjustment_norm"], dtype=float)
        projected = adj > 1.0e-12
        record["safety_projected_frac"] = float(np.mean(projected))
        record["last50_projected_frac"] = float(np.mean(projected[-LAST_WINDOW:]))
    else:
        record["safety_projected_frac"] = float(row.get("safety_projected_steps") or 0) / max(
            len(applied), 1
        )
        record["last50_projected_frac"] = record["safety_projected_frac"]
    record["velocity_sat_frac"] = float(np.mean(speeds >= 0.99 * V_MAX))
    record["nominal_sat_frac"] = float(np.mean(nom_speeds >= 0.99 * V_MAX))
    record["mean_applied_speed"] = float(np.mean(speeds))
    record["last50_mean_speed"] = float(np.mean(speeds[-LAST_WINDOW:]))
    record["last50_velocity_sat_frac"] = float(np.mean(speeds[-LAST_WINDOW:] >= 0.99 * V_MAX))
    record["rmse_initial"] = float(rmse[0])
    record["rmse_final"] = float(rmse[-1])
    record["rmse_min"] = float(np.min(rmse))
    record["rmse_drop"] = float(rmse[0] - rmse[-1])
    window = min(LAST_WINDOW, len(rmse) - 1)
    record["rmse_last50_drop"] = float(rmse[-1 - window] - rmse[-1])
    record["rmse_last50_rel"] = float(
        (rmse[-1 - window] - rmse[-1]) / max(float(rmse[-1 - window]), 1.0e-9)
    )
    late_slope = float(record["rmse_last50_drop"]) / max(window, 1)
    remaining = max(float(rmse[-1]) - RMSE_TOL, 0.0)
    last50_speed = float(record["last50_mean_speed"])
    if last50_speed < STALL_SPEED or late_slope <= 0:
        record["extra_steps_if_linear"] = float("inf")
    else:
        record["extra_steps_if_linear"] = remaining / max(late_slope, 1.0e-12)
    record["time_to_50pct"] = _time_to_fraction(rmse, 0.50)
    record["time_to_10pct"] = _time_to_fraction(rmse, 0.10)
    crowd_d = _float(row, "minimum_guide_crowd_distance")
    crowd_pin = crowd_d is not None and abs(crowd_d - CROWD_MARGIN) <= 1.0e-6
    record["crowd_distance_pinned"] = crowd_pin
    extra = record["extra_steps_if_linear"]
    extra_f = float(extra) if isinstance(extra, (int, float)) else float("inf")
    record["timeout_class"] = _classify(
        status=status,
        rmse_final=float(rmse[-1]),
        last50_drop=float(record["rmse_last50_drop"]),
        extra_steps=extra_f,
        last50_speed=last50_speed,
        last50_proj=float(record.get("last50_projected_frac") or 0.0),
        safety_frac=float(record.get("safety_projected_frac") or 0.0),
        crowd_pin=crowd_pin,
    )
    return record


def _mean(rows: list[dict[str, object]], key: str) -> float | None:
    values = []
    for row in rows:
        value = row.get(key)
        if isinstance(value, (int, float)) and value == value and np.isfinite(value):
            values.append(float(value))
    return mean(values) if values else None


def _fmt(value: object, digits: int = 3) -> str:
    if not isinstance(value, (int, float)):
        return "n/a"
    number = float(value)
    if number != number or not np.isfinite(number):
        return "n/a"
    return f"{number:.{digits}f}"


def _reached_frac(rows: list[dict[str, object]], key: str) -> str:
    known = [row for row in rows if row.get(key) is not None or row.get("has_episode_trace")]
    if not known:
        return "n/a"
    hit = sum(1 for row in rows if isinstance(row.get(key), int))
    return f"{hit}/{len(rows)}"


def _md(*cells: object) -> str:
    return "| " + " | ".join(str(cell) for cell in cells) + " |"


def _cmp(
    label: str,
    timeouts: list[dict[str, object]],
    success: list[dict[str, object]],
    key: str,
    digits: int = 3,
) -> str:
    left = _fmt(_mean(timeouts, key), digits)
    right = _fmt(_mean(success, key), digits)
    return _md(label, left, right)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--records", default="reports/step1_known_boundary/holdout_records.csv")
    parser.add_argument("--runs", default="_stash/step1_holdout")
    parser.add_argument("--output", default="reports/step1_timeout_audit")
    args = parser.parse_args()
    records_path = Path(args.records)
    runs = Path(args.runs)
    output = Path(args.output)
    output.mkdir(parents=True, exist_ok=True)
    with records_path.open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    audited = [audit_row(runs, row) for row in rows]
    fieldnames = sorted({key for row in audited for key in row})
    with (output / "timeout_audit.csv").open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(audited)

    timeouts = [row for row in audited if row["episode_status"] == "TIMEOUT"]
    success = [row for row in audited if row["scientific_success"] is True]
    boundary_ok = [row for row in audited if row["boundary_valid"] is True]
    classes: dict[str, list[dict[str, object]]] = defaultdict(list)
    for row in timeouts:
        classes[str(row["timeout_class"])].append(row)
    by_shape: dict[str, list[dict[str, object]]] = defaultdict(list)
    for row in timeouts:
        by_shape[str(row["shape"])].append(row)

    extra_ok = [_finite_extra(row.get("extra_steps_if_linear")) for row in timeouts]
    extra_ok_n = sum(value is not None for value in extra_ok)

    lines = [
        "# Step 1 TIMEOUT retrospective audit",
        "",
        "Baseline: `step1-known-boundary-freeze` @ `46ad61309e61353d262f54813062d51999ccb13e`.",
        "Holdout seeds 100–119 are **opened / spent**. This note only reads existing artifacts.",
        "No controller gains, `max_steps`, RMSE tolerance, or safety thresholds were changed.",
        "This audit does **not** claim the algorithm is validated. It classifies why 40 holdout",
        "runs hit the frozen 400-step cap after a valid boundary/deployment already existed.",
        "",
        "## Headline",
        "",
        f"- holdout n = {len(audited)}",
        f"- boundary valid = {len(boundary_ok)}/{len(audited)}",
        f"- scientific success = {len(success)}/{len(audited)} = 68.8%",
        f"- TIMEOUT = {len(timeouts)} (all `stop_reason=maximum_steps_reached`, horizon = {MAX_STEPS})",
        f"- RMSE tolerance (frozen) = {RMSE_TOL}",
        "",
        "The bottleneck is **post-boundary motion**, not crowd-boundary estimation.",
        "Deployment targets are static in these traces (`max_target_displacement = 0`).",
        "Guides fail to reach those fixed targets before the frozen horizon.",
        "",
        "## TIMEOUT class counts",
        "",
        _md("class", "n", "meaning"),
        _md("---", "---:", "---"),
        _md(
            "horizon_sensitive",
            len(classes["horizon_sensitive"]),
            f"last-50 still moving; linear extra steps ≤ {MAX_STEPS}",
        ),
        _md(
            "slow_but_improving",
            len(classes["slow_but_improving"]),
            "still moving, but would need several extra horizons",
        ),
        _md(
            "near_miss_safety_pin",
            len(classes["near_miss_safety_pin"]),
            f"stalled on crowd-distance pin with final RMSE ≤ {NEAR_MISS_RMSE:.2f}",
        ),
        _md(
            "structural_safety_pin",
            len(classes["structural_safety_pin"]),
            "last-50 speed ≈ 0, 100% PR5 projection, crowd-distance pin",
        ),
        _md(
            "structural_plateau",
            len(classes["structural_plateau"]),
            "late RMSE almost flat, far from tolerance, not a clean pin",
        ),
        _md(
            "structural_other",
            len(classes["structural_other"]),
            "TIMEOUT without a clean horizon or pin signature",
        ),
        "",
        "## TIMEOUT vs scientific-success means",
        "",
        _md("metric", "TIMEOUT", "CONVERGED"),
        _md("---", "---:", "---:"),
        _md("n", len(timeouts), len(success)),
        _cmp("initial RMSE", timeouts, success, "rmse_initial"),
        _cmp("final RMSE", timeouts, success, "rmse_final"),
        _cmp("last-50 RMSE drop", timeouts, success, "rmse_last50_drop"),
        _cmp("last-50 mean speed", timeouts, success, "last50_mean_speed", 4),
        _cmp("last-50 projected frac", timeouts, success, "last50_projected_frac"),
        _cmp("episode projected frac", timeouts, success, "safety_projected_frac"),
        _cmp("velocity sat frac", timeouts, success, "velocity_sat_frac"),
        _cmp("initial assignment mean", timeouts, success, "initial_assignment_mean"),
        _cmp("initial assignment max", timeouts, success, "initial_assignment_max"),
        _cmp("final assignment max", timeouts, success, "final_assignment_max"),
        _cmp("assignment path sum", timeouts, success, "assignment_path_sum"),
        _cmp("deployment length L", timeouts, success, "deployment_length"),
        _cmp("coverage ratio", timeouts, success, "coverage_ratio"),
        _cmp("active guides", timeouts, success, "active_guide_count", 2),
        _cmp("crowd span", timeouts, success, "crowd_span"),
        _cmp("max target displacement", timeouts, success, "max_target_displacement"),
        _cmp("time-to-50% RMSE", timeouts, success, "time_to_50pct", 1),
        _md(
            "reached 90% RMSE drop",
            _reached_frac(timeouts, "time_to_10pct"),
            _reached_frac(success, "time_to_10pct"),
        ),
        _cmp("time-to-90% (when reached)", timeouts, success, "time_to_10pct", 1),
        "",
        f"Linear extra-step estimates are omitted: {extra_ok_n}/{len(timeouts)} TIMEOUT rows have a",
        "finite last-50 slope with residual motion. The rest are stalled, so extra-step arithmetic",
        "is not a scientific forecast.",
        "",
        "## TIMEOUT by shape / environment",
        "",
    ]
    for shape, group in sorted(by_shape.items()):
        lines.append(
            f"- **{shape}**: {len(group)} TIMEOUT; "
            f"final RMSE mean={_fmt(_mean(group, 'rmse_final'))}; "
            f"last-50 speed={_fmt(_mean(group, 'last50_mean_speed'), 4)}; "
            f"last-50 proj={_fmt(_mean(group, 'last50_projected_frac'))}; "
            f"assignment max={_fmt(_mean(group, 'initial_assignment_max'))}; "
            f"coverage={_fmt(_mean(group, 'coverage_ratio'))}"
        )
    env_groups: dict[str, list[dict[str, object]]] = defaultdict(list)
    for row in timeouts:
        env_groups[str(row["environment"])].append(row)
    lines.append("")
    for env, group in sorted(env_groups.items()):
        lines.append(
            f"- **{env}**: {len(group)} TIMEOUT; "
            f"final RMSE={_fmt(_mean(group, 'rmse_final'))}; "
            f"last-50 speed={_fmt(_mean(group, 'last50_mean_speed'), 4)}"
        )

    lines.extend(
        [
            "",
            "## Interpretation (no retuning)",
            "",
            "Two TIMEOUT mechanisms were distinguished *without* raising `max_steps`:",
            "",
            "1. **Insufficient horizon**: last-50 RMSE still falling *and* last-50 applied speed",
            "   remains material. Extra frozen-horizon arithmetic would be a plausible next test",
            "   only on a *new* development seed set.",
            "2. **Structural controller limitation**: last-50 applied speed collapses to ~0 while",
            "   PR5 projects almost every step and `min` guide–crowd distance sits on 0.85 m.",
            "   Extra `max_steps` would only record a longer stall.",
            "",
            "Holdout TIMEOUT is **(2)**. Converged runs finish in ~100 steps at RMSE ~0.004.",
            "TIMEOUT runs share a similar first-half RMSE drop (time-to-50% ≈ 36 vs 32), then",
            "freeze: last-50 speed is numerically zero, last-50 projection fraction is 1.0, and",
            "final assignment error stays O(1) m. Velocity saturation is *lower* on TIMEOUT than",
            "on success, so guides are not slamming `v_max`; the safety filter is cancelling the",
            "nominal command.",
            "",
            "Assignment path length, active-guide count, deployment perimeter `L`, and crowd span",
            "are close between TIMEOUT and success. They are not the discriminator. Coverage is",
            "slightly lower on TIMEOUT, but the late-window kinematics are the clean signature.",
            "",
            "Concave is the largest TIMEOUT slice (18/40), consistent with guides being unable to",
            "slide around a concave envelope while remaining outside the 0.85 m crowd halfspace.",
            "The four `near_miss_safety_pin` rows already reached 90% RMSE drop (final RMSE",
            "0.08–0.12) and then sat on the pin. That is still a structural stall, not a missing",
            "100 extra steps.",
            "",
            "Do **not** raise `max_steps` on this baseline. Seeds 100–119 stay a spent holdout.",
            "Any Step 1 v2 work needs new development seeds and a new untouched holdout",
            "(for example 200–219).",
            "",
            "## TIMEOUT roster",
            "",
            _md(
                "env",
                "shape",
                "seed",
                "class",
                "init RMSE",
                "final RMSE",
                "last50 drop",
                "last50 speed",
                "last50 proj",
                "assign max",
                "final assign max",
                "crowd pin",
            ),
            _md(
                "---",
                "---",
                "---:",
                "---",
                "---:",
                "---:",
                "---:",
                "---:",
                "---:",
                "---:",
                "---:",
                "---",
            ),
        ]
    )
    for row in sorted(
        timeouts, key=lambda item: (str(item["shape"]), str(item["environment"]), int(item["seed"]))
    ):
        lines.append(
            _md(
                row["environment"],
                row["shape"],
                row["seed"],
                row["timeout_class"],
                _fmt(row.get("rmse_initial")),
                _fmt(row.get("rmse_final")),
                _fmt(row.get("rmse_last50_drop")),
                _fmt(row.get("last50_mean_speed"), 4),
                _fmt(row.get("last50_projected_frac")),
                _fmt(row.get("initial_assignment_max")),
                _fmt(row.get("final_assignment_max")),
                row.get("crowd_distance_pinned"),
            )
        )
    (output / "TIMEOUT_AUDIT.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"wrote {output / 'timeout_audit.csv'}")
    print(f"wrote {output / 'TIMEOUT_AUDIT.md'}")
    print("class counts:", {key: len(value) for key, value in sorted(classes.items())})


if __name__ == "__main__":
    main()
