# PPT Outline

## Slide 1: Motivation

Message:

- Goal: test whether a robot cargo-guidance / DBACT-style multi-agent positioning idea can transfer to crowd guidance.
- Current question: can mobile guiders placed around a crowd improve evacuation behavior in a simple simulator?
- Important honesty: this is a feasibility sprint, not a complete crowd-management theory.

Visual suggestion:

- Diagram: cargo-guidance idea -> active crowd -> mobile guiders -> exit.

Speaker note:

The main contribution so far is an executable transfer pipeline and an interpretable mathematical baseline.

## Slide 2: Why Start From a Simple Crowd Model?

Message:

- Simple, interpretable, controllable.
- Good for checking whether the transferred robot algorithm can run.
- Avoids premature complexity.

Key statement:

```text
We first fix a minimal microscopic model, then test whether the DBACT-style guider placement has any useful effect.
```

Out of scope for current version:

- exclusion queue;
- hybrid micro-macro model;
- detailed psychological model;
- CBF / LLM / hardware experiments.

## Slide 3: Pedestrian State Variables

Label: `[Implemented]`

Formula:

```latex
p_i(t)\in\mathbb{R}^2,\quad
v_i(t)\in\mathbb{R}^2,\quad
c_i\in[0,1]
```

Meaning:

- `p_i`: pedestrian position.
- `v_i`: pedestrian velocity.
- `c_i`: compliance with guider influence.

Source:

- `src/crowd_management/types.py:210-219`
- `src/crowd_management/crowd_model.py:59-78`

Speaker note:

Each pedestrian is a lightweight microscopic agent. This is enough to model motion, avoidance, guidance response, and evacuation.

## Slide 4: Desired Exit Direction

Label: `[Implemented]`

Formula:

```latex
d_i^{exit}(t)=
\frac{e-p_i(t)}{\|e-p_i(t)\|+\varepsilon}
```

Goal acceleration:

```latex
f_i^{goal}(t)=
\frac{v_i^0d_i^{exit}(t)-v_i(t)}{\tau}
```

Source:

- `src/crowd_management/crowd_model.py:92-96`

Speaker note:

The baseline behavior is simple: pedestrians relax toward a desired velocity pointing at the exit.

## Slide 5: Pedestrian-Pedestrian Repulsion

Label: `[Implemented]`

Formula:

```latex
f_i^{rep}(t)=
\sum_{j\ne i}
\mathbf{1}_{r_{ij}\le R_{int}}
\left[
A_p\exp\left(\frac{2r_p-r_{ij}}{B_p}\right)
6\max(0,2r_p-r_{ij})
\right]
\frac{p_i-p_j}{r_{ij}}
```

Source:

- `src/crowd_management/crowd_model.py:98-118`

Speaker note:

This term prevents overlap and creates local congestion behavior without adding a complex psychological model.

## Slide 6: Wall/Boundary Handling

Label: `[Implemented]`

Wall repulsion example:

```latex
f_x^{left}=A_w\frac{m-x_i}{m}\quad\text{if }x_i<m
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

Speaker note:

The room has hard boundaries. The right wall is open only at the exit, so evacuation is a clear event.

## Slide 7: Guider Influence Model

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

Source:

- `src/crowd_management/guidance_controller.py:20-33`
- `src/crowd_management/crowd_model.py:221-222`

Speaker note:

Guiders do not push pedestrians. They locally bias pedestrian direction, scaled by distance and compliance.

## Slide 8: DBACT-Transfer Idea

Label: `[Implemented]`

Crowd center:

```latex
c(t)=
\frac{1}{|\mathcal{A}(t)|}
\sum_{i\in\mathcal{A}(t)}p_i(t)
```

Crowd radius:

```latex
R_c(t)=
\max\left(
\mathrm{percentile}_{65}
\{\|p_i(t)-c(t)\|\},
0.6
\right)
```

Guider target:

```latex
q_k^*(t)=
\mathrm{clip}_{room}
\left(c(t)-\beta R_c(t)d_c(t)+s_kd_c^\perp(t)\right)
```

Source:

- `src/crowd_management/dbact_transfer.py:32-42`
- `src/crowd_management/dbact_transfer.py:69-95`

Speaker note:

The original cargo algorithm is not copied literally. The transferred structure is: estimate group state, place agents around the rear/side boundary, and let their field guide the group.

## Slide 9: Density-Aware Extension

Label: `[Planned]`

Planned density field:

```latex
\rho(x,t)=
\sum_{i\in\mathcal{A}(t)}
\exp\left(-\frac{\|x-p_i(t)\|^2}{2\sigma_\rho^2}\right)
```

Planned exit cost:

```latex
C_{im}(t)=
\lambda_d\|p_i(t)-e_m\|
+\lambda_\rho\rho_m(t)
+\lambda_qQ_m(t)
```

Planned assignment:

```latex
a_i(t)=\arg\min_m C_{im}(t)
```

Speaker note:

This is not yet implemented. It is the next mathematical extension for two-exit or bottleneck scenarios, where guidance can split flow rather than only nudge everyone toward one exit.

## Slide 10: Current Test Result

Message:

- Pipeline runs successfully.
- Baseline, static, random, and DBACT modes can be compared.
- In the simple one-exit scenario, DBACT is stable and slightly better than no guidance in final evacuation rate.
- It does not clearly outperform static guidance.

Result table:

| Metric | Baseline | Static | Random | DBACT |
|---|---:|---:|---:|---:|
| Final evacuated | 149 | 150 | 150 | 150 |
| Final evacuation rate | 0.93125 | 0.93750 | 0.93750 | 0.93750 |
| Mean speed | 1.05445 | 1.06463 | 1.05412 | 1.05781 |
| Congestion index | 1.51381 | 1.48335 | 1.60127 | 1.61035 |

Speaker note:

This should be presented as proof of execution and feasibility, not proof of superiority.

## Slide 11: Limitation of the Single-Exit Scenario

Message:

- Everyone has the same exit target.
- Route choice is absent.
- Density is visualized and measured, but not used by the controller.
- Guiders can only provide local directional bias.
- Static guidance remains competitive because the scenario is too simple.

Speaker note:

The weak DBACT advantage is informative. It means the next experiment should expose a real crowd-management decision, such as which exit or corridor should receive more flow.

## Slide 12: Next Step: Two-Exit / Bottleneck Experiment

Message:

- Implement true multi-exit logic.
- Add density-aware exit costs.
- Use DBACT-style placement for assigned subgroups.
- Evaluate flow splitting, congestion, near-collision count, mean speed, and evacuation rate.

Planned experiment structure:

```text
No guidance
vs static guidance
vs random guidance
vs current DBACT
vs density-aware DBACT
```

Speaker note:

The next version should test whether guidance can redirect part of the crowd away from a congested exit or bottleneck. That is where density-aware guidance can show clearer value.
