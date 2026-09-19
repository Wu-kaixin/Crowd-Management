# Step 1–3 research roadmap (STEP1-Research-Extension)

Status: **ACTIVE** on branch `STEP1-Research-Extension`.  
Authority: this note + [`RESEARCH_SPEC.md`](RESEARCH_SPEC.md) + [`CODEMAP.zh.md`](CODEMAP.zh.md).

## Claim labels

| Label | Meaning |
| --- | --- |
| CURRENT | Implemented and tested on this branch |
| DESIGNED | Public interface reserved; not implemented |
| FUTURE | Outside the active Step |

## Step 1 — CURRENT (optimize ABCG in a closed venue)

Assumptions:

- Environment \(\partial\Omega_{\mathrm{env}}\) is **known and closed**.
- Supported venue types today: **square** and **rectangle** (`scenarios.register_scenario`).
- Crowd location / shape / scale / \(\partial\Omega_c\) are **unknown**.
- JuPedSim places a physically spaced **static** crowd (`dx^c/dt = 0`). Spawn polygons are simulator-only.
- Observation is centralized (global point cloud + allowed attributes).
- Communication among guides is unrestricted.
- Guide **initial positions are random/unknown** inside the feasible workspace (`guiders.init: random`), then ABCG-v2 tracks the deployment curve (surround).

Heterogeneity (CURRENT attributes, FUTURE dynamics):

- `radius`, `desired_speed`, `time_gap`, optional `demand` live in `crowd/heterogeneity.py`.
- Step 1 pedestrians remain static; speed/time-gap are metadata / JuPedSim Step 2 hooks.
- Observable subset enters `CrowdObservation` (no spawn / truth leakage).

Multi-crowd surround (CURRENT):

- YAML `crowd.groups` places 2+ static JuPedSim clusters in one closed room
  (`configs/step1_known_boundary/square_two_crowds.yaml`, `square_three_crowds.yaml`,
  `rectangle_two_crowds.yaml`).
- Unified rule: **N observed connected components → N crowd boundaries → N deployment rings**.
  Guides are split by ring length and merged into one ABCG episode.
- Partition uses **observation-only connectivity** (`partition_observed_components`).
  Generator `crowd.groups` labels are evaluator-only and must not enter planning.
- Per-group estimator cascade (no bootstrap flaking): alpha → radial → convex hull.
- Blind joint estimate on all points still fails (`multiple_significant_components`);
  unlabeled analytic `two_cluster` remains out-of-scope.

Dispersed static surround (CURRENT, Option A):

- `crowd.shape: dispersed` places many small static clusters in the room
  (`square_dispersed.yaml`, `rectangle_dispersed.yaml`).
- Large `connectivity_radius` joins them into one estimated envelope; random
  guides surround that envelope. Pedestrians remain static.

```bash
python scripts/run_static_containment.py \
  --config configs/step1_known_boundary/square_dispersed.yaml \
  --output runs/step1_dispersed \
  --methods abcg
```

Primary Step 1 entry (single crowd):

```bash
python scripts/run_static_containment.py \
  --config configs/step1_known_boundary/square_circle.yaml \
  --output runs/step1_square_circle \
  --methods abcg
```

Live visualization is default (`visualization.live: true`). Use `--headless` for CI.

## Step 2 — CURRENT gather-then-surround (Option B)

Implemented in `controllers/step2_gather/` + `experiments/step2_gather/`:

1. **Gather**: dispersed pedestrians walk toward a rendezvous disk
   (`AttractiveRendezvousMotion`); guides take a loose ring around it.
2. **Surround**: when enough people are inside the disk, re-estimate one
   deployment ring and track ABCG targets (crowd frozen).

```bash
python scripts/run_gather_then_surround.py \
  --config configs/step2_gather/square_dispersed_gather.yaml \
  --output runs/step2_gather
```

Also reserved for later Step 2 work:

- `BoundaryOpening` on rectangular walls; non-rectangular venues via the registry.
- Pedestrian dynamics using heterogeneity attributes.
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

## Explicit non-goals for Step 1

- Wall-opening containment, multi-crowd tracking, local sensing, video perception, hardware, human trials.
- Feeding spawn / truth / room polygons into ABCG as a crowd boundary.
