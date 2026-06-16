# Crowd-Management Sprint

This repository is a **simple crowd-management feasibility simulator**. It was built for a short sprint whose objective is not to reproduce a complete exclusion-queue model, hybrid crowd model, CBF controller, or LLM planner. The immediate goal is:

> Test whether a cargo-guidance / DBACT-style group-guidance algorithm can be transferred to a simple crowd model and produce visible simulation results.

## Model Choice

The first sprint uses a **simple microscopic agent-based crowd model with social-force-like interactions**.

Each pedestrian has:

- position and velocity;
- desired speed;
- target exit;
- personal radius;
- compliance to guidance.

Pedestrian motion is computed from:

- attraction toward the exit;
- pedestrian-pedestrian repulsion;
- wall repulsion;
- optional mobile-guider influence.

## Transfer Idea from DBACT / Cargo Guidance

The original cargo problem uses robots around a passive object. Here the crowd is treated as an **active deformable group**, not a rigid cargo. The transferred idea is:

1. estimate the crowd center and spread;
2. compute the direction from the crowd center to the exit;
3. place guiders behind and beside the active crowd;
4. use those guiders to locally influence pedestrian desired directions.

The implementation is in:

```text
src/crowd_management/dbact_transfer.py
```

## Repository Structure

```text
Crowd-Management/
├── configs/
│   └── simple_room.yaml
├── src/
│   └── crowd_management/
│       ├── types.py
│       ├── crowd_model.py
│       ├── guider_model.py
│       ├── guidance_controller.py
│       ├── dbact_transfer.py
│       ├── metrics.py
│       └── visualization.py
├── scripts/
│   ├── run_baseline.py
│   ├── run_guided.py
│   └── compare_results.py
├── tests/
├── outputs/
├── README.md
├── requirements.txt
└── pyproject.toml
```

## Setup with Miniconda

Create and activate the project environment:

```bash
conda create -n C-M python=3.12 -y
conda activate C-M

python -m pip install -U pip
python -m pip install -e ".[dev]"
```

If `conda activate` is not available in a non-interactive shell, use `conda run`:

```bash
conda run -n C-M python -m pip install -U pip
conda run -n C-M python -m pip install -e ".[dev]"
conda run -n C-M pytest
```

## Run Experiments

Baseline, no guidance:

```bash
python scripts/run_baseline.py --config configs/simple_room.yaml --output outputs/baseline
```

Guided case with transferred DBACT-style controller:

```bash
python scripts/run_guided.py --config configs/simple_room.yaml --output outputs/guided
```

Compare results:

```bash
python scripts/compare_results.py --baseline outputs/baseline --guided outputs/guided --output outputs/comparison
```

To save GIF animations, add `--animation`:

```bash
python scripts/run_guided.py --animation
```

## Outputs

Each run saves:

- `metrics.json`
- `timeseries.csv`
- `timeseries.png`
- `final_snapshot.png`
- `density_heatmap.png`
- optional `animation.gif`

Comparison saves:

- `comparison.json`
- `evacuation_rate_comparison.png`

## Tests

```bash
pytest
```

Expected result in this packaged version:

```text
6 passed
```

## Sprint Interpretation

A good first report should not claim that this is a final crowd model. It should say:

1. we selected a simple microscopic crowd model;
2. we implemented baseline evacuation;
3. we transferred DBACT-style group guidance to mobile guiders;
4. we compared no-guidance and guided cases;
5. the result shows what works and what needs modification.

This is intentionally a simple basis for the first one- or two-week progress check.
