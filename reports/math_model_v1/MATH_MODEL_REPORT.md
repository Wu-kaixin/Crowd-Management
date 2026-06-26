# Mathematical Model Report V1

Prepared for the June 26 supervisor presentation.

## Project Objective

The project is a first feasibility sprint for transferring a robot cargo-guidance / DBACT-style idea into crowd guidance. The implemented question is:

```text
Can a multi-agent positioning rule originally used around a passive cargo object be reused as mobile guider placement around an active crowd?
```

This repository is not a full crowd-management theory implementation. It currently contains a simple microscopic 2D crowd simulator, mobile guiders, DBACT-style group-state estimation and guider placement, baseline comparisons, metrics, and visualizations.

Important implemented/planned distinction:

- The simple microscopic crowd model is implemented.
- The DBACT-transfer guider placement pipeline is implemented.
- Density heatmap visualization and congestion metrics are implemented.
- Density-aware two-exit route-choice control is planned, not implemented.
- The prepared `configs/two_exits.yaml` documents a future scenario, but the current simulator still uses the primary `room.exit`.

## Why This Model Was Selected

The model was selected because it is simple, interpretable, controllable, and suitable for a first transfer test.

- Simple: each pedestrian is a particle with position, velocity, desired speed, radius, compliance, and evacuation state.
- Interpretable: every motion term can be explained as exit attraction, pedestrian repulsion, wall handling, or guider influence.
- Controllable: parameters such as desired speed, repulsion strength, wall margin, guider influence radius, and guider speed are explicit in config files.
- Suitable for transfer testing: it lets the project ask whether the robot DBACT placement idea can run in a crowd simulator before adding richer crowd behavior.
- Avoids premature complexity: no exclusion queue, no hybrid micro-macro model, no detailed psychological model, no CBF controller, no LLM planner, and no real-robot dynamics are claimed.

## Model Assumptions

1. Pedestrians move in a 2D rectangular room.
2. The current implemented evacuation model has one active exit.
3. Pedestrians are represented as circular particles with radius `r_p`.
4. Pedestrians seek the exit while avoiding nearby pedestrians and walls.
5. Guiders do not physically push pedestrians. They add a local directional influence scaled by pedestrian compliance.
6. Guiders are simple mobile agents with first-order motion and max-speed saturation.
7. Density is currently used for visualization and metrics, not for route-choice control.

## A. Current Implemented Simple Microscopic Crowd Model

### A1. Pedestrian State `[Implemented]`

Formula:

```latex
p_i(t)\in\mathbb{R}^2,\quad v_i(t)\in\mathbb{R}^2,\quad c_i\in[0,1]
```

Variables:

- `p_i(t)`: pedestrian position.
- `v_i(t)`: pedestrian velocity.
- `c_i`: compliance with guider influence.

Source:

- `src/crowd_management/types.py:210-219`
- `src/crowd_management/crowd_model.py:59-78`

Behavioral interpretation:

Each pedestrian is an individual microscopic agent. The model stores only the state needed for movement, guidance response, and evacuation measurement.

Why reasonable for first feasibility test:

It supports controlled experiments without introducing unvalidated behavioral detail.

### A2. Desired Exit Direction `[Implemented]`

Formula:

```latex
d_i^{exit}(t)=
\frac{e-p_i(t)}{\|e-p_i(t)\|+\varepsilon}
```

Variables:

- `e`: configured exit center.
- `\varepsilon`: small numerical safeguard in the `unit` helper.

Source:

- `src/crowd_management/crowd_model.py:92-96`
- `src/crowd_management/types.py:58-60`
- `src/crowd_management/types.py:28-35`

Behavioral interpretation:

Each active pedestrian wants to move toward the exit.

Why reasonable:

It creates a clear baseline evacuation behavior before testing guidance.

### A3. Goal Acceleration `[Implemented]`

Formula:

```latex
f_i^{goal}(t)=
\frac{v_i^0d_i^{exit}(t)-v_i(t)}{\tau}
```

Variables:

- `v_i^0`: pedestrian desired speed.
- `\tau`: relaxation time.

Source:

- `src/crowd_management/crowd_model.py:92-96`

Behavioral interpretation:

Pedestrian velocity relaxes toward the desired exit-seeking velocity.

Why reasonable:

It is a standard and explainable social-force-like structure.

### A4. Pedestrian-Pedestrian Repulsion `[Implemented]`

Formula:

```latex
f_i^{rep}(t)=
\sum_{j\in\mathcal{A}(t),j\ne i}
\mathbf{1}_{r_{ij}\le R_{int}}
\left[
A_p\exp\left(\frac{2r_p-r_{ij}}{B_p}\right)
6\max(0,2r_p-r_{ij})
\right]
\frac{p_i-p_j}{r_{ij}}
```

```latex
r_{ij}=\|p_i-p_j\|
```

Variables:

- `\mathcal{A}(t)`: active pedestrians.
- `A_p`: repulsion strength.
- `B_p`: repulsion range.
- `R_int`: interaction range.
- `r_p`: pedestrian radius.

Source:

- `src/crowd_management/crowd_model.py:98-118`

Behavioral interpretation:

Nearby pedestrians push each other apart. The term becomes stronger at short distances and includes an overlap penalty.

Why reasonable:

It prevents unrealistic overlap and creates congestion behavior with few parameters.

### A5. Wall and Boundary Handling `[Implemented]`

Formula:

```latex
f_x^{left}=A_w\frac{m-x_i}{m}\quad\text{if }x_i<m
```

```latex
f_x^{right}=-A_w\frac{x_i-(W-m)}{m}
\quad\text{if }x_i>W-m\text{ and }y_i\notin[y_e-w_e/2,y_e+w_e/2]
```

```latex
f_y^{bottom}=A_w\frac{m-y_i}{m},\quad
f_y^{top}=-A_w\frac{y_i-(H-m)}{m}
```

Evacuation condition:

```latex
s_i(t+\Delta t)=1
\quad\text{if}\quad
x_i(t+\Delta t)\ge W,\quad
y_i(t+\Delta t)\in[y_e-w_e/2,y_e+w_e/2]
```

Source:

- `src/crowd_management/crowd_model.py:120-162`
- `src/crowd_management/types.py:62-77`

Behavioral interpretation:

Walls repel pedestrians and hard clipping prevents escape through closed boundaries. The right boundary is open only at the exit.

Why reasonable:

It gives a stable rectangular-room simulation with a clear evacuation event.

### A6. Full Motion Update `[Implemented]`

Formula:

```latex
F_i(t)=f_i^{goal}(t)+f_i^{rep}(t)+f_i^{wall}(t)+f_i^{guide}(t)+\eta_i(t)
```

```latex
v_i(t+\Delta t)=
\mathrm{sat}_{v_{max}}\left(v_i(t)+\Delta tF_i(t)\right)
```

```latex
p_i(t+\Delta t)=p_i(t)+\Delta tv_i(t+\Delta t)
```

Source:

- `src/crowd_management/crowd_model.py:209-227`
- `src/crowd_management/types.py:38-43`

Behavioral interpretation:

All active pedestrians are updated by explicit Euler integration with speed saturation.

Why reasonable:

It is transparent and reproducible, which is useful for comparing baseline, static, random, and DBACT modes.

## B. Current Implemented DBACT-Transfer / Guider-Based Guidance Logic

### B1. Crowd Center `[Implemented]`

Formula:

```latex
c(t)=
\frac{1}{|\mathcal{A}(t)|}
\sum_{i\in\mathcal{A}(t)}p_i(t)
```

Source:

- `src/crowd_management/dbact_transfer.py:32-42`
- `src/crowd_management/dbact_transfer.py:48-53`

Behavioral interpretation:

The active crowd is represented by its mean position.

Why reasonable:

It provides a simple group-level state analogous to a cargo object center, while still simulating pedestrians individually.

### B2. Crowd Spatial Range `[Implemented]`

Formula:

```latex
R_c(t)=
\max\left(
\mathrm{percentile}_{65}
\{\|p_i(t)-c(t)\|:i\in\mathcal{A}(t)\},
0.6
\right)
```

Source:

- `src/crowd_management/dbact_transfer.py:38-41`
- `src/crowd_management/dbact_transfer.py:55-61`

Behavioral interpretation:

The controller estimates crowd spread from the 65th percentile distance to the center.

Why reasonable:

It is robust to outliers and useful for placing guiders around the active crowd boundary.

### B3. Crowd Target Direction `[Implemented]`

Formula:

```latex
d_c(t)=\frac{e-c(t)}{\|e-c(t)\|+\varepsilon}
```

Source:

- `src/crowd_management/dbact_transfer.py:41`
- `src/crowd_management/dbact_transfer.py:63-64`

Behavioral interpretation:

The group-level objective points from the crowd center to the exit.

Why reasonable:

It is the simplest possible transfer target for a one-exit feasibility test.

### B4. DBACT-Style Guider Target Position `[Implemented]`

Formula:

```latex
q_k^*(t)=
\mathrm{clip}_{room}
\left(
c(t)-\beta R_c(t)d_c(t)+s_k d_c^\perp(t)
\right)
```

```latex
d_c^\perp(t)=(-d_{c,y}(t),d_{c,x}(t))^T
```

```latex
s_k=\left(k-\frac{M-1}{2}\right)\Delta_s
```

Variables:

- `q_k^*(t)`: target position for guider `k`.
- `\beta`: rear distance gain.
- `\Delta_s`: side spacing.
- `M`: number of guiders.

Source:

- `src/crowd_management/dbact_transfer.py:69-95`
- `src/crowd_management/types.py:46-47`

Behavioral interpretation:

Guiders are placed behind the crowd relative to the exit direction and spread laterally around that rear boundary.

Why reasonable:

This is the implemented DBACT transfer: not the full original robot algorithm, but the structural idea of boundary-aware multi-agent placement.

### B5. Guider Motion `[Implemented]`

Formula:

```latex
u_k(t)=
\mathrm{sat}_{u_{max}}
\left(
\frac{q_k^*(t)-q_k(t)}{\Delta t}
\right)
```

```latex
q_k(t+\Delta t)=
\mathrm{clip}_{room}
\left(q_k(t)+\Delta t u_k(t)\right)
```

Source:

- `src/crowd_management/guider_model.py:37-44`

Behavioral interpretation:

Guiders move toward assigned target positions with max-speed saturation.

Why reasonable:

It tests controller geometry without adding robot dynamics.

### B6. Guider Influence on Pedestrians `[Implemented]`

Formula:

```latex
f_i^{guide}(t)=
\sum_{k=1}^{M}
\mathbf{1}_{r_{ik}<R_g}
\gamma c_i
\left(1-\frac{r_{ik}}{R_g}\right)^2
d_k^{guide}(t)
```

```latex
r_{ik}=\|p_i(t)-q_k(t)\|,\quad d_k^{guide}(t)=d_c(t)
```

Source:

- `src/crowd_management/guidance_controller.py:20-33`
- `src/crowd_management/dbact_transfer.py:97-103`
- `src/crowd_management/crowd_model.py:221-222`

Behavioral interpretation:

A guider locally suggests a direction. The influence is strongest near the guider, decays smoothly to zero at the influence radius, and is scaled by pedestrian compliance.

Why reasonable:

It is a minimal way to represent guidance without claiming physical pushing, leader following, or psychology.

## C. Planned Density-Aware Extension for Two-Exit / Bottleneck Scenarios

### C1. Implemented Density-Related Elements `[Partially implemented]`

The project already contains:

- congestion index as average local neighbor count;
- near-collision count as close-pair count;
- histogram-based density heatmaps for visualization.

Formula for implemented congestion metric:

```latex
C(t)=
\frac{1}{|\mathcal{A}(t)|}
\sum_{i\in\mathcal{A}(t)}
\sum_{j\in\mathcal{A}(t),j\ne i}
\mathbf{1}[\|p_i(t)-p_j(t)\|<R_c^{metric}]
```

Formula for implemented heatmap:

```latex
H_{ab}(t)=
\sum_{i\in\mathcal{A}(t)}
\mathbf{1}[p_i(t)\in \mathrm{cell}_{ab}]
```

Source:

- `src/crowd_management/metrics.py:44-54`
- `src/crowd_management/visualization.py:56-75`
- `src/crowd_management/advanced_visualization.py:100-112`

Important limitation:

These density-related computations are not yet used by the guidance controller.

### C2. Planned Continuous Density Field `[Planned]`

Formula:

```latex
\rho(x,t)=
\sum_{i\in\mathcal{A}(t)}
\exp\left(
-\frac{\|x-p_i(t)\|^2}{2\sigma_\rho^2}
\right)
```

Purpose:

Use a smooth density estimate to identify crowded exits, bottlenecks, or approach corridors.

Status:

Not implemented or validated.

### C3. Planned Exit Route-Cost Model `[Planned]`

Formula:

```latex
C_{im}(t)=
\lambda_d\|p_i(t)-e_m\|
+\lambda_\rho \rho_m(t)
+\lambda_q Q_m(t)
```

```latex
a_i(t)=\arg\min_m C_{im}(t)
```

Variables:

- `e_m`: exit `m`.
- `\rho_m(t)`: density around exit `m` or along its path.
- `Q_m(t)`: queue/load proxy.
- `a_i(t)`: assigned exit for pedestrian `i`.

Status:

Planned only. The current parser and simulator do not implement multi-exit assignment.

Why this is the right next step:

The current single-exit scenario gives the guider policy limited opportunity to improve route choice. A two-exit or bottleneck scenario can test whether density-aware guidance can split flow and reduce congestion.

## Evaluation Metrics Currently Implemented

### Evacuation Rate `[Implemented]`

```latex
E(t)=\frac{1}{N}\sum_{i=1}^{N}\mathbf{1}[s_i(t)=1]
```

Source: `src/crowd_management/metrics.py:13-18`

### Mean Active Speed `[Implemented]`

```latex
\bar v(t)=
\frac{1}{|\mathcal{A}(t)|}
\sum_{i\in\mathcal{A}(t)}\|v_i(t)\|
```

Source: `src/crowd_management/metrics.py:21-29`

### Near-Collision Count `[Implemented]`

```latex
N_{near}(t)=
\sum_{i<j,\ i,j\in\mathcal{A}(t)}
\mathbf{1}[\|p_i(t)-p_j(t)\|<d_{near}]
```

Source: `src/crowd_management/metrics.py:32-41`

### Mean Path Length `[Implemented]`

```latex
\bar L=\frac{1}{N}\sum_i\sum_k
\|p_i(t_k)-p_i(t_{k-1})\|
```

Source: `src/crowd_management/metrics.py:78-87`

## Current Experimental Findings

From `reports/guidance_baselines_v1/GUIDANCE_BASELINES_REPORT.md` and related metrics:

| Metric | Baseline | Static | Random | DBACT |
|---|---:|---:|---:|---:|
| Final evacuated | 149 | 150 | 150 | 150 |
| Final evacuation rate | 0.93125 | 0.93750 | 0.93750 | 0.93750 |
| Mean speed | 1.05445 | 1.06463 | 1.05412 | 1.05781 |
| Congestion index | 1.51381 | 1.48335 | 1.60127 | 1.61035 |
| Near-collision count | 246 | 246 | 246 | 246 |
| Full evacuation time | not reached | not reached | not reached | not reached |

Honest summary:

- The simulator and DBACT-transfer pipeline run successfully.
- In the simple single-exit scenario, guided modes are stable.
- DBACT is slightly better than no guidance in final evacuation count and evacuation rate.
- DBACT does not yet clearly outperform static guidance.
- Static guidance has better mean speed and congestion in the reported simple scenario.
- Therefore the current result is proof of execution and transfer feasibility, not proof of method superiority.

## Limitations

1. Current experiments use a simple one-exit scenario.
2. Density is not yet used in the controller.
3. The two-exit configuration is prepared but not active route-choice logic.
4. Guider influence is only local directional acceleration, not leader following or behavioral decision-making.
5. No exclusion queue, hybrid micro-macro model, psychological model, CBF, LLM planning, or hardware experiment is implemented.
6. The current DBACT transfer uses the structural idea of group boundary placement, not the full original robot-control stack.

## Next Steps

1. Implement a true two-exit or bottleneck scenario in the simulator.
2. Add density-aware exit cost and route assignment.
3. Reuse the implemented DBACT-style guider placement on exit-assigned subgroups.
4. Compare no guidance, static guidance, random guidance, current DBACT, and density-aware DBACT.
5. Evaluate whether guidance improves flow splitting, congestion, near-collision count, and evacuation rate.

## Recommended Supervisor Message

The current version proves that the simulator, guider model, DBACT-transfer controller, metrics, and visualization pipeline work end to end. It does not yet prove that DBACT-style guidance is superior. The next mathematically meaningful experiment is a two-exit or bottleneck setup where density-aware guidance can influence route choice and flow splitting.
