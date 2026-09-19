# Step 1 v2 development snapshot: dual-ring routing

Label: **`step1-v2-dev-dual-ring`**  
This is a **development comparison baseline**, not a freeze and not a holdout claim.

Branch: `STEP1-Research-Extension`  
Protocol: [`docs/STEP1_V2_PROTOCOL.md`](../../docs/STEP1_V2_PROTOCOL.md)  
Raw summaries:

- Development 300–349: [`v2_dev_dual_ring/development_300_349_summary.json`](v2_dev_dual_ring/development_300_349_summary.json)
- Spent regression 100–119: [`v2_dev_dual_ring/spent_100_119_summary.json`](v2_dev_dual_ring/spent_100_119_summary.json)

Do **not** treat 100–119 as holdout. Do **not** open 350–369 or 400–449 from this snapshot.

## Headline

| Matrix | Scientific success | Boundary valid | TIMEOUT | BOUNDARY_INVALID |
| --- | ---: | ---: | ---: | ---: |
| Frozen Core holdout 100–119 (`46ad613`) | 110/160 = 68.8% | 150/160 | 40 | 10 |
| Spent regression 100–119 (dual-ring v2) | 153/160 = 95.6% | 160/160 | 7 | 0 |
| **Development 300–349 (dual-ring v2)** | **362/400 = 90.5%** | **400/400** | **38** | **0** |

Spent 95.6% did **not** generalize to development 300–349. That is the point of the development set.

PR5 distances, `max_steps`, RMSE tolerance, and assignment were not changed.

## Development 300–349 by shape

| Shape | Current | Next development closure target |
| --- | ---: | ---: |
| circle | 99/100 | ≥ 99/100 |
| ellipse | 98/100 | ≥ 99/100 |
| concave | 90/100 | ≥ 99/100 |
| irregular | 75/100 | ≥ 99/100 |
| **Overall** | **362/400** | **≥ 396/400** |

Gate B (boundary) is provisionally closed on this snapshot: 400/400 valid. All 38 remaining failures are TIMEOUT in the motion layer. Irregular accounts for 25/38.

## What this snapshot contains

Control chain:

```text
z_i → route planner → w_i → sat(k_p (w_i − p_i)) → PR5 → u_i
```

Route modes: `DIRECT` / `APPROACH_RING` / `FOLLOW_BOUNDARY` (outer transit) /
`FOLLOW_DEPLOYMENT` (inner deployment ring) / `FINAL_APPROACH`.

Estimator cascade: alpha → radial_fallback → convex_fallback, without lowering
coverage thresholds. Method labels are honest.

## Known remaining failure mode

Last-step diagnostics on the 38 TIMEOUT rows are typically `FINAL_APPROACH` with
high PR5 projection. The dual-ring path can reach the neighborhood of the
target; the suspect is **eligibility for `FINAL_APPROACH`**, not another ring.

Later improvements on 300–349 must be compared with **362/400**, not with spent 95.6%.
