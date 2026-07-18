# ABCG-v2 Step 1 freeze audit

Audit date: 2026-07-18

Branch: `main`

Original baseline: `fe4e7c1dd310c4eaef814c70e9edb34ec02227ae`

Intermediate reviewed implementation commit: `ae9b845d5559da9c2703f54ffab3ed94675a5fbb`

Implementation freeze: `f2494922b2431bfd9a37a247add8a79acfdc18ed`

This audit covers only PR0-PR6 for one static, unknown crowd. Dynamic or
multiple crowds, crowd-guide behavioral interaction, limited communication,
real-person studies, UAV integration, and frontend work remain out of scope.

## Files included in the Step 1 implementation freeze

Repository and research specification:

- `.gitignore`
- `AGENTS.md`
- `README.md`
- `README.ja.md`
- `README.zh-TW.md`
- `TEST_REPORT.md`
- `docs/RESEARCH_SPEC.md`
- `docs/STEP1_FREEZE_AUDIT.md`
- `environment.yml`
- `pyproject.toml`

Step 1 configurations:

- `configs/static_crowd_circle.yaml`
- `configs/static_crowd_ellipse.yaml`
- `configs/static_crowd_nonconvex.yaml`
- `configs/static_crowd_two_clusters.yaml`
- `configs/static_crowd_capacity_shortfall.yaml`
- `configs/static_crowd_safety_infeasible.yaml`
- `configs/static_crowd_timeout.yaml`

Source and CLI:

- `scripts/build_readme_media.py`
- `scripts/run_static_containment.py`
- `scripts/run_step1_pr6_evaluation.py`
- `scripts/run_step1_g6_compliance.py`
- `src/crowd_management/__init__.py`
- `src/crowd_management/containment_metrics.py`
- `src/crowd_management/controllers/__init__.py`
- `src/crowd_management/controllers/abcg_v2.py`
- `src/crowd_management/controllers/assignment.py`
- `src/crowd_management/controllers/periodic_arc_cvt.py`
- `src/crowd_management/controllers/resources.py`
- `src/crowd_management/controllers/safety.py`
- `src/crowd_management/crowd/__init__.py`
- `src/crowd_management/crowd/truth.py`
- `src/crowd_management/estimation/__init__.py`
- `src/crowd_management/estimation/boundary_v2.py`
- `src/crowd_management/evaluation/__init__.py`
- `src/crowd_management/evaluation/step1_g6.py`
- `src/crowd_management/evaluation/step1_pr6.py`
- `src/crowd_management/experiments/static_containment.py`
- `src/crowd_management/geometry/__init__.py`
- `src/crowd_management/geometry/arclength.py`

Tests:

- `tests/test_static_containment.py`
- `tests/step1/test_abcg_v2_episode.py`
- `tests/step1/test_arclength.py`
- `tests/step1/test_boundary_pr6.py`
- `tests/step1/test_boundary_v2.py`
- `tests/step1/test_g6_compliance.py`
- `tests/step1/test_periodic_arc_cvt.py`
- `tests/step1/test_pr0_spec_truth.py`
- `tests/step1/test_pr6_evaluation.py`
- `tests/step1/test_resources_assignment.py`
- `tests/step1/test_velocity_safety.py`

Compact, versioned research evidence:

- `reports/step1_g6_compliance/G6_COMPLIANCE_REPORT.md`
- `reports/step1_g6_compliance/aggregate.json`
- `reports/step1_g6_compliance/ablation_aggregate.json`
- `reports/step1_g6_compliance/evaluation_config.json`
- `reports/step1_g6_compliance/evaluation_snapshot.json`
- `reports/step1_g6_compliance/failure_gallery.json`
- `reports/step1_g6_compliance/gate_evidence.json`
- `reports/step1_g6_compliance/paired_comparisons.json`
- `reports/step1_g6_compliance/performance.json`
- `reports/step1_g6_compliance/preflight_evidence.json`
- `reports/step1_g6_compliance/robustness_aggregate.json`
- `reports/step1_g6_compliance/stress_cases.json`
- `reports/step1_pr6_evaluation/PR6_EVALUATION_REPORT.md`
- `reports/step1_pr6_evaluation/aggregate.json`
- `reports/step1_pr6_evaluation/evaluation_config.json`
- `reports/step1_pr6_evaluation/evaluation_snapshot.json`
- `reports/step1_pr6_evaluation/failure_gallery.json`
- `reports/step1_pr6_evaluation/gate_evidence.json`
- `reports/step1_pr6_evaluation/paired_comparisons.json`
- `reports/media/abcg_metrics_summary.png`
- `reports/media/abcg_static_containment.gif`
- `reports/media/abcg_static_containment_grid.png`

