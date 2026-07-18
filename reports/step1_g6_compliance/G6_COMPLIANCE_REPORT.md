# ABCG-v2 Step 1 G6 formal compliance report

- Primary matrix: 4 scenarios × 5 methods × 30 paired seeds
- Bootstrap boundary samples: 30
- Initial layouts: balanced perimeter, one-sided, opposed sides
- Freeze status: `UNFROZEN_DIRTY_WORKTREE`
- G6 status: `UNMET_FROZEN_COMMIT`

## Primary closed-loop outcomes

| Scenario | Method | Success/total | Failure rate | Arc gap mean | Coverage mean | Runtime P95 ms |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| circle | endpoint_abcg | 20/30 | 0.333 | 1.621670597759801 | 0.9599999999999999 | 9720.25072499946 |
| circle | uniform_angular | 20/30 | 0.333 | 1.573907163251653 | 0.9473015873015872 | 9504.708165000193 |
| circle | uniform_arc | 19/30 | 0.367 | 1.3711467942291027 | 0.9293121693121693 | 15850.427805000978 |
| circle | fixed_m_periodic | 19/30 | 0.367 | 1.3711467942291027 | 0.9293121693121693 | 17695.25418499997 |
| circle | abcg_v2 | 18/30 | 0.400 | 2.031375451428342 | 0.8191534391534393 | 14564.822694999379 |
| ellipse | endpoint_abcg | 20/30 | 0.333 | 1.735296729760588 | 0.9604301075268816 | 11799.842559999972 |
| ellipse | uniform_angular | 19/30 | 0.367 | 1.7830681494961182 | 0.3674193548387096 | 9246.653219999276 |
| ellipse | uniform_arc | 22/30 | 0.267 | 1.3502638405382306 | 0.9788172043010752 | 19913.560634999067 |
| ellipse | fixed_m_periodic | 22/30 | 0.267 | 1.3502638405382312 | 0.9788172043010752 | 17400.806499999086 |
| ellipse | abcg_v2 | 26/30 | 0.133 | 2.048562236391258 | 0.8478494623655913 | 21632.792779998996 |
| u_shape | endpoint_abcg | 18/30 | 0.400 | 2.869067781305549 | 0.39403050108932464 | 23553.86046999945 |
| u_shape | uniform_angular | 13/30 | 0.567 | 2.8128897716228973 | 0.19542483660130724 | 22818.705434999887 |
| u_shape | uniform_arc | 11/30 | 0.633 | 2.3987736300412554 | 0.4443137254901961 | 56785.96743500011 |
| u_shape | fixed_m_periodic | 11/30 | 0.633 | 2.3987736300412554 | 0.4443137254901961 | 49747.622370001314 |
| u_shape | abcg_v2 | 9/30 | 0.700 | 2.0993087138930764 | 0.4956427015250544 | 50525.34788999916 |
| c_shape | endpoint_abcg | 18/30 | 0.400 | 2.8524948724101904 | 0.4015913978494624 | 24389.491515000638 |
| c_shape | uniform_angular | 17/30 | 0.433 | 2.8289144395147336 | 0.19088172043010754 | 47299.4815550001 |
| c_shape | uniform_arc | 8/30 | 0.733 | 2.393976076729124 | 0.45961290322580645 | 66171.01571499968 |
| c_shape | fixed_m_periodic | 8/30 | 0.733 | 2.3939760767291243 | 0.45961290322580645 | 63806.73291000011 |
| c_shape | abcg_v2 | 5/30 | 0.833 | 2.119727755252149 | 0.5081290322580645 | 63986.700194999845 |

## Failure interpretation

Across all 600 primary records, 323 converged, 242 timed out, 5 returned
`SAFETY_INFEASIBLE`, and 30 returned `BOUNDARY_INVALID`. The one-sided layout
accounts for 169 timeouts and all five safety-infeasible outcomes. A
straight-line fixed-target feedback law cannot reliably move guides to the
opposite side of a crowd while the sampled-data safety layer prevents travel
through the observed cloud. The result exposes a path-planning limitation; it
is not evidence that full ABCG-v2 dominates the baselines.

The U/C failure rates and truth coverage remain material limitations. The
narrow-neck stress case was valid at the formal observation count, while the
double-cluster and capacity-shortfall fixtures are actual visualized failures.

## Evidence boundary

Analytic truth is used only by the evaluator. Each method receives the same paired observation and initial guide state.
Invalid boundary, capacity, assignment, safety, degraded, and timeout states remain in the denominator.
The report is synthetic Step 1 evidence; it does not claim human-crowd interaction or decentralized Step 2/3 performance.
A dirty working tree intentionally keeps the frozen-commit condition unmet until the user authorizes a freeze.
