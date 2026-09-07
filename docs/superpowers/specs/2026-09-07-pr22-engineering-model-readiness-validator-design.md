# PR22 — Engineering Model Readiness Validator Design

Date: 2026-09-07
Roadmap label: PR22
Branch: `feat/pr22-engineering-model-readiness`
Dependency: PR21 — Engineering Model Specification V1
Stacked base while PR21 is open: `feat/pr21-engineering-model-spec-v1`

## 1. Goal

PR22 adds a deterministic **Engineering Model Readiness Validator** between PR21 ModelSpec validation and future solver-specific renderers.

PR21 answers:

> Is this `EngineeringModelSpec` structurally well-formed, internally consistent, and fingerprintable?

PR22 answers:

> Given a PR21-valid 2D elastic frame ModelSpec, is the model sufficiently restrained and structurally connected to be admitted to a deterministic renderer without relying on a solver failure to discover obvious rigid-body defects?

PR22 must reduce preventable renderer/solver failures while preserving FEMagent's trust boundary:

- no solver execution;
- no stiffness-matrix assembly;
- no hidden engineering defaults;
- no geometry mutation;
- no unit guessing;
- no semantic-role inference;
- no RAG dependency.

## 2. Why PR22 exists after PR21

PR21 already owns strict schema validation, references, positive material/section properties, exact zero-length checks, constraints, nodal masses, normalization, and `modelSpecFingerprint`.

A PR21-valid model can still be unsuitable for rendering and later analysis. Examples include:

- a completely unrestrained frame;
- two disconnected frame components where one component is free;
- an isolated unused node that remains unconstrained;
- support DOFs that exist but do not eliminate all three planar rigid-body modes;
- duplicate/parallel connectivity that is legal but suspicious and deserves explicit visibility.

PR22 therefore adds **engineering readiness**, not another copy of PR21 schema validation.

## 3. Considered approaches

### Approach A — deterministic graph + exact rigid-body rank analysis — selected

Use the normalized PR21 ModelSpec to build connected components and an exact rigid-body constraint matrix for each component.

For a 2D frame component, the three rigid-body generalized motions are:

```text
q = [TX, TY, RZ]
```

At a node `(x, y)`, the constrained DOFs contribute these rows:

```text
UX -> [1, 0, -y]
UY -> [0, 1,  x]
RZ -> [0, 0,  1]
```

A component is globally restrained when the constraint-row matrix has rank 3.

Advantages:

- deterministic;
- solver-neutral;
- directly tied to the current PR21 2D frame element family;
- no solver call;
- no stiffness matrix;
- no arbitrary engineering tolerance is required if exact decimal arithmetic is used;
- identifies defects before renderer execution.

Limitation:

- the conclusion is intentionally limited to PR21 V1 elastic 2D frame elements without releases, hinges, springs, contact, nonlinearities, or multi-point constraints.

### Approach B — assemble stiffness matrix and check numerical rank/eigenvalues — rejected for V1

This is more general in theory, but it begins to reproduce a finite-element solver inside the validator and immediately introduces numerical tolerances, conditioning decisions, element stiffness implementations, and solver-like semantics.

That violates PR22's intended role and would make the validation layer harder to audit than necessary.

### Approach C — rely on renderer/build-only/solver failures — rejected

This keeps PR22 trivial but pushes basic engineering defects downstream. It weakens future controlled repair because singularity-like failures would first appear as renderer or solver feedback rather than deterministic pre-render issues.

## 4. Architecture

```text
EngineeringModelSpec
        |
        v
PR21 validate_engineering_model_spec()
        |
        +-- INVALID --------------------------+
        |                                     |
        v                                     v
normalizedSpec                         INVALID_SPEC
modelSpecFingerprint                  readiness result
        |
        v
PR22 evaluate_engineering_model_readiness()
        |
        +-- graph components
        +-- exact rigid-body restraint rank
        +-- parallel connectivity diagnostics
        |
        v
READY / NOT_READY
        |
        v
future PR23 OpenSees Renderer
```

Python `fem_core` remains the sole authoritative deterministic engineering implementation.

