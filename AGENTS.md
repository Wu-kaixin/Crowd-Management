# AGENTS.md

## Project Direction

This repository is now centered on **ABCG static unknown-crowd containment**.
The active workflow is not DBAct evacuation optimization. DBAct, density-DBAct,
and old evacuation-guidance material have been removed from `main` and are
preserved on the `local-main-backup` branch:

```text
local-main-backup:legacy/evacuation_guidance/
local-main-backup:src/crowd_management/legacy/
```

New work should start from:

```text
scripts/run_static_containment.py
configs/static_crowd_*.yaml
src/crowd_management/controllers/abcg.py
```

## Environment

This is a Python 3.12 CLI research simulator. There is no long-running server or
web app. Run experiments through scripts and inspect generated metrics/figures.

Preferred setup:

```bash
python -m venv .venv
source .venv/bin/activate  # Windows: .\.venv\Scripts\Activate.ps1
python -m pip install -U pip
python -m pip install -e ".[dev]"
```

Project Conda environment:

```bash
conda env update -n abcg -f environment.yml
conda run -n abcg python -m pip install -e ".[dev]"
```

## Testing

Standard command:

```bash
pytest --basetemp=.tmp/pytest-temp -o cache_dir=.tmp/pytest-cache
```

The authoritative suite size is whatever `pytest --collect-only` reports on
the current branch (see the `TEST_COUNT` marker in `README.md`, checked by
`scripts/check_readme_consistency.py`). Legacy evacuation tests live on the
`local-main-backup` branch.

Dependency health command:

```bash
python -m pip check
```

The success message `No broken requirements found.` has exit code zero and is
not an error.

## Main Commands

Run ABCG static containment:

```bash
python scripts/run_static_containment.py --config configs/static_crowd_circle.yaml --output runs/static_containment_circle --methods random static_circle legacy_center_radius abcg
```

Run the PR6 held-out paired evaluation:

```bash
python scripts/run_step1_pr6_evaluation.py --output reports/step1_pr6_evaluation --seed-count 30
```

Evaluation scripts select worker processes hardware-adaptively by default
(`--workers auto`, balanced mode). Override with `--workers N` or
`--performance-mode conservative|balanced|maximum`. Worker count never
changes scientific results (verified by `scripts/compare_results.py`);
see `docs/performance/final_report.md`.

Regenerate README media:

```bash
python scripts/build_readme_media.py
```

Legacy evacuation scripts, their compatibility wrappers, and old media no
longer live on `main`. Use the `local-main-backup` branch to access them.
