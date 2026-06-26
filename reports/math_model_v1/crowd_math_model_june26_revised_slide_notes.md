# Crowd Math Model June 26 Revised - Slide Notes

## Slide 1: Title

This presentation is a feasibility report. I will explain the simple mathematical model used in the simulator, why I selected this model, how the robot DBACT-style idea was transferred to crowd guidance, and what has already been tested. The important point is that this is not a final crowd-management theory. It is a first reproducible testbed for checking whether my previous robot-guidance idea can work at all in a simple crowd model.

## Slide 2: Supervisor Question and My Answer

I will answer directly. The first version has already been tested. The pipeline works: simulation, guider placement, metrics, and visualization run end to end. However, I should not overstate the result. In the simple single-exit scenario, DBACT-transfer is stable and slightly better than no guidance, but it does not clearly outperform the static-guidance baseline. Therefore, the honest conclusion is proof of execution and transfer feasibility, not proof that DBACT is the best crowd-management method.

## Slide 3: Why Start Simple?

The modeling philosophy is to build from behavior assumptions step by step. First, pedestrians should move toward an exit. Second, they should avoid other pedestrians. Third, the walls and exit must be handled correctly. Fourth, guiders should influence pedestrian intention. After that, the DBACT-style placement rule can be tested. More advanced density-aware split-flow guidance is a planned next step. At this stage, I intentionally avoid exclusion queues, hybrid models, detailed psychology, CBF, LLM planning, and hardware dynamics because those would make it harder to understand whether the robot-guidance transfer itself works.

## Slide 4: State Variables

Each pedestrian is represented by a position, a velocity, an evacuation state, and a compliance value. The guiders also have positions. The exits and the room domain define the environment. This state is intentionally lightweight. It is enough for movement, collision avoidance, guidance response, and evacuation measurement, while still being easy to explain mathematically.

## Slide 5: Desired Exit Direction

The baseline behavior is exit seeking. For each pedestrian, I compute a unit vector from the pedestrian position to the active exit center. Then the pedestrian velocity relaxes toward the desired velocity, which is desired speed times the exit direction. This is simple, but it gives a clear baseline behavior that can be compared with guided behavior.

## Slide 6: Pedestrian-Pedestrian Repulsion

The repulsion term is a local collision-avoidance mechanism. It uses the distance between two active pedestrians. If the distance is within the interaction range, an exponential repulsion is applied, plus an additional overlap penalty when pedestrians are closer than twice the pedestrian radius. This is not a full psychological model. It is the minimum mechanism needed to avoid unrealistic overlap and create local congestion dynamics.

## Slide 7: Wall and Boundary Handling

Walls are handled by repulsion near the boundary and by clipping if a pedestrian would move outside the room. Evacuation is only counted when the pedestrian crosses the right wall inside the exit opening. This gives a clear binary evacuation event and makes the rectangular-room simulation stable.

## Slide 8: Full Pedestrian Dynamics

The full pedestrian update combines exit seeking, pedestrian repulsion, wall handling, guider influence, and optional noise. The update uses explicit Euler integration, and the velocity is saturated by the maximum walking speed. The important point for the supervisor meeting is that every term has a direct behavioral interpretation, so this model is easy to inspect and control.

## Slide 9: Guider Influence Model

This slide is important because the guider is not a physical pushing force. It is modeled as a local influence on walking intention. The effect is applied only within the guider influence radius. It is scaled by guidance strength, pedestrian compliance, and a smooth distance weight. This keeps the model simple and avoids claiming detailed psychological behavior.

## Slide 10: From Robot DBACT to Crowd Guidance

The DBACT transfer should be explained carefully. I am not claiming that the original robot algorithm is copied literally into a crowd. Instead, I transfer the structural idea. In robot cargo transport, multiple robots estimate or interact with an object boundary and position themselves for cooperative transport. In crowd guidance, I estimate the active crowd center and spread, place guiders around the rear and side boundary, and let their local influence field bias pedestrian movement. DBACT is a first transfer candidate and a useful baseline, not a final answer.

## Slide 11: Crowd Center, Spread, and Direction

