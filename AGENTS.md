# AGENTS.md

## Project Direction

This repository is now centered on **ABCG static unknown-crowd containment**.
The active workflow is not DBAct evacuation optimization. DBAct, density-DBAct,
and old evacuation-guidance material are archived under:

```text
legacy/evacuation_guidance/
src/crowd_management/legacy/evacuation/
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

The current suite has 88 tests.

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

Regenerate README media:

```bash
python scripts/build_readme_media.py
```

Legacy evacuation scripts remain as compatibility wrappers in `scripts/`, but
their original implementations and media are stored under
`legacy/evacuation_guidance/`.