The README media are small maintained documentation assets. They are not G6
trajectory evidence.

## Files deliberately excluded

| Path | Reason |
| --- | --- |
| `runs/` | 4,800 local episode artifact files (about 33.4 MB); reproducible and ignored |
| `.tmp/`, `.pytest_cache/`, `__pycache__/`, `*.pyc`, `.mplconfig/` | Test, bytecode, and plotting caches |
| `reports/stage4_density_eval_v1/` | Ignored duplicate of archived DBAct Stage 4 results; unrelated to Step 1 |
| `reports/step1_g6_compliance/records.csv` | Repeated per-episode intermediate table; generated in the external artifact directory |
| `reports/step1_g6_compliance/records.json` | Repeated per-episode intermediate data; generated in the external artifact directory |
| `reports/step1_g6_compliance/ablation_records.json` | Raw ablation rows; replaced in Git by compact `ablation_aggregate.json` |
| `reports/step1_g6_compliance/robustness_records.json` | Raw robustness rows; compact aggregate remains versioned |
| `reports/step1_g6_compliance/failure_gallery.png` | Generated visualization; JSON failure evidence remains versioned |
| `reports/step1_pr6_evaluation/records.csv` | Superseded raw PR6 diagnostic rows |
| `reports/step1_pr6_evaluation/records.json` | Superseded raw PR6 diagnostic rows |
| `reports/step1_pr6_evaluation/failure_gallery.png` | Generated diagnostic image |

All files under `legacy/evacuation_guidance/`, including the archived Stage 4
report, were already tracked before this Step 1 work and are unchanged. The
ignored top-level `reports/stage4_density_eval_v1/` copy is preserved locally
but is not staged.

## Frozen evidence architecture

The evaluator snapshots `HEAD` and repository cleanliness before writing any
output. The formal CLI automatically runs commit-bound `pytest`, `compileall`,
and `pip check`; no CLI flag can manually assert that this preflight passed.
`gate_evidence.json` records `overall_status`, `evaluated_commit`,
`code_freeze_commit`, `frozen_commit`, G0-G6 statuses, all checks, record
accounting, and terminal-state counts. A formal run writes to an artifact
directory outside the checkout, preventing tracked report updates from making
the checkout dirty. The final-HEAD verification artifact is authoritative and
is not committed back into its own evaluated commit, avoiding a SHA
self-reference cycle.

## Verification commands

Pre-commit verification in the `abcg` Conda environment:

```powershell
conda run --no-capture-output -n abcg python -m pytest --basetemp=.tmp/pytest-temp -o cache_dir=.tmp/pytest-cache
conda run --no-capture-output -n abcg python -m compileall -q src scripts
conda run --no-capture-output -n abcg python -m pip check
```

Formal G6 from a clean checkout, with artifacts outside the repository:

```powershell
conda run --no-capture-output -n abcg python scripts/run_step1_g6_compliance.py `
  --output E:\Crowd-Management-step1-artifacts\<commit>\report `
  --run-root E:\Crowd-Management-step1-artifacts\<commit>\runs `
  --seed-count 30 --bootstrap-samples 30
```

## Research-complete criteria

Step 1 may be labelled `research-complete` only after a clean, fresh checkout
automatically produces all of the following:

- full preflight success and `frozen_commit = PASS`;
- `overall_status = PASS`, `evaluated_commit` equal to the checked-out commit,
  and G0-G6 all `PASS`;
- all 600 primary records accounted for, with every failure retained in the
  denominator and terminal-state counts;
- independent evaluator-only truth for the general nonconvex U and C cases;
- ablation, robustness, stress, performance, failure-gallery, and full run
  artifact evidence;
- documentation claims that exactly match the measured results and preserve
  the Step 1 limitations.

After the research-complete documentation commit, the same frozen consistency
checks and full G6 evaluation must pass again at final `main` HEAD before push.

## Implementation-freeze verification result

The fresh checkout at `f2494922b2431bfd9a37a247add8a79acfdc18ed`
produced evaluator-generated `overall_status=PASS`, `frozen_commit=PASS`, and
G0-G6 all `PASS`. The JSON, CSV, and per-run artifact counts each equal 600.
Terminal accounting is 323 `CONVERGED`, 242 `TIMEOUT`, 5
`SAFETY_INFEASIBLE`, and 30 `BOUNDARY_INVALID`; all 277 failures remain in the
denominator. Full artifacts are retained at
`E:\Crowd-Management-step1-artifacts\f2494922b2431bfd9a37a247add8a79acfdc18ed\`.
