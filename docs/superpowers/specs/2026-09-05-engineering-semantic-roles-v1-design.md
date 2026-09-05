# PR13 — Engineering Semantic Roles V1 Design

## Goal

Add a deterministic engineering-semantic layer that maps user/project-declared structural roles to solver-native entities without asking the LLM to infer structural meaning from names, coordinates, constraints, or numerical results.

PR13 enables requests such as:

```text
"left tower base X displacement"
        ↓
TOWER_BASE_LEFT
        ↓
NODE 1024
        ↓
Result Intelligence
        ↓
Engineering Evidence
```

The semantic layer does not create solver truth. It only validates and resolves explicit role declarations against an exact Model Bundle identity, then composes that resolved identity with existing Result Intelligence / Evidence Center APIs.

## Background

Through PR12, FEMagent already has deterministic boundaries for:

- Model Intelligence and Model Bundle identity;
- Load Intelligence;
- OpenSees / ANSYS solver execution;
- Result Intelligence;
- Engineering Evidence and read-only evidence projection.

The remaining usability gap is engineering identity. Result Intelligence can query `NODE 1024`, but FEMagent cannot safely claim that node 1024 is a tower base, girder end, support, bearing, damper attachment, or midspan location.

Current Model Intelligence intentionally warns:

```text
COMPONENT_NAMES_DO_NOT_PROVE_ENGINEERING_ROLES
```

That invariant remains valid in PR13.

## Design decision

PR13 uses an explicit **Semantic Role Manifest** as the source of truth.

The manifest is supplied by the user/project workflow. A user does not need to hand-write JSON in the final product: a future UI or conversational confirmation flow may create/update the manifest. But V1 treats only the persisted explicit manifest as authoritative.

FEMagent validates and resolves the declaration. It does not invent the declaration.

## Alternatives considered

### A. Explicit manifest bound to Model Bundle identity — selected

Advantages:

- deterministic and auditable;
- survives solver-specific node numbering as long as each model has its own mapping;
- supports future ANSYS/OpenSees cross-solver comparison by common engineering role IDs;
- does not let LLM interpretation become engineering truth.

Cost:

- the project/user must provide or confirm the mapping at least once.

### B. Infer roles from ANSYS component names or OpenSees variable names — rejected

A name such as `TOWER_BASE` is useful evidence for a future candidate suggestion but does not prove structural meaning. Naming conventions vary and may be stale or misleading.

### C. Infer from geometry/constraints — rejected for V1

Rules such as lowest elevation = tower base, fixed node = support, or span midpoint = midspan are unsafe for general bridge/building models. They may become future deterministic candidate generators, but candidates must not be promoted automatically to resolved roles.

## Trust model

PR13 separates three concepts:

1. **Role declaration truth** — explicit Semantic Role Manifest.
2. **Model identity truth** — Model Intelligence `bundleFingerprint`.
3. **Solver result truth** — Result Intelligence + Engineering Evidence.

A semantic role is never considered resolved for a model whose bundle fingerprint differs from the manifest.

## Manifest location and discovery

V1 does **not** silently scan the workspace for semantic files.

Every semantic operation receives an explicit workspace-relative `manifestPath` and `modelPath`.

This avoids ambiguity when a workspace contains multiple models or multiple semantic mappings.

A later product layer may remember the selected manifest path, but that is outside PR13.

## Semantic Role Manifest schema

V1 JSON example:

```json
{
  "schemaVersion": "1.0",
  "kind": "engineering_semantic_roles",
  "model": {
    "bundleFingerprint": "64-character-sha256"
  },
  "roles": [
    {
      "roleId": "TOWER_BASE_LEFT",
      "roleType": "TOWER_BASE",
      "entity": {
        "type": "NODE",
        "id": 1024
      }
    }
  ]
}
```

Required top-level fields:

