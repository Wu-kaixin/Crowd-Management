from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path
import subprocess

import numpy as np
import pytest

import crowd_management.evaluation.step1_g7 as g7
from crowd_management.estimation.boundary_v2 import BoundaryEstimateFailure
from crowd_management.evaluation.schemas import ResourceRegime


ROOT = Path(__file__).resolve().parents[2]
CONFIG = ROOT / "configs" / "step1_g7.yaml"


def _git(repo: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True)


def _clean_fixture_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "clean-repo"
    (repo / "src" / "crowd_management").mkdir(parents=True)
    (repo / "scripts").mkdir()
    (repo / "src" / "crowd_management" / "dummy.py").write_text("VALUE = 1\n", encoding="utf-8")
    (repo / "scripts" / "run_step1_g7.py").write_text("# frozen cli\n", encoding="utf-8")
    (repo / "scripts" / "build_step1_g7_media.py").write_text("# frozen media\n", encoding="utf-8")
    _git(repo, "init")
    _git(repo, "config", "user.name", "G7 Test")
    _git(repo, "config", "user.email", "g7-test@example.invalid")
    _git(repo, "add", ".")
    _git(repo, "commit", "-m", "fixture")
    return repo


def _protocol_evidence(
    tmp_path: Path, config: g7.G7EvaluationConfig
) -> tuple[Path, Path]:
    config_hash = g7.resolved_config_hash(config)
    pilot = tmp_path / "pilot.json"
    calibration = tmp_path / "calibration.json"
    methods = g7.evaluation_methods("pilot", quick=True)
    pilot_records = [
        {
            "scenario": case["scenario"],
            "seed": case["seed"],
            "method": method,
            "config_hash": config_hash,
            "split": "pilot",
            "pilot_data_used": False,
            "terminal_status": "TIMEOUT",
        }
        for case in g7.evaluation_cases(config, "pilot")
        for method in methods
    ]
    g7.write_strict_json(
        pilot,
        {
            "schema": "abcg-v2.1-g7-pilot-evidence-v1",
            "split": "pilot",
            "formal": False,
            "quick": True,
            "diagnostic_only": True,
            "pilot_data_used": False,
            "pilot_data_used_for_formal_conclusion": False,
            "historical_g6_seeds_used": False,
            "seeds": list(config.pilot_seeds),
            "scenarios": list(config.blocked_scenarios),
            "methods": list(methods),
            "record_count": len(pilot_records),
            "expected_record_count": len(pilot_records),
            "config_hash": config_hash,
            "records_sha256": g7._canonical_hash(pilot_records),
            "deterministic_records_sha256": g7._canonical_hash(
                [g7._deterministic_record_projection(record) for record in pilot_records]
            ),
            "records": pilot_records,
        },
    )
    calibration_cases = [
        {
            "calibration_subset": subset,
            "scenario": scenario,
            "seed": seed,
            "truth_access": "calibration_scoring_only",
            "status": "CALIBRATION_RATIO_INVALID",
        }
        for subset, seeds in (
            ("factor_fit", config.calibration_fit_seeds),
            ("independent_validation", config.calibration_validation_seeds),
        )
        for scenario in config.scenarios
        for seed in seeds
    ]
    recalculated = g7._recalculate_calibration_contract(calibration_cases, config)
    g7.write_strict_json(
        calibration,
        {
            "schema": "abcg-v2.1-g7-independent-calibration-v1",
            "split": "calibration",
            "formal": False,
            "quick": True,
            "config_hash": config_hash,
            "pilot_data_used": False,
            "historical_g6_seeds_used": False,
            "factor_fit_uses_validation_data": False,
            "target_coverage": 0.95,
            "seed_splits_disjoint": True,
            "seeds": list(config.calibration_seeds),
            "factor_fit_seeds": list(config.calibration_fit_seeds),
            "independent_validation_seeds": list(config.calibration_validation_seeds),
            "scenarios": list(config.scenarios),
            "status": recalculated["status"],
            "calibration_factor": recalculated["calibration_factor"],
            "fitted_calibration_factor": recalculated["fitted_calibration_factor"],
            "pointwise_coverage": recalculated["validation_pointwise_coverage"],
            "simultaneous_coverage": recalculated["validation_simultaneous_coverage"],
            "validation_pointwise_coverage": recalculated["validation_pointwise_coverage"],
            "validation_simultaneous_coverage": recalculated["validation_simultaneous_coverage"],
            "coverage_gate_passed": recalculated["coverage_gate_passed"],
            "case_count": recalculated["case_count"],
            "fit_valid_case_count": recalculated["fit_valid_case_count"],
            "validation_valid_case_count": recalculated["validation_valid_case_count"],
            "validation_point_count": recalculated["validation_point_count"],
            "validation_covered_count": recalculated["validation_covered_count"],
            "recalculated_contract": recalculated,
            "cases": calibration_cases,
        },
    )
    return pilot, calibration


