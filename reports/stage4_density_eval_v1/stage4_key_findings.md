# Stage 4 Key Findings

- Stage 4 evaluated `9` modes across `5` seeds.
- Fair baselines were included so secondary-exit access is not exclusive to `density_dbact`.
- Composite score is heuristic and should be read together with congestion and exit-balance metrics.

## Aggregate Snapshot

| mode | final_evacuation_rate_mean | congestion_index_mean | cumulative_congestion_mean | exit_1_usage_ratio_mean | exit_imbalance_mean | composite_score_mean |
| --- | --- | --- | --- | --- | --- | --- |
| baseline | 0.9988 | 2.2051 | 85.4759 | 0.0000 | 1.0000 | 0.3487 |
| static | 0.9988 | 2.2001 | 84.5981 | 0.0000 | 1.0000 | 0.3537 |
| dbact | 1.0000 | 2.4917 | 92.2167 | 0.0000 | 1.0000 | 0.2719 |
| nearest_exit | 1.0000 | 1.7827 | 67.7229 | 0.1575 | 0.6850 | 0.5654 |
| balanced_exit_static | 0.9994 | 1.4516 | 53.4892 | 0.4997 | 0.0256 | 0.8177 |
| density_only | 0.9994 | 1.1975 | 41.3473 | 0.4891 | 0.0231 | 0.9170 |
| exit_pressure_only | 0.9694 | 1.5653 | 62.6891 | 0.6647 | 0.3295 | 0.6647 |
| split_flow_only | 0.9994 | 1.4516 | 53.4892 | 0.4997 | 0.0256 | 0.8177 |
| density_dbact | 0.9925 | 1.5523 | 62.1684 | 0.6883 | 0.3766 | 0.6830 |
