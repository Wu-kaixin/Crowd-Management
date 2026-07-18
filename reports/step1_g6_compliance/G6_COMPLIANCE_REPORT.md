# ABCG-v2 Step 1 G6 formal compliance report

- Primary matrix: 4 scenarios × 5 methods × 30 paired seeds
- Bootstrap boundary samples: 30
- Initial layouts: balanced perimeter, one-sided, opposed sides
- Freeze status: `FROZEN_COMMIT`
- Overall status: `PASS`
- G6 status: `PASS`
- Evaluated commit: `f2494922b2431bfd9a37a247add8a79acfdc18ed`

## Primary closed-loop outcomes

| Scenario | Method | Success/total | Failure rate | Arc gap mean | Coverage mean | Runtime P95 ms |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| circle | endpoint_abcg | 20/30 | 0.333 | 1.621670597759801 | 0.9599999999999999 | 10011.595919999672 |
| circle | uniform_angular | 20/30 | 0.333 | 1.573907163251653 | 0.9473015873015872 | 8759.674394998183 |
| circle | uniform_arc | 19/30 | 0.367 | 1.3711467942291027 | 0.9293121693121693 | 16736.01824499874 |
| circle | fixed_m_periodic | 19/30 | 0.367 | 1.3711467942291027 | 0.9293121693121693 | 14443.203524999624 |
| circle | abcg_v2 | 18/30 | 0.400 | 2.031375451428342 | 0.8191534391534393 | 15275.693185002818 |
| ellipse | endpoint_abcg | 20/30 | 0.333 | 1.735296729760588 | 0.9604301075268816 | 11068.198140000457 |
| ellipse | uniform_angular | 19/30 | 0.367 | 1.7830681494961182 | 0.3674193548387096 | 9342.263780000027 |
| ellipse | uniform_arc | 22/30 | 0.267 | 1.3502638405382306 | 0.9788172043010752 | 16722.44739500111 |
| ellipse | fixed_m_periodic | 22/30 | 0.267 | 1.3502638405382312 | 0.9788172043010752 | 15680.85802500081 |
| ellipse | abcg_v2 | 26/30 | 0.133 | 2.048562236391258 | 0.8478494623655913 | 13522.791474999756 |
| u_shape | endpoint_abcg | 18/30 | 0.400 | 2.869067781305549 | 0.39403050108932464 | 16060.512984999868 |
| u_shape | uniform_angular | 13/30 | 0.567 | 2.8128897716228973 | 0.19542483660130724 | 13475.905909998432 |
| u_shape | uniform_arc | 11/30 | 0.633 | 2.3987736300412554 | 0.4443137254901961 | 48335.957890000995 |
| u_shape | fixed_m_periodic | 11/30 | 0.633 | 2.3987736300412554 | 0.4443137254901961 | 46877.47735500215 |
| u_shape | abcg_v2 | 9/30 | 0.700 | 2.0993087138930764 | 0.4956427015250544 | 42566.07530000147 |
| c_shape | endpoint_abcg | 18/30 | 0.400 | 2.8524948724101904 | 0.4015913978494624 | 20235.648059999556 |
| c_shape | uniform_angular | 17/30 | 0.433 | 2.8289144395147336 | 0.19088172043010754 | 20989.94516500096 |
| c_shape | uniform_arc | 8/30 | 0.733 | 2.393976076729124 | 0.45961290322580645 | 39203.02706999882 |
| c_shape | fixed_m_periodic | 8/30 | 0.733 | 2.3939760767291243 | 0.45961290322580645 | 46829.55789999942 |
| c_shape | abcg_v2 | 5/30 | 0.833 | 2.119727755252149 | 0.5081290322580645 | 38332.06622499783 |

## Evidence boundary

Analytic truth is used only by the evaluator. Each method receives the same paired observation and initial guide state.
Invalid boundary, capacity, assignment, safety, degraded, and timeout states remain in the denominator.
The report is synthetic Step 1 evidence; it does not claim human-crowd interaction or decentralized Step 2/3 performance.
The evaluator recorded a clean frozen commit.

## Research-complete boundary and limitations

ABCG-v2 Step 1 is research-complete only for guide-agent deployment around one
static unknown crowd in simulation. The label does not establish human
compliance, containment effectiveness, evacuation improvement, behavior
change, or dynamic/multiple-crowd applicability. Full ABCG-v2 converged in
9/30 U-shape and 5/30 C-shape episodes; fixed-target straight-line feedback has
no obstacle-routing path planner. The sequential sampled-data safety
projection is an auditable engineering filter, not an unconditional formal
safety certificate. All `TIMEOUT`, `SAFETY_INFEASIBLE`, `BOUNDARY_INVALID`, and
other failure states remain part of the research result and denominator.
