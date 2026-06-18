# Stage 4 Key Findings

- Stage 4 evaluated `9` modes across `10` seeds.
- Fair baselines were included so secondary-exit access is not exclusive to `density_dbact`.
- Composite score is heuristic and should be read together with congestion and exit-balance metrics.

## Aggregate Snapshot

| mode | final_evacuation_rate_mean | congestion_index_mean | cumulative_congestion_mean | exit_1_usage_ratio_mean | exit_imbalance_mean | composite_score_mean |
| --- | --- | --- | --- | --- | --- | --- |
| baseline | 0.9994 | 2.2056 | 85.4368 | 0.0000 | 1.0000 | 0.3592 |
| static | 0.9994 | 2.2033 | 84.5823 | 0.0000 | 1.0000 | 0.3635 |
| dbact | 1.0000 | 2.4961 | 92.3552 | 0.0000 | 1.0000 | 0.2819 |
| nearest_exit | 1.0000 | 1.8076 | 68.0892 | 0.1559 | 0.6881 | 0.5650 |
| balanced_exit_static | 0.9997 | 1.4810 | 53.2548 | 0.5002 | 0.0222 | 0.8177 |
| density_only | 0.9997 | 1.1949 | 41.6274 | 0.4889 | 0.0266 | 0.9156 |
| exit_pressure_only | 0.9722 | 1.5553 | 62.2892 | 0.6686 | 0.3372 | 0.6741 |
| split_flow_only | 0.9997 | 1.4810 | 53.2548 | 0.5002 | 0.0222 | 0.8177 |
| density_dbact | 0.9928 | 1.5474 | 61.9751 | 0.6912 | 0.3824 | 0.6883 |
