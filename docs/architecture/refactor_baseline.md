# Refactor baseline (Phase 0)

Captured on branch `maintenance-architecture-ci-v1` before any intentional
architecture, README, or CI changes.

## Environment

| Field | Value |
| --- | --- |
| Base branch | `main` |
| Base SHA | `93745582d849dafaa6251e9b2e12141be2117fe8` |
| Python | 3.12.13 (`conda` env `abcg`) |
| pip check | `No broken requirements found.` |
| compileall | `python -m compileall -q src scripts` → OK |
| Lint tooling on main | none configured (no Ruff/flake8/mypy in `pyproject.toml`) |
| Type-check tooling on main | none configured |

## Authoritative pytest count

Commands (do **not** trust README badges for this):

```bash
pytest --collect-only -q
pytest --basetemp=.tmp/pytest-temp -o cache_dir=.tmp/pytest-cache -q
```

| Metric | Value |
| --- | --- |
| Collected | **168** |
| Passed | 164 |
| Failed | 4 |
| Skipped | 0 |
| Errors (clean re-run) | 0 |
| Wall time (clean re-run) | ~6.2 s |

### Pre-existing failures on Linux

`tests/step1/test_hotspot_characterization.py::test_halfspaces_match_loop_reference`
fails for seeds `[5, 15, 16, 17]`. Diffs are **1 ULP** (`maxdiff ≈ 1.1e-16` to
`2.2e-16`) between the vectorized `_build_velocity_halfspaces` and the
scalar loop reference. `np.allclose` holds; `np.array_equal` does not.
Reproduced with NumPy 2.4.6 and 2.5.1. Documented as baseline debt; bitwise
lock claimed in `docs/performance/final_report.md` appears platform-sensitive
(original evidence was Windows + OpenBLAS).

An earlier full-suite run under a shared basetemp also showed transient
setup `ERROR`s that disappeared on a clean basetemp re-run (164/168).

## README vs reality (test counts)

| Location | Claim |
| --- | --- |
| `README.md` Tests badge | `77 passed` |
| `README.md` Development Status | `95 passed` |
| `AGENTS.md` | `168 tests` |
| `docs/performance/final_report.md` | `168 passed` |
| `TEST_REPORT.md` (historical freeze) | `95 passed` |
| **Actual collect-only** | **168** |

## CLI smoke (deterministic)

```bash
python scripts/run_static_containment.py \
  --config configs/static_crowd_circle.yaml \
  --output /tmp/baseline_static_circle \
  --methods abcg --skip-plots
```

| Field | Value |
| --- | --- |
| Exit code | 0 |
| Wall time | ~0.60 s |
| `coverage_ratio` | `0.8527777777777777` |
| `max_euclidean_boundary_distance` | `1.621010891922382` |
| `evaluation_status` | `valid` |
| `boundary_v2_status` | `VALID` |
| `periodic_plan_status` | `VALID` |
| `resource_status` | `VALID` |
| `assignment_status` | `VALID` |
| `episode_status` | `TIMEOUT` |
| `safety_filter_status` | `ENABLED_PR5` |
| `safety_projected_steps` | `400` |
| `method_status` | `diagnostic_only` |

## Output schema samples (static containment)

- `summary.json`: per-method scientific fields listed in
  `artifacts/maintenance/refactor_baseline.json`
- `manifest.json` top-level keys: `schema_version`, `created_at_utc`,
  `run_scope`, `run_status`, `stop_reason`, `converged`, `limitations`,
  `repository`, `environment`, `config`, `methods`, `boundary_v2`,
  `periodic_plan`, `resource_decision`, `assignments`, `episodes`,
  `closed_loop`, `velocity_safety`, `truth_boundary`

## Oversized files (>500 lines)

| Lines | Path |
| ---: | --- |
| 1561 | `src/crowd_management/evaluation/step1_g6.py` |
| 846 | `src/crowd_management/estimation/boundary_v2.py` |
| 796 | `src/crowd_management/controllers/abcg_v2.py` |
| 789 | `src/crowd_management/experiments/static_containment.py` |
| 549 | `src/crowd_management/evaluation/step1_pr6.py` |

## Oversized functions (>80 lines)

| Lines | CC | Nest | Symbol |
| ---: | ---: | ---: | --- |
| 305 | 22 | 3 | `controllers/abcg_v2.py:run_fixed_target_episode` |
| 216 | 27 | 4 | `experiments/static_containment.py:run_static_containment` |
| 182 | 37 | 4 | `evaluation/step1_g6.py:run_g6_evaluation` |
| 165 | 20 | 3 | `controllers/safety.py:project_velocity_safety` |
| 150 | 25 | 2 | `controllers/abcg_v2.py:step` |
| 145 | 8 | 4 | `evaluation/step1_g6.py:_run_method` |
| 129 | 18 | 8 | `experiments/static_containment.py:_build_manifest` |
| 118 | 15 | 2 | `controllers/periodic_arc_cvt.py:plan_periodic_arc_coverage` |
| 106 | 19 | 2 | `estimation/boundary_v2.py:boundary_v2_from_curve` |
| 102 | 15 | 2 | `controllers/safety.py:_build_velocity_halfspaces` |
| 100 | 18 | 2 | `estimation/boundary_v2.py:_alpha_shape_candidate` |

## Module dependency sketch (package level)

```text
experiments.static_containment
  → controllers, crowd, estimation, types, containment_metrics

evaluation.step1_g6 / step1_pr6
  → controllers, estimation, geometry, runtime, types, containment_metrics

runtime
  → (stdlib + psutil/threadpoolctl; no evaluation import)

controllers / estimation / geometry / crowd
  → types (+ numpy/scipy/shapely); no evaluation/reporting imports
```

No package-level import cycles detected among the active ABCG-v2 modules.

## Stable scientific fields for smoke golden

Fields that must remain identical under the same seed/config (runtime metadata
excluded):

- `coverage_ratio`, `max_euclidean_boundary_distance`, `max_boundary_gap`
- `evaluation_status`, `boundary_v2_status`, `periodic_plan_status`
- `resource_status`, `assignment_status`, `episode_status`
- `safety_filter_status`, `safety_projected_steps`, `safety_infeasible_steps`
- `active_guide_count`, `reserve_guide_count`, `method_status`
- `truth_component_count`, `metrics_position_source`

Machine/run metadata that may differ: wall time, memory, timestamps, commit
SHA, hardware, parallel plan, package versions.
