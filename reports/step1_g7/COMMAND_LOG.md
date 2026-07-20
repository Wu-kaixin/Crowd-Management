# ABCG-v2.1 Step 1 command log

Commands in this file were run from `E:\Crowd-Management`. Formal Python
validation and experiments use the Python 3.12 Conda environment `abcg`.

## Baseline protection

```powershell
git status --short --branch
git switch main
git pull --ff-only origin main
git rev-parse HEAD
git switch -c step1-proof-strengthening-v1
conda run -n abcg python -m pytest --basetemp=.tmp/pytest-temp -o cache_dir=.tmp/pytest-cache
conda run -n abcg python -m compileall src scripts
conda run -n abcg python -m pip check
```

Observed baseline: `1c3642c1adef0f11e0bde7651e2da64afbc45a8b`,
`95 passed in 134.65s`, compileall exit 0, and
`No broken requirements found.`

## S0

```powershell
conda run -n abcg python -m pytest tests/step1/test_g7_semantics.py --basetemp=.tmp/pytest-s0-target -o cache_dir=.tmp/pytest-cache-s0-target -q
conda run -n abcg python -m pytest --basetemp=.tmp/pytest-s0-full -o cache_dir=.tmp/pytest-cache-s0-full -q
conda run -n abcg python -m compileall -q src scripts
conda run -n abcg python -m pip check
```

Observed: `7 passed in 0.54s`; full suite `102 passed in 90.59s`;
compileall and pip check passed.

## S1

```powershell
conda run -n abcg python -m pytest tests/step1/test_boundary_v3.py tests/step1/test_g7_semantics.py --basetemp=.tmp/pytest-s1-target -o cache_dir=.tmp/pytest-cache-s1-target -q
conda run -n abcg python -m pytest --basetemp=.tmp/pytest-s1-full -o cache_dir=.tmp/pytest-cache-s1-full -q
conda run -n abcg python -m compileall -q src scripts
conda run -n abcg python -m pip check
```

Observed: targeted `16 passed in 0.47s`; full suite
`111 passed in 122.56s`; compileall and pip check passed.

## S2

```powershell
conda run -n abcg python -m pytest tests/step1/test_analytic_arc_resources.py tests/step1/test_periodic_arc_cvt.py tests/step1/test_resources_assignment.py --basetemp=.tmp/pytest-s2-target -o cache_dir=.tmp/pytest-cache-s2-target -q
conda run -n abcg python -m pytest --basetemp=.tmp/pytest-s2-full -o cache_dir=.tmp/pytest-cache-s2-full -q
conda run -n abcg python -m compileall -q src scripts
conda run -n abcg python -m pip check
```

Observed: targeted `45 passed in 0.52s`; full suite
`138 passed in 139.65s`; compileall and pip check passed.

## S3

```powershell
conda run -n abcg python -m pytest tests/step1/test_routing.py tests/step1/test_route_assignment.py tests/step1/test_resources_assignment.py tests/step1/test_abcg_v2_episode.py tests/step1/test_velocity_safety.py --basetemp=.tmp/pytest-s3-target -o cache_dir=.tmp/pytest-cache-s3-target -q
conda run -n abcg python -m pytest --basetemp=.tmp/pytest-s3-full -o cache_dir=.tmp/pytest-cache-s3-full -q
conda run -n abcg python -m compileall -q src scripts
conda run -n abcg python -m pip check
git diff --check
```

Observed: targeted `47 passed in 0.48s`; full suite
`156 passed in 134.74s`; compileall, pip check, and diff check passed.

## S4

```powershell
conda run -n abcg python -m pytest tests/step1/test_waypoint.py tests/step1/test_abcg_v2_episode.py tests/step1/test_velocity_safety.py --basetemp=.tmp/pytest-s4-target -o cache_dir=.tmp/pytest-cache-s4-target -q
conda run -n abcg python -m pytest --basetemp=.tmp/pytest-s4-full -o cache_dir=.tmp/pytest-cache-s4-full -q
conda run -n abcg python -m compileall -q src scripts
conda run -n abcg python -m pip check
git diff --check
```

Observed: targeted `28 passed in 0.49s`; full suite
`166 passed in 135.48s`; compileall, pip check, and diff check passed.

