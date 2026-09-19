# Step 1 TIMEOUT retrospective audit

Baseline: `step1-known-boundary-freeze` @ `46ad61309e61353d262f54813062d51999ccb13e`.
Holdout seeds 100–119 are **opened / spent**. This note only reads existing artifacts.
No controller gains, `max_steps`, RMSE tolerance, or safety thresholds were changed.
This audit does **not** claim the algorithm is validated. It classifies why 40 holdout
runs hit the frozen 400-step cap after a valid boundary/deployment already existed.

## Headline

- holdout n = 160
- boundary valid = 150/160
- scientific success = 110/160 = 68.8%
- TIMEOUT = 40 (all `stop_reason=maximum_steps_reached`, horizon = 400)
- RMSE tolerance (frozen) = 0.03

The bottleneck is **post-boundary motion**, not crowd-boundary estimation.
Deployment targets are static in these traces (`max_target_displacement = 0`).
Guides fail to reach those fixed targets before the frozen horizon.

## TIMEOUT class counts

| class | n | meaning |
| --- | ---: | --- |
| horizon_sensitive | 0 | last-50 still moving; linear extra steps ≤ 400 |
| slow_but_improving | 0 | still moving, but would need several extra horizons |
| near_miss_safety_pin | 4 | stalled on crowd-distance pin with final RMSE ≤ 0.15 |
| structural_safety_pin | 36 | last-50 speed ≈ 0, 100% PR5 projection, crowd-distance pin |
| structural_plateau | 0 | late RMSE almost flat, far from tolerance, not a clean pin |
| structural_other | 0 | TIMEOUT without a clean horizon or pin signature |

## TIMEOUT vs scientific-success means

| metric | TIMEOUT | CONVERGED |
| --- | ---: | ---: |
| n | 40 | 110 |
| initial RMSE | 5.957 | 5.521 |
| final RMSE | 1.092 | 0.004 |
| last-50 RMSE drop | 0.004 | 1.057 |
| last-50 mean speed | 0.0005 | 0.1143 |
| last-50 projected frac | 1.000 | 0.843 |
| episode projected frac | 0.961 | 0.586 |
| velocity sat frac | 0.102 | 0.359 |
| initial assignment mean | 5.649 | 5.180 |
| initial assignment max | 8.839 | 8.117 |
| final assignment max | 3.485 | 0.012 |
| assignment path sum | 59.544 | 53.618 |
| deployment length L | 25.193 | 24.613 |
| coverage ratio | 0.880 | 0.975 |
| active guides | 10.55 | 10.35 |
| crowd span | 3.785 | 3.634 |
| max target displacement | 0.000 | 0.000 |
| time-to-50% RMSE | 36.3 | 32.1 |
| reached 90% RMSE drop | 4/40 | 110/110 |
| time-to-90% (when reached) | 75.0 | 68.3 |

Linear extra-step estimates are omitted: 0/40 TIMEOUT rows have a
finite last-50 slope with residual motion. The rest are stalled, so extra-step arithmetic
is not a scientific forecast.

## TIMEOUT by shape / environment

- **circle**: 3 TIMEOUT; final RMSE mean=1.755; last-50 speed=0.0000; last-50 proj=1.000; assignment max=9.182; coverage=0.907
- **concave**: 18 TIMEOUT; final RMSE mean=0.862; last-50 speed=0.0008; last-50 proj=1.000; assignment max=8.577; coverage=0.859
- **ellipse**: 8 TIMEOUT; final RMSE mean=1.405; last-50 speed=0.0000; last-50 proj=1.000; assignment max=8.340; coverage=0.899
- **irregular**: 11 TIMEOUT; final RMSE mean=1.060; last-50 speed=0.0003; last-50 proj=1.000; assignment max=9.536; coverage=0.893

- **rectangle**: 23 TIMEOUT; final RMSE=1.155; last-50 speed=0.0006
- **square**: 17 TIMEOUT; final RMSE=1.007; last-50 speed=0.0002

## Interpretation (no retuning)

Two TIMEOUT mechanisms were distinguished *without* raising `max_steps`:

1. **Insufficient horizon**: last-50 RMSE still falling *and* last-50 applied speed
   remains material. Extra frozen-horizon arithmetic would be a plausible next test
   only on a *new* development seed set.
