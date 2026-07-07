<div align="center">

# Crowd Management

Adaptive guide-agent deployment around unknown crowds.

[English](README.md) | [繁體中文](README.zh-TW.md) | [日本語](README.ja.md)

![License](https://img.shields.io/badge/License-MIT-green.svg)
![Python](https://img.shields.io/badge/Python-3.12%2B-blue.svg)
![Tests](https://img.shields.io/badge/Tests-23%20passed-brightgreen.svg)
![Version](https://img.shields.io/badge/Version-0.1.0-informational.svg)
![Visualization](https://img.shields.io/badge/Visualization-Matplotlib-orange.svg)

</div>

Crowd Management is now centered on **ABCG: Adaptive Boundary-Coverage Guidance**. The current research problem is deliberately narrow: given an unknown static crowd represented as a point cloud, estimate the crowd boundary and deploy multiple guide agents around that boundary at a desired safety distance.

The previous evacuation / DBACT / density-DBACT line has been archived as legacy material. It remains available for comparison and reproducibility, but it is no longer the main project narrative.

> This is a research prototype, not a calibrated real-world crowd-management product or safety-certified deployment system.

---

## Visual Snapshot

The active README media now shows ABCG static unknown-crowd containment. Old DBAct images, GIFs, and videos are kept only under `legacy/evacuation_guidance/`.

![ABCG static containment grid](reports/media/abcg_static_containment_grid.png)

![ABCG containment animation](reports/media/abcg_static_containment.gif)

![ABCG metrics summary](reports/media/abcg_metrics_summary.png)

The repository currently commits PNG and GIF media for the new static containment line. Existing DBAct-related MP4/GIF artifacts are archived or kept as ignored local run outputs because they describe the old direction.

---

## Current Direction

Short-term target: **static unknown crowd containment**.

- Crowd state: one static point cloud, no evacuation, no crowd-guide interaction, no communication limits.
- Estimation: center and radial boundary estimation from observed pedestrian points.
- Deployment: guide agents cover an offset safety boundary using ABCG / CVT-style coverage control.
- Metrics: coverage ratio, maximum boundary gap, radial deployment error, angular uniformity, guide-guide separation, and guide-crowd safety violations.

Longer-term stages will reintroduce dynamic crowds, behavior response, route choice, local collision avoidance, and evacuation management.

---

## Quick Start

Create an environment:

```bash
python -m venv .venv
source .venv/bin/activate  # Windows: .\.venv\Scripts\Activate.ps1
python -m pip install -U pip
python -m pip install -e ".[dev]"
```

Run the main ABCG experiment:

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

## Repository Structure

```text
Crowd-Management/
|-- configs/                         # Active static crowd containment scenarios
|-- src/crowd_management/
|   |-- crowd/                        # Static unknown-crowd point-cloud generators
|   |-- estimation/                   # Boundary and state estimation
|   |-- controllers/                  # ABCG, CVT, random/static/legacy deployment baselines
|   |-- experiments/                  # Static containment experiment runner
|   |-- legacy/evacuation/            # Legacy evacuation / DBACT implementation
|   |-- containment_metrics.py        # Static containment metrics
|   `-- containment_visualization.py  # Static containment plots
|-- scripts/
|   |-- run_static_containment.py     # Main experiment CLI
|   |-- build_readme_media.py         # Reproducible README media builder
|   `-- *_legacy wrappers             # Compatibility wrappers for archived evacuation scripts
|-- reports/
|   `-- media/                        # Active ABCG README media
|-- legacy/
|   `-- evacuation_guidance/           # Archived old configs, reports, media, and scripts
|-- tests/
|-- pyproject.toml
`-- README.md
```

---

## Legacy Archive

The old evacuation-guidance direction is stored in one place:

- `legacy/evacuation_guidance/configs/`: old evacuation scenario files.
- `legacy/evacuation_guidance/reports/`: old Stage 1-4 reports, figures, CSV files, GIF media, and archived visual outputs.
- `legacy/evacuation_guidance/scripts/`: original old CLI implementations.
- `src/crowd_management/legacy/evacuation/`: old simulator, DBACT-style controller, density-DBACT controller, metrics, replay, and visualization code.

Root-level legacy scripts remain as compatibility wrappers, but new work should start from `scripts/run_static_containment.py`.

---

## Literature-Backed Roadmap

- Coverage control and CVT provide the main deployment theory for ABCG.
- Shepherding studies motivate multi-guide containment and later collect/drive extensions.
- Social-force, CA/floor-field, and navigation-field papers remain as dynamic-crowd and evacuation extensions.
- RVO/ORCA and safety-control ideas should be added before any future real-time moving-guide claim.
- Crowd disaster and congestion-risk papers motivate pressure, velocity variance, LOS, bottleneck, and failure-mode metrics.

---

## Project Status

- Active branch of research: ABCG static unknown-crowd containment.
- Legacy branch of research: evacuation / DBACT / density-DBACT, archived for reproducibility.
- Latest local validation: `23 passed`.

This project is released under the [MIT License](LICENSE).