TypeScript and Pi layers transport the request/result but do not reimplement engineering readiness logic.

## 5. Public Python contract

Add a new deterministic entry point under the ModelSpec subsystem:

```python
def evaluate_engineering_model_readiness(spec: dict[str, Any]) -> dict[str, Any]:
    ...
```

The function accepts the raw ModelSpec object and **always invokes PR21 validation internally**.

This prevents callers from bypassing PR21 validation.

The readiness implementation may only operate on `validation["normalizedSpec"]` when PR21 returned `VALID`.

## 6. Result schema

PR22 returns:

```json
{
  "schema": "FEMAGENT_MODEL_SPEC_READINESS_V1",
  "status": "READY",
  "profile": "FRAME_2D_ELASTIC_READINESS_V1",
  "modelSpecFingerprint": "...",
  "validation": {
    "schema": "FEMAGENT_MODEL_SPEC_VALIDATION_V1",
    "status": "VALID",
    "issues": []
  },
  "checks": {
    "connectivity": {
      "status": "PASS",
      "componentCount": 1,
      "components": [
        {
          "index": 0,
          "nodeIds": [1, 2, 3, 4],
          "elementIds": [1, 2, 3]
        }
      ]
    },
    "rigidBodyRestraint": {
      "status": "PASS",
      "requiredRankPerComponent": 3,
      "components": [
        {
          "index": 0,
          "constraintRank": 3,
          "deficiency": 0
        }
      ]
    },
    "parallelConnectivity": {
      "status": "PASS",
      "groups": []
    }
  },
  "issues": []
}
```

### 6.1 Overall status

Allowed values:

```text
READY
NOT_READY
INVALID_SPEC
```

Rules:

- `INVALID_SPEC`: PR21 validation is `INVALID`; readiness checks are not performed.
- `NOT_READY`: PR21 validation is `VALID`, but at least one PR22 readiness `ERROR` exists.
- `READY`: PR21 validation is `VALID` and there are no PR22 readiness `ERROR`s. Warnings are allowed.

PR22 does not redefine PR21's `VALID | INVALID` semantics.

### 6.2 Check status

Individual readiness checks use:

```text
PASS
WARN
FAIL
SKIPPED
```

`SKIPPED` is used only when PR21 validation blocks readiness evaluation.

## 7. Validation passthrough

The readiness result exposes a compact PR21 validation summary:

```json
{
  "schema": "FEMAGENT_MODEL_SPEC_VALIDATION_V1",
  "status": "VALID",
  "issues": []
}
```

It does not duplicate `normalizedSpec` in the readiness response.

`modelSpecFingerprint` is copied from PR21 without recalculation.

PR22 must never modify the normalized ModelSpec or fingerprint.

## 8. Connectivity model

### 8.1 Graph definition

All ModelSpec nodes are graph vertices.

Every frame element creates an undirected edge between `nodeI` and `nodeJ`.

This intentionally includes unused nodes as singleton connected components.

Reason: a renderer that materializes an unconstrained isolated node can still introduce zero-stiffness DOFs. PR22 should not silently ignore such nodes.

### 8.2 Deterministic connected components

Connected components are produced deterministically:

1. nodes are considered in ascending node ID order;
2. adjacency lists are sorted by node ID;
3. component nodes are sorted ascending;
4. component elements are sorted ascending;
5. final components are sorted by their smallest node ID;
6. the returned `index` is the zero-based position in that final order.

### 8.3 Multiple components

More than one component is not automatically invalid.

PR22 emits:

```text
severity: WARNING
code: MODEL_READINESS_DISCONNECTED_COMPONENTS
```

The model may still be `READY` if **every** component independently passes the rigid-body restraint check.

This preserves legitimate multi-component modeling while exposing the topology explicitly.

## 9. Exact planar rigid-body restraint check

### 9.1 Scope

PR21 V1 frame elements have positive `E`, `A`, and `Iz`, nonzero length, Euler-Bernoulli behavior, and no releases or nonlinear connection features.

Within that scope, a connected frame component's element stiffness nullspace is limited to the component's planar rigid-body motions. Therefore PR22 can check global restraint sufficiency without implementing full FE stiffness assembly.

