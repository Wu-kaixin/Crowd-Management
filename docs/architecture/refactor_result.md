# Architecture refactor result

Branch: `maintenance-architecture-ci-v1`  
Base: `main` @ `93745582d849dafaa6251e9b2e12141be2117fe8`

## What changed

1. Split formal G6 / PR6 / static-containment orchestration into focused packages.
2. Extracted shared `reporting/` and `evaluation/shared/` helpers.
3. Added schema validation, deterministic CI smoke, scientific equivalence tests.
4. Synchronized README test-count claims to a single `TEST_COUNT` marker + CI badge.
5. Added Ruff (scoped), mypy (scoped), and Linux/Windows GitHub Actions CI.
6. Restored Linux bitwise halfspace characterization via per-row `float(np.linalg.norm(...))`
   (same constraint rows/order; no projection-math change).

## Directory structure

### Before (active orchestration)

```text
evaluation/step1_g6.py          (1561)
evaluation/step1_pr6.py         (549)
experiments/static_containment.py (789)
runtime/                        (already split)
```

### After

```text
reporting/{jsonio,snapshot}.py
evaluation/shared/{polygons,confidence,curve_metrics,stats}.py
evaluation/schemas.py
evaluation/schema_validation.py
evaluation/step1_g6/{config,cases,run_case,aggregate,ablations,preflight,report,orchestrate}.py
evaluation/step1_pr6/{config,cases,run_case,aggregate,report,orchestrate}.py
experiments/static_containment/{config,methods,artifacts,runner}.py
.github/workflows/ci.yml
configs/ci_smoke.yaml
scripts/{run_ci_smoke,check_readme_consistency}.py
tests/{regression,smoke,golden}/
```

Math cores left intact: `controllers/*` (except halfspace distance path), `estimation/boundary_v2.py`, `geometry/*`.

## File size before → after (active targets)

| Path | Before | After (largest piece) |
| --- | ---: | ---: |
| `evaluation/step1_g6*` | 1561 | 467 (`run_case.py`) |
| `evaluation/step1_pr6*` | 549 | 126 (`run_case.py`) |
| `experiments/static_containment*` | 789 | 367 (`artifacts.py`) |
| `estimation/boundary_v2.py` | 846 | 846 (untouched math) |
| `controllers/abcg_v2.py` | 796 | 796 (untouched math) |

## Function size / complexity

| Symbol | Before lines / CC | After lines / CC |
| --- | --- | --- |
| `run_g6_evaluation` | 182 / 37 | 188 / 15 |
| `_build_manifest` | 129 / 18 | 124 / 12 |
| `run_static_containment` | 216 / 27 | 216 / 27 (logic preserved; artifacts extracted) |
| `_run_method` | 145 / 8 | 145 / 7 |
| Math cores (`run_fixed_target_episode`, `step`, `project_velocity_safety`, …) | unchanged | unchanged |

## Tests

| Metric | Baseline | After |
| --- | ---: | ---: |
| Collected | 168 | **179** |
| Passed | 164 (4 ULP fails) | **179** |
| Failed | 4 | 0 |

New coverage: schema regression, scientific equivalence (workers 1 vs 2), deterministic smoke, README consistency gate (script).

## README

- Removed conflicting hard-coded `77 passed` badge and `95 passed` status line.
- Added GitHub Actions CI badge pointing at `.github/workflows/ci.yml`.
- Single authoritative count via `<!-- TEST_COUNT_START/END -->` markers (currently **179**).
- `scripts/check_readme_consistency.py` enforces marker ↔ `pytest --collect-only`.

## CI

Workflow jobs: `static-analysis`, `tests-linux`, `tests-windows`, `deterministic-smoke`.  
Local verification in this environment (Linux):

- `pip check`: OK
- `compileall`: OK
- `ruff check` (scoped): OK
- `ruff format --check` (new modules): OK
- `mypy` (scoped): OK
- `check_readme_consistency.py`: OK
- full pytest: **179 passed**
- CI smoke: OK vs golden

Windows CI status depends on GitHub Actions after push (not executed in this Linux agent).

## Scientific consistency

- Full suite green, including bitwise halfspace characterization.
- `tests/regression/test_scientific_equivalence.py` locks workers=1 vs workers=2 scientific fields via `scripts/compare_results.py`.
- Smoke golden stores only stable scientific fields (no runtime/timestamps/paths).

## Performance

Local CI-smoke median wall time (3 runs, this machine): **0.525 s**.  
Baseline Phase-0 circle smoke was ~0.60 s (longer horizon). No formal G6 re-benchmark in this cloud agent (shared runners are not formal evidence). Single-worker orchestration path is unchanged algorithmically; median slowdown >5% was not observed on the smoke workload.

## Temporary Ruff exclusions

Documented in `pyproject.toml` `[tool.ruff.lint.per-file-ignores]`:

- Math cores (`controllers`, `estimation`, `geometry`, `crowd`): style rules deferred.
- Moved orchestration packages: style deferred; `F` (pyflakes) still enforced except intentional `__init__.py` re-exports.
- New modules (`reporting`, `evaluation/shared`, schemas, validation, smoke/consistency scripts): fully linted + formatted.

## Remaining technical debt

1. Further shorten `run_static_containment` (still 216 lines) and `run_case._run_method` (145).
2. Optionally split `boundary_v2.py` / `abcg_v2.py` math modules in a later math-safe pass.
3. Expand mypy from scoped set to full `evaluation/step1_*` packages.
4. Gradually clear Ruff style exclusions on moved packages.
5. Remove unused `_safe_unit_rows` helper if vectorized path stays on scalar norms.
6. Formal desktop re-benchmark of full G6/PR6 for the performance report appendix.