## S5 and independent-review regression fixes

```powershell
conda run -n abcg python -m pytest tests/step1/test_boundary_v3.py tests/step1/test_analytic_arc_resources.py tests/step1/test_g7_semantics.py tests/step1/test_route_assignment.py --basetemp=.tmp/pytest-review-fixes -o cache_dir=.tmp/pytest-cache-review-fixes -q
conda run -n abcg python -m pytest tests/step1/test_safety_v2.py tests/step1/test_waypoint.py tests/step1/test_velocity_safety.py tests/step1/test_abcg_v2_episode.py --basetemp=.tmp/pytest-s5-target -o cache_dir=.tmp/pytest-cache-s5-target -q
conda run -n abcg python -m pytest --basetemp=.tmp/pytest-s5-full -o cache_dir=.tmp/pytest-cache-s5-full -q
conda run -n abcg python -m compileall -q src scripts
conda run -n abcg python -m pip check
git diff --check
conda run -n abcg python -c "import sys;sys.path.insert(0,'src');from pathlib import Path;from crowd_management.evaluation.step1_g7 import audit_frozen_g6_evidence;r=audit_frozen_g6_evidence(Path('.'));assert r['all_match'] and r['legacy_visual_overview_all_match'];print('G6_READONLY_AUDIT_PASS',r['file_count'],r['legacy_visual_overview_file_count'])"
```

Observed: review regressions `57 passed in 0.78s`; S5 targeted
`46 passed in 0.55s`; full suite `189 passed in 75.95s`; compileall,
pip check, diff check, and frozen G6 hash audit passed.

## S6 pre-freeze validation

```powershell
conda run -n abcg python -m py_compile src/crowd_management/evaluation/step1_g7.py scripts/run_step1_g7.py scripts/build_step1_g7_media.py
conda run -n abcg python -m pytest tests/step1/test_step1_g7_evaluation.py tests/step1/test_step1_g7_media.py tests/step1/test_statistics_v2.py tests/step1/test_g7_semantics.py --basetemp=.tmp/pytest-s6-integrated-root -o cache_dir=.tmp/pytest-cache-s6-integrated-root -q
conda run -n abcg python -m pytest --basetemp=.tmp/pytest-s6-full-root -o cache_dir=.tmp/pytest-cache-s6-full-root -q
conda run -n abcg python -m compileall -q src scripts
conda run -n abcg python -m pip check
git diff --check
```

Observed: integrated `92 passed in 30.32s`; full suite
`272 passed in 105.61s`; py_compile, compileall, pip check, and diff check
passed.  Independent S6 audit found no P0/P1 blocker.  The formal G7 gate
remains `NOT_RUN` until the committed clean-tree Pilot -> Calibration ->
Freeze -> Holdout protocol is complete.

## S6 parallel execution hardening and refreeze requirement

The initial frozen serial Holdout was intentionally stopped before any formal
Holdout evidence was published after hardware utilization was reviewed.  Its
Pilot, Calibration, and Freeze files were preserved only under the ignored
`runs/step1_g7_serial_attempt_2bbc623/` directory and are not used by the
formal conclusion.

Hardware audit: Intel Core i9-14900KF (8P+16E, 24 physical cores, 32 logical
processors); NVIDIA GeForce RTX 5080 (16303 MiB), CUDA available through
`torch 2.13.0+cu130`.  The formal algorithms remain CPU-only because the
Shapely/GEOS, Qhull, Hungarian, and SciPy SLSQP paths have no numerically
equivalent CUDA backend.  The frozen replacement uses 24 independent
case-level Windows spawn workers and constrains each worker's numeric-library
thread count to one.

```powershell
conda run -n abcg python -m py_compile src/crowd_management/evaluation/step1_g7.py scripts/run_step1_g7.py scripts/build_step1_g7_media.py
conda run -n abcg python -m pytest tests/step1/test_step1_g7_evaluation.py tests/step1/test_step1_g7_media.py tests/step1/test_statistics_v2.py tests/step1/test_g7_semantics.py --basetemp=.tmp/pytest-parallel-integrated-root -o cache_dir=.tmp/pytest-cache-parallel-integrated-root -q
conda run -n abcg python -m pytest --basetemp=.tmp/pytest-parallel-full-root -o cache_dir=.tmp/pytest-cache-parallel-full-root -q
conda run -n abcg python -m compileall -q src scripts
conda run -n abcg python -m pip check
git diff --check
```