def _failed_planning_case() -> g7._PreparedCase:
    return g7._PreparedCase(
        scenario="u_shape",
        seed=11000,
        cohort="blocked_supplement",
        initial_layout="one_sided",
        observation=np.zeros((8, 2)),
        initial_guides=np.array([[0.5, 0.5], [0.5, 1.5]]),
        boundary=BoundaryEstimateFailure(
            status="BOUNDARY_INVALID",
            component_count=0,
            method="alpha_shape",
            version=2,
            diagnostics={"reason": "fixture"},
        ),
        stability_status="BOUNDARY_INVALID",
        stability_score=None,
        raw_tube_max=None,
        calibration_factor=None,
        calibration_status="CALIBRATION_INSUFFICIENT",
        route_cache={},
    )


def test_config_freezes_disjoint_nonhistorical_splits_and_expected_matrix() -> None:
    full = g7.load_g7_config(CONFIG)
    quick = g7.load_g7_config(CONFIG, quick=True)
    assert full.parallel_workers == 24
    assert quick.parallel_workers == 24
    split_sets = [
        set(full.pilot_seeds),
        set(full.calibration_seeds),
        set(full.holdout_general_seeds),
        set(full.holdout_blocked_seeds),
    ]
    assert all(not (left & right) for index, left in enumerate(split_sets) for right in split_sets[index + 1 :])
    assert all(not set(range(30)).intersection(values) for values in split_sets)
    assert not set(full.calibration_fit_seeds).intersection(full.calibration_validation_seeds)
    assert len(g7.evaluation_cases(full, "holdout")) == 30
    assert len(g7.evaluation_methods("holdout", quick=False)) == 11
    assert len(g7.evaluation_cases(quick, "holdout")) * len(
        g7.evaluation_methods("holdout", quick=True)
    ) == 10
    assert g7._public_route_variant("legacy_unchecked_straight") == "legacy_unchecked_straight"
    assert g7._public_route_variant("straight_hungarian") == "straight"
    assert g7.evaluation_methods("pilot", quick=True) == (
        "g6_fixed_resource_rerun",
        "visibility_hungarian",
    )
    stability_reference = (
        "visibility_hungarian",
        "straight_hungarian",
        "boundary_corridor_hungarian",
        "visibility_cyclic",
        "visibility_phase0",
        "visibility_qp",
    )
    assert all(g7._method_spec(method)["uncertainty"] == "stability" for method in stability_reference)
    assert g7._method_spec("visibility_uncertainty_none")["uncertainty"] == "none"
    assert g7._method_spec("visibility_uncertainty_calibrated")["uncertainty"] == "calibrated_tube"


def test_pilot_plan_never_contains_holdout_seed() -> None:
    config = g7.load_g7_config(CONFIG)
    pilot = g7.evaluation_cases(config, "pilot")
    pilot_seeds = {int(case["seed"]) for case in pilot}
    assert pilot_seeds == set(config.pilot_seeds)
    assert not pilot_seeds.intersection(config.holdout_general_seeds)
    assert not pilot_seeds.intersection(config.holdout_blocked_seeds)
    assert {case["scenario"] for case in pilot} == {"u_shape", "c_shape"}