This claim must not be generalized to future truss, spring, hinge, release, shell, solid, contact, or nonlinear models.

### 9.2 Constraint matrix

For each component, collect only constraints belonging to nodes in that component.

For node `(x, y)`, add one row per constrained DOF:

```text
UX: [1, 0, -y]
UY: [0, 1,  x]
RZ: [0, 0,  1]
```

A component is restrained when:

```text
rank(C) == 3
```

The returned diagnostics include:

```json
{
  "index": 0,
  "constraintRank": 2,
  "deficiency": 1
}
```

A rank below 3 emits:

```text
severity: ERROR
code: MODEL_READINESS_RIGID_BODY_RESTRAINT_INSUFFICIENT
```

The overall readiness status becomes `NOT_READY`.

### 9.3 No hidden numerical tolerance

PR22 must not use `numpy.linalg.matrix_rank`, floating-point eigenvalue thresholds, or a hidden epsilon.

Coordinates are converted using the canonical decimal text of the normalized JSON number and evaluated with exact `decimal.Decimal` arithmetic.

Rank is determined using deterministic Gaussian elimination over the at-most-three-column constraint matrix with exact zero comparison.

This avoids an undocumented tolerance becoming an engineering rule.

## 10. Parallel connectivity diagnostics

Two or more elements may connect the same unordered node pair.

That can be intentional, so PR22 must **not** reject it automatically.

For each repeated unordered pair, return a deterministic group:

```json
{
  "nodeIds": [2, 5],
  "elementIds": [7, 12]
}
```

and emit:

```text
severity: WARNING
code: MODEL_READINESS_PARALLEL_CONNECTIVITY
```

This causes `parallelConnectivity.status = WARN` but does not by itself make the model `NOT_READY`.

## 11. Readiness issue contract

Readiness issues use the same structural shape as PR21 issues:

```json
{
  "severity": "ERROR",
  "code": "MODEL_READINESS_RIGID_BODY_RESTRAINT_INSUFFICIENT",
  "path": "components[0]",
  "message": "..."
}
```

V1 readiness codes are limited to:

```text
MODEL_READINESS_INVALID_SPEC
MODEL_READINESS_DISCONNECTED_COMPONENTS
MODEL_READINESS_RIGID_BODY_RESTRAINT_INSUFFICIENT
MODEL_READINESS_PARALLEL_CONNECTIVITY
```

No free-form issue category should be required by downstream repair logic.

## 12. Invalid-spec behavior

If PR21 returns `INVALID`:

```json
{
  "schema": "FEMAGENT_MODEL_SPEC_READINESS_V1",
  "status": "INVALID_SPEC",
  "profile": "FRAME_2D_ELASTIC_READINESS_V1",
  "modelSpecFingerprint": null,
  "validation": {
    "schema": "FEMAGENT_MODEL_SPEC_VALIDATION_V1",
    "status": "INVALID",
    "issues": ["..."]
  },
  "checks": {
    "connectivity": {"status": "SKIPPED", "componentCount": 0, "components": []},
    "rigidBodyRestraint": {"status": "SKIPPED", "requiredRankPerComponent": 3, "components": []},
    "parallelConnectivity": {"status": "SKIPPED", "groups": []}
  },
  "issues": [
    {
      "severity": "ERROR",
      "code": "MODEL_READINESS_INVALID_SPEC",
      "path": "",
      "message": "Engineering readiness requires a PR21-valid ModelSpec"
    }
  ]
}
```

PR21 validation issues remain in the nested `validation.issues`; PR22 does not copy or reinterpret every schema issue.

## 13. Bridge contract

Add a new bridge command:

```text
modelSpec.readiness
```

Input:

```json
{
  "spec": {"...": "EngineeringModelSpec"}
}
```

Rules:

- `payload.spec` must be a JSON object;
- malformed bridge payloads use existing bridge/domain error handling;
- a PR21-invalid ModelSpec returns a successful bridge envelope containing `status = INVALID_SPEC`;
- a PR21-valid but under-restrained model returns a successful bridge envelope containing `status = NOT_READY`;
- readiness findings are not transport errors.