- `schemaVersion == "1.0"`;
- `kind == "engineering_semantic_roles"`;
- `model.bundleFingerprint`: exactly one 64-character SHA-256 identity;
- `roles`: non-empty array.

### `roleId`

`roleId` is a project-specific stable instance identifier.

Examples:

```text
TOWER_BASE_LEFT
TOWER_BASE_RIGHT
GIRDER_END_A
GIRDER_END_B
MIDSPAN_MAIN
```

Rules:

- uppercase ASCII letters, digits, and `_` only;
- begins with a letter;
- unique inside one manifest;
- maximum 64 characters.

### `roleType`

V1 controlled vocabulary:

```text
TOWER_BASE
GIRDER_END
BEARING
DAMPER_ATTACHMENT
MIDSPAN
SUPPORT
```

`roleType` is intentionally small. PR13 does not attempt to model every possible bridge/building semantic.

### `entity`

V1 supports only:

```json
{
  "type": "NODE",
  "id": 1024
}
```

Node IDs must be positive integers.

Element, component, surface, section, coordinate-system, and set/group roles are deferred.

## Semantic status model

Semantic status is independent of PR12 Evidence status. `VERIFIED` continues to mean evidence/result integrity; PR13 does not reuse it for role resolution.

Resolution statuses:

```text
RESOLVED
UNRESOLVED
INVALID
STALE_MODEL
```

### RESOLVED

The manifest is structurally valid, the requested role exists, and the manifest model fingerprint exactly matches current Model Intelligence.

`RESOLVED` means the explicit declaration is bound to the exact model identity. It does not imply that a solver has already produced a result for that entity.

### UNRESOLVED

Used in inspection summaries when a declared entity cannot yet be statically enumerated. Direct `semantic.resolve` still returns the explicit mapping with `status: RESOLVED` when the fingerprint is current, but carries `entityValidation: NOT_STATICALLY_ENUMERABLE`.

This distinction preserves the user's explicit mapping without falsely claiming topology verification.

### INVALID

The manifest schema, role ID, role type, entity shape, or duplicate constraints are invalid.

Invalid manifests fail closed with a stable domain error rather than returning partial mappings.

### STALE_MODEL

The manifest fingerprint differs from the inspected Model Bundle fingerprint.

No role is returned for downstream querying until the mapping is updated/reconfirmed for the current model.

## Entity validation basis

Role resolution reports one of:

```text
STATICALLY_CONFIRMED
NOT_STATICALLY_ENUMERABLE
```

### OpenSees Python

If Model Intelligence exposes literal static node tags (`dynamicGeneration == false`), the resolver checks that the declared node exists.

If the model uses dynamic generation, role mapping may still be `RESOLVED` by explicit declaration + fingerprint, but entity validation is `NOT_STATICALLY_ENUMERABLE`.

### ANSYS APDL

PR13 makes one targeted Model Intelligence extension: when an ANSYS bundle is statically enumerable from explicit numeric `N` commands, `manifest.topology.nodeTags` exposes the sorted explicit node IDs.

If the model is block-based, parameterized, or include-driven such that static topology is incomplete, node tags remain unavailable and entity validation is `NOT_STATICALLY_ENUMERABLE`.

PR13 does not add a second APDL parser in the semantic package.

### Missing node in a statically enumerable model

If Model Intelligence can enumerate the complete node set and the manifest references a missing node, resolution fails with:

```text
SEMANTIC_ROLE_ENTITY_NOT_FOUND
```

It is not silently downgraded.

## Core Python package

Add:

```text
fem_core/semantic_roles/
  __init__.py
  models.py
  manifest.py
  resolver.py
  api.py
```

Responsibilities:

### `models.py`

Defines controlled role types, resolution status values, and deterministic serialization helpers.

### `manifest.py`

Loads a workspace-local UTF-8 JSON manifest and validates schema, uniqueness, role vocabulary, and NODE identity.

No model or solver inspection occurs here.

### `resolver.py`