def test_freeze_and_holdout_hash_verification_and_dirty_rejection(tmp_path: Path) -> None:
    repo = _clean_fixture_repo(tmp_path)
    config = g7.load_g7_config(CONFIG, quick=True)
    pilot, calibration = _protocol_evidence(tmp_path, config)
    manifest_path = tmp_path / "freeze_manifest.json"
    manifest = g7.create_freeze_manifest(
        repo,
        CONFIG,
        manifest_path,
        pilot_evidence_path=pilot,
        calibration_evidence_path=calibration,
        quick=True,
    )
    assert manifest["expected_holdout_record_count"] == 10
    assert manifest["expected_holdout_v2_1_record_count"] == 8
    assert manifest["expected_g6_tracking_comparator_record_count"] == 2
    assert manifest["execution"]["configured_parallel_workers"] == 24
    assert manifest["execution"]["expected_actual_case_workers"] == 2
    assert manifest["execution"]["worker_start_method"] == "spawn"
    assert manifest["execution"]["worker_numeric_thread_limit"] == 1
    assert manifest["pilot_evidence_summary"]["record_count"] == 2
    assert manifest["calibration_evidence_summary"]["factor_fit_uses_validation_data"] is False
    assert g7.verify_freeze_manifest(repo, CONFIG, manifest_path, quick=True)["holdout_verification"] == "PASS"

    tampered = dict(manifest)
    tampered["success_definition_sha256"] = "0" * 64
    tampered_path = tmp_path / "tampered.json"
    g7.write_strict_json(tampered_path, tampered)
    with pytest.raises(RuntimeError, match="frozen input verification failed"):
        g7.verify_freeze_manifest(repo, CONFIG, tampered_path, quick=True)

    tampered_execution = json.loads(json.dumps(manifest))
    tampered_execution["execution"]["configured_parallel_workers"] = 1
    tampered_execution_path = tmp_path / "tampered-execution.json"
    g7.write_strict_json(tampered_execution_path, tampered_execution)
    with pytest.raises(RuntimeError, match="frozen input verification failed"):
        g7.verify_freeze_manifest(repo, CONFIG, tampered_execution_path, quick=True)

    (repo / "src" / "crowd_management" / "dummy.py").write_text("VALUE = 2\n", encoding="utf-8")
    with pytest.raises(RuntimeError, match="clean worktree"):
        g7.create_freeze_manifest(
            repo,
            CONFIG,
            tmp_path / "dirty.json",
            pilot_evidence_path=pilot,
            calibration_evidence_path=calibration,
            quick=True,
        )


def test_freeze_recalculates_calibration_instead_of_trusting_summary(tmp_path: Path) -> None:
    repo = _clean_fixture_repo(tmp_path)
    config = g7.load_g7_config(CONFIG, quick=True)
    pilot, calibration = _protocol_evidence(tmp_path, config)
    value = json.loads(calibration.read_text(encoding="utf-8"))
    value["validation_pointwise_coverage"] = 1.0
    g7.write_strict_json(calibration, value)
    with pytest.raises(ValueError, match="independently reproducible"):
        g7.create_freeze_manifest(
            repo,
            CONFIG,
            tmp_path / "invalid-freeze.json",
            pilot_evidence_path=pilot,
            calibration_evidence_path=calibration,
            quick=True,
        )


def test_route_infeasible_failure_never_calls_control_and_serializes_strictly(tmp_path: Path) -> None:
    planning = _failed_planning_case()
    record, media = g7._failure_record(
        planning,
        method="visibility_hungarian",
        regime=ResourceRegime.SAME_RESOURCE,
        active_count=2,
        status="ROUTE_INFEASIBLE",
        reason="DISCONNECTED_FREE_SPACE",
        config_hash="config",
        branch_sha="branch",
        frozen_sha="frozen",
        plan_optimal=True,
        diagnostics={"nonfinite_is_null": np.inf},
    )
    assert record.outcome.route_feasible is False
    assert record.metadata["control_called"] is False
    assert record.outcome.controller_terminal_state == "ROUTE_INFEASIBLE"
    assert media["trajectories"] == [[[0.5, 0.5]], [[0.5, 1.5]]]
    output = tmp_path / "record.json"
    g7.write_strict_json(output, g7._record_dict(record))
    text = output.read_text(encoding="utf-8")
    assert "NaN" not in text and "Infinity" not in text
    assert json.loads(text)["metadata"]["nonfinite_is_null"] is None


def test_layered_terminal_status_never_promotes_controller_converged() -> None:
    planning = _failed_planning_case()
    record, _ = g7._failure_record(
        planning,
        method="visibility_hungarian",
        regime=ResourceRegime.SAME_RESOURCE,
        active_count=2,
        status="ROUTE_INFEASIBLE",
        reason="no route",
        config_hash="config",
        branch_sha="branch",
        frozen_sha="frozen",
    )
    row = g7._record_dict(record)
    assert row["terminal_status"] == "ROUTE_INFEASIBLE"
    assert row["controller_terminal_state"] == "ROUTE_INFEASIBLE"
    assert all(
        key in row
        for key in (
            "PLAN_OPTIMAL",
            "ROUTE_FEASIBLE",
            "TRACK_CONVERGED",
            "SAMPLED_SAFE",
            "ESTIMATED_DEPLOYMENT_SUCCESS",
            "TRUTH_VALIDATED_SUCCESS",
        )
    )


