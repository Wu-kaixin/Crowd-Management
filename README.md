<div align="center">

# Crowd Management

Research simulator for adaptive guide-agent deployment around unknown crowds.

[English](README.md) | [Traditional Chinese](README.zh-TW.md) | [Japanese](README.ja.md)

![License](https://img.shields.io/badge/License-MIT-green.svg)
![Python](https://img.shields.io/badge/Python-3.12%2B-blue.svg)
![Tests](https://img.shields.io/badge/Tests-23%20passed-brightgreen.svg)
![Version](https://img.shields.io/badge/Version-0.1.0-informational.svg)
![Visualization](https://img.shields.io/badge/Visualization-Matplotlib-orange.svg)

</div>

Crowd Management is a Python research prototype for studying how multiple guide agents can be deployed around an unknown crowd. The active scope is static containment: a crowd is represented as a point cloud, its boundary is estimated, and guide agents are placed around an offset safety boundary.

The current method family is **ABCG: Adaptive Boundary-Coverage Guidance**. It combines radial boundary estimation, coverage-control ideas, CVT-style deployment, and simple safety projection. The goal is to create a small, reproducible platform for testing boundary-aware deployment before adding dynamic crowd response, route choice, evacuation behavior, or real-time safety constraints.

Previous evacuation-guidance experiments are preserved as legacy baselines. They are available for reproducibility, but they are not the main project direction.

> This repository is a research prototype. It is not a calibrated crowd-safety product, deployment planner, or safety-certified control system.

---

## Visual Overview

The active media below shows ABCG static containment on circular, elliptical, irregular, and two-cluster point clouds.

![ABCG static containment grid](reports/media/abcg_static_containment_grid.png)

![ABCG containment animation](reports/media/abcg_static_containment.gif)

![ABCG metrics summary](reports/media/abcg_metrics_summary.png)

Legacy evacuation, DBAct, and density-DBAct media are stored under `legacy/evacuation_guidance/` and are not used as the main README visuals.

---

## Active Research Scope

The current stage evaluates static unknown-crowd containment.

- **Input:** a static 2D crowd point cloud.
- **Estimator:** center estimation, radial boundary estimation, and offset safety-boundary construction.
- **Controller:** ABCG guide-agent placement using weighted boundary coverage.
- **Baselines:** random deployment, static circular deployment, and legacy center-radius deployment.
- **Metrics:** coverage ratio, maximum boundary gap, radial deployment error, angular uniformity, minimum guide-guide distance, and guide-crowd safety violations.

The next stages can add dynamic crowds, behavior response, local collision avoidance, route choice, and evacuation scenarios after the static containment layer is stable.

---

## Quick Start

Create or update the conda environment:

```bash
conda env update -n abcg -f environment.yml
conda activate abcg
```

Run the main static containment experiment:

```bash
python scripts/run_static_containment.py --config configs/static_crowd_circle.yaml --output runs/static_containment_circle --methods random static_circle legacy_center_radius abcg
```

Important outputs:

- `runs/static_containment_circle/summary.json`
- `runs/static_containment_circle/summary.csv`
- `runs/static_containment_circle/abcg/metrics.json`
- `runs/static_containment_circle/abcg/containment.png`

Regenerate README media:

```bash
python scripts/build_readme_media.py
```

Run tests:

```bash
pytest --basetemp=.tmp/pytest-temp -o cache_dir=.tmp/pytest-cache
```

---

## Repository Layout

```text
Crowd-Management/
|-- configs/                         # Active static containment scenarios
|-- src/crowd_management/
|   |-- crowd/                        # Static crowd point-cloud generators
|   |-- estimation/                   # Boundary and state estimation
|   |-- controllers/                  # ABCG, CVT, and deployment baselines
|   |-- experiments/                  # Experiment runners
|   |-- legacy/evacuation/            # Archived evacuation implementation
|   |-- containment_metrics.py        # Static containment metrics
|   `-- containment_visualization.py  # Static containment plotting
|-- scripts/
|   |-- run_static_containment.py     # Main experiment CLI
|   |-- build_readme_media.py         # README media generation
|   `-- legacy wrappers               # Compatibility wrappers for archived scripts
|-- reports/
|   `-- media/                        # Active ABCG media
|-- legacy/
|   `-- evacuation_guidance/           # Archived old configs, reports, media, and scripts
|-- tests/
|-- pyproject.toml
`-- README.md
```

---

## Legacy Archive

The earlier evacuation-guidance line is stored in:

```text
legacy/evacuation_guidance/
src/crowd_management/legacy/evacuation/
```

The archive contains old scenario files, reports, figures, GIF media, original script implementations, replay utilities, metrics, and evacuation controllers. Root-level compatibility wrappers remain for older commands, but new development should start from `scripts/run_static_containment.py`.

---

## Development Status

- Active branch: `main`.
- Active method family: ABCG static unknown-crowd containment.
- Local validation: `23 passed`.
- Main committed media: PNG and GIF artifacts under `reports/media/`.

## License

This project is released under the [MIT License](LICENSE).
