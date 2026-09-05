# Engineering Semantic Roles V1

## Purpose

PR13 adds a deterministic semantic identity layer between solver-native entity IDs and engineering roles such as `TOWER_BASE`, `GIRDER_END`, `BEARING`, `DAMPER_ATTACHMENT`, `MIDSPAN`, and `SUPPORT`.

The layer does **not** infer structural meaning from geometry, coordinates, component names, constraints, variable names, or LLM reasoning. Engineering meaning enters FEMagent only through an explicit workspace-local Semantic Role Manifest that is hard-bound to a Model Bundle fingerprint.

```text
Semantic Role Manifest
  explicit role -> solver entity
        |
        | bundleFingerprint must match
        v
Model Intelligence
  current Model Bundle identity
        |
        v
Semantic Resolver
  roleId -> NODE id
        |
        +-------------------------------+
        |                               |
        v                               v
semantic.inspect                 semantic.resolve
        |                               |
        +---------------+---------------+
                        |
                        v
              role-based evidence
                        |
             recorded run identity check
                        |
                        v
                Result Intelligence
                        |
                        v
             Engineering Evidence Center
```

PR13 is read-only. It never writes a semantic manifest and never starts OpenSees or ANSYS.

## Trust model

There are three separate trust questions. They must not be collapsed into one status.

### 1. Semantic declaration truth

A role is semantic truth for PR13 only when it is explicitly declared in a valid Semantic Role Manifest whose `model.bundleFingerprint` matches the current Model Bundle.

Example:

```json
{
  "schemaVersion": "1.0",
  "kind": "engineering_semantic_roles",
  "model": {
    "bundleFingerprint": "<64-hex model bundle fingerprint>"
  },
  "roles": [
    {
      "roleId": "TOWER_BASE_LEFT",
      "roleType": "TOWER_BASE",
      "entity": {"type": "NODE", "id": 1024}
    }
  ]
}
```

The manifest is data, not executable code. V1 accepts NODE entities only.

### 2. Static entity confirmation

After the semantic declaration is accepted, Model Intelligence may or may not be able to prove that the declared NODE exists from static inspection.

PR13 reports this separately through `entityValidation`:

| Value | Meaning |
| --- | --- |
| `STATICALLY_CONFIRMED` | Model Intelligence can fully enumerate the relevant node topology and the declared node exists. |
| `NOT_STATICALLY_ENUMERABLE` | The role is explicitly declared and model identity matches, but static inspection cannot fully enumerate the realized node topology. |

This distinction is critical for dynamic OpenSees models. A dynamically generated model can still have a valid explicit semantic declaration. Lack of static enumeration does **not** erase that declaration.

Therefore:

```text
explicit declaration + matching Model Bundle
    -> status = RESOLVED

static topology fully enumerable + node exists
    -> entityValidation = STATICALLY_CONFIRMED

static topology not fully enumerable
    -> entityValidation = NOT_STATICALLY_ENUMERABLE
    -> warning is retained
    -> status remains RESOLVED
```

`RESOLVED` answers “is this role explicitly and validly bound to this model?”

`entityValidation` answers “can static Model Intelligence independently confirm the declared solver entity?”

They are intentionally independent.

### 3. Recorded numerical evidence integrity

A resolved semantic role is not numerical evidence by itself.

Role-based evidence additionally requires:

1. a completed recorded run;
2. the recorded run to expose the same Model Bundle fingerprint as the semantic model;
3. Result Intelligence to validate the recorded result artifact;
4. the requested result query to succeed for the resolved NODE;
5. Engineering Evidence Center promotion to satisfy PR12 rules.

A semantic role therefore cannot bypass result-artifact integrity.

## Manifest validation

`fem_core/semantic_roles/manifest.py` validates the workspace-local UTF-8 JSON manifest before model binding.

V1 rejects malformed or unsupported manifests, including:

- unsupported schema/kind;
- malformed JSON;
- duplicate or invalid `roleId`;
- unsupported `roleType`;
- unsupported entity type;
- invalid NODE IDs;
- missing or malformed Model Bundle fingerprint;
- paths outside the workspace through existing FEMagent path guards.

The public system exposes no manifest create/update tool in PR13.

## Model identity binding

`resolver.py` calls production `inspect_model()` and obtains the current Model Bundle `bundleFingerprint`.

The manifest fingerprint must match exactly. A stale manifest fails closed with:

```text
SEMANTIC_ROLE_MODEL_MISMATCH
```

No usable role-to-node mapping is returned after this mismatch.

The Model Bundle fingerprint remains the model identity boundary rather than an entrypoint file name or entrypoint SHA alone.

## Static node validation

### ANSYS APDL text

