# Step 1 known-boundary results

The environment boundary is known. The crowd boundary is not known.
JuPedSim spawn geometry is evaluator/simulator-only and is not exposed to ABCG.

This report distinguishes **execution success** (pipeline completed without crash),
**scientific success** (valid boundary, deployment, resources, plan, assignment,
convergence, and sampled safety), and **failure** (kept in every denominator).

## All records

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

## Environment: rectangle

- n: 80
- execution success: 0.938
- scientific success: 52/80 = 0.650
- boundary valid: 75/80 = 0.938
- deployment valid: 0.938
- convergence: 52/80 = 0.650
- sampled safety: 0.938
- mean coverage: 0.8940
- mean tracking RMSE (reported rows): 0.3571
- failures (kept in denominator): BOUNDARY_INVALID=5, TIMEOUT=23

## Environment: square

- n: 80
- execution success: 0.938
- scientific success: 58/80 = 0.725
- boundary valid: 75/80 = 0.938
- deployment valid: 0.938
- convergence: 58/80 = 0.725
- sampled safety: 0.938
- mean coverage: 0.9027
- mean tracking RMSE (reported rows): 0.2316
- failures (kept in denominator): BOUNDARY_INVALID=5, TIMEOUT=17

## Crowd shape: circle

- n: 40
- execution success: 0.950
- scientific success: 35/40 = 0.875
- boundary valid: 38/40 = 0.950
- deployment valid: 0.950
- convergence: 35/40 = 0.875
- sampled safety: 0.950
- mean coverage: 0.9478
- mean tracking RMSE (reported rows): 0.1416
- failures (kept in denominator): BOUNDARY_INVALID=2, TIMEOUT=3

## Crowd shape: concave

- n: 40
- execution success: 0.950
- scientific success: 20/40 = 0.500
- boundary valid: 38/40 = 0.950
- deployment valid: 0.950
- convergence: 20/40 = 0.500
- sampled safety: 0.950
- mean coverage: 0.8474
- mean tracking RMSE (reported rows): 0.4110
- failures (kept in denominator): BOUNDARY_INVALID=2, TIMEOUT=18

## Crowd shape: ellipse

- n: 40
- execution success: 0.850
- scientific success: 26/40 = 0.650
- boundary valid: 34/40 = 0.850
- deployment valid: 0.850
- convergence: 26/40 = 0.650
- sampled safety: 0.850
- mean coverage: 0.8362
- mean tracking RMSE (reported rows): 0.3335
- failures (kept in denominator): BOUNDARY_INVALID=6, TIMEOUT=8

## Crowd shape: irregular

- n: 40
- execution success: 1.000
- scientific success: 29/40 = 0.725
- boundary valid: 40/40 = 1.000
- deployment valid: 1.000
- convergence: 29/40 = 0.725
- sampled safety: 1.000
- mean coverage: 0.9619
- mean tracking RMSE (reported rows): 0.2955
- failures (kept in denominator): TIMEOUT=11

## Heterogeneous

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