2. **Structural controller limitation**: last-50 applied speed collapses to ~0 while
   PR5 projects almost every step and `min` guide–crowd distance sits on 0.85 m.
   Extra `max_steps` would only record a longer stall.

Holdout TIMEOUT is **(2)**. Converged runs finish in ~100 steps at RMSE ~0.004.
TIMEOUT runs share a similar first-half RMSE drop (time-to-50% ≈ 36 vs 32), then
freeze: last-50 speed is numerically zero, last-50 projection fraction is 1.0, and
final assignment error stays O(1) m. Velocity saturation is *lower* on TIMEOUT than
on success, so guides are not slamming `v_max`; the safety filter is cancelling the
nominal command.

Assignment path length, active-guide count, deployment perimeter `L`, and crowd span
are close between TIMEOUT and success. They are not the discriminator. Coverage is
slightly lower on TIMEOUT, but the late-window kinematics are the clean signature.

Concave is the largest TIMEOUT slice (18/40), consistent with guides being unable to
slide around a concave envelope while remaining outside the 0.85 m crowd halfspace.
The four `near_miss_safety_pin` rows already reached 90% RMSE drop (final RMSE
0.08–0.12) and then sat on the pin. That is still a structural stall, not a missing
100 extra steps.

Do **not** raise `max_steps` on this baseline. Seeds 100–119 stay a spent holdout.
Any Step 1 v2 work needs new development seeds and a new untouched holdout
(for example 200–219).

## TIMEOUT roster

