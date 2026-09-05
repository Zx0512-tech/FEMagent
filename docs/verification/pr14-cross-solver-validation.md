# PR14 Validation — Cross-Solver Validation V1

## Status

PR14 implements a deterministic, read-only evidence-first comparison layer for two solver/model sides that represent the same explicit engineering semantic role.

This verification record distinguishes:

- semantic identity;
- recorded-run model identity;
- result artifact integrity;
- evidence promotion;
- metadata compatibility;
- deterministic comparison math.

Ready-for-review requires a fresh full repository CI run on the exact final documentation head.

## Trust chain under test

```text
left explicit Semantic Role Manifest        right explicit Semantic Role Manifest
             |                                           |
             v                                           v
      PR13 role resolution                         PR13 role resolution
             |                                           |
             v                                           v
  recorded run Model Bundle gate              recorded run Model Bundle gate
             |                                           |
             v                                           v
 Result Intelligence integrity/query        Result Intelligence integrity/query
             |                                           |
             v                                           v
    PR12 VERIFIED Evidence                       PR12 VERIFIED Evidence
              \                                         /
               +------ PR14 compatibility check -------+
                                  |
                                  v
                    COMPARABLE / NOT_COMPARABLE
```

PR14 does not replace any upstream verification boundary.

## Baseline

PR14 started from `main` merge commit:

```text
508f34b29c6c9e03aa0c0ee838cc44acf016bd17
```

which includes merged PR13 Engineering Semantic Roles V1.

The design-only PR14 baseline head passed CI **#231** before implementation:

- TypeScript: 15/15 PASS;
- Python: 118/118 PASS;
- Ruff: PASS;
- OpenSees adapter availability smoke: PASS;
- ANSYS result-reader import smoke: PASS;
- health smoke: PASS.

## TDD history

### Task 1 — pure comparison core

#### RED — CI #233

Tests were committed before production code.

The existing TypeScript suite passed **15/15**. Python then stopped during collection with:

```text
ModuleNotFoundError: No module named 'fem_core.cross_solver'
```

This established a clean RED for the new comparison subsystem.

#### GREEN — CI #236

The implementation added:

- comparison statuses;
- stable limitation codes;
- pure evidence-report extraction;
- deterministic compatibility ordering;
- `absolutePeak` difference math;
- symmetric relative difference;
- different NODE/model identities allowed across sides.

CI #236 passed the full repository gate. The Python suite increased to **128/128** while the TypeScript suite remained **15/15**.

Task 1 tests explicitly cover:

```text
COMPARABLE with different NODE IDs
zero/zero relative difference
SIDE_NOT_VERIFIED
ROLE_MISMATCH
QUERY_MISMATCH
UNIT_UNKNOWN
UNIT_MISMATCH
REFERENCE_FRAME_MISMATCH
METRIC_UNAVAILABLE
```

### Task 2 — evidence-first orchestration API

#### RED — CI #237

The API tests were committed before `fem_core.cross_solver.api` existed.

The existing TypeScript suite passed **15/15**. Python collection then failed specifically with:

```text
ModuleNotFoundError: No module named 'fem_core.cross_solver.api'
```

#### GREEN — CI #239

`validate_cross_solver()` was added as a thin orchestration layer:

```text
validate request
-> reject non-SUMMARY comparison before side access
-> project left role-backed evidence
-> project right role-backed evidence
-> compare the two evidence reports
```

CI #239 passed the full repository workflow.

API regression coverage proves:

- two independently verified recorded OpenSees sides with different NODE IDs compare successfully when metadata is compatible;
- `SERIES` returns `CROSS_SOLVER_OPERATION_NOT_SUPPORTED` before nonexistent side paths are accessed;
- stale Semantic Role Manifest remains `SEMANTIC_ROLE_MODEL_MISMATCH`;
- recorded run/model identity mismatch remains `SEMANTIC_ROLE_RUN_MODEL_MISMATCH`;
- tampered result artifact remains `RESULT_ARTIFACT_HASH_MISMATCH`.

The last three cases prove PR14 does not turn integrity/provenance failures into soft comparison limitations.

### Task 3 — Python Bridge, TypeScript client, Pi SAFE tool

#### RED — CI #240

The TypeScript bridge test was committed before the client existed.

Typecheck failed with exactly:

```text
Module '"@femagent/fem-tools"' has no exported member 'runFemCrossSolverValidation'.
```

No unrelated fixture/type failure was present.

#### GREEN — CI #245

Head:

```text
af198cbfb4b7996afad5b08b7ac7bcc2213a3f76
```

CI #245 passed:

- `pnpm typecheck` — PASS;
- TypeScript — **17/17 PASS**;
- Python — **133/133 PASS**;
- Ruff — PASS;
- OpenSees adapter availability smoke — PASS;
- ANSYS result-reader import smoke — PASS;
- `pnpm fem:health` — PASS.

