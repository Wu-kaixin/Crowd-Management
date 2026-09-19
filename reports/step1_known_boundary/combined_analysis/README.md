# Step 1 known-boundary results

The environment boundary is known. The crowd boundary is not known.
JuPedSim spawn geometry is evaluator/simulator-only and is not exposed to ABCG.

This report distinguishes **execution success** (pipeline completed without crash),
**scientific success** (valid boundary, deployment, resources, plan, assignment,
convergence, and sampled safety), and **failure** (kept in every denominator).

## All records

- n: 200
- execution success: 0.920
- scientific success: 142/200 = 0.710
- boundary valid: 184/200 = 0.920
- deployment valid: 0.920
- convergence: 142/200 = 0.710
- sampled safety: 0.920
- mean coverage: 0.9121
- mean tracking RMSE (reported rows): 0.2424
- failures (kept in denominator): BOUNDARY_INVALID=16, TIMEOUT=42

## Environment: rectangle

- n: 100
- execution success: 0.920
- scientific success: 68/100 = 0.680
- boundary valid: 92/100 = 0.920
- deployment valid: 0.920
- convergence: 68/100 = 0.680
- sampled safety: 0.920
- mean coverage: 0.9086
- mean tracking RMSE (reported rows): 0.2935
- failures (kept in denominator): BOUNDARY_INVALID=8, TIMEOUT=24

## Environment: square

- n: 100
- execution success: 0.920
- scientific success: 74/100 = 0.740
- boundary valid: 92/100 = 0.920
- deployment valid: 0.920
- convergence: 74/100 = 0.740
- sampled safety: 0.920
- mean coverage: 0.9155
- mean tracking RMSE (reported rows): 0.1912
- failures (kept in denominator): BOUNDARY_INVALID=8, TIMEOUT=18

## Crowd shape: circle

- n: 50
- execution success: 0.880
- scientific success: 41/50 = 0.820
- boundary valid: 44/50 = 0.880
- deployment valid: 0.880
- convergence: 41/50 = 0.820
- sampled safety: 0.880
- mean coverage: 0.9582
- mean tracking RMSE (reported rows): 0.1229
- failures (kept in denominator): BOUNDARY_INVALID=6, TIMEOUT=3

## Crowd shape: concave

- n: 50
- execution success: 0.960
- scientific success: 30/50 = 0.600
- boundary valid: 48/50 = 0.960
- deployment valid: 0.960
- convergence: 30/50 = 0.600
- sampled safety: 0.960
- mean coverage: 0.8589
- mean tracking RMSE (reported rows): 0.3266
- failures (kept in denominator): BOUNDARY_INVALID=2, TIMEOUT=18

## Crowd shape: ellipse

- n: 50
- execution success: 0.840
- scientific success: 34/50 = 0.680
- boundary valid: 42/50 = 0.840
- deployment valid: 0.840
- convergence: 34/50 = 0.680
- sampled safety: 0.840
- mean coverage: 0.8659
- mean tracking RMSE (reported rows): 0.2705
- failures (kept in denominator): BOUNDARY_INVALID=8, TIMEOUT=8

## Crowd shape: irregular

- n: 50
- execution success: 1.000
- scientific success: 37/50 = 0.740
- boundary valid: 50/50 = 1.000
- deployment valid: 1.000
- convergence: 37/50 = 0.740
- sampled safety: 1.000
- mean coverage: 0.9653
- mean tracking RMSE (reported rows): 0.2431
- failures (kept in denominator): TIMEOUT=13

## Heterogeneous

- n: 200
- execution success: 0.920
- scientific success: 142/200 = 0.710
- boundary valid: 184/200 = 0.920
- deployment valid: 0.920
- convergence: 142/200 = 0.710
- sampled safety: 0.920
- mean coverage: 0.9121
- mean tracking RMSE (reported rows): 0.2424
- failures (kept in denominator): BOUNDARY_INVALID=16, TIMEOUT=42

## Split: development

- n: 40
- execution success: 0.850
- scientific success: 32/40 = 0.800
- boundary valid: 34/40 = 0.850
- deployment valid: 0.850
- convergence: 32/40 = 0.800
- sampled safety: 0.850
- mean coverage: 0.9670
- mean tracking RMSE (reported rows): 0.0129
- failures (kept in denominator): BOUNDARY_INVALID=6, TIMEOUT=2

## Split: holdout

- n: 160
- execution success: 0.938
- scientific success: 110/160 = 0.688
- boundary valid: 150/160 = 0.938
- deployment valid: 0.938
- convergence: 110/160 = 0.688
- sampled safety: 0.938
- mean coverage: 0.8984
- mean tracking RMSE (reported rows): 0.2944
- failures (kept in denominator): BOUNDARY_INVALID=10, TIMEOUT=40
