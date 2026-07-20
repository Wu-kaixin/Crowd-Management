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
