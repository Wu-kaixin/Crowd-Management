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

Do **not** add to Core: crowd dynamics, gather, split/merge, decentralized
communication, or crowd–guide interaction. v2 may add route-aware nominal
motion and an evidence-gated estimator cascade; it must not lower
observation-coverage or PR5 thresholds. See [`STEP1_V2_PROTOCOL.md`](STEP1_V2_PROTOCOL.md).

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

**Step 1 v2 (this branch):** structural repairs only — route-aware nominal motion
and an evidence-gated estimator cascade. Protocol:
[`docs/STEP1_V2_PROTOCOL.md`](STEP1_V2_PROTOCOL.md).
Do not retune PR5, `max_steps`, RMSE tolerance, or assignment to chase 99%.
Seeds 100–119 are `SPENT_REGRESSION`. Development 300–349; intermediate 350–369;
final untouched holdout 400–449.

Version chain:

```text
46ad613  (= step1-known-boundary-freeze)
│
├── analysis/step1-timeout-audit     ← read-only
├── feature/step1-improvement-v2     ← route-aware motion + robust boundary
│     └── step1-v2-dev-dual-ring @ 649480d   ← 362/400 development
│           └── feature/step1-v2-safe-geodesic  ← visibility-graph motion
└── step2-dynamic-crowd              ← crowd dynamics / gather / interaction
```
