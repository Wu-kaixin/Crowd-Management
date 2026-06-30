# AGENTS.md

## Cursor Cloud specific instructions

This is a Python 3.12 CLI research simulator (crowd evacuation). There is no
long-running server or web app — you "run the application" by executing the
experiment/visualization scripts in `scripts/`, which write metrics and figures.

### Environment
- Use the project virtualenv at `.venv` (created by the startup update script).
  Run tools as `.venv/bin/python ...` / `.venv/bin/pytest ...`, or activate with
  `source .venv/bin/activate`.
- `ffmpeg` and `python3.12-venv` are provided at the system level; the update
  script only refreshes the Python deps via an editable install (`pip install -e ".[dev]"`).

### Testing
- Standard command: `.venv/bin/pytest` (passes 18 tests).
- Gotcha: the README's `pytest --basetemp=.tmp/pytest-temp -o cache_dir=.tmp/pytest-cache`
  fails unless the parent `.tmp/` directory already exists (pytest will not create
  the missing parent of `basetemp`). Run `mkdir -p .tmp/pytest-temp` first, or just
  run plain `.venv/bin/pytest`.

### Running experiments (commands documented in `README.md` "Useful Commands")
- Quick smoke: `scripts/run_density_dbact_experiment.py ... --skip-video --fast-test`.
- Single runs: `scripts/run_baseline.py`, `scripts/run_guided.py`.
- Outputs land under `runs/` (git-ignored) and `outputs/` (git-ignored except
  `.gitkeep`); generated figures are PNG/GIF artifacts.

### Lint
- No linter is configured in this repo (no ruff/flake8/black/pre-commit config).