Consumes a validated manifest plus production `inspect_model()` output.

Responsibilities:

- compare `bundleFingerprint` exactly;
- determine static entity-validation basis;
- resolve one `roleId` or summarize all roles;
- never infer a role from model names/geometry/constraints.

### `api.py`

Public read-only semantic operations:

```python
inspect_semantic_roles(
    workspace: Path,
    *,
    model_path: str,
    manifest_path: str,
) -> dict[str, Any]

resolve_semantic_role(
    workspace: Path,
    *,
    model_path: str,
    manifest_path: str,
    role_id: str,
) -> dict[str, Any]
```

## `semantic.inspect`

Bridge command inputs:

```json
{
  "modelPath": "models/bridge.inp",
  "manifestPath": "project/semantic-roles.json"
}
```

Output includes:

```json
{
  "schemaVersion": "1.0",
  "kind": "semantic_role_inspection",
  "status": "RESOLVED",
  "model": {
    "path": "models/bridge.inp",
    "bundleFingerprint": "..."
  },
  "manifest": {
    "path": "project/semantic-roles.json",
    "sha256": "..."
  },
  "roles": [
    {
      "roleId": "TOWER_BASE_LEFT",
      "roleType": "TOWER_BASE",
      "entity": {"type": "NODE", "id": 1024},
      "status": "RESOLVED",
      "entityValidation": "STATICALLY_CONFIRMED"
    }
  ],
  "warnings": []
}
```

For statically non-enumerable models, the role remains explicitly declared but inspection adds a warning and returns `entityValidation: NOT_STATICALLY_ENUMERABLE`.

## `semantic.resolve`

Bridge command inputs:

```json
{
  "modelPath": "models/bridge.inp",
  "manifestPath": "project/semantic-roles.json",
  "roleId": "TOWER_BASE_LEFT"
}
```

Output:

```json
{
  "schemaVersion": "1.0",
  "kind": "semantic_role_resolution",
  "status": "RESOLVED",
  "roleId": "TOWER_BASE_LEFT",
  "roleType": "TOWER_BASE",
  "entity": {"type": "NODE", "id": 1024},
  "entityValidation": "STATICALLY_CONFIRMED",
  "modelBundleFingerprint": "...",
  "manifestSha256": "..."
}
```

Unknown role IDs fail with:

```text
SEMANTIC_ROLE_NOT_FOUND
```

## Error contract

Stable V1 domain errors:

```text
INVALID_SEMANTIC_ROLE_MANIFEST
SEMANTIC_ROLE_MODEL_MISMATCH
SEMANTIC_ROLE_NOT_FOUND
SEMANTIC_ROLE_ENTITY_NOT_FOUND
```

Existing workspace/path errors remain unchanged.

### `INVALID_SEMANTIC_ROLE_MANIFEST`

Covers malformed JSON/schema, unsupported role type, duplicate `roleId`, invalid node ID, or unsupported entity type.

### `SEMANTIC_ROLE_MODEL_MISMATCH`

Manifest `bundleFingerprint` does not match current `inspect_model()` bundle identity.

The resolver must not return a usable entity after this error.

### `SEMANTIC_ROLE_NOT_FOUND`

Requested role ID is not declared.

### `SEMANTIC_ROLE_ENTITY_NOT_FOUND`

The current model is fully statically enumerable and the declared NODE does not exist.

## Result / Evidence composition

PR13 adds one higher-level read-only composition API so callers do not have to manually translate a role into a node and then accidentally lose semantic provenance:

```python
project_role_evidence(
    workspace: Path,
    *,
    project_id: str,
    model_path: str,
    manifest_path: str,
    role_id: str,
    run_ref: str,
    evidence_id: str,
    quantity: str,
    component: str,
    operation: str,
    offset: int = 0,
    limit: int = 500,
) -> dict[str, Any]
```

The flow is:

