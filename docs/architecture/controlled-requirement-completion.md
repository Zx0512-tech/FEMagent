# Controlled Requirement Completion

## Purpose

PR24 adds a deterministic, evidence-backed requirement-completion layer between natural-language engineering requests and PR21 `EngineeringModelSpec` validation.

The capability does not let the Python core guess engineering intent from arbitrary prose. The Agent remains responsible for organizing user/project statements into a structured, source-backed `RequirementDraft`; the Python core then validates the evidence, applies only allow-listed derivations, reports unresolved facts, and emits a candidate ModelSpec only when the requirement is deterministically complete.

```text
natural-language / project context
        ↓
Agent extraction
        ↓
source-backed RequirementDraft
        ↓
Python schema + evidence admission
        ↓
controlled completion
        ├─ INVALID_DRAFT
        ├─ CONFLICT
        ├─ INCOMPLETE
        └─ COMPLETE
              ↓
        candidate EngineeringModelSpec
              ↓
        PR21 validation
              ↓
        PR22 readiness
              ↓
        PR23 OpenSees renderer, only when READY
```

## Trust boundary

PR24 separates conversational interpretation from engineering truth.

- The Agent may identify candidate facts from conversation or project context, but it is not engineering truth authority.
- Every submitted `USER_EXPLICIT` fact must cite an exact source message and exact quote.
- The deterministic Python core validates source containment and kind-specific numeric, unit, relation, and template evidence.
- Retrieved knowledge, RAG output, LLM assumptions, defaults, or common engineering practice cannot be relabeled as `USER_EXPLICIT`.
- Templates and deterministic rules may add only explicitly allow-listed derived facts.
- PR21 remains the authoritative ModelSpec validator.
- PR22 remains the authoritative V1 renderer-admission readiness check.
- PR23 remains the controlled OpenSees authoring layer.
- Solver execution and numerical results remain outside PR24.

A PR24 result with `status = COMPLETE` means only that an evidence-backed candidate ModelSpec was assembled and passed PR21 validation. It does **not** mean the model is PR22 `READY`, PR23 `RENDERED`, successfully constructed by OpenSees, structurally adequate, or numerically solved.

## RequirementDraft contract

V1 uses:

```text
schema  = FEMAGENT_ENGINEERING_REQUIREMENT_DRAFT_V1
profile = FRAME_2D_REQUIREMENT_V1
```

A draft contains:

- exact source messages;
- an optional versioned template intent;
- typed engineering facts;
- exact evidence `{sourceId, quote}` for every `USER_EXPLICIT` fact and template intent.

Supported V1 explicit fact kinds are:

```text
SPAN
UNIT_DECLARATION
YOUNGS_MODULUS
SECTION_AREA
SECTION_IZ
NODE_COORDINATE
ELEMENT_CONNECTIVITY
ELEMENT_MATERIAL_REF
ELEMENT_SECTION_REF
NODE_CONSTRAINT
NODAL_MASS
```

The completion core does not accept arbitrary extra fields or unknown fact kinds as an escape hatch for unverified engineering meaning.

## Provenance classes

### USER_EXPLICIT

A fact explicitly adopted by the user/project source and admitted through deterministic evidence validation.

For each such fact:

```text
evidence.sourceId → exactly one declared source
evidence.quote    → non-empty exact substring of source.text
submitted value   → must match the kind-specific evidence grammar
```

Examples include explicit span, units, `E`, `A`, `Iz`, node coordinates, connectivity, element references, DOF constraints, or nodal masses.

### TEMPLATE_DERIVED

A fact produced by one selected, versioned controlled template. Template-derived facts always retain their template provenance and are never presented as user statements.

V1 templates are:

```text
SIMPLY_SUPPORTED_BEAM_2D_V1
CANTILEVER_BEAM_2D_V1
FIXED_FIXED_BEAM_2D_V1
```

They may provide the template-owned beam topology/support convention only when the template intent itself is evidenced by an exact controlled alias and the required span is explicit.

### DETERMINISTIC_DERIVED

A fact produced mechanically by a named V1 rule. PR24 V1 has exactly six allow-listed derivations:

1. `FRAME_2D_PROFILE_FIELDS_V1` — fixed PR21 profile fields and supported entity/formulation types.
2. `CONSISTENT_LENGTH_UNIT_V1` — derives the model length unit only when all admitted length-bearing facts use one identical supported unit and no explicit declaration conflicts.
3. `BEAM_SPAN_COORDINATES_V1` — controlled beam template span to canonical two-node beam coordinates.
4. `SINGLETON_ENTITY_ID_V1` — assigns ID `1` only when exactly one otherwise-unidentified material or section exists.
5. `SINGLETON_ELEMENT_BINDING_V1` — binds an element to the only material/section only when those entities are singletons.
6. `EMPTY_NODAL_MASS_COLLECTION_V1` — no declared nodal-mass facts produces an empty ModelSpec mass collection, without claiming physical zero mass.

No other deterministic completion is allowed in V1.

In particular, PR24 does not derive missing `E`, `A`, `Iz`, force units, time units, arbitrary topology, arbitrary support conditions, density, self-weight, or loads.

## Missing, ambiguous, and conflicting facts

Unresolved engineering facts are first-class output, not prompts for silent guessing.

### MISSING

Required assembly information is absent. For example, `建立一个15m简支梁` can establish template intent, span, and consistent length unit, but remains incomplete without facts such as:

```text
units.force
units.time
material.youngsModulus
section.area
section.iz
```

### AMBIGUOUS

Information exists but cannot be deterministically admitted to one V1 meaning. Examples include unsupported structural-relation wording, a missing element material reference when multiple materials exist, or non-template support prose without explicit DOFs.

### CONFLICT

Admissible facts disagree. PR24 does not silently apply precedence to overwrite one source with another.

Conceptually:

```text
USER_EXPLICIT > TEMPLATE_DERIVED > DETERMINISTIC_DERIVED
```

but operationally:

```text
consistent   → merge
inconsistent → CONFLICT
```

Examples include contradictory support DOFs, inconsistent span/model units, duplicate material properties with different values, or conflicting node coordinates.

## Completion status contract

Completion output schema:

```text
FEMAGENT_ENGINEERING_REQUIREMENT_COMPLETION_V1
```

Statuses are:

- `COMPLETE` — all facts admitted/resolved, no conflicts, candidate ModelSpec assembled, internal PR21 validation passes; candidate is non-null.
- `INCOMPLETE` — admissible request but required facts are missing or unresolved; candidate is null.
- `CONFLICT` — admitted facts disagree and automatic resolution is refused; candidate is null.
- `INVALID_DRAFT` — draft schema/evidence integrity is malformed; candidate is null.

Unexpected implementation faults remain stable `FemCoreError` failures rather than being disguised as an engineering status.

## Templates are optional, not a model whitelist

The three beam templates are shortcuts for narrowly controlled recurring structural intent. They are **not** a global whitelist of models that FEMagent can represent.

A no-template path is supported when the source provides sufficient explicit facts. For example, a V1 2D frame can be completed from explicit node coordinates, element connectivity, constraints, units, material properties, section properties, and required references. PR24 does not invent missing topology or support semantics merely because no template matches.

This distinction is intentional:

```text
controlled template path → safe versioned derivation for known patterns
no-template path          → explicit engineering facts only
```

Future templates extend convenience, not engineering truth authority.

## Determinism and identity

Completion canonicalizes semantically irrelevant source/fact collection order and produces a deterministic `requirementFingerprint` over normalized draft content affecting completion.

On `COMPLETE`, the returned `modelSpecFingerprint` is the authoritative PR21 fingerprint. The identity chain is therefore:

```text
source-backed RequirementDraft
        ↓
requirementFingerprint
        ↓
accepted + derived provenance
        ↓
candidate EngineeringModelSpec
        ↓
PR21 modelSpecFingerprint
```

Equivalent admitted requirements must not produce engineering differences because of array ordering.

## Public interfaces

Python:

```python
complete_engineering_requirement(draft)
```

Bridge command:

```text
requirement.complete
```

TypeScript transport:

```ts
runFemRequirementComplete(cwd, draft, signal?)
```

Pi tool:

```text
fem_requirement_complete
```

The Pi tool is SAFE/read-only. It exposes no `outputPath`, does not call `runFemModelSpecRenderOpenSees`, and does not call `runFemSolverRun`.

Recommended Agent workflow:

```text
source-backed requirement extraction
→ fem_requirement_complete
→ if COMPLETE: fem_model_spec_validate
→ fem_model_spec_readiness
→ only if READY: fem_model_render_opensees
→ Model Intelligence / solver preflight evidence
```

## Explicit V1 non-goals

PR24 does not add:

- an unconstrained natural-language parser inside the Python engineering core;
- RAG/LLM promotion into engineering truth;
- automatic material or section-property selection;
- unit inference from magnitude or convention;
- arbitrary topology, support, mesh, or Semantic Role inference;
- loads or analysis configuration;
- solver execution;
- structural adequacy or stability proof beyond existing downstream checks;
- automatic repair of `MISSING`, `AMBIGUOUS`, `CONFLICT`, PR21 invalidity, or PR22 non-readiness.
