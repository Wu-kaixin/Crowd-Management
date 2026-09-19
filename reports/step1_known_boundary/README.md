# Step 1 known-boundary results

The environment boundary is known. The crowd boundary is not known.
JuPedSim spawn geometry is evaluator/simulator-only and is not exposed to ABCG.

This report distinguishes **execution success** (pipeline completed without crash),
**scientific success** (valid boundary, deployment, resources, plan, assignment,
convergence, and sampled safety), and **failure** (kept in every denominator).

## All records

- n: 40
- execution success: 0.850
- scientific success: 0.800
- boundary valid: 0.850
- deployment valid: 0.850
- convergence: 0.800
- failures (kept in denominator): BOUNDARY_INVALID=6, TIMEOUT=2

## Environment: rectangle

- n: 20
- execution success: 0.850
- scientific success: 0.800
- boundary valid: 0.850
- deployment valid: 0.850
- convergence: 0.800
- failures (kept in denominator): BOUNDARY_INVALID=3, TIMEOUT=1

## Environment: square

- n: 20
- execution success: 0.850
- scientific success: 0.800
- boundary valid: 0.850
- deployment valid: 0.850
- convergence: 0.800
- failures (kept in denominator): BOUNDARY_INVALID=3, TIMEOUT=1

## Crowd shape: circle

- n: 10
- execution success: 0.600
- scientific success: 0.600
- boundary valid: 0.600
- deployment valid: 0.600
- convergence: 0.600
- failures (kept in denominator): BOUNDARY_INVALID=4

## Crowd shape: concave

- n: 10
- execution success: 1.000
- scientific success: 1.000
- boundary valid: 1.000
- deployment valid: 1.000
- convergence: 1.000
- failures (kept in denominator): none

## Crowd shape: ellipse

- n: 10
- execution success: 0.800
- scientific success: 0.800
- boundary valid: 0.800
- deployment valid: 0.800
- convergence: 0.800
- failures (kept in denominator): BOUNDARY_INVALID=2

## Crowd shape: irregular

- n: 10
- execution success: 1.000
- scientific success: 0.800
- boundary valid: 1.000
- deployment valid: 1.000
- convergence: 0.800
- failures (kept in denominator): TIMEOUT=2

## Heterogeneous

- n: 40
- execution success: 0.850
- scientific success: 0.800
- boundary valid: 0.850
- deployment valid: 0.850
- convergence: 0.800
- failures (kept in denominator): BOUNDARY_INVALID=6, TIMEOUT=2

## Split: development

- n: 40
- execution success: 0.850
- scientific success: 0.800
- boundary valid: 0.850
- deployment valid: 0.850
- convergence: 0.800
- failures (kept in denominator): BOUNDARY_INVALID=6, TIMEOUT=2

## Homogeneous vs heterogeneous ablation

Paired `square_circle` vs `homogeneous_square_circle`, seeds 0-4, same controller parameters.

- seeds 0, 2, 3: both CONVERGED with identical tracking RMSE to 1e-15
- seeds 1, 4: both BOUNDARY_INVALID (`alpha_resampled_observation_coverage_below_threshold` class)
- No measurable heterogeneity effect on this static Step 1 controller. `desired_speed` and `time_gap` remain metadata; demand/radius are observed but did not change ABCG outputs here.

Holdout seeds 100-119 were not used for tuning and have not been run yet.
