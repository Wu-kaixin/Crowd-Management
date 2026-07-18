# ABCG-v2 Step 1 PR6 Paired Robust Evaluation

- Paired seeds: 30 (`0` through `29`)
- Held-out shapes: u_shape, c_shape
- Variants: radial neutral, alpha neutral, alpha bootstrap gain, alpha bootstrap gain ablated
- Repository freeze status: `UNFROZEN_DIRTY_WORKTREE`
- Source SHA-256: `d8344d87f47afe8ed470edb05cf4f1455b99432b70adbde32877369e26c01baa`

## Aggregate boundary error

| Shape | Variant | Valid/total | Chamfer mean [95% CI] | Hausdorff mean [95% CI] |
| --- | --- | --- | --- | --- |
| u_shape | alpha_bootstrap_gain | 30/30 | 0.11666810616687373 [0.11067496795141493, 0.12302861589328702] | 0.47669869870630155 [0.439593510548822, 0.5196151444439583] |
| u_shape | alpha_bootstrap_no_gain | 30/30 | 0.11666810616687373 [0.11052763871469679, 0.12293677995415113] | 0.47669869870630155 [0.4405107007430266, 0.5162192323101865] |
| u_shape | alpha_neutral | 30/30 | 0.11666810616687373 [0.1107708210997455, 0.12285570894166524] | 0.47669869870630155 [0.44058161893669356, 0.517967780728775] |
| u_shape | radial_neutral | 30/30 | 0.33557181663151037 [0.3316693517746829, 0.3392045051470988] | 1.0370710862520915 [1.0274124169377932, 1.0479683276465206] |
| c_shape | alpha_bootstrap_gain | 30/30 | 0.12838598371697899 [0.12081860735928959, 0.13646944987166526] | 0.4658544091878595 [0.43120265207143954, 0.5027044673309525] |
| c_shape | alpha_bootstrap_no_gain | 30/30 | 0.12838598371697899 [0.12055004190547756, 0.13677366091799306] | 0.4658544091878595 [0.4313947146946904, 0.5016032108409745] |
| c_shape | alpha_neutral | 30/30 | 0.12838598371697899 [0.12060612435346016, 0.13666939647775708] | 0.4658544091878595 [0.43202161946935913, 0.5027639101521931] |
| c_shape | radial_neutral | 30/30 | 0.361282840645047 [0.35701862347583163, 0.3661432620867997] | 1.1563099905713288 [1.1222990132516462, 1.1903209034990707] |

## Evidence boundary

Results are paired synthetic boundary-reconstruction evidence. They do not prove continuous-time safety,
human containment efficacy, or performance on real sensor data. Invalid runs remain in the denominator.
Confidence gates Lloyd step size only; it is not treated as risk density.
The radial geometry baseline uses a relaxed 0.60 observation-coverage validity threshold versus 0.80
for alpha variants so its non-star reconstruction error remains measurable; failure rates are not compared
as though those thresholds were identical.

Failure gallery entries: 6.

The complete paired differences and bootstrap confidence intervals are in `paired_comparisons.json`.
G6 cannot be called fully frozen while the repository snapshot reports `UNFROZEN_DIRTY_WORKTREE`.