When Model Intelligence exposes a complete numeric node list for `ANSYS_APDL_TEXT`, PR13 validates the explicit NODE ID against that list.

If the declared node is absent, resolution fails with:

```text
SEMANTIC_ROLE_ENTITY_NOT_FOUND
```

### OpenSees Python

For statically enumerable OpenSees Python models, the explicit NODE is validated against `staticTopology.nodeTags`.

For models with `dynamicGeneration=true`, PR13 does not pretend the AST can prove realized topology. The role remains `RESOLVED`, while `entityValidation` becomes `NOT_STATICALLY_ENUMERABLE` and inspection emits `SEMANTIC_ROLE_ENTITY_NOT_STATICALLY_ENUMERABLE`.

Downstream Result Intelligence remains responsible for whether a completed recorded run actually contains the requested target.

## Public semantic APIs

### Python

```python
inspect_semantic_roles(
    workspace,
    model_path=...,
    manifest_path=...,
)

resolve_semantic_role(
    workspace,
    model_path=...,
    manifest_path=...,
    role_id=...,
)
```

### Bridge commands

```text
semantic.inspect
semantic.resolve
evidence.projectRole
```

### TypeScript clients

```text
runFemSemanticInspect()
runFemSemanticResolve()
runFemRoleEvidenceProject()
```

Type definitions are isolated in `packages/fem-tools/src/semanticTypes.ts` and reuse existing Result/Evidence contracts where possible.

### Pi SAFE tools

PR13 keeps semantic tools in a focused extension file:

```text
.pi/extensions/semantic-tools.ts
```

It registers:

```text
fem_semantic_inspect
fem_semantic_resolve
fem_evidence_project_role
```

All three are SAFE/read-only. The existing permission gate remains focused on real `fem_solver_run` execution.

## Role-based Engineering Evidence

`project_role_evidence()` composes PR13 with PR12 rather than creating a parallel result/evidence subsystem.

```text
resolve role
   -> explicit NODE
   -> inspect_result(run)
   -> compare run model bundle fingerprint
   -> query Result Intelligence
   -> project_run_evidence()
   -> retain semantic provenance
```

The run must belong to the same Model Bundle. A mismatch fails before evidence promotion with:

```text
SEMANTIC_ROLE_RUN_MODEL_MISMATCH
```

Role provenance attached to Engineering Evidence includes:

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

This metadata identifies what the requested engineering role meant for that model. It does not alter the numerical result.

## Result Intelligence extension

PR13 extends `inspect_result()` with a read-only `model` identity block copied from the recorded run manifest when available:

```json
{
  "model": {
    "path": "...",
    "bundleFingerprint": "..."
  }
}
```

This is provenance exposure only. PR13 does not recompute a result model fingerprint, reinterpret numerical values, or change Result Intelligence quantities.

If a recorded run lacks a usable Model Bundle fingerprint, role-based evidence fails closed rather than assuming the run belongs to the current semantic model.

## Unit semantics

PR13 never infers result units.

- Result units remain owned by Result Intelligence.
- Unknown ANSYS result units remain `null`.
- Semantic role names do not imply axes, coordinate systems, or units.
- Role-based evidence copies PR12/Result Intelligence unit semantics unchanged.

## Stable failure contract

V1 preserves stable semantic errors:

```text
INVALID_SEMANTIC_ROLE_MANIFEST
SEMANTIC_ROLE_MODEL_MISMATCH
SEMANTIC_ROLE_NOT_FOUND
SEMANTIC_ROLE_ENTITY_NOT_FOUND
SEMANTIC_ROLE_RUN_MODEL_MISMATCH
```

Existing workspace/path and Result Intelligence integrity/query errors are preserved rather than translated into heuristic fallbacks.

## Determinism

Given identical:

- semantic manifest bytes;
- Model Bundle bytes;
- role ID;
- recorded run manifest/result artifacts;
- result query parameters;

PR13 returns identical semantic mapping/provenance and delegates numerical determinism to existing Result Intelligence and Evidence Center code.

## V1 non-goals

PR13 intentionally does not add:

- automatic semantic-role inference;
- geometry/coordinate heuristics;
- component-name or variable-name heuristics;
- constraint-pattern heuristics;
- LLM role guessing;
- automatic manifest generation;
- manifest write/update tools;
- ELEMENT roles;
- new solver execution behavior;
- new numerical Result Intelligence quantities;
- result unit inference;
- cross-solver comparison/ranking;
- alignment or resampling;
- optimization runtime;
- UI or PDF reporting.

Cross-solver comparison remains PR14 scope. PR13 only establishes independently verified solver-specific semantic mappings that later comparison can consume.