| env | shape | seed | class | init RMSE | final RMSE | last50 drop | last50 speed | last50 proj | assign max | final assign max | crowd pin |
| --- | --- | ---: | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| rectangle | circle | 114 | structural_safety_pin | 5.844 | 1.640 | 0.000 | 0.0000 | 1.000 | 10.599 | 5.188 | True |
| rectangle | circle | 119 | structural_safety_pin | 6.585 | 1.638 | 0.000 | 0.0000 | 1.000 | 9.101 | 5.179 | True |
| square | circle | 114 | structural_safety_pin | 5.333 | 1.988 | 0.000 | 0.0000 | 1.000 | 7.846 | 6.285 | True |
| rectangle | concave | 100 | structural_safety_pin | 6.272 | 1.401 | 0.000 | 0.0000 | 1.000 | 8.177 | 4.429 | True |
| rectangle | concave | 104 | structural_safety_pin | 5.188 | 0.806 | 0.000 | 0.0000 | 1.000 | 9.002 | 2.650 | True |
| rectangle | concave | 108 | structural_safety_pin | 6.158 | 1.338 | 0.000 | 0.0000 | 1.000 | 7.897 | 4.438 | True |
| rectangle | concave | 110 | structural_safety_pin | 7.226 | 1.332 | -0.000 | 0.0000 | 1.000 | 10.510 | 4.203 | True |
| rectangle | concave | 112 | near_miss_safety_pin | 7.561 | 0.124 | -0.000 | 0.0000 | 1.000 | 10.231 | 0.269 | True |
| rectangle | concave | 113 | structural_safety_pin | 5.661 | 0.845 | 0.000 | 0.0000 | 1.000 | 9.284 | 2.801 | True |
| rectangle | concave | 114 | structural_safety_pin | 5.789 | 0.737 | 0.146 | 0.0149 | 1.000 | 9.909 | 2.331 | True |
| rectangle | concave | 115 | near_miss_safety_pin | 6.789 | 0.080 | 0.000 | 0.0000 | 1.000 | 10.872 | 0.176 | True |
| rectangle | concave | 116 | structural_safety_pin | 5.377 | 0.795 | 0.000 | 0.0000 | 1.000 | 7.967 | 2.635 | True |
| rectangle | concave | 117 | structural_safety_pin | 5.745 | 1.120 | 0.000 | 0.0000 | 1.000 | 9.536 | 3.691 | True |
| rectangle | concave | 119 | structural_safety_pin | 6.483 | 1.791 | 0.000 | 0.0000 | 1.000 | 9.109 | 5.665 | True |
| square | concave | 104 | structural_safety_pin | 4.863 | 0.806 | 0.000 | 0.0000 | 1.000 | 7.656 | 2.650 | True |
| square | concave | 107 | structural_safety_pin | 5.016 | 0.910 | 0.000 | 0.0000 | 1.000 | 7.274 | 3.020 | True |
| square | concave | 109 | structural_safety_pin | 5.941 | 1.019 | 0.000 | 0.0000 | 1.000 | 7.944 | 3.222 | True |
| square | concave | 112 | near_miss_safety_pin | 5.495 | 0.124 | 0.000 | 0.0000 | 1.000 | 7.592 | 0.269 | True |
| square | concave | 113 | structural_safety_pin | 4.466 | 1.308 | 0.000 | 0.0000 | 1.000 | 5.977 | 4.334 | True |
| square | concave | 114 | structural_safety_pin | 5.690 | 0.893 | 0.000 | 0.0000 | 1.000 | 7.837 | 2.822 | True |
| square | concave | 115 | near_miss_safety_pin | 5.837 | 0.080 | 0.000 | 0.0000 | 1.000 | 7.615 | 0.176 | True |
| rectangle | ellipse | 100 | structural_safety_pin | 6.435 | 1.446 | 0.000 | 0.0000 | 1.000 | 11.075 | 4.795 | True |
| rectangle | ellipse | 102 | structural_safety_pin | 6.093 | 1.158 | 0.000 | 0.0000 | 1.000 | 8.228 | 3.839 | True |
| rectangle | ellipse | 103 | structural_safety_pin | 6.512 | 1.655 | 0.000 | 0.0000 | 1.000 | 8.142 | 5.235 | True |
| rectangle | ellipse | 118 | structural_safety_pin | 5.502 | 1.620 | 0.000 | 0.0000 | 1.000 | 8.565 | 5.123 | True |
| square | ellipse | 100 | structural_safety_pin | 5.192 | 1.534 | 0.000 | 0.0000 | 1.000 | 8.334 | 5.089 | True |
| square | ellipse | 111 | structural_safety_pin | 5.492 | 1.572 | 0.000 | 0.0000 | 1.000 | 6.978 | 4.971 | True |
| square | ellipse | 115 | structural_safety_pin | 5.765 | 0.784 | 0.000 | 0.0000 | 1.000 | 7.978 | 2.474 | True |
| square | ellipse | 119 | structural_safety_pin | 4.868 | 1.471 | 0.000 | 0.0000 | 1.000 | 7.423 | 4.651 | True |
| rectangle | irregular | 100 | structural_safety_pin | 6.886 | 1.236 | -0.000 | 0.0000 | 1.000 | 10.705 | 3.278 | True |
| rectangle | irregular | 102 | structural_safety_pin | 6.144 | 0.792 | 0.000 | 0.0000 | 1.000 | 8.307 | 2.628 | True |
| rectangle | irregular | 103 | structural_safety_pin | 6.350 | 1.050 | 0.000 | 0.0000 | 1.000 | 8.971 | 3.483 | True |
| rectangle | irregular | 104 | structural_safety_pin | 6.109 | 1.653 | 0.000 | 0.0000 | 1.000 | 9.674 | 4.465 | True |
| rectangle | irregular | 109 | structural_safety_pin | 7.503 | 0.882 | 0.000 | 0.0000 | 1.000 | 11.043 | 2.921 | True |
| rectangle | irregular | 111 | structural_safety_pin | 7.028 | 1.415 | 0.000 | 0.0000 | 1.000 | 11.738 | 4.693 | True |
| square | irregular | 100 | structural_safety_pin | 5.184 | 0.994 | 0.000 | 0.0000 | 1.000 | 8.776 | 3.278 | True |
| square | irregular | 102 | structural_safety_pin | 5.951 | 0.792 | 0.000 | 0.0000 | 1.000 | 7.244 | 2.628 | True |
| square | irregular | 104 | structural_safety_pin | 5.553 | 0.960 | -0.000 | 0.0036 | 1.000 | 9.264 | 3.182 | True |
| square | irregular | 109 | structural_safety_pin | 6.171 | 1.004 | 0.000 | 0.0000 | 1.000 | 9.068 | 3.331 | True |
| square | irregular | 115 | structural_safety_pin | 6.224 | 0.877 | 0.000 | 0.0000 | 1.000 | 10.110 | 2.908 | True |
