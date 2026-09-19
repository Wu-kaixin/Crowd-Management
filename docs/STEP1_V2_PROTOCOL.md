# Step 1 v2 experiment protocol (frozen before development)

Status: **ACTIVE for algorithm work**. This is not a re-opening of the spent
holdout 100–119. Frozen Core baseline remains `step1-known-boundary-freeze`
@ `46ad613` with observed scientific success **110/160 = 68.8%**.

Do **not** change `max_steps`, PR5 distances, RMSE tolerance, or assignment
in order to chase 99%. v2 is two structural repairs:

1. Route-aware nominal motion (`controllers/boundary_route.py`, `abcg_v2_route.py`)
2. Evidence-gated boundary cascade (alpha → radial → convex envelope)

PR5 (`safety.py`) stays the authority on forbidden velocities.

## Why routing is required

Even if every TIMEOUT were fixed, 10 `BOUNDARY_INVALID` remain:

```text
110/160 = 68.75%
40 TIMEOUT + 10 BOUNDARY_INVALID
150/160 = 93.75%   if TIMEOUT vanished and nothing else failed
159/160 = 99.375%  is the discrete 160-run 99% gate
```

TIMEOUT audit: last-50 speed ≈ 0 and PR5 projection fraction = 1.0. Horizon
is not the bottleneck. Guides command a straight line through the crowd;
PR5 deletes that direction.

## Seed contract

| Set | Seeds | Runs (2 env × 4 shapes) | Role |
| --- | ---: | ---: | --- |
| SPENT_REGRESSION | 100–119 | 160 | Gate A/B only. Not a holdout. |
| Development | 300–349 | 400 | Tune routing / cascade. Ablation allowed. |
| Intermediate | 350–369 | 160 | Overfit check. Looking then editing converts it to development. |
| Final holdout | 400–449 | 400 | One shot after SHA / configs / success definition are frozen. |

## Engineering closure (final holdout)

Recommended 400-run gate, not 160:

- overall scientific success ≥ **396/400 = 99.0%**
- each shape ≥ **98%**
- boundary valid ≥ **99.5%**
- TIMEOUT ≤ **0.5%**
- safety violation = 0
- `SAFETY_INFEASIBLE` = 0
- execution crash = 0
- truth-leakage tests PASS
- Linux / Windows / static analysis PASS
- success-run RMSE must not worsen vs the frozen baseline

396/400 is an **observed** rate. It is not a Clopper–Pearson claim that
`p_success > 0.99`. That language needs 400/400 (lower 95% bound ≈ 99.25%)
and still does not generalize beyond this test distribution.

## Ablation (Gate D)

Compare on the same development seeds:

1. Frozen ABCG-v2 (`motion.route_aware: false`, `boundary.cascade: false`)
2. Route-aware only
3. Robust-boundary only
4. Route-aware + robust-boundary

## Spent-regression gates (100–119)

- Gate A: TIMEOUT 40 → ≤ 1
- Gate B: BOUNDARY_INVALID 10 → ≤ 1, especially ellipse seeds 104, 105, 114

Do not retune after seeing 400–449. If the frozen holdout misses 396/400,
report the number.

## Commands

Spent regression (labeled, not holdout):

```bash
python scripts/run_step1_known_boundary.py \
  --manifest configs/step1_known_boundary/benchmark_manifest.yaml \
  --seeds 100:119 \
  --output runs/step1_v2_spent_regression \
  --headless
```

Development:

```bash
python scripts/run_step1_known_boundary.py \
  --manifest configs/step1_known_boundary/v2_protocol_manifest.yaml \
  --seeds 300:349 \
  --output runs/step1_v2_development \
  --headless
```

Disable one v2 piece for ablation:

```yaml
motion:
  route_aware: false
boundary:
  cascade: false
```

`transit_clearance` is a **development** parameter. It is not a new success
threshold and must not be fitted on 100–119 or 400–449.

## Development snapshot (not a freeze)

Dual-ring routing on 300–349 is recorded as **`step1-v2-dev-dual-ring`**:
**362/400 = 90.5%**, boundary **400/400**, TIMEOUT **38**. See
[`reports/step1_known_boundary/STEP1_V2_DEV_DUAL_RING.md`](../reports/step1_known_boundary/STEP1_V2_DEV_DUAL_RING.md).

Spent 100–119 under the same code was 153/160 = 95.6%. That number is **not**
a generalization claim. Later 300–349 runs compare against 362/400.

Do not open 350–369 until development 300–349 is ≥ 396/400 with each shape
≥ 99/100, boundary 400/400, TIMEOUT ≤ 4, and no truth leakage.