For DBACT-style placement, the active crowd is summarized by three quantities: centroid, spread, and direction to the exit. The spread is not the maximum distance; it is the 65th percentile distance from the centroid, with a minimum value. This is robust to outliers and gives a stable estimate for placing guiders around the group boundary. I should emphasize that the crowd is not treated as a rigid object. It is still simulated as individual pedestrians.

## Slide 12: DBACT-Style Guider Target Position

This is the implemented DBACT-transfer core. The target position for each guider is computed from the crowd center, then shifted backward opposite the exit direction, and shifted sideways using symmetric lateral offsets. The target is clipped inside the room. This implements the idea of placing multiple agents around the rear and side boundary of the active crowd.

## Slide 13: Guider Motion

The guider motion model is deliberately simple. A guider moves toward its assigned target position, with a maximum speed limit and room clipping. This tests the geometry of the placement rule without introducing full robot dynamics. That is appropriate because the current question is whether the DBACT-style placement idea can transfer to crowd guidance in principle.

## Slide 14: Current Test Result: What Worked and What Did Not

The first version has been tested. The simulator, DBACT-transfer controller, metrics, and visual outputs run successfully. In the simple one-exit scenario, DBACT-transfer evacuated 150 out of 160 pedestrians, while the no-guidance baseline evacuated 149 out of 160. However, static and random guidance also evacuated 150 out of 160, and static guidance has better mean speed and congestion in this report. Therefore, I should say clearly: the current result is proof of execution and transfer feasibility, not proof that DBACT is superior.

## Slide 15: Visual Evidence from Repository

The repository contains visual evidence from the existing runs. The dashboard summarizes evacuation curves, final metrics, and final snapshots. The all-mode grid compares baseline, static, random, and DBACT modes. Heatmap snapshots make congestion easier to inspect. These visuals are useful because they show that the pipeline works, but they also reveal the limitation: in a single-exit setting, the algorithm has limited opportunity to redistribute flow.

## Slide 16: Why Single-Exit Is Not Enough

The single-exit scenario is useful as a first smoke test, but it is not enough to demonstrate crowd-management value. Everyone has the same target exit, so route choice is absent. The guider can only nudge direction locally; it cannot meaningfully split flow between exits. Static guidance remains competitive for this reason. The current density computations are used for visualization and metrics, not for control. This limitation is not a failure. It tells us that the next experiment needs a real crowd-management decision, such as two exits or a bottleneck.

## Slide 17: Planned Density-Aware Extension

This slide must be labeled planned. The current repository does not contain a completed Stage 4 density-aware controller or a density_dbact module. The planned idea is to estimate a smooth density field, define an exit cost based on distance, local density, and queue or load proxy, and assign pedestrians or guider targets based on that cost. This is where crowd-management behavior becomes more meaningful, because a two-exit or bottleneck setup can test flow splitting, route diversion, and congestion avoidance.

## Slide 18: DBACT Is a Candidate, Not the Final Answer

This slide is important for the supervisor meeting. DBACT-transfer is a natural first candidate because it connects to my previous robot work. But for the larger KAKENHI-scale research topic, I should not assume that DBACT is the final or optimal method. It should be compared with density-based assignment, potential fields, optimal control or MPC, queueing-inspired control, reinforcement learning, hybrid micro-macro models, and methods found in the literature review. This shows that the current work is a starting point and a reproducible baseline.

## Slide 19: Next Plan

The next plan has three levels. In the short term, I will improve visual evidence, verify formulas against code, and run controlled comparisons. In the mid term, I will build a two-exit or bottleneck scenario, add density-aware route assignment, run parameter sweeps and multi-seed statistics, and compare DBACT with strong baselines. In the long term, I need a literature review for the KAKENHI topic and a broader decision about whether DBACT, queueing, density control, or another framework is most promising.

## Slide 20: Takeaway

I will end with three takeaways. First, a simple microscopic crowd model has been implemented and is mathematically interpretable. Second, DBACT-style guider placement has been transferred and tested; it runs, but superiority is not yet proven. Third, the next meaningful step is a two-exit or bottleneck density-aware guidance experiment, together with literature review and method comparison. The final sentence should be: the current contribution is a reproducible first testbed and an honest first evaluation, not a final claim of optimality.