```text
resolve semantic role
        ↓
NODE id
        ↓
inspect recorded run/result
        ↓
confirm run Model Bundle identity == semantic Model Bundle identity
        ↓
query Result Intelligence using resolved NODE
        ↓
project Engineering Evidence
        ↓
retain semantic provenance
```

### Result Intelligence identity extension

Current run manifests already record model bundle identity for supported solver paths. PR13 extends `inspect_result()` output to expose a read-only `model` identity block from the completed run manifest where available, including `bundleFingerprint`.

This is provenance exposure only; no result interpretation changes.

If the recorded run does not expose a usable model bundle fingerprint, role-based evidence fails closed rather than assuming the run belongs to the inspected model.

If the run fingerprint differs from the semantic model fingerprint, return:

```text
SEMANTIC_ROLE_RUN_MODEL_MISMATCH
```

### Evidence semantic provenance

Role-projected evidence records:

```json
{
  "semanticRole": {
    "roleId": "TOWER_BASE_LEFT",
    "roleType": "TOWER_BASE",
    "entity": {"type": "NODE", "id": 1024},
    "manifestSha256": "...",
    "modelBundleFingerprint": "...",
    "entityValidation": "STATICALLY_CONFIRMED"
  }
}
```

This metadata is provenance. It does not change Result Intelligence unit semantics or numerical values.

## Bridge API

Add Python bridge commands:

```text
semantic.inspect
semantic.resolve
evidence.projectRole
```

TypeScript clients:

```text
runFemSemanticInspect()
runFemSemanticResolve()
runFemRoleEvidenceProject()
```

TypeScript types live in a focused semantic type module and reuse existing Result/Evidence types where possible.

## Pi SAFE tools

Add:

```text
fem_semantic_inspect
fem_semantic_resolve
fem_evidence_project_role
```

All are SAFE/read-only.

Prompt contract:

- do not infer a role from component names, variable names, coordinates, constraints, or topology alone;
- require an explicit semantic manifest path;
- preserve stale-model and missing-entity failures;
- do not rewrite the manifest;
- do not execute a solver;
- do not infer result units;
- only describe PR12 evidence as verified when Evidence Center returns `VERIFIED`.

Manifest creation/editing is intentionally **not** exposed as a Pi write tool in PR13 V1. User confirmation workflows may be designed later with a separate permission/write boundary.

## Security and path boundary

Semantic manifests are workspace-local UTF-8 JSON files.

The implementation reuses FEMagent workspace path guards. Absolute/out-of-workspace references are rejected.

The manifest contains only identifiers and model fingerprint data. It does not allow executable expressions, include paths, templates, or arbitrary code.

## Determinism

Given identical:

- manifest bytes;
- Model Bundle bytes;
- role ID;
- run manifest/result artifacts;
- query parameters;

PR13 must return identical semantic mapping/provenance and defer numerical determinism to existing Result Intelligence.

## TDD plan constraints

Implementation must preserve explicit RED → GREEN evidence.

Required regression groups:

1. semantic manifest validation;
2. model fingerprint binding;
3. statically confirmed NODE resolution;
4. non-enumerable topology behavior;
5. missing-node fail-closed behavior;
6. Bridge / TypeScript round trip;
7. role → Result Intelligence → Engineering Evidence composition;
8. run/model fingerprint mismatch;
9. Pi typecheck / repository regression gate.

The RED tests must be committed/run before implementing each major slice.

## Acceptance scenarios

### Scenario 1 — statically confirmed ANSYS role

- ANSYS model has explicit numeric nodes;
- manifest fingerprint matches model bundle;
- manifest declares `TOWER_BASE_LEFT -> NODE 1`;
- `semantic.resolve` returns `RESOLVED` + `STATICALLY_CONFIRMED`.

### Scenario 2 — stale manifest

- model changes and bundle fingerprint changes;
- old manifest is reused;
- resolver fails with `SEMANTIC_ROLE_MODEL_MISMATCH`;
- no node mapping is returned.

### Scenario 3 — invalid explicit node

- model is fully statically enumerable;
- manifest declares a node absent from the model;
- resolver fails with `SEMANTIC_ROLE_ENTITY_NOT_FOUND`.

### Scenario 4 — dynamic OpenSees model

- manifest fingerprint matches;
- model topology cannot be fully enumerated statically;
- role declaration resolves to the explicit node;
- `entityValidation == NOT_STATICALLY_ENUMERABLE`;
- downstream Result Intelligence remains responsible for whether the recorded run actually contains the requested target.

### Scenario 5 — role-based verified evidence

- role resolves;
- recorded run model bundle fingerprint matches semantic model identity;
- result artifact integrity passes;
- Result Intelligence query succeeds;
- Engineering Evidence is `VERIFIED` according to PR12 rules;
- evidence provenance contains semantic role ID/type/manifest SHA/model fingerprint.

### Scenario 6 — wrong recorded run

- semantic role resolves against model A;
- caller supplies a recorded run from model B;
- role-evidence projection fails with `SEMANTIC_ROLE_RUN_MODEL_MISMATCH` before promoting an engineering claim.

## Non-goals

PR13 does not add:

- automatic semantic-role inference;
- geometric heuristics;
- component-name heuristics;
- LLM role guessing;
- automatic manifest generation;
- semantic manifest write/update tools;
- ELEMENT roles;
- cross-solver numerical comparison/ranking;
- result alignment/resampling;
- optimization;
- UI;
- PDF reports;
- new solver execution behavior;
- new numerical Result Intelligence quantities.

Those remain separate future work.

## Relationship to PR14

PR14 Cross-Solver Validation can use the same engineering role ID across solver-specific models:

```text
TOWER_BASE_LEFT
  ├─ ANSYS model A   -> NODE 1024
  └─ OpenSees model B -> NODE 17
```

PR14 will compare responses only after each solver-specific mapping has independently passed PR13 semantic resolution and PR12 evidence validation.

PR13 itself does not perform that comparison.

## Files expected to change

Expected implementation surface:

```text
fem_core/semantic_roles/__init__.py
fem_core/semantic_roles/models.py
fem_core/semantic_roles/manifest.py
fem_core/semantic_roles/resolver.py
fem_core/semantic_roles/api.py
fem_core/model_inspection.py
fem_core/result_intelligence.py
fem_core/evidence/api.py
fem_core/evidence/result_projection.py
fem_core/bridge.py
packages/fem-tools/src/semanticTypes.ts
packages/fem-tools/src/evidenceTypes.ts
packages/fem-tools/src/pythonBridge.ts
packages/fem-tools/src/index.ts
.pi/extensions/fem-tools.ts
tests/python/test_semantic_roles.py
tests/python/test_semantic_role_evidence.py
tests/ts/semantic-roles.test.ts
docs/architecture/engineering-semantic-roles.md
docs/verification/pr13-engineering-semantic-roles.md
```

Exact file names may be adjusted during the implementation plan if current repository conventions require it, but no additional subsystem should be introduced without revisiting the design.

## Completion criteria

PR13 is complete when:

1. explicit semantic manifests are parsed and validated deterministically;
2. manifests are hard-bound to Model Bundle fingerprint identity;
3. NODE roles resolve without model-name/geometry/constraint guessing;
4. statically enumerable missing nodes fail closed;
5. non-enumerable topology is represented honestly;
6. semantic inspect/resolve cross the existing Python/TypeScript/Pi bridge;
7. role-based Evidence projection verifies recorded run model identity before numerical promotion;
8. semantic provenance survives into Engineering Evidence;
9. no unit semantics or solver execution behavior are changed;
10. final repository CI is green on the exact PR head;
11. PR remains open for explicit merge decision.

Do not merge PR13 without explicit user instruction.
