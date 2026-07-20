# Step 1 G7 post-run audit and errata

This note does not replace or edit the frozen Holdout records. It documents the
interpretation boundary discovered after the completed formal run.

## Frozen result

- Gate: **G7 FAIL**
- Frozen evaluator SHA: `dc73866254136b1e14237483bc4c8a0934e8732f`
- Resolved configuration SHA-256:
  `6e6a1459bcf845e5db6dd653d682f330cda66d4cef3ecba1df04aca4b7cb48ce`
- Compact-record SHA-256:
  `b8b5ddb9879c268e62447b89572b8dd8b9167f0096fdaa0b32099f1b88b91238`
- Denominator: 330 records: 300 ABCG-v2.1 deployment records plus 30
  tracking-only G6 adapter records.
- ABCG-v2.1 outcomes: 0/300 estimated deployment successes, 0/300
  truth-validated successes, 232 `ROUTE_INFEASIBLE`, 60
  `RESOURCE_UNCERTAIN`, and 8 `TIMEOUT`.

The formal failure reasons are independent uncertainty calibration failure,
failure of the Holm-adjusted primary superiority family, and forbidden primary
inference for tracking RMSE and minimum intersample clearance because the
paired continuous endpoints were missing.

## Interpretation corrections

1. The blocked-route comparison reports G6 TIMEOUT in 5/6 matched U/C cases
   and visibility-routing TIMEOUT in 0/6. All six visibility cases instead
   terminated `ROUTE_INFEASIBLE` before control. The lower TIMEOUT count is
   therefore not evidence of successful deployment. The regenerated figure
   states this terminal composition directly.
2. The frozen `resource_pareto.json` mechanically labels finite,
   failure-inclusive points `COMPARABLE`. Every one of its ten grouped points
   contains failures, so none supports a deployment-Pareto conclusion. The
   README renderer recomputes the frozen compact-record failure count, plots
   every such group with an X, and states that there are 0/10 zero-failure
   deployment-Pareto groups. The frozen statistics file itself remains
   unchanged.
3. The first media validator incorrectly required each method-estimated
   `source_polygon` to remain concave. The paired held-out U/C
   `truth_boundary` is genuinely concave, while both formal method estimates
   are valid convex outputs. The validator now checks the hash-linked truth
   geometry and retains each method's actual estimate and failure.
4. The frozen manifest's source aggregate was computed from checkout-filtered
   Windows bytes. It verified in the run checkout but is not portable across
   CRLF policies. Later code hashes canonical Git blobs and includes a line-end
   regression test. This provenance correction was not used to relabel or
   recompute the frozen Holdout.

## No replacement Holdout

After these downstream rendering and provenance corrections, a new freeze was
prepared but the user requested that computation stop and the completed failure
be summarized. No replacement Holdout was run. Consequently:

- the formal conclusion remains the frozen `dc738662...` **G7 FAIL**;
- post-run code changes are not claimed as formally validated performance;
- the original 330-record denominator and every failure remain intact; and
- G6 compact evidence and Visual Overview media remain read-only and
  hash-verified.

The results apply only to guide deployment around one static synthetic point
cloud with global observation. They do not establish human containment,
evacuation improvement, behavior change, dynamic or multi-group capability,
general path-planning completeness, safety certification, or unconditional
continuous-time safety.
