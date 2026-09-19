# Step 1–3 research roadmap (STEP1-Research-Extension)

Status: **STEP1 CLOSURE** on branch `STEP1-Research-Extension`.  
Authority: this note + [`RESEARCH_SPEC.md`](RESEARCH_SPEC.md) + [`CODEMAP.zh.md`](CODEMAP.zh.md).  
Paper baseline: **Step 1 Core only**. See [`reports/step1_known_boundary/STEP1_CLOSURE_REPORT.md`](../reports/step1_known_boundary/STEP1_CLOSURE_REPORT.md).

## Claim labels

| Label | Meaning |
| --- | --- |
| CURRENT | Implemented and tested on this branch |
| DESIGNED | Public interface reserved; not implemented |
| FUTURE | Outside the active Step |
| EXTENSION | Implemented on this branch, **not** in the Step 1 Core freeze |

## Step 1 Core — freeze target (single static crowd)

This is the only Step 1 claim that may be frozen as a research baseline:

- Environment \(\partial\Omega_{\mathrm{env}}\) is **known and closed** (square or rectangle).
- Crowd boundary \(\partial\Omega_c\) is **unknown**. Controllers see the observed point cloud only.
- One **static** crowd (`dx^c/dt = 0`). JuPedSim spawn polygons are simulator/evaluator-only.
- **Moderate representation-level heterogeneity**: `radius`, `desired_speed`, `time_gap`, optional `demand` are stored and (where allowed) observed. Pedestrians do not move, so `desired_speed` / `time_gap` are metadata, not behavioral dynamics.
- Observation is centralized (global point cloud + allowed attributes).
- Communication among guides is unrestricted.
- Guides are velocity-controlled external agents. Initial positions are random/unknown in the feasible workspace (`guiders.init: random`), then ABCG-v2 tracks the deployment curve.

Primary Core entry:

```bash
python scripts/run_static_containment.py \
  --config configs/step1_known_boundary/square_circle.yaml \
  --output runs/step1_square_circle \
  --methods abcg --headless
```

Canonical Core matrix: `configs/step1_known_boundary/benchmark_manifest.yaml`
(2 environments × 4 shapes × development seeds 0–4 and holdout seeds 100–119).

Live visualization is the interactive default (`visualization.live: true`). Use `--headless` for CI and holdout.

Do **not** add to Core: new estimators, crowd dynamics, gather, split/merge, decentralized communication, or crowd–guide interaction.

## Step 1 Extension — CURRENT, out of Core freeze

These remain on the branch as prototypes. They are **not** part of the known-boundary paper baseline and are not in the 160-run holdout.

**Multi-crowd static surround**

- YAML `crowd.groups` places 2+ static JuPedSim clusters in one closed room
  (`square_two_crowds.yaml`, `square_three_crowds.yaml`, `rectangle_two_crowds.yaml`).
- Unified rule: **N observed connected components → N crowd boundaries → N deployment rings**.
- Partition uses observation-only connectivity (`partition_observed_components`).
  Generator labels are evaluator-only.

**Dispersed static surround (Option A)**

- `crowd.shape: dispersed` (`square_dispersed.yaml`, `rectangle_dispersed.yaml`).
- Large `connectivity_radius` joins clusters into one estimated envelope. Pedestrians remain static.

```bash
python scripts/run_static_containment.py \
  --config configs/step1_known_boundary/square_dispersed.yaml \
  --output runs/step1_dispersed \
  --methods abcg --headless
```

## Step 2 — CURRENT prototype (gather-then-surround)

**Not Step 1.** Behavioral heterogeneity and pedestrian motion belong here.

Implemented in `controllers/step2_gather/` + `experiments/step2_gather/`:

1. **Gather**: dispersed pedestrians walk toward a rendezvous disk
   (`AttractiveRendezvousMotion`); guides take a loose ring around it.
2. **Surround**: when enough people are inside the disk, re-estimate one
   deployment ring and track ABCG targets (crowd frozen).

```bash
python scripts/run_gather_then_surround.py \
  --config configs/step2_gather/square_dispersed_gather.yaml \
  --output runs/step2_gather --headless
```

Reserved for later Step 2 work:

- `BoundaryOpening` on rectangular walls; non-rectangular venues via the registry.
- Pedestrian dynamics using heterogeneity attributes (`desired_speed`, `time_gap`).
- Multiple crowds that move, disperse, split, or merge.
- Opening-aware or expanded workspace containment.

## Step 3 — DESIGNED interfaces (decentralized, limited communication)

Package: `src/crowd_management/controllers/decentralized/`.

| Protocol | Role |
| --- | --- |
| `LocalPerception` | Local crowd / neighbor sensing |
| `LocalCommunication` | Bandwidth- or range-limited messages |
| `CrowdGroupIdentifier` | Local group / split / merge hypotheses |
| `DecentralizedAssigner` | Local role assignment |
| `DecentralizedContainmentController` | search → identify → assign → contain |

`NotImplementedDecentralizedController` raises if called. Step 1 runners must continue to use centralized ABCG-v2 only.

## Explicit non-goals for Step 1 Core

- Wall-opening containment, multi-crowd tracking, local sensing, video perception, hardware, human trials.
- Feeding spawn / truth / room polygons into ABCG as a crowd boundary.
- Claiming ABCG is validated against *behavioral* heterogeneous crowds. Step 1 only has representation-level heterogeneity.

## After freeze (analysis only; not Core code)

Software baseline: annotated tag `step1-known-boundary-freeze` @ `46ad613`.
Independent holdout remains **110/160 = 68.8%**. Seeds **100–119 are spent**.

Read-only TIMEOUT audit (this branch): [`reports/step1_timeout_audit/TIMEOUT_AUDIT.md`](../reports/step1_timeout_audit/TIMEOUT_AUDIT.md).
All 40 TIMEOUT rows are safety-pin stalls (36 structural, 4 near-miss). None are horizon-sensitive.
Do not raise `max_steps` on `46ad613`.

Version chain:

```text
46ad613  (= step1-known-boundary-freeze)
│
├── analysis/step1-timeout-audit     ← this note; read-only
├── feature/step1-improvement-v2     ← only if Step 1 is revised; new seeds
└── step2-dynamic-crowd              ← crowd dynamics / gather / interaction
```

A later algorithm revision needs new development seeds and a new untouched holdout (for example 200–219).
