# Formula Inventory

This inventory extracts the mathematical logic currently present in the repository. Labels are strict:

- `[Implemented]`: directly supported by current code.
- `[Partially implemented]`: related code exists, but the full mathematical idea is not implemented as control logic.
- `[Planned]`: proposed next step, not implemented or validated.

## A. Current Implemented Simple Microscopic Crowd Model

### A1. Pedestrian State

Label: `[Implemented]`

Formula:

```latex
p_i(t) \in \mathbb{R}^2,\quad v_i(t) \in \mathbb{R}^2,\quad
s_i \in \{0,1\},\quad c_i \in [0,1]
```

Variables:

- `p_i(t)`: position of pedestrian `i`.
- `v_i(t)`: velocity of pedestrian `i`.
- `s_i`: evacuated state; true after crossing the exit.
- `c_i`: compliance with guider influence.

Source:

- `src/crowd_management/types.py:210-219`
- `src/crowd_management/crowd_model.py:59-78`

Interpretation:

Each pedestrian is a simple particle with position, velocity, desired speed, personal radius, compliance, and evacuation state.

Why reasonable for first feasibility test:

It is the minimum state needed to test whether mobile guider placement can influence a moving crowd.

### A2. Initialization Distribution

Label: `[Implemented]`

Formula:

```latex
p_i(0) \sim \mathcal{N}(\mu_{spawn}, \Sigma_{spawn}),\quad
v_i(0)=0
```

```latex
v_i^0 = \max(0.3,\ \mathcal{N}(\mu_v,\sigma_v^2)),\quad
c_i = \mathrm{clip}(\mathcal{N}(\mu_c,\sigma_c^2),0,1)
```

Source:

- `src/crowd_management/crowd_model.py:63-77`
- `configs/simple_room.yaml`

Interpretation:

The initial crowd is a noisy cluster, with heterogeneous walking speeds and compliance.

Why reasonable:

It creates repeatable but non-identical pedestrians without adding psychological or demographic complexity.

### A3. Exit Direction

Label: `[Implemented]`

Formula:

```latex
d_i^{exit}(t)=
\frac{e-p_i(t)}{\|e-p_i(t)\|+\varepsilon}
```

Variables:

- `e`: configured exit center, stored outside the right wall as `[room.width + exit_depth, exit_center_y]`.
- `\varepsilon`: numerical fallback used by `unit`.

Source:

- `src/crowd_management/crowd_model.py:92-96`
- `src/crowd_management/types.py:58-60`
- `src/crowd_management/types.py:28-35`

Interpretation:

Each active pedestrian tries to move toward the single configured exit.

Why reasonable:

The one-exit setup isolates whether DBACT-style guider placement runs before adding route choice.

### A4. Goal Acceleration / Relaxation

Label: `[Implemented]`

Formula:

```latex
f_i^{goal}(t)=
\frac{v_i^0 d_i^{exit}(t)-v_i(t)}{\tau}
```

Variables:

- `v_i^0`: individual desired speed.
- `\tau`: relaxation time.

Source:

- `src/crowd_management/crowd_model.py:92-96`
- `src/crowd_management/types.py:181`

Interpretation:

Velocity relaxes toward the desired velocity pointing at the exit.

Why reasonable:

This is an interpretable social-force-like term with direct control over walking smoothness.

### A5. Pedestrian-Pedestrian Repulsion

Label: `[Implemented]`

Formula:

```latex
f_i^{rep}(t)=
\sum_{j\in \mathcal{A}(t), j\ne i}
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

- `\mathcal{A}(t)`: active, not evacuated pedestrians.
- `R_int`: interaction range.
- `A_p`: repulsion strength.
- `B_p`: repulsion range.
- `r_p`: pedestrian radius.

Source:

- `src/crowd_management/crowd_model.py:98-118`
- `src/crowd_management/types.py:181-184`

Interpretation:

Nearby pedestrians repel each other. The force increases when pedestrians are close, with an extra linear overlap penalty.

Why reasonable:

It prevents unrealistic merging and gives crowd congestion behavior while staying simple.

### A6. Wall Repulsion

Label: `[Implemented]`

Formula:

```latex
f_i^{wall}(t)=
\begin{bmatrix}
f_x^{wall}\\
f_y^{wall}
\end{bmatrix}
```

For margin `m` and wall strength `A_w`:

```latex
f_x^{left}=A_w\frac{m-x_i}{m}\quad \text{if }x_i<m
```

```latex
f_x^{right}=-A_w\frac{x_i-(W-m)}{m}
\quad \text{if }x_i>W-m \text{ and not inside exit opening}
```

```latex
f_y^{bottom}=A_w\frac{m-y_i}{m}\quad \text{if }y_i<m
```

```latex
f_y^{top}=-A_w\frac{y_i-(H-m)}{m}\quad \text{if }y_i>H-m
```

Source:

- `src/crowd_management/crowd_model.py:120-139`

Interpretation:

Walls push pedestrians back into the room. The right wall is open only inside the exit interval.

Why reasonable:

Linear wall handling is stable and easy to explain in a first-stage 2D simulator.

### A7. Boundary Projection and Evacuation

Label: `[Implemented]`

Formula:

```latex
s_i(t+\Delta t)=1
\quad \text{if}\quad
x_i(t+\Delta t)\ge W,\quad
y_i(t+\Delta t)\in [y_e-w_e/2,\ y_e+w_e/2]
```

Otherwise, positions are clipped to the valid room boundary and velocity components pointing into walls are removed.

Source:

- `src/crowd_management/crowd_model.py:141-162`
- `src/crowd_management/types.py:62-77`

Interpretation:

Pedestrians evacuate only by crossing the right wall through the configured opening.

Why reasonable:

This gives a clear binary evacuation metric in the first one-exit experiment.

### A8. Total Pedestrian Dynamics

Label: `[Implemented]`

Formula:

```latex
F_i(t)=f_i^{goal}(t)+f_i^{rep}(t)+f_i^{wall}(t)+f_i^{guide}(t)+\eta_i(t)
```

```latex
v_i(t+\Delta t)=
\mathrm{sat}_{v_{max}}\left(v_i(t)+\Delta t F_i(t)\right)
```

```latex
p_i(t+\Delta t)=p_i(t)+\Delta t v_i(t+\Delta t)
```

Variables:

- `\eta_i(t)`: optional Gaussian noise, controlled by `noise_std`.
- `\mathrm{sat}_{v_{max}}`: Euclidean norm clipping.

Source:

- `src/crowd_management/crowd_model.py:209-227`
- `src/crowd_management/types.py:38-43`

Interpretation:

The simulator uses explicit Euler integration with speed saturation.

Why reasonable:

It is transparent, deterministic under a seed, and easy to compare across guidance modes.

## B. Current Implemented DBACT-Transfer / Guider-Based Guidance Logic

### B1. Active Crowd Center

Label: `[Implemented]`

Formula:

```latex
c(t)=\frac{1}{|\mathcal{A}(t)|}
\sum_{i\in\mathcal{A}(t)} p_i(t)
```

Source:

- `src/crowd_management/dbact_transfer.py:32-42`
- `src/crowd_management/dbact_transfer.py:48-53`

Interpretation:

The active crowd is summarized by its mean position.

Why reasonable:

It transfers the cargo-guidance idea at the group level without pretending the crowd is rigid.

### B2. Active Crowd Radius / Spread

Label: `[Implemented]`

Formula:

```latex
R_c(t)=
\max\left(
\mathrm{percentile}_{65}
\left(\{\|p_i(t)-c(t)\|: i\in\mathcal{A}(t)\}\right),
0.6
\right)
```

Source:

- `src/crowd_management/dbact_transfer.py:38-41`
- `src/crowd_management/dbact_transfer.py:55-61`

Interpretation:

The crowd size is estimated from the 65th percentile distance to the center, with a minimum radius.

Why reasonable:

A percentile spread is robust to outliers and enough for placing guiders around the group boundary.

### B3. Crowd Target Direction

Label: `[Implemented]`

Formula:

```latex
d_c(t)=\frac{e-c(t)}{\|e-c(t)\|+\varepsilon}
```

Source:

- `src/crowd_management/dbact_transfer.py:41`
- `src/crowd_management/dbact_transfer.py:63-64`

Interpretation:

The group-level direction points from the active crowd center to the exit.

Why reasonable:

It gives a simple transfer target for the guider team.

### B4. Lateral Direction

Label: `[Implemented]`

Formula:

```latex
d_c^\perp(t)=
\begin{bmatrix}
-d_{c,y}(t)\\
d_{c,x}(t)
\end{bmatrix}
```

Source:

- `src/crowd_management/types.py:46-47`
- `src/crowd_management/dbact_transfer.py:72-75`

Interpretation:

The lateral vector lets guiders spread sideways around the rear side of the crowd.

Why reasonable:

It mirrors boundary placement in cargo transport but remains simple in 2D.

### B5. DBACT-Style Guider Target Positions

Label: `[Implemented]`

Formula:

```latex
q_k^*(t)=
\mathrm{clip}_{room}
\left(
c(t)-\beta R_c(t)d_c(t)+s_k d_c^\perp(t)
\right)
```

```latex
s_k \in
\left\{
\left(k-\frac{M-1}{2}\right)\Delta_s
\right\}_{k=0}^{M-1}
```

Variables:

- `q_k^*`: target position for guider `k`.
- `M`: number of guiders.
- `\beta`: `target_distance_gain`.
- `\Delta_s`: `side_spacing`.

Source:

- `src/crowd_management/dbact_transfer.py:69-95`

Interpretation:

Guiders are placed behind the active crowd relative to the exit direction, with symmetric side offsets.

Why reasonable:

This is the direct implemented transfer of the DBACT structure: estimate group state, then position multiple agents around the boundary.

### B6. Guider Desired Direction

Label: `[Implemented]`

Formula:

```latex
d_k^{guide}(t)=d_c(t)
```

Source:

- `src/crowd_management/dbact_transfer.py:93-102`

Interpretation:

Each guider suggests the crowd-level exit direction.

Why reasonable:

It separates guider placement from pedestrian response and keeps the first transfer test interpretable.

### B7. Guider Motion Dynamics

Label: `[Implemented]`

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

Interpretation:

Guiders move toward their assigned target as fast as allowed by the max-speed limit.

Why reasonable:

First-order motion is sufficient for testing the placement policy without robot dynamics.

### B8. Guider Influence on Pedestrians

Label: `[Implemented]`

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
r_{ik}=\|p_i(t)-q_k(t)\|
```

Variables:

- `R_g`: guider influence radius.
- `\gamma`: guidance strength.
- `c_i`: pedestrian compliance.

Source:

- `src/crowd_management/guidance_controller.py:20-33`
- `src/crowd_management/crowd_model.py:221-222`

Interpretation:

A guider adds a directional acceleration only to nearby pedestrians. Influence decays smoothly to zero at the radius boundary.

Why reasonable:

This is easy to explain as a local directional suggestion rather than physical pushing.

### B9. Static Guider Baseline

Label: `[Implemented]`

Formula:

```latex
q_k=q_k^*=
\mathrm{clip}_{room}\left(
c(0)+0.35(e-c(0))+s_k d_c^\perp(0)
\right)
```

Source:

- `src/crowd_management/crowd_model.py:164-181`

Interpretation:

Static guiders stay at fixed positions between the initial crowd and the exit.

Why reasonable:

It checks whether DBACT-specific dynamic placement is better than simply adding visible guiders.

### B10. Random Guider Baseline

Label: `[Implemented]`

Formula:

```latex
q_k^* \sim \mathrm{Uniform}([0.5,W-0.8]\times[0.5,H-0.5])
```

Every 40 simulation steps:

```latex
d_k^{guide}=
\frac{e-q_k^*}{\|e-q_k^*\|+\varepsilon}
```

Source:

- `src/crowd_management/crowd_model.py:183-204`

Interpretation:

Guiders move to reproducible random targets and suggest the exit direction from those targets.

Why reasonable:

It controls for the effect of mobile agents without meaningful DBACT-style placement.

## C. Metrics, Density Visualization, and Planned Density-Aware Extension

### C1. Evacuation Rate

Label: `[Implemented]`

Formula:

```latex
E(t)=\frac{1}{N}\sum_{i=1}^{N} \mathbf{1}[s_i(t)=1]
```

Source:

- `src/crowd_management/metrics.py:13-18`

Interpretation:

Fraction of pedestrians already evacuated.

Why reasonable:

It is the clearest first outcome metric.

### C2. Mean Active Speed

Label: `[Implemented]`

Formula:

```latex
\bar v(t)=
\frac{1}{|\mathcal{A}(t)|}
\sum_{i\in\mathcal{A}(t)} \|v_i(t)\|
```

Source:

- `src/crowd_management/metrics.py:21-29`

Interpretation:

Average speed among pedestrians still inside the simulation.

Why reasonable:

It measures whether guidance keeps people moving.

### C3. Near-Collision Count

Label: `[Implemented]`

Formula:

```latex
N_{near}(t)=
\sum_{i<j,\ i,j\in\mathcal{A}(t)}
\mathbf{1}[\|p_i(t)-p_j(t)\|<d_{near}]
```

Source:

- `src/crowd_management/metrics.py:32-41`

Interpretation:

Counts close active pedestrian pairs below a threshold.

Why reasonable:

It provides a simple safety/congestion proxy.

### C4. Congestion Index

Label: `[Implemented]`

Formula:

```latex
C(t)=
\frac{1}{|\mathcal{A}(t)|}
\sum_{i\in\mathcal{A}(t)}
\sum_{j\in\mathcal{A}(t),j\ne i}
\mathbf{1}[\|p_i(t)-p_j(t)\|<R_c^{metric}]
```

Source:

- `src/crowd_management/metrics.py:44-54`

Interpretation:

Average number of nearby active pedestrians around each active pedestrian.

Why reasonable:

It is a directly interpretable local crowding metric.

### C5. Path Length

Label: `[Implemented]`

Formula:

```latex
L_i=\sum_{k=1}^{T}\|p_i(t_k)-p_i(t_{k-1})\|
```

```latex
\bar L=\frac{1}{N}\sum_{i=1}^{N}L_i,\quad
L_{total}=\sum_{i=1}^{N}L_i
```

Source:

- `src/crowd_management/metrics.py:78-87`

Interpretation:

Measures total traveled distance and mean traveled distance.

Why reasonable:

It helps detect inefficient wandering or detours.

### C6. Density Heatmap

Label: `[Partially implemented]`

Formula:

```latex
H_{ab}(t)=
\sum_{i\in\mathcal{A}(t)}
\mathbf{1}[p_i(t)\in \mathrm{cell}_{ab}]
```

Source:

- `src/crowd_management/visualization.py:56-75`
- `src/crowd_management/advanced_visualization.py:100-112`

Interpretation:

The project computes histogram-based density grids for visualization only.

Why partially implemented:

Density is implemented for heatmaps and visual inspection, but not yet used by the guider controller or route-choice logic.

### C7. Two-Exit Scenario Configuration

Label: `[Partially implemented]`

Formula:

```latex
\mathcal{E}=\{e_1,e_2\}
```

Source:

- `configs/two_exits.yaml`
- `reports/guidance_baselines_v1/GUIDANCE_BASELINES_REPORT.md`

Interpretation:

The second exit is documented in configuration as an intended future scenario.

Why partially implemented:

Current simulator still parses and uses only the primary `room.exit` field. No implemented route-choice assignment exists.

### C8. Planned Continuous Density Field

Label: `[Planned]`

Formula:

```latex
\rho(x,t)=
\sum_{i\in\mathcal{A}(t)}
\exp\left(
-\frac{\|x-p_i(t)\|^2}{2\sigma_\rho^2}
\right)
```

Source:

- Not implemented. Proposed next-step extension.

Interpretation:

Estimate local crowd density smoothly rather than using only neighbor counts or visualization histograms.

Why reasonable:

It can support density-aware guidance while remaining interpretable.

### C9. Planned Exit Load / Route Cost

Label: `[Planned]`

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
- `\rho_m(t)`: density near exit `m` or along its approach corridor.
- `Q_m(t)`: exit-load or queue proxy.
- `a_i(t)`: assigned exit for pedestrian `i`.

Source:

- Not implemented. Proposed next-step extension.

Interpretation:

Pedestrians would be assigned or nudged toward exits based on distance and congestion, enabling route-choice diversion.

Why reasonable:

It targets the main limitation of the current single-exit scenario: there is little meaningful route choice for guidance to improve.

### C10. Planned Density-Aware Guider Target

Label: `[Planned]`

Formula:

```latex
q_k^*(t)=
c_g(t)-\beta R_g(t)d_g(t)+s_k d_g^\perp(t)
```

where `c_g`, `R_g`, and `d_g` are computed for a selected sub-group or exit-assignment group, not necessarily the whole active crowd.

Source:

- Not implemented. Proposed next-step extension based on current `dbact_transfer.py`.

Interpretation:

Use the implemented DBACT-style placement rule, but apply it to split-flow groups rather than the whole crowd.

Why reasonable:

It reuses the current transfer mechanism while giving the guider policy a harder and more meaningful control task.