Observed: integrated `96 passed in 102.87s`; full suite
`276 passed in 255.05s`; py_compile, compileall, pip check, and diff check
passed.  Tests include serial/parallel deterministic-projection equivalence,
stable case/method ordering, complete algorithm-failure denominators,
infrastructure-failure abort before evidence publication, frozen worker-count
verification, numeric thread limits, and a real detached local-clone media
reproduction.  The 24-worker implementation now requires a new commit and a
fresh Pilot -> Calibration -> Freeze -> Holdout sequence.

## Formal 24-worker Pilot -> Calibration -> Freeze -> Holdout

```powershell
conda run -n abcg python scripts/run_step1_g7.py --phase pilot --config configs/step1_g7.yaml --output runs/step1_g7/pilot --workers 24
conda run -n abcg python scripts/run_step1_g7.py --phase calibration --config configs/step1_g7.yaml --output runs/step1_g7/calibration
conda run -n abcg python scripts/run_step1_g7.py --phase freeze --config configs/step1_g7.yaml --output runs/step1_g7/freeze --pilot-evidence runs/step1_g7/pilot/pilot_evidence.json --calibration-evidence runs/step1_g7/calibration/calibration_evidence.json
conda run -n abcg python scripts/run_step1_g7.py --phase holdout --config configs/step1_g7.yaml --output reports/step1_g7 --freeze-manifest runs/step1_g7/freeze/freeze_manifest.json --workers 24
```

Observed frozen SHA: `dc73866254136b1e14237483bc4c8a0934e8732f`.
The Holdout completed with 24 case workers in `1739256.23 ms` and wrote all
330 expected records.  Record SHA-256:
`b8b5ddb9879c268e62447b89572b8dd8b9167f0096fdaa0b32099f1b88b91238`.
The gate result was **G7 FAIL**: independent calibration was insufficient,
Holm-adjusted primary superiority did not pass, and missing paired tracking
RMSE and minimum-clearance values prohibited primary inference.  All 300
ABCG-v2.1 deployment records failed: 232 `ROUTE_INFEASIBLE`, 60
`RESOURCE_UNCERTAIN`, and 8 `TIMEOUT`.

## Formal media and post-run audit corrections

```powershell
conda run -n abcg python scripts/build_step1_g7_media.py --input reports/step1_g7 --output reports/media/step1_g7
conda run -n abcg python -m pytest tests/step1/test_step1_g7_media.py -q --basetemp=.tmp/pytest-media-fix2 -o cache_dir=.tmp/pytest-cache-media-fix2
conda run -n abcg python -m pytest tests/step1/test_step1_g7_evaluation.py -q -k "source_hash_uses_git_blobs or freeze_and_holdout_hash_verification" --basetemp=.tmp/pytest-source-hash -o cache_dir=.tmp/pytest-cache-source-hash
conda run -n abcg python -m pytest tests/step1/test_step1_g7_evaluation.py tests/step1/test_step1_g7_media.py -q --basetemp=.tmp/pytest-presentation-fix -o cache_dir=.tmp/pytest-cache-presentation-fix
```

The first media build exposed a validator bug: formal U/C truth was concave,
but both method-estimated source polygons were legitimately convex.  The
validator was corrected to bind scenario identity to the frozen truth geometry;
44 media tests passed and all seven assets were generated.  A subsequent
presentation audit added the compact-record terminal composition to the
TIMEOUT figure and marked every failure-inclusive adaptive group with an X;
70 evaluator/media tests passed in 122.65s.  The Git source aggregate was also changed
to canonical Git-blob bytes, with 2/2 targeted provenance tests passing.

These corrections were made after the frozen FAIL run.  A replacement Pilot
was started and stopped before evidence publication when the user requested a
summary instead of another full Holdout.  No replacement formal conclusion is
claimed; see `POST_RUN_AUDIT.md`.
