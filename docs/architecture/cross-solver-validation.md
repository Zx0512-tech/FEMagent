# Cross-Solver Validation V1

## Purpose

Cross-Solver Validation V1 compares two independently verified FEM responses that represent the same explicit engineering semantic role.

It is deliberately a validation layer, not a solver, result reader, unit converter, calibration engine, or engineering acceptance policy.

```text
left model + manifest + recorded run         right model + manifest + recorded run
              |                                            |
              v                                            v
       PR13 Semantic Roles                          PR13 Semantic Roles
              |                                            |
              v                                            v
       role -> solver NODE                         role -> solver NODE
              |                                            |
              v                                            v
       run/model identity                           run/model identity
              |                                            |
              v                                            v
 PR12 role-backed VERIFIED Evidence       PR12 role-backed VERIFIED Evidence
              \                                            /
               \                                          /
                +------ Cross-Solver Validation ----------+
                                  |
                                  v
                      COMPARABLE / NOT_COMPARABLE
```

PR14 never executes either solver.

## Evidence-first boundary

`validate_cross_solver()` does not accept numerical values, artifact hashes, units, NODE IDs, or semantic metadata from the caller.

For each side it delegates to the existing production path:

```text
explicit Semantic Role Manifest
-> exact current Model Bundle fingerprint
-> explicit roleId -> NODE resolution
-> recorded run Model Bundle identity check
-> Result Intelligence artifact/query validation
-> PR12 Engineering Evidence promotion
```

Only after both side reports exist does the pure comparison layer inspect their verified evidence metadata.

This preserves ownership:

- PR13 owns engineering semantic identity;
- Result Intelligence owns recorded numerical result interpretation;
- PR12 owns artifact-backed evidence promotion;
- PR14 owns compatibility checking and deterministic deltas only.

## Public Python API

```python
validate_cross_solver(
    workspace: Path,
    *,
    project_id: str,
    left: dict[str, str],
    right: dict[str, str],
    query: dict[str, Any],
) -> dict[str, Any]
```

Each side requires:

```text
modelPath
manifestPath
roleId
runRef
```

The shared query requires:

```text
quantity
component
operation
```

V1 supports comparison only when `operation == SUMMARY`.

A `SERIES` request returns `NOT_COMPARABLE` before either side's model, semantic manifest, or recorded result path is accessed.

## Pure comparison core

`fem_core.cross_solver.validation.compare_role_evidence_reports()` is intentionally pure with respect to the FEM workspace.

It does not:

- inspect model files;
- resolve roles;
- read result artifacts;
- hash files;
- parse ANSYS binary results;
- parse OpenSees response CSV;
- run a solver;
- convert units.

It receives two role-backed Engineering Evidence reports and checks compatibility in stable order.

## Compatibility order

V1 returns the first deterministic limitation in this order:

1. exactly one `VERIFIED` evidence record exists on each side;
2. `semanticRole.roleId` and `semanticRole.roleType` match;
3. quantity/component/operation match each other and the common request;
4. both result units are known;
5. units match exactly;
6. reference frames are present and match exactly;
7. `metric.summary.absolutePeak` is finite on both sides.

Stable limitation codes are:

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

## Semantic identity across solvers

Different solver-native identities are expected.

For example:

```text
TOWER_BASE_LEFT
  ANSYS model     -> NODE 1024
  OpenSees model  -> NODE 17
```

PR14 never requires NODE IDs or Model Bundle fingerprints to match across solver sides.

Instead, each side independently proves its explicit role mapping against its own exact Model Bundle, and PR14 then requires the role ID/type to agree.

This is the first FEMagent layer where solver-specific model identities can participate in one common engineering comparison without pretending their native entity numbering is shared.

## Comparison status

PR14 defines comparison-specific status independently from PR12 Evidence status and PR13 Semantic status:

```text
COMPARABLE
NOT_COMPARABLE
```

### COMPARABLE

Both sides contain compatible verified evidence. A numerical comparison is emitted.

### NOT_COMPARABLE

The supplied evidence may be valid but V1 does not have sufficient compatible metadata for a meaningful numerical comparison.

