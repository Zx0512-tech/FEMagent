# PR14 — Cross-Solver Validation V1 Design

## Goal

Add a deterministic, read-only cross-solver validation layer that compares two independently verified FEM responses for the same explicit engineering semantic role without inventing units, choosing a ground-truth solver, applying hidden tolerances, or inferring role mappings.

PR14 builds on three existing trust boundaries:

```text
PR13 Semantic Role Manifest
    -> explicit engineering role -> solver-native NODE

PR9 Result Intelligence
    -> deterministic recorded result query

PR12 Engineering Evidence Center
    -> artifact-backed VERIFIED engineering evidence
```

The V1 comparison path is:

```text
left solver side                              right solver side
model + semantic manifest + recorded run      model + semantic manifest + recorded run
        |                                             |
        v                                             v
PR13 role resolution                           PR13 role resolution
        |                                             |
        v                                             v
run/model identity gate                        run/model identity gate
        |                                             |
        v                                             v
PR12 role-backed VERIFIED evidence             PR12 role-backed VERIFIED evidence
        \                                             /
         \                                           /
          +-------- Cross-Solver Validation --------+
                          |
                          v
          COMPARABLE or NOT_COMPARABLE record
```

PR14 does not run either solver. It compares only existing recorded evidence.

## Architectural decision

PR14 uses an **Evidence-first strict comparison** model.

Each side is independently resolved and verified before comparison. The comparison layer never reads ANSYS `.rst` files or OpenSees CSV files directly and never creates a second result parser. It consumes the role-backed Engineering Evidence reports produced through PR13/PR12.

This preserves a clean responsibility split:

- PR13 decides what solver-native entity an explicit engineering role refers to for one exact model;
- Result Intelligence decides what a recorded run/result artifact contains;
- PR12 decides whether a numerical result is backed by auditable artifacts;
- PR14 decides only whether two verified evidence records are compatible enough to compare and, if so, calculates deterministic deltas.

## Alternatives considered

### A. Evidence-first strict summary comparison — selected

Compare only already-verified `SUMMARY` evidence and require exact compatibility of semantic role, quantity, component, unit, and reference frame.

Advantages:

- deterministic and auditable;
- no duplicate result parsing;
- no hidden unit conversion;
- no solver ranking;
- immediately useful for ANSYS/OpenSees checks where comparable metadata is actually known.

Cost:

- many current ANSYS-vs-OpenSees cases will correctly be `NOT_COMPARABLE` because ANSYS result units remain `null` unless proven.

### B. Normalize units automatically — rejected for V1

Automatic conversion would require a trusted unit contract for both result sets. Current Result Intelligence intentionally leaves ANSYS units `null` when they are not proven. Treating model/load conventions as result-unit truth would violate the existing architecture.

### C. Time-history alignment/resampling — rejected for V1

OpenSees controlled response uses time in seconds, while ANSYS result-set abscissa remains solver-native unless independently proven. V1 therefore does not resample, interpolate, phase-align, or compare full SERIES traces.

## Scope

### Included

- two-side cross-solver validation request;
- independent PR13 role resolution for each side;
- independent PR12 role-backed Engineering Evidence projection for each side;
- exact compatibility checks;
- deterministic comparison of `summary.absolutePeak` only;
- absolute difference;
- symmetric relative difference;
- explicit `COMPARABLE` / `NOT_COMPARABLE` status;
- deterministic limitation reason codes;
- Python API;
- existing Python/TypeScript bridge integration;
- TypeScript types/client;
- Pi SAFE read-only tool;
- TDD regression coverage;
- architecture/verification documentation.

### Excluded

- solver execution;
- automatic unit inference or conversion;
- SERIES interpolation/resampling/alignment;
- comparison of abscissa-at-peak values;
- tolerance-based pass/fail;
- solver ranking or trust scoring;
- declaration that one solver is ground truth;
- automatic semantic-role inference;
- manifest writes;
- ELEMENT semantic roles;
- optimization;
- UI/dashboard/PDF reporting.

