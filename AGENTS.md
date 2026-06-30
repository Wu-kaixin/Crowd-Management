# AGENTS.md

## Cursor Cloud specific instructions

This is a Python 3.12 CLI research simulator (crowd evacuation). There is no
long-running server or web app — you "run the application" by executing the
experiment/visualization scripts in `scripts/`, which write metrics and figures.

### Environment (conda — preferred)
- Miniconda is installed at `~/miniconda3`. The project env is the conda env
  `C-M` (Python 3.12). Run tools via `conda run -n C-M ...` (e.g.
  `~/miniconda3/bin/conda run -n C-M pytest`) or `conda activate C-M`.
- Gotcha — do NOT run `conda env create -f environment.yml` on this VM as-is:
  1. conda's default channels require Terms-of-Service acceptance
     (`conda tos accept --override-channels --channel https://repo.anaconda.com/pkgs/main`
     and `.../pkgs/r`).
  2. conda-forge's `matplotlib` drags in heavy `qt6-main`/`pyside6` packages that
     fail to link on this VM's overlay filesystem ("Cannot link a source that
     does not exist"). They are unnecessary for this headless Agg-backend
     simulator. Instead, create the env and install deps via pip (this is what the
     startup update script does):
     `conda create -n C-M python=3.12 -y`
     then `conda run -n C-M python -m pip install -e ".[dev]" imageio-ffmpeg`.
- `conda config --set always_copy true` is set to avoid hardlink issues on this FS.
- A plain `.venv` virtualenv (`python3 -m venv .venv`; needs system
  `python3.12-venv`) also works if you prefer not to use conda.

### Testing
- Standard command: `conda run -n C-M pytest` (passes 18 tests).
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
