# Research Archive Index

This file records historical branch snapshots that are intentionally kept outside the active `main` development line.

## Active branch policy

`main` is the single active research/development branch for the current ABCG Step 1 code and its mathematical-verification evidence. Historical experimental or pre-ABCG evacuation lines must not be merged back into `main` wholesale.

## Preserved snapshots

| Archive branch | Frozen source SHA | Purpose | Status |
| --- | --- | --- | --- |
| `archive/g7-proof-strengthening-failed-2026-07-20` | `a6b4c4206ad0c8cc5919c945f2287169ec8c240b` | Preserves the remaining tip of the former `step1-proof-strengthening-v1` branch, including the failed proof-strengthening/G7 research history. | Historical / read-only |
| `archive/legacy-evacuation-2026-07-21` | `fb35ac215bc968cda7466d4c4f56c1b710eb4b70` | Preserves legacy evacuation, DBAct/density-DBAct prototypes, reports, media, scripts, and compatibility code formerly kept on `local-main-backup`. | Historical / read-only |

The G7 failure is research evidence, not a successful deployment result. Preserve its failure semantics and provenance when referring to it.

## Mathematical verification

The former `math-verification-main-v1` work was merged into `main` through PR #15. Mathematical-verification reports, Wolfram sources, figures, integrity checks, and machine-readable artifacts are therefore retained on `main`; no separate long-lived verification branch is required.

## Reuse rule

If a future Step 2/3 branch needs a legacy crowd-behavior, evacuation, compliance, exit-choice, or visualization component, copy or re-implement only the required module from the archive and revalidate it under the new research contract. Do not merge the entire legacy archive into `main`.

## Inspection

```bash
git fetch origin
git switch archive/legacy-evacuation-2026-07-21
# or
git switch archive/g7-proof-strengthening-failed-2026-07-20
```

New development should return to `main` before editing active research code.