## Input model

The cross-solver API receives two explicit sides plus one shared result query.

Conceptual request:

```json
{
  "projectId": "bridge-demo",
  "left": {
    "modelPath": "ansys/model.inp",
    "manifestPath": "ansys/semantic-roles.json",
    "roleId": "TOWER_BASE_LEFT",
    "runRef": "run_ansys001"
  },
  "right": {
    "modelPath": "opensees/model.py",
    "manifestPath": "opensees/semantic-roles.json",
    "roleId": "TOWER_BASE_LEFT",
    "runRef": "run_ops001"
  },
  "query": {
    "quantity": "DISPLACEMENT",
    "component": "X",
    "operation": "SUMMARY"
  }
}
```

The two sides may have:

- different solver names;
- different Model Bundle fingerprints;
- different solver-native NODE IDs;
- different result artifact formats.

That difference is expected. Cross-solver identity is established by the explicit semantic role, not by node numbering or model fingerprint equality across solvers.

## Side validation pipeline

For each side, PR14 calls the existing role-backed evidence path rather than reconstructing it.

Conceptually:

```python
project_role_evidence(
    workspace,
    project_id=...,
    model_path=...,
    manifest_path=...,
    role_id=...,
    run_ref=...,
    evidence_id=...,
    quantity=...,
    component=...,
    operation="SUMMARY",
)
```

This already guarantees:

1. the semantic manifest is valid;
2. the manifest fingerprint matches that side's current Model Bundle;
3. the declared semantic role resolves to a NODE;
4. the recorded run belongs to the same Model Bundle as that side's semantic mapping;
5. Result Intelligence validates declared result artifacts;
6. the result query succeeds;
7. PR12 evidence promotion determines whether the evidence is `VERIFIED`.

PR14 must not bypass any of these gates.

## Comparison status model

PR14 uses a comparison-specific status independent of PR12 Evidence status and PR13 Semantic status.

```text
COMPARABLE
NOT_COMPARABLE
```

### COMPARABLE

Both sides have exactly one usable `VERIFIED` evidence record and all V1 compatibility checks pass.

A `COMPARABLE` record may contain numerical deltas.

### NOT_COMPARABLE

Both side pipelines may have succeeded and produced valid evidence, but V1 lacks enough compatible metadata to calculate a meaningful numerical comparison.

Examples:

- one or both units are `null`;
- units differ;
- reference frames differ;
- role IDs or role types differ;
- quantity/component/operation differ from the required common contract;
- the request is not `SUMMARY`.

`NOT_COMPARABLE` is not an integrity failure. It is an explicit limitation record.

## Fail-closed errors versus limitations

Existing deterministic domain errors continue to propagate and are not converted into `NOT_COMPARABLE`.

Examples that remain hard errors:

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

This distinction is important:

- invalid/stale/tampered evidence -> error;
- valid evidence that cannot be safely compared -> `NOT_COMPARABLE`.

## Compatibility checks

The comparison layer evaluates compatibility in deterministic order.

### 1. Operation

V1 accepts only:

```text
SUMMARY
```

A non-SUMMARY request returns `NOT_COMPARABLE` with:

```text
CROSS_SOLVER_OPERATION_NOT_SUPPORTED
```

No SERIES query is issued by the V1 comparison path when the request is unsupported.

### 2. Evidence promotion

Each side must expose exactly one `VERIFIED` evidence record for the requested role/query.

If a side returns no verified evidence, comparison returns `NOT_COMPARABLE` with:

```text
CROSS_SOLVER_SIDE_NOT_VERIFIED
```

This does not replace hard Result Intelligence integrity errors; those still propagate before this stage.

### 3. Semantic role identity

The two evidence records must have the same exact:

```text
semanticRole.roleId
semanticRole.roleType
```

Different NODE IDs are allowed and expected.

Mismatch reason:

```text
CROSS_SOLVER_ROLE_MISMATCH
```

### 4. Quantity and component

The two evidence metrics must have the same exact normalized:

```text
quantity
component
operation
```

Mismatch reason:

```text
CROSS_SOLVER_QUERY_MISMATCH
```

### 5. Unit

Both evidence metrics must contain a non-null string unit and the strings must match exactly.

If either unit is null:

```text
CROSS_SOLVER_UNIT_UNKNOWN
```

If both are known but differ:

```text
CROSS_SOLVER_UNIT_MISMATCH
```

PR14 performs no conversion.

### 6. Reference frame

Both evidence metrics must expose the same non-empty `referenceFrame` string.

Mismatch or missing frame:

```text
CROSS_SOLVER_REFERENCE_FRAME_MISMATCH
```

No transformation between `RELATIVE`, `ABSOLUTE`, or `SOLVER_NATIVE` frames is attempted.

### 7. Summary value

Both evidence records must contain finite numeric:

```text
metric.summary.absolutePeak
```

If not:

```text
CROSS_SOLVER_METRIC_UNAVAILABLE
```

## Numerical comparison

V1 compares only `absolutePeak`.

Let:

```text
L = left absolutePeak
R = right absolutePeak
```

Then:

```text
absoluteDifference = abs(L - R)
```

The symmetric relative difference is:

```text
scale = max(abs(L), abs(R))
relativeDifference = 0.0                      if scale == 0
relativeDifference = absoluteDifference/scale otherwise
```

Properties:

- independent of which solver is placed on the left/right;
- bounded to `[0, 2]` for arbitrary signed inputs and `[0, 1]` for non-negative absolute peaks;
- does not imply either side is correct;
- no percentage tolerance is built in.

Because `absolutePeak` is non-negative by Result Intelligence definition, normal V1 relative difference is in `[0, 1]`.

## Output schema

Comparable example:

```json
{
  "schemaVersion": "1.0",
  "kind": "cross_solver_validation",
  "status": "COMPARABLE",
  "projectId": "bridge-demo",
  "role": {
    "roleId": "TOWER_BASE_LEFT",
    "roleType": "TOWER_BASE"
  },
  "query": {
    "quantity": "DISPLACEMENT",
    "component": "X",
    "operation": "SUMMARY"
  },
  "sides": {
    "left": {
      "solver": "OPENSEESPY",
      "runId": "run_ops001",
      "modelBundleFingerprint": "...",
      "entity": {"type": "NODE", "id": 17},
      "unit": "m",
      "referenceFrame": "RELATIVE",
      "absolutePeak": 0.031
    },
    "right": {
      "solver": "OPENSEESPY",
      "runId": "run_ops002",
      "modelBundleFingerprint": "...",
      "entity": {"type": "NODE", "id": 1024},
      "unit": "m",
      "referenceFrame": "RELATIVE",
      "absolutePeak": 0.030
    }
  },
  "comparison": {
    "metric": "absolutePeak",
    "left": 0.031,
    "right": 0.030,
    "absoluteDifference": 0.001,
    "relativeDifference": 0.03225806451612903
  },
  "limitations": []
}
```

A V1 validation may compare two runs produced by the same solver as a deterministic regression case, but the intended architecture supports different solvers. The comparison contract is solver-neutral.

Not-comparable example:

```json
{
  "schemaVersion": "1.0",
  "kind": "cross_solver_validation",
  "status": "NOT_COMPARABLE",
  "projectId": "bridge-demo",
  "role": {
    "roleId": "TOWER_BASE_LEFT",
    "roleType": "TOWER_BASE"
  },
  "query": {
    "quantity": "DISPLACEMENT",
    "component": "X",
    "operation": "SUMMARY"
  },
  "sides": {
    "left": {"...": "..."},
    "right": {"...": "..."}
  },
  "comparison": null,
  "limitations": [
    {
      "code": "CROSS_SOLVER_UNIT_UNKNOWN",
      "message": "Both sides require proven result units before numerical comparison"
    }
  ]
}
```

## Core Python package

Add a focused package:

```text
fem_core/cross_solver/
  __init__.py
  models.py
  validation.py
  api.py
```

### `models.py`

Contains comparison status and stable limitation-code constants only. It does not contain solver-specific logic.

### `validation.py`

Contains pure deterministic extraction/compatibility/comparison helpers over two role-backed Evidence reports.

It must not:

- inspect model files;
- read result artifacts;
- run solvers;
- infer units;
- resolve semantic roles directly.

### `api.py`

Public orchestration API:

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

Responsibilities:

1. validate the V1 request shape;
2. reject/limit unsupported operation before unnecessary result queries;
3. call `project_role_evidence()` independently for left and right;
4. pass the resulting reports to the pure comparison layer;
5. return deterministic validation JSON.

## Request validation

Required side fields:

```text
modelPath
manifestPath
roleId
runRef
```

Required query fields:

```text
quantity
component
operation
```

Missing/empty values fail with the existing bridge/request validation convention or a focused:

```text
INVALID_CROSS_SOLVER_VALIDATION_REQUEST
```

PR14 does not accept caller-provided numerical values, result hashes, units, or semantic-role metadata.

## Bridge API

Add one Python bridge command:

```text
validation.crossSolver
```

Payload:

```json
{
  "projectId": "bridge-demo",
  "left": {...},
  "right": {...},
  "query": {...}
}
```

The bridge does no comparison logic itself.

## TypeScript client

Add focused types, preferably:

```text
packages/fem-tools/src/validationTypes.ts
```

and client:

```text
runFemCrossSolverValidation()
```

The public TypeScript schema should preserve:

- status;
- role identity;
- query;
- left/right side provenance;
- comparison or `null`;
- limitation codes/messages.

## Pi SAFE tool

Add a separate read-only extension file or use the existing semantic-focused extension only if it remains small and coherent. Preferred V1 tool name:

```text
fem_cross_solver_validate
```

Prompt contract must explicitly state:

- use only explicit semantic manifests;
- do not infer or rewrite role mappings;
- do not execute either solver;
- do not infer or convert result units;
- do not treat one solver as ground truth;
- do not declare pass/fail without an explicit future tolerance policy;
- `NOT_COMPARABLE` is a limitation, not evidence that one solver is wrong;
- preserve Result Intelligence / Evidence / Semantic domain errors.

## ANSYS unit boundary

A primary V1 acceptance case is intentionally non-comparable:

```text
OpenSees evidence unit = "m"
ANSYS evidence unit = null
```

Expected result:

```text
status = NOT_COMPARABLE
limitation = CROSS_SOLVER_UNIT_UNKNOWN
comparison = null
```

PR14 must not reinterpret ANSYS model units, input command units, load units, or value magnitude as proof of result units.

## Reference-frame boundary

Example:

```text
left.referenceFrame = RELATIVE
right.referenceFrame = SOLVER_NATIVE
```

Even if both units are known and identical, V1 returns:

```text
NOT_COMPARABLE
CROSS_SOLVER_REFERENCE_FRAME_MISMATCH
```

No coordinate/reference transformation is introduced.

## Semantic identity boundary

The same engineering role across two solver models may resolve to different nodes:

```text
TOWER_BASE_LEFT
  -> ANSYS NODE 1024
  -> OpenSees NODE 17
```

That is valid.

The following is not V1-comparable:

```text
left  -> TOWER_BASE_LEFT / TOWER_BASE
right -> GIRDER_END_A / GIRDER_END
```

Role mismatch returns `NOT_COMPARABLE`; PR14 never tries to decide that the two locations are “close enough.”

## No pass/fail policy in V1

PR14 reports differences; it does not judge acceptance.

It does not embed thresholds such as:

```text
5%
10%
correlation > 0.95
```

A future validation-policy layer may accept an explicit user/project tolerance and turn a comparison into an acceptance decision. That is not PR14 V1.

## Determinism

Given identical:

- left/right model bundles;
- semantic manifest bytes;
- recorded run manifests/result artifacts;
- query;

PR14 must return identical comparison JSON.