def test_legacy_route_infeasible_layer_can_still_record_control_timeout() -> None:
    failure_reason = g7._episode_failure_reason(
        route_feasible=False,
        replan_reason="NO_PROGRESS_DETECTED",
    )
    outcome = g7.compose_layered_outcome(
        plan_optimal=True,
        route_feasible=False,
        controller_terminal_state="TIMEOUT",
        sampled_safe=True,
        truth_criteria_met=False,
        terminal_reason="maximum step count reached",
        failure_reason=failure_reason,
        diagnostics={
            "control_called": True,
            "control_despite_route_infeasible_for_legacy_ablation": True,
        },
    )
    assert outcome.route_feasible is False
    assert outcome.controller_terminal_state == "TIMEOUT"
    assert outcome.failure_reason == "ROUTE_INFEASIBLE"
    assert outcome.diagnostics["control_called"] is True
    assert outcome.estimated_deployment_success is False


def test_precontrol_failure_is_scored_on_truth_after_terminal() -> None:
    planning = _failed_planning_case()
    config = g7.load_g7_config(CONFIG, quick=True)
    truth = np.array([[1.0, 1.0], [3.0, 1.0], [3.0, 3.0], [1.0, 3.0]])
    record, media = g7._failure_record(
        planning,
        method="visibility_hungarian",
        regime=ResourceRegime.SAME_RESOURCE,
        active_count=0,
        status="ROUTE_INFEASIBLE",
        reason="DISCONNECTED_FREE_SPACE",
        config_hash="config",
        branch_sha="branch",
        frozen_sha="frozen",
        truth=truth,
        evaluation_config=config,
    )
    assert record.metrics.truth_coverage == 0.0
    assert record.metrics.maximum_consecutive_arc_gap == pytest.approx(8.0)
    assert record.metadata["truth_access"] == "post_terminal_failure_scoring_only"
    assert media["truth_boundary"] == truth.tolist()


def test_failure_denominator_and_deterministic_projection() -> None:
    planning = _failed_planning_case()
    records = [
        g7._failure_record(
            planning,
            method=method,
            regime=ResourceRegime.SAME_RESOURCE,
            active_count=2,
            status=status,
            reason=status,
            config_hash="config",
            branch_sha="branch",
            frozen_sha="frozen",
        )[0]
        for method, status in (
            ("legacy_unchecked_straight", "TIMEOUT"),
            ("visibility_hungarian", "ROUTE_INFEASIBLE"),
        )
    ]
    composition = g7._failure_composition_records(records)
    assert composition["n_total"] == 2
    assert sum(composition["counts"].values()) == 2
    first = g7._record_dict(records[0])
    second = json.loads(json.dumps(first))
    second["metrics"]["runtime_ms"] = 999.0
    second["metrics"]["peak_memory_bytes"] = 999
    assert g7._canonical_hash(g7._deterministic_record_projection(first)) == g7._canonical_hash(
        g7._deterministic_record_projection(second)
    )
    nested = {
        "metadata": {
            "safety": {"runtime_ms": 5.0, "peak_memory_includes_replay": True},
            "replay": [{"total_instrumented_runtime_ms": 7.0}],
        }
    }
    projected = g7._deterministic_record_projection(nested)
    assert projected["metadata"]["safety"]["runtime_ms"] is None
    assert projected["metadata"]["safety"]["peak_memory_includes_replay"] is None
    assert projected["metadata"]["replay"][0]["total_instrumented_runtime_ms"] is None


def test_same_resource_precontrol_failure_keeps_frozen_count_and_zero_motion() -> None:
    planning = _failed_planning_case()
    planning.route_cache[("stale",)] = object()
    config = g7.load_g7_config(CONFIG, quick=True)
    truth = np.array([[1.0, 1.0], [3.0, 1.0], [3.0, 3.0], [1.0, 3.0]])
    record, _ = g7.evaluate_g7_method(
        planning,
        truth,
        config,
        "legacy_unchecked_straight",
        config_hash="config",
        branch_sha="branch",
        frozen_sha="frozen",
    )
    assert record.metrics.active_guide_count == config.fixed_active_guides
    assert record.metadata["resource_cohort"] == f"blocked_supplement:{config.fixed_active_guides}"
    assert record.metrics.path_length == 0.0
    assert record.metrics.control_energy == 0.0
    assert record.metrics.runtime_ms is not None and record.metrics.runtime_ms >= 0.0
    assert record.metrics.peak_memory_bytes is not None
    assert record.metrics.tracking_rmse is None
    assert record.metrics.minimum_intersample_clearance is None
    assert planning.route_cache == {}