`NOT_COMPARABLE` does not mean either solver is wrong.

## Hard failures remain hard failures

Semantic, provenance, and result-integrity failures are not converted into comparison limitations.

Examples include:

```text
INVALID_SEMANTIC_ROLE_MANIFEST
SEMANTIC_ROLE_MODEL_MISMATCH
SEMANTIC_ROLE_NOT_FOUND
SEMANTIC_ROLE_ENTITY_NOT_FOUND
SEMANTIC_ROLE_RUN_MODEL_MISMATCH
RESULT_ARTIFACT_HASH_MISMATCH
INVALID_RESULT_QUERY
RESULT_SERIES_UNAVAILABLE
```

This keeps the distinction clear:

```text
invalid / stale / tampered evidence -> domain error
valid evidence lacking compatibility -> NOT_COMPARABLE
```

## Numerical metric

V1 compares only:

```text
metric.summary.absolutePeak
```

Let the left and right values be `L` and `R`.

```text
absoluteDifference = abs(L - R)
scale = max(abs(L), abs(R))
relativeDifference = 0.0 if scale == 0 else absoluteDifference / scale
```

The relative difference is symmetric. Swapping left/right does not change it.

Neither side is defined as a reference truth.

PR14 does not provide a tolerance and therefore does not return engineering PASS/FAIL.

## Unit boundary

Both evidence records must expose the same non-null unit string.

No conversion is performed.

The important current ANSYS/OpenSees case is:

```text
OpenSees Result Intelligence unit = "m"
ANSYS Result Intelligence unit    = null
```

PR14 must return:

```text
status = NOT_COMPARABLE
comparison = null
limitation = CROSS_SOLVER_UNIT_UNKNOWN
```

It must not derive ANSYS result units from model conventions, APDL input assumptions, load units, filenames, magnitude, or the other solver.

## Reference-frame boundary

Reference frames must also match exactly.

For example:

```text
RELATIVE != SOLVER_NATIVE
```

PR14 does not transform coordinate/reference frames and therefore returns `CROSS_SOLVER_REFERENCE_FRAME_MISMATCH` for that case.

## No time-history alignment in V1

Current OpenSees controlled responses use time in seconds, while ANSYS binary-result abscissa remains solver-native unless independently proven.

Therefore V1 does not:

- compare SERIES values;
- interpolate or resample;
- synchronize time points;
- align phases;
- compare peak occurrence abscissae;
- assume ANSYS result-set abscissa is seconds.

These require a later explicit alignment/unit contract.

## Bridge and TypeScript contract

Python bridge command:

```text
validation.crossSolver
```

TypeScript client:

```text
runFemCrossSolverValidation()
```

Types live in:

```text
packages/fem-tools/src/validationTypes.ts
```

The bridge contains no validation math. It only forwards the typed request to the deterministic Python API.

## Pi SAFE tool

PR14 registers:

```text
fem_cross_solver_validate
```

in:

```text
.pi/extensions/validation-tools.ts
```

The tool is read-only and carries no solver execution permission.

Its prompt contract forbids:

- semantic role guessing;
- manifest rewriting;
- unit inference/conversion;
- treating one solver as ground truth;
- solver ranking;
- hidden tolerance judgments;
- describing `NOT_COMPARABLE` as solver failure;
- swallowing upstream integrity errors.

## Determinism

Given identical:

- Model Bundle bytes;
- Semantic Role Manifest bytes;
- recorded run manifests/artifacts;
- shared result query;

PR14 returns the same compatibility result and the same numerical deltas.

The comparison layer does not call an LLM.

## V1 non-goals

PR14 intentionally excludes:

- solver execution;
- automatic role inference;
- semantic manifest writes;
- ELEMENT roles;
- unit inference or conversion;
- coordinate/reference-frame transformation;
- SERIES alignment/resampling/interpolation;
- solver ranking/trust scoring;
- ground-truth selection;
- tolerance policies;
- engineering PASS/FAIL decisions;
- optimization runtime;
- UI/dashboard/PDF generation.

Those are separate future capabilities and require their own evidence contracts.