The comparison layer contains no stochastic algorithm and no LLM-authored engineering conclusion.

## TDD acceptance scenarios

### Scenario 1 — comparable same-role summary

Two independently verified role-backed evidence records have:

- same `roleId` / `roleType`;
- different NODE IDs allowed;
- same quantity/component/operation;
- same known unit;
- same reference frame;
- finite `absolutePeak`.

Expected:

```text
COMPARABLE
absoluteDifference calculated
relativeDifference calculated symmetrically
```

### Scenario 2 — node IDs differ

Left NODE 17 and right NODE 1024 represent the same explicit `TOWER_BASE_LEFT` role.

Expected: node-number mismatch alone does not block comparison.

### Scenario 3 — ANSYS unit unknown

One side unit is `null`.

Expected:

```text
NOT_COMPARABLE
CROSS_SOLVER_UNIT_UNKNOWN
comparison = null
```

### Scenario 4 — known units differ

Expected:

```text
NOT_COMPARABLE
CROSS_SOLVER_UNIT_MISMATCH
```

No conversion.

### Scenario 5 — reference frame differs

Expected:

```text
NOT_COMPARABLE
CROSS_SOLVER_REFERENCE_FRAME_MISMATCH
```

### Scenario 6 — semantic role mismatch

Expected:

```text
NOT_COMPARABLE
CROSS_SOLVER_ROLE_MISMATCH
```

### Scenario 7 — stale/wrong run-model identity

Existing PR13 error propagates:

```text
SEMANTIC_ROLE_RUN_MODEL_MISMATCH
```

No comparison record is fabricated.

### Scenario 8 — artifact tampering

Existing Result Intelligence error propagates:

```text
RESULT_ARTIFACT_HASH_MISMATCH
```

### Scenario 9 — unsupported SERIES operation

Expected:

```text
NOT_COMPARABLE
CROSS_SOLVER_OPERATION_NOT_SUPPORTED
```

V1 performs no alignment/resampling.

### Scenario 10 — zero/zero peaks

Expected:

```text
absoluteDifference = 0.0
relativeDifference = 0.0
```

## Verification gate

Final PR14 head must pass the full existing repository gate:

```text
pnpm typecheck
pnpm test:ts
python -m pytest
python -m ruff check fem_core tests/python examples/ansys/golden_path
OpenSees adapter availability smoke
ANSYS result-reader import smoke
pnpm fem:health
```

PR14 must retain explicit RED -> GREEN evidence for each major implementation slice.

## Expected file surface

```text
fem_core/cross_solver/__init__.py
fem_core/cross_solver/models.py
fem_core/cross_solver/validation.py
fem_core/cross_solver/api.py
fem_core/bridge.py
packages/fem-tools/src/validationTypes.ts
packages/fem-tools/src/pythonBridge.ts
packages/fem-tools/src/index.ts
.pi/extensions/validation-tools.ts
tests/python/test_cross_solver_validation.py
tests/ts/cross-solver-validation.test.ts
docs/architecture/cross-solver-validation.md
docs/verification/pr14-cross-solver-validation.md
```

Existing semantic/result/evidence production modules should be modified only when a narrow reusable interface is genuinely required. PR14 should not expand their responsibilities.

## Completion criteria

PR14 is complete when:

1. each side is independently resolved and projected through existing role-backed verified evidence;
2. different solver NODE IDs can represent the same engineering role;
3. only compatible verified SUMMARY evidence produces numerical deltas;
4. unknown/different units produce `NOT_COMPARABLE`, never guessed conversion;
5. different reference frames produce `NOT_COMPARABLE`;
6. semantic mismatch produces `NOT_COMPARABLE` without heuristic remapping;
7. integrity/model-identity failures propagate fail-closed;
8. no solver is treated as ground truth;
9. no tolerance/pass-fail policy is embedded;
10. Bridge/TypeScript/Pi surfaces remain read-only;
11. exact final head passes full CI;
12. PR remains open until explicit user merge instruction.