def test_case_preparation_exception_expands_to_every_frozen_pilot_method(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config = g7.load_g7_config(CONFIG, quick=True)

    def fail_prepare(*args: object, **kwargs: object) -> object:
        raise RuntimeError("fixture preparation failure")

    monkeypatch.setattr(g7, "_prepare_case", fail_prepare)
    evidence = g7.run_deployment_phase(
        ROOT,
        config,
        tmp_path,
        phase="pilot",
        quick=True,
        config_hash="config",
        branch_sha="branch",
        frozen_sha="frozen",
    )
    assert evidence["record_count"] == len(g7.evaluation_methods("pilot", quick=True))
    assert evidence["record_count"] == evidence["expected_record_count"]
    assert all(record["terminal_status"] == "EVALUATION_ERROR" for record in evidence["records"])
    assert all(record["metadata"]["exception_scope"] == "case_preparation" for record in evidence["records"])


def _small_parallel_config() -> g7.G7EvaluationConfig:
    return replace(
        g7.load_g7_config(CONFIG, quick=True),
        blocked_scenarios=("u_shape", "c_shape"),
        observation_count=24,
        boundary_bootstrap_samples=1,
        calibration_bootstrap_replicas=1,
        phase_grid_size=2,
        bootstrap_resamples=20,
        available_guides=2,
        fixed_active_guides=1,
        hold_steps=1,
        max_steps=2,
        no_progress_window=2,
        safety_replay_stride=1,
        parallel_workers=2,
    )


def test_serial_and_process_pool_have_identical_deterministic_projection_and_order(
    tmp_path: Path,
) -> None:
    config = _small_parallel_config()
    config_hash = g7.resolved_config_hash(config)
    serial = g7.run_deployment_phase(
        ROOT,
        config,
        tmp_path / "serial",
        phase="pilot",
        quick=True,
        config_hash=config_hash,
        branch_sha="branch",
        frozen_sha="frozen",
        workers=1,
    )
    parallel = g7.run_deployment_phase(
        ROOT,
        config,
        tmp_path / "parallel",
        phase="pilot",
        quick=True,
        config_hash=config_hash,
        branch_sha="branch",
        frozen_sha="frozen",
        workers=2,
    )

    assert serial["deterministic_records_sha256"] == parallel["deterministic_records_sha256"]
    identity = lambda row: (row["scenario"], row["seed"], row["method"])
    expected = [
        (case["scenario"], case["seed"], method)
        for case in g7.evaluation_cases(config, "pilot")
        for method in g7.evaluation_methods("pilot", quick=True)
    ]
    assert [identity(row) for row in serial["records"]] == expected
    assert [identity(row) for row in parallel["records"]] == expected
    assert serial["execution"]["execution_mode"] == "serial_case_loop"
    assert serial["execution"]["actual_case_workers"] == 1
    assert parallel["execution"]["execution_mode"] == "case_process_pool_spawn"
    assert parallel["execution"]["actual_case_workers"] == 2
    assert all(
        row["metadata"]["configured_parallel_workers"] == 2
        and row["metadata"]["actual_case_workers"] == 2
        and row["metadata"]["worker_numeric_thread_limit"] == 1
        and row["metadata"]["case_process_thread_environment"]["OMP_NUM_THREADS"] == "1"
        and row["metadata"]["case_process_thread_environment"]["OPENBLAS_NUM_THREADS"] == "1"
        and row["metadata"]["case_process_thread_environment"]["MKL_NUM_THREADS"] == "1"
        for row in parallel["records"]
    )


def test_parallel_case_algorithm_exception_keeps_every_method_denominator() -> None:
    config = _small_parallel_config()
    cases = [
        {
            "scenario": "unsupported_a",
            "seed": 12000,
            "cohort": "pilot",
            "forced_layout": None,
        },
        {
            "scenario": "unsupported_b",
            "seed": 12001,
            "cohort": "pilot",
            "forced_layout": None,
        },
    ]
    methods = g7.evaluation_methods("pilot", quick=True)
    evaluated, actual_workers, mode = g7._execute_deployment_cases(
        cases,
        config,
        methods,
        config_hash="config",
        branch_sha="branch",
        frozen_sha="frozen",
        calibration_status="CALIBRATION_INSUFFICIENT",
        calibration_factor=None,
        workers=2,
    )
    records = [record for record, _ in evaluated]
    assert actual_workers == 2
    assert mode == "case_process_pool_spawn"
    assert len(records) == len(cases) * len(methods)
    assert [(record.scenario, record.method) for record in records] == [
        (case["scenario"], method)
        for case in cases
        for method in methods
    ]
    assert all(record.outcome.controller_terminal_state == "EVALUATION_ERROR" for record in records)
    assert all(record.metadata["exception_scope"] == "input_generation" for record in records)


def test_process_serialization_failure_aborts_before_evidence_write(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config = _small_parallel_config()
    cases = [
        {
            "scenario": "unsupported_a",
            "seed": 12000,
            "cohort": "pilot",
            "forced_layout": None,
            "unpicklable": lambda: None,
        },
        {
            "scenario": "unsupported_b",
            "seed": 12001,
            "cohort": "pilot",
            "forced_layout": None,
        },
    ]
    monkeypatch.setattr(g7, "evaluation_cases", lambda *_args, **_kwargs: cases)
    output = tmp_path / "must-not-exist"
    with pytest.raises(RuntimeError, match="process/serialization infrastructure failure"):
        g7.run_deployment_phase(
            ROOT,
            config,
            output,
            phase="pilot",
            quick=True,
            config_hash="config",
            branch_sha="branch",
            frozen_sha="frozen",
            workers=2,
        )
    assert not output.exists()


def test_formal_holdout_rejects_worker_override_different_from_frozen_config(
    tmp_path: Path,
) -> None:
    config = g7.load_g7_config(CONFIG)
    with pytest.raises(ValueError, match="must equal the frozen parallel_workers=24"):
        g7.run_deployment_phase(
            ROOT,
            config,
            tmp_path / "holdout",
            phase="holdout",
            quick=False,
            config_hash="config",
            branch_sha="branch",
            frozen_sha="frozen",
            verified_manifest={"expected_holdout_record_count": 330},
            workers=1,
        )


def test_failure_truth_scoring_exception_cannot_erase_original_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    planning = _failed_planning_case()

    def fail_truth(*args: object, **kwargs: object) -> object:
        raise RuntimeError("fixture truth scorer failure")

    monkeypatch.setattr(g7, "_truth_metrics", fail_truth)
    record, media = g7._failure_record(
        planning,
        method="straight_hungarian",
        regime=ResourceRegime.SAME_RESOURCE,
        active_count=2,
        status="ROUTE_INFEASIBLE",
        reason="original route failure",
        config_hash="config",
        branch_sha="branch",
        frozen_sha="frozen",
        truth=np.array([[1.0, 1.0], [2.0, 1.0], [2.0, 2.0]]),
        evaluation_config=g7.load_g7_config(CONFIG, quick=True),
    )
    assert record.outcome.failure_reason == "ROUTE_INFEASIBLE"
    assert record.metadata["truth_access"] == "post_terminal_truth_scoring_failed_record_retained"
    assert record.metadata["truth_scoring_error"]["exception_type"] == "RuntimeError"
    assert media["truth_boundary"] == []


def test_calibration_ratio_zero_policy_and_fit_validation_separation() -> None:
    ratios, invalid = g7._safe_calibration_ratios(
        np.array([0.0, 1.0]),
        np.array([0.0, 2.0]),
    )
    assert invalid == 0
    assert ratios is not None and ratios.tolist() == [0.0, 0.5]
    ratios, invalid = g7._safe_calibration_ratios(
        np.array([1.0]),
        np.array([0.0]),
    )
    assert ratios is None and invalid == 1

    config = g7.load_g7_config(CONFIG)
    cases = []
    for subset, seeds in (
        ("factor_fit", config.calibration_fit_seeds),
        ("independent_validation", config.calibration_validation_seeds),
    ):
        for scenario in config.scenarios:
            for seed in seeds:
                values = [1.0] * 8
                cases.append(
                    {
                        "calibration_subset": subset,
                        "scenario": scenario,
                        "seed": seed,
                        "status": "VALID_CALIBRATION_CASE",
                        "point_count": len(values),
                        "point_ratio_values": values,
                        "simultaneous_score": 1.0,
                    }
                )
    passed = g7._recalculate_calibration_contract(cases, config)
    assert passed["status"] == "CALIBRATED_TUBE"
    assert passed["fitted_calibration_factor"] == 1.0
    validation_case = next(
        case for case in cases if case["calibration_subset"] == "independent_validation"
    )
    validation_case["point_ratio_values"] = [2.0] * 8
    validation_case["simultaneous_score"] = 2.0
    failed = g7._recalculate_calibration_contract(cases, config)
    assert failed["status"] == "CALIBRATION_INSUFFICIENT"
    assert failed["fitted_calibration_factor"] == 1.0
    assert failed["calibration_factor"] is None


def test_stability_primary_is_a_distinct_uncalibrated_geometry_heuristic() -> None:
    config = g7.load_g7_config(CONFIG, quick=True)
    planning, _ = g7._prepare_case(
        config,
        "u_shape",
        1000,
        "pilot",
        forced_layout="one_sided",
        calibration_status="CALIBRATION_INSUFFICIENT",
        calibration_factor=None,
    )
    none_buffer, _, none_info = g7._canonical_geometry(planning, config, "none")
    stability_buffer, _, stability_info = g7._canonical_geometry(planning, config, "stability")
    assert none_buffer is not None and stability_buffer is not None
    assert none_info["status"] == stability_info["status"] == "VALID"
    assert none_info["uncertainty_extra_clearance"] == 0.0
    assert planning.raw_tube_max is not None and planning.raw_tube_max > 0.0
    assert stability_info["uncertainty_extra_clearance"] == pytest.approx(planning.raw_tube_max)
    assert stability_info["uncertainty_status"] == "UNCALIBRATED_STABILITY_HEURISTIC"
    assert stability_info["uncertainty_is_calibrated_confidence"] is False
    assert stability_info["stability_mode_semantics"] == (
        "raw_tube_max_heuristic_expansion_not_calibrated_confidence"
    )
    assert stability_info["geometry_sha256"] != none_info["geometry_sha256"]
    assert stability_info["canonical_source_sha256"] == none_info["canonical_source_sha256"]


def test_ofat_statistics_pair_every_ablation_against_stability_primary() -> None:
    planning = _failed_planning_case()
    config = g7.load_g7_config(CONFIG, quick=True)
    records = [
        g7._failure_record(
            planning,
            method=method,
            regime=ResourceRegime.SAME_RESOURCE,
            active_count=config.fixed_active_guides,
            status="TIMEOUT",
            reason="fixture_timeout",
            config_hash="config",
            branch_sha="branch",
            frozen_sha="frozen",
        )[0]
            for method in (
                "straight_hungarian",
                "visibility_hungarian",
                "g6_fixed_resource_rerun",
                "boundary_corridor_hungarian",
                "visibility_uncertainty_calibrated",
            )
    ]
    paired = g7._paired_statistics(records, config)
    for method in ("boundary_corridor_hungarian", "visibility_uncertainty_calibrated"):
        item = paired["ofat_ablations"][method]
        assert item["reference_method"] == "visibility_hungarian"
        assert item["pair_count"] == 1
        assert item["binary"]["estimated_success"]["n_total"] == 1
        difference = item["continuous"]["active_guide_count"]["paired_difference"]
        assert {"mean", "median", "worst_5_percent_mean", "ci_low", "ci_high"} <= set(difference)


def test_frozen_safety_pilot_tolerances_are_explicit() -> None:
    config = g7.load_g7_config(CONFIG)
    assert config.safety_primal_tolerance == 1.0e-8
    assert config.safety_kkt_tolerance == 2.0e-5
    assert config.safety_active_tolerance == 2.0e-4
    assert config.safety_iterate_tolerance == 1.0e-5
    assert config.safety_max_iterations == 1500
    assert config.safety_replay_stride == 20
    assert config.geometry_clearance_tolerance == 1.0e-7


def test_safety_points_share_the_exact_canonical_routing_source() -> None:
    buffered = g7.build_polygon_buffer(
        np.array([[2.0, 2.0], [8.0, 2.0], [8.0, 7.0], [2.0, 7.0]]),
        g7.PolygonBufferConfig(clearance=0.8, room_size=(10.0, 10.0), room_margin=0.2),
    )
    assert isinstance(buffered, g7.BufferedPolygonGeometry)
    free_space = g7.build_guide_free_space(
        buffered,
        g7.FreeSpaceConfig(room_size=(10.0, 10.0), room_margin=0.2),
    )
    assert isinstance(free_space, g7.GuideFreeSpace)
    safety_points = g7._canonical_safety_points(buffered, spacing=0.2)
    source_again, _, _, _, _ = g7.resample_closed_curve_by_arclength(
        np.asarray(free_space.source_polygon.exterior.coords[:-1]),
        spacing=0.2,
    )
    assert np.array_equal(safety_points, source_again)
    assert free_space.source_buffer_sha256 == buffered.sha256


def test_g6_output_directory_is_rejected() -> None:
    with pytest.raises(ValueError, match="frozen G6 evidence"):
        g7.reject_g6_output(ROOT, ROOT / "reports" / "step1_g6_compliance" / "new")


def test_backend_noninferiority_uses_identical_problem_replay_only() -> None:
    config = g7.load_g7_config(CONFIG, quick=True)
    replay = {
        "step_index": 0,
        "capture_rule": "fixture",
        "problem_sha256_match": True,
        "closed_loop_probe_matches_primary": True,
        "dykstra": {
            "feasible": True,
            "primal_residual": 0.0,
            "kkt_residual": 0.0,
            "runtime_ms": 1.0,
            "control_adjustment": 0.1,
            "zoh": {"safe": True, "minimum_clearance": 0.2},
        },
        "qp": {
            "feasible": True,
            "primal_residual": 0.0,
            "kkt_residual": 0.0,
            "runtime_ms": 2.0,
            "control_adjustment": 0.1,
            "zoh": {"safe": True, "minimum_clearance": 0.2},
        },
        "applied_control_distance": 0.0,
    }

    def pair(planning: g7._PreparedCase) -> tuple[g7.G7Record, g7.G7Record]:
        baseline = g7._failure_record(
            planning,
            method="straight_hungarian",
            regime=ResourceRegime.SAME_RESOURCE,
            active_count=2,
            status="TIMEOUT",
            reason="TIMEOUT",
            config_hash="config",
            branch_sha="branch",
            frozen_sha="frozen",
        )[0]
        candidate = g7._failure_record(
            planning,
            method="visibility_hungarian",
            regime=ResourceRegime.SAME_RESOURCE,
            active_count=2,
            status="TIMEOUT",
            reason="TIMEOUT",
            config_hash="config",
            branch_sha="branch",
            frozen_sha="frozen",
        )[0]
        candidate = replace(
            candidate,
            outcome=replace(candidate.outcome, diagnostics={"control_called": True}),
            metadata={**candidate.metadata, "identical_problem_replay": [dict(replay)]},
        )
        return baseline, candidate

    first = pair(_failed_planning_case())
    single = g7._noninferiority(list(first), config)
    single_backend = single["results"]["qp_vs_dykstra_identical_problem_sampled_safe"]
    assert single_backend["decision"]["status"] == "NOT_EVALUABLE_INSUFFICIENT_CASES"

    second_planning = replace(_failed_planning_case(), seed=11001)
    second = pair(second_planning)
    noninferiority = g7._noninferiority([*first, *second], config)
    backend = noninferiority["results"]["qp_vs_dykstra_identical_problem_sampled_safe"]
    assert backend["identical_problem_snapshot_replay"] is True
    assert backend["all_problem_sha256_match"] is True
    assert backend["summary"]["event_name"] == "CASE_LEVEL_ALL_CAPTURED_SNAPSHOTS_SAMPLED_SAFE"
    assert backend["complete_case_count"] == 2
    assert backend["decision"]["noninferior"] is True

    comparison = g7._safety_comparison([*first, *second])
    replay_summary = comparison["identical_problem_replay"]
    assert replay_summary["backends"]["dykstra"]["feasible_rate"] == 1.0
    assert replay_summary["backends"]["qp"]["zoh_safe_rate"] == 1.0
    assert comparison["closed_loop_ablation"]["methods"]["visibility_hungarian"]["identical_instances"] is False


def test_readme_same_resource_projection_excludes_ofat_methods() -> None:
    planning = _failed_planning_case()
    records = [
        g7._failure_record(
            planning,
            method=method,
            regime=ResourceRegime.SAME_RESOURCE,
            active_count=2,
            status="TIMEOUT",
            reason="TIMEOUT",
            config_hash="config",
            branch_sha="branch",
            frozen_sha="frozen",
        )[0]
        for method in (
            "g6_fixed_resource_rerun",
            "straight_hungarian",
            "visibility_hungarian",
            "boundary_corridor_hungarian",
        )
    ]
    config = g7.load_g7_config(CONFIG, quick=True)
    summary = g7._readme_summary(
        records,
        g7.aggregate_records(records),
        {"points": []},
        {"status": "FAIL"},
        config,
        records_sha256="records",
        config_hash="config",
        frozen_sha="frozen",
        branch_sha="branch",
    )
    assert {row["method"] for row in summary["same_resource"]} == set(g7.PRIMARY_METHODS)