## 14. TypeScript contract

Add TypeScript result types under the existing ModelSpec type boundary.

Public transport helper:

```ts
runFemModelSpecReadiness(cwd, spec)
```

TypeScript must not reproduce graph/rank/readiness calculations.

The Python result is the engineering authority.

## 15. Pi tool

Add a SAFE/read-only tool:

```text
fem_model_spec_readiness
```

Input:

```text
spec: EngineeringModelSpec JSON object
```

Behavior:

```text
Pi tool
  -> TypeScript bridge
  -> modelSpec.readiness
  -> Python readiness validator
```

The tool:

- does not write files;
- does not invoke OpenSees or ANSYS;
- does not mutate the spec;
- does not repair defects;
- does not infer missing engineering facts.

Agent guidance must distinguish:

```text
fem_model_spec_validate   -> Is the spec valid?
fem_model_spec_readiness  -> Is a valid spec ready to enter renderer authoring?
```

## 16. Readiness vs renderer compatibility

PR22 does not claim that a solver-specific renderer exists or succeeds.

The readiness `profile` is solver-neutral:

```text
FRAME_2D_ELASTIC_READINESS_V1
```

PR23 may consume this result before OpenSees rendering and may add its own solver-specific capability checks.

This avoids claiming `OPENSEES_FRAME_V1 = READY` before the OpenSees renderer is actually implemented.

## 17. Explicit non-goals

PR22 does not implement:

- OpenSees rendering;
- ANSYS rendering;
- model-file persistence;
- solver preflight or execution;
- FE stiffness-matrix assembly;
- eigenvalue analysis;
- numerical condition-number analysis;
- geometric-scale heuristic thresholds;
- material/property magnitude heuristics;
- unit inference or conversion;
- support-type inference;
- automatic constraint insertion;
- automatic node merging;
- automatic component joining;
- semantic-role inference;
- dynamic-analysis mass sufficiency;
- load readiness;
- analysis readiness;
- RAG/knowledge lookup;
- ModelSpec patch/repair.

Geometric/property magnitude heuristics are deliberately deferred because they require explicit, reviewable engineering policy rather than hidden thresholds.

## 18. Test matrix

### 18.1 Invalid-spec gate

Test that:

- missing/invalid PR21 fields produce `INVALID_SPEC`;
- readiness checks are `SKIPPED`;
- PR21 validation issues are preserved in the nested summary;
- no ModelSpec fingerprint is created by PR22.

### 18.2 Stable portal frame

Use PR21's `simple-portal-frame.json` fixture.

Expected:

```text
status = READY
componentCount = 1
constraintRank = 3
deficiency = 0
parallel groups = []
modelSpecFingerprint == PR21 fingerprint
```

### 18.3 Completely free frame

Remove all constraints.

Expected:

```text
status = NOT_READY
constraintRank = 0
deficiency = 3
MODEL_READINESS_RIGID_BODY_RESTRAINT_INSUFFICIENT
```

### 18.4 Partial restraint

Constrain only `UX` and `UY` at one node without `RZ` or a second geometrically independent restraint.

Expected:

```text
constraintRank = 2
status = NOT_READY
```

### 18.5 Simple support geometry

Construct a beam/frame component with:

```text
node A: UX, UY
node B: UY
```

with distinct x-coordinates.

Expected rank 3 and `READY`.

A geometrically degenerate support arrangement that yields rank 2 must be `NOT_READY` even though three DOF constraints exist numerically.

### 18.6 Disconnected components

Create two disconnected frame components.

Cases:

1. both components independently rank 3 -> `READY` plus `MODEL_READINESS_DISCONNECTED_COMPONENTS` warning;
2. one component rank below 3 -> `NOT_READY` plus disconnected warning and rigid-body error.

### 18.7 Isolated node

Add an unused unconstrained node.

Expected:

- singleton component appears;
- PR21 `MODEL_SPEC_UNUSED_NODE` warning is preserved under validation issues;
- singleton component has rank 0;
- overall readiness is `NOT_READY`.