Python reported **66 existing third-party VTK/NumPy deprecation warnings** from the established ANSYS result-reading paths. There were no test or lint failures.

The TypeScript regressions prove:

- a comparable two-side validation crosses the strict TypeScript/Python bridge;
- different NODE IDs survive in left/right provenance;
- a `SERIES` request crosses the bridge and returns the explicit V1 limitation without touching missing side paths.

## Fixture-backed versus solver-backed evidence

The hosted CI comparable-path tests use deterministic **recorded OpenSees fixtures** for both sides. This validates the cross-model/cross-entity comparison contract without requiring a commercial ANSYS runtime.

The fixtures still exercise the production PR13/PR12 path:

- production Model Intelligence creates each Model Bundle fingerprint;
- production Semantic Role resolver binds each explicit role;
- production Result Intelligence reads and verifies the recorded response artifact;
- production Evidence Center promotes the query;
- production PR14 compares the resulting verified evidence.

Hosted CI does **not** claim that a licensed ANSYS-vs-OpenSees numerical pair was executed for PR14.

The ANSYS result reader import smoke remains green, and existing ANSYS Result Intelligence tests remain in the full regression suite.

## ANSYS unit boundary

Current ANSYS Result Intelligence deliberately reports result units as `null` unless independently proven.

PR14 therefore requires this behavior:

```text
left unit = "m"
right unit = null
-> status = NOT_COMPARABLE
-> comparison = null
-> CROSS_SOLVER_UNIT_UNKNOWN
```

The pure comparison regression includes a null-unit case and proves no numerical delta is produced.

PR14 does not infer ANSYS result units from:

- APDL model conventions;
- load-unit declarations;
- file names;
- result magnitude;
- the other solver's unit.

## Reference-frame boundary

The pure comparison regression also proves:

```text
RELATIVE vs SOLVER_NATIVE
-> NOT_COMPARABLE
-> CROSS_SOLVER_REFERENCE_FRAME_MISMATCH
```

No frame transformation is implemented.

## Numerical formula verification

For compatible peaks:

```text
L = 0.031
R = 0.030
```

tests require:

```text
absoluteDifference = 0.001
relativeDifference = 0.001 / 0.031
```

A separate zero/zero regression requires:

```text
relativeDifference = 0.0
```

The denominator uses `max(abs(L), abs(R))`, so the calculation is symmetric and does not nominate a reference solver.

## Architecture diff checklist

Closeout review requires all of these statements to remain true:

- **solver execution added by PR14:** none;
- **new ANSYS/OpenSees result parser:** none;
- **unit inference:** none;
- **unit conversion:** none;
- **reference-frame transformation:** none;
- **SERIES interpolation/resampling/alignment:** none;
- **abscissa comparison:** none;
- **semantic role inference:** none;
- **semantic manifest write API:** none;
- **solver ranking/trust scoring:** none;
- **ground-truth solver selection:** none;
- **hidden tolerance:** none;
- **engineering PASS/FAIL judgment:** none;
- **optimization/UI/PDF scope:** none.

The Pi tool is read-only and does not acquire the existing real-solver execution permission boundary.

## Limitation/error separation

Comparison limitations are deterministic and non-accusatory:

```text
CROSS_SOLVER_OPERATION_NOT_SUPPORTED
CROSS_SOLVER_SIDE_NOT_VERIFIED
CROSS_SOLVER_ROLE_MISMATCH
CROSS_SOLVER_QUERY_MISMATCH
CROSS_SOLVER_UNIT_UNKNOWN
CROSS_SOLVER_UNIT_MISMATCH
CROSS_SOLVER_REFERENCE_FRAME_MISMATCH
CROSS_SOLVER_METRIC_UNAVAILABLE
```

Upstream integrity/provenance domain errors are preserved rather than translated into these limitations.

`NOT_COMPARABLE` must never be interpreted as evidence that either solver is wrong.

## Final closeout gate

After architecture and verification documentation is committed, the exact final head must freshly pass:

```text
pnpm typecheck
pnpm test:ts
python -m pytest
python -m ruff check fem_core tests/python examples/ansys/golden_path
OpenSees adapter availability smoke
ANSYS result-reader import smoke
pnpm fem:health
```

Expected completed implementation counts before documentation are:

```text
TypeScript: 17 tests
Python: 133 tests
```

Before Draft -> Ready for review, also require:

```text
behind_by = 0
mergeable = true
no unresolved review blocker
final diff within approved PR14 scope
exact-final-head CI = success
```

Ready-for-review is not merge approval. PR14 must remain unmerged until the user explicitly requests merge.
