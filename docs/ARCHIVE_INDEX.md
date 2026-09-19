# Research Archive Index

This file records historical branch snapshots that are intentionally kept outside the active Step 1 line (`STEP1-Research-Extension`).

## Active branch policy

Active Step 1 work lives on **`STEP1-Research-Extension`** (known closed environment boundary + unknown static crowd).

The previous GitHub `main` tip (G6 research-complete ABCG, including mathematical-verification evidence) is stored as the read-only snapshot **`archive/main-2026-09-19`**. The `main` ref itself is left at that same commit unless explicitly retargeted. Historical experimental or pre-ABCG evacuation lines must not be merged wholesale into the active line.

## Preserved snapshots

| Archive branch | Frozen source SHA | Purpose | Status |
| --- | --- | --- | --- |
| `archive/g7-proof-strengthening-failed-2026-07-20` | `a6b4c4206ad0c8cc5919c945f2287169ec8c240b` | Preserves the remaining tip of the former `step1-proof-strengthening-v1` branch, including the failed proof-strengthening/G7 research history. | Historical / read-only |
| `archive/legacy-evacuation-2026-07-21` | `fb35ac215bc968cda7466d4c4f56c1b710eb4b70` | Preserves legacy evacuation, DBAct/density-DBAct prototypes, reports, media, scripts, and compatibility code formerly kept on `local-main-backup`. | Historical / read-only |
| `archive/main-2026-09-19` | `2e87d4914b9f3a65e363994cb00bc4938b010a2f` | Snapshot of the previous `main` tip before the Step 1 research-extension branch (`STEP1-Research-Extension`). Includes G6 research-complete ABCG and the merged mathematical-verification evidence. | Historical / read-only |

The G7 failure is research evidence, not a successful deployment result. Preserve its failure semantics and provenance when referring to it.

## Mathematical verification

The former `math-verification-main-v1` work was merged into `main` through PR #15. Those reports, Wolfram sources, figures, integrity checks, and machine-readable artifacts are retained on `archive/main-2026-09-19` (and on the `main` ref while it still points at that snapshot).

## Reuse rule

If a future Step 2/3 branch needs a legacy crowd-behavior, evacuation, compliance, exit-choice, or visualization component, copy or re-implement only the required module from the archive and revalidate it under the new research contract. Do not merge the entire legacy archive into `STEP1-Research-Extension` or `main`.

## Inspection

```bash
git fetch origin
git switch archive/legacy-evacuation-2026-07-21
# or
git switch archive/g7-proof-strengthening-failed-2026-07-20
# or
git switch archive/main-2026-09-19
```

New development should return to `STEP1-Research-Extension` before editing active research code. Inspect the frozen previous main with `git switch archive/main-2026-09-19`.