A fully constrained isolated node may remain `READY` with disconnected/unused warnings because PR22 does not silently delete it.

### 18.8 Parallel connectivity

Add two legal elements between the same node pair.

Expected:

```text
MODEL_READINESS_PARALLEL_CONNECTIVITY
parallelConnectivity.status = WARN
```

but overall status remains `READY` if all components are restrained.

### 18.9 Determinism

Reorder:

- nodes;
- elements;
- constraints.

Expected:

- same PR21 fingerprint;
- same component ordering;
- same ranks;
- same readiness issue ordering;
- semantically identical readiness result.

## 19. Deterministic issue ordering

PR22 issue ordering is fixed:

1. `MODEL_READINESS_DISCONNECTED_COMPONENTS` if applicable;
2. rigid-body restraint issues in component index order;
3. parallel connectivity warnings in lexicographic node-pair order.

This supports stable tests and future structured repair.

## 20. Proposed files

New production files:

```text
fem_core/model_spec/readiness.py
```

Modified production files:

```text
fem_core/model_spec/__init__.py
fem_core/bridge.py
packages/fem-tools/src/modelSpecTypes.ts
packages/fem-tools/src/pythonBridge.ts
packages/fem-tools/src/index.ts
.pi/extensions/model-spec-tools.ts
apps/agent/src/main.ts
```

New tests:

```text
tests/python/test_model_spec_readiness.py
tests/python/test_model_spec_readiness_bridge.py
tests/ts/model-spec-readiness.test.ts
```

Documentation after implementation:

```text
docs/architecture/engineering-model-readiness.md
docs/verification/pr22-engineering-model-readiness.md
```

No solver adapter, Result Intelligence, Load Intelligence, Semantic Role, Engineering Evidence, Cross-Solver Validation, or knowledge provider production file should require modification.

## 21. TDD implementation sequence

1. RED: Python readiness tests establish missing `evaluate_engineering_model_readiness`.
2. GREEN: implement connectivity, exact Decimal rank, issue/status contract.
3. RED: Bridge tests establish missing `modelSpec.readiness`.
4. GREEN: register Python bridge command.
5. RED: TypeScript transport tests establish missing types/helper.
6. GREEN: add TS contracts and bridge helper.
7. RED: Pi registration tests establish missing public tool wiring.
8. GREEN: expose SAFE `fem_model_spec_readiness` and register in Agent.
9. Regression: full TypeScript/Python/Ruff/OpenSees/ANSYS-reader/health gates.
10. Architecture and verification docs.
11. Exact-final-head CI.

## 22. Acceptance criteria

PR22 is complete only when all of the following are true:

1. readiness always gates through PR21 validation;
2. PR21-invalid specs return `INVALID_SPEC`, not a bridge failure;
3. every graph component is deterministic and includes isolated nodes;
4. each component's 2D rigid-body constraint rank is evaluated independently;
5. rank uses exact Decimal arithmetic with no hidden numerical tolerance;
6. rank below 3 is a stable blocking readiness error;
7. multiple components are visible as a warning, not automatically rejected;
8. repeated node-pair connectivity is a warning, not automatically rejected;
9. PR21 fingerprint is preserved exactly and never recalculated by PR22;
10. TypeScript does not duplicate readiness engineering logic;
11. `fem_model_spec_readiness` is SAFE/read-only and cannot run a solver;
12. no renderer or solver-specific readiness claim is introduced before PR23;
13. no geometric/property magnitude heuristic is introduced in V1;
14. full repository CI is green on the final PR head.

## 23. Product boundary after PR22

After PR22, FEMagent's controlled model-authoring path becomes:

```text
engineering facts
      |
      v
EngineeringModelSpec
      |
      v
PR21 ModelSpec Validation
      |
      v
VALID + normalizedSpec + fingerprint
      |
      v
PR22 Engineering Readiness
      |
      +-- INVALID_SPEC
      +-- NOT_READY
      +-- READY
              |
              v
future PR23 OpenSees Renderer
```

PR22 therefore establishes the last deterministic engineering gate before solver-model generation begins.