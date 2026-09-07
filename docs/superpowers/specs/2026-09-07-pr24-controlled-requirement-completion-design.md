# PR24 — Controlled Natural-Language Requirement Completion Design

Date: 2026-09-07
Status: written spec pending user review
Roadmap label: PR24 — Natural Language Requirement → EngineeringModelSpec Controlled Completion

## 1. Purpose

PR24 fills the gap between a user's natural-language engineering request and the deterministic `EngineeringModelSpec` introduced by PR21.

The goal is not to let an LLM directly write engineering truth. The goal is to let the Agent interpret flexible user language into a structured **requirement draft**, then let deterministic Python code decide which claims are admissible, which controlled template facts may be added, which deterministic derivations are allowed, and whether enough information exists to assemble a candidate ModelSpec.

The trust boundary is:

```text
User natural-language requirement
        ↓
Agent / LLM extraction
        ↓
EngineeringRequirementDraft V1
        ↓
PR24 Python Controlled Completion Engine
        ├─ validates draft schema
        ├─ validates self-contained evidence
        ├─ validates controlled template intent
        ├─ applies versioned template facts
        ├─ applies allow-listed deterministic derivations
        ├─ detects conflicts
        └─ reports missing / ambiguous facts
        ↓
COMPLETE → candidate EngineeringModelSpec
INCOMPLETE / CONFLICT / INVALID_DRAFT → no candidate ModelSpec
        ↓
PR21 ModelSpec validation
        ↓
PR22 readiness
        ↓
PR23 renderer
```

PR24 preserves the project principle:

- the Agent/LLM decides how to interpret and organize a request;
- deterministic engineering code decides whether those claims are admissible and how controlled completion works;
- PR21 remains the authoritative ModelSpec validator;
- PR22 remains the authoritative renderer-admission readiness evaluator;
- PR23 remains the authoritative OpenSees translation layer.

PR24 does not execute a solver and does not render a model.

## 2. Problem Statement

Before PR24, a user can provide a full explicit ModelSpec and FEMagent can validate, readiness-check, and render it. However, a common request is much shorter:

```text
“建立一个15m简支梁”
```

That sentence contains an explicit span and a controlled structural term, but it does not contain all numerical facts needed by the current 2D elastic-frame ModelSpec. A naive LLM could silently invent Young's modulus, section properties, units, or supports. PR24 must prevent that.

PR24 therefore distinguishes between:

```text
USER_EXPLICIT
TEMPLATE_DERIVED
DETERMINISTIC_DERIVED
MISSING / AMBIGUOUS
```

There is intentionally no `LLM_INFERRED` source that may enter a candidate ModelSpec.

## 3. Architectural Decision

PR24 uses a two-stage hybrid architecture.

### Stage A — Agent extraction

The Agent reads natural language and proposes a typed `EngineeringRequirementDraft`. It may identify:

- exact user-provided numerical facts;
- exact user-provided unit declarations;
- exact user-provided node, element, support, mass, material-property, and section-property facts;
- one optional controlled template intent.

Every fact claimed as `USER_EXPLICIT` must carry evidence copied from a supplied source segment.

### Stage B — Python controlled completion

Python does not perform general-purpose NLP. It:

- validates the closed draft schema;
- validates evidence containment and kind-specific scalar consistency;
- validates template aliases from a versioned allow-list;
- applies template facts only from versioned templates;
- applies deterministic derivations only from versioned rules;
- rejects conflicting claims;
- reports missing and ambiguous facts;
- assembles a candidate ModelSpec only when completion is `COMPLETE`.

This approach is selected over:

1. **Pure rule-based NLP** — safer but too brittle for flexible natural-language extraction.
2. **LLM directly generates ModelSpec** — simpler but cannot preserve the distinction between user facts and LLM invention.

## 4. V1 Scope

PR24 V1 targets the same engineering family already supported by PR21–PR23:

```text
profile          = FRAME_2D_REQUIREMENT_V1
dimension        = 2D
family           = FRAME
coordinateSystem = CARTESIAN_XY
node DOFs        = UX, UY, RZ
material type    = LINEAR_ELASTIC
section type     = FRAME_2D
element type     = ELASTIC_FRAME_2D
formulation      = EULER_BERNOULLI
```

V1 supports two authoring paths:

1. controlled single-span beam templates;
2. explicit no-template 2D frame facts.

A template is an optional completion mechanism, not a model-type whitelist.

## 5. Source Segments and Multi-Turn Provenance

The earlier conceptual examples used one `sourceText` field. The written design replaces that with a closed `sources[]` collection so multi-turn completion can preserve evidence without concatenating or rewriting user messages.

Conceptual shape:

```json
{
  "sources": [
    {
      "sourceId": "source_1",
      "kind": "USER_MESSAGE",
      "text": "建立一个15m简支梁"
    },
    {
      "sourceId": "source_2",
      "kind": "USER_MESSAGE",
      "text": "单位用m、N、s，E=2.06e11 Pa，A=0.02m²，Iz=8e-5m⁴"
    }
  ]
}
```

Each source ID must be unique within the draft. V1 accepts only `kind = USER_MESSAGE`.

Evidence references a source and an exact quote:

```json
{
  "sourceId": "source_1",
  "quote": "15m"
}
```

The quote must be a literal substring of the referenced source text.

### 5.1 V1 provenance limitation

PR24 V1 provides **self-contained evidence integrity**, not cryptographic authentication of the chat transcript. The Python core can prove that a submitted evidence quote exists inside the submitted source segment and that supported scalar values agree with the quote. It cannot independently prove that the Agent did not fabricate or alter the entire source segment before the tool call because the current tool boundary does not expose an authenticated conversation transcript to `fem_core`.

Accordingly, `USER_EXPLICIT` in PR24 V1 means:

> accepted as an explicit user claim within the submitted draft after deterministic evidence checks.

It must not be described as cryptographically authenticated conversation evidence.

Future work may bind source segments to authenticated conversation/message identifiers if the host runtime exposes them deterministically.

## 6. EngineeringRequirementDraft V1

The top-level conceptual contract is:

```json
{
  "schema": "FEMAGENT_ENGINEERING_REQUIREMENT_DRAFT_V1",
  "profile": "FRAME_2D_REQUIREMENT_V1",
  "sources": [],
  "templateIntent": null,
  "facts": []
}
```

Unknown top-level fields are rejected.

### 6.1 Closed tagged fact union

The brainstorming examples used generic `facts[].path` strings. The written spec intentionally replaces arbitrary paths with a **closed tagged union**. This prevents an arbitrary-path mini-language from becoming a schema-bypass surface.

V1 fact kinds are exactly:

```text
SPAN
UNIT_DECLARATION
YOUNGS_MODULUS
SECTION_AREA
SECTION_IZ
NODE_COORDINATE
ELEMENT_CONNECTIVITY
NODE_CONSTRAINT
NODAL_MASS
```

Every input fact has:

```text
source = USER_EXPLICIT
kind   = one allow-listed fact kind
evidence = {sourceId, quote}
```

`TEMPLATE_DERIVED` and `DETERMINISTIC_DERIVED` are output provenance values only. The Agent cannot submit them as authoritative input facts.

### 6.2 SPAN

Conceptual shape:

```json
{
  "kind": "SPAN",
  "source": "USER_EXPLICIT",
  "value": 15,
  "unit": "m",
  "evidence": {"sourceId": "source_1", "quote": "15m"}
}
```

Rules:

- value must be finite and strictly positive;
- unit must be `m`, `cm`, or `mm`;
- evidence must deterministically contain the same numeric value and unit;
- only one non-conflicting V1 span may survive normalization.

### 6.3 UNIT_DECLARATION

Conceptual shape:

```json
{
  "kind": "UNIT_DECLARATION",
  "source": "USER_EXPLICIT",
  "dimension": "force",
  "value": "N",
  "evidence": {"sourceId": "source_2", "quote": "m、N、s"}
}
```

Allowed declarations mirror PR21:

```text
length: m | cm | mm
force:  N | kN
time:   s | ms
```

A length unit may also be deterministically derived from explicit geometry when every accepted length-bearing fact uses the same unit and no explicit length-unit declaration conflicts with it.

Force and time units are never inferred from common convention or numerical magnitude.

### 6.4 YOUNGS_MODULUS

Conceptual shape:

```json
{
  "kind": "YOUNGS_MODULUS",
  "source": "USER_EXPLICIT",
  "materialId": 1,
  "value": 2.06e11,
  "unit": "Pa",
  "evidence": {"sourceId": "source_2", "quote": "E=2.06e11 Pa"}
}
```

`materialId` may be omitted only for the singleton-template convenience case. In that case the completion engine may deterministically assign material ID `1` if there is exactly one accepted material property set.

PR24 V1 performs no unit conversion. A modulus unit must be dimensionally and numerically identical to the active ModelSpec force/length unit system.

Examples:

```text
force=N, length=m   → Pa or N/m² is identity-compatible
force=N, length=mm  → N/mm² is identity-compatible
force=kN, length=m  → kN/m² is identity-compatible
force=kN, length=mm → kN/mm² is identity-compatible
```

A value stated in `Pa` with `force=kN, length=m` would require numerical conversion and is therefore not accepted in V1. It produces a unit conflict rather than silent conversion.

### 6.5 SECTION_AREA

Conceptual shape:

```json
{
  "kind": "SECTION_AREA",
  "source": "USER_EXPLICIT",
  "sectionId": 1,
  "value": 0.02,
  "unit": "m²",
  "evidence": {"sourceId": "source_2", "quote": "A=0.02m²"}
}
```

Rules:

- finite and strictly positive;
- area unit must be the square of the accepted model length unit;
- no unit conversion;
- optional `sectionId` follows the same singleton rule as material IDs.

### 6.6 SECTION_IZ

Conceptual shape:

```json
{
  "kind": "SECTION_IZ",
  "source": "USER_EXPLICIT",
  "sectionId": 1,
  "value": 8e-5,
  "unit": "m⁴",
  "evidence": {"sourceId": "source_2", "quote": "Iz=8e-5m⁴"}
}
```

Rules:

- finite and strictly positive;
- inertia unit must be the fourth power of the accepted model length unit;
- no unit conversion.

### 6.7 NODE_COORDINATE

Conceptual shape:

```json
{
  "kind": "NODE_COORDINATE",
  "source": "USER_EXPLICIT",
  "nodeId": 2,
  "x": 5,
  "y": 3,
  "unit": "m",
  "evidence": {"sourceId": "source_1", "quote": "节点2在(5,3)m"}
}
```

Rules:

- node ID must be a positive integer;
- x and y must be finite;
- unit must be a supported length unit;
- evidence validation must recover the same node identifier and coordinate pair under one of the deterministic V1 coordinate evidence forms;
- duplicate node IDs with different coordinates are `CONFLICT`.

### 6.8 ELEMENT_CONNECTIVITY

Conceptual shape:

```json
{
  "kind": "ELEMENT_CONNECTIVITY",
  "source": "USER_EXPLICIT",
  "elementId": 1,
  "nodeI": 1,
  "nodeJ": 2,
  "materialId": 1,
  "sectionId": 1,
  "evidence": {
    "sourceId": "source_1",
    "quote": "单元1连接节点1和节点2"
  }
}
```

Rules:

- element and node IDs must be positive integers;
- nodeI and nodeJ must differ;
- materialId and sectionId may be omitted only when singleton deterministic binding is possible;
- evidence must match an allow-listed explicit connectivity evidence form;
- V1 never invents arbitrary mesh connectivity.

### 6.9 NODE_CONSTRAINT

Conceptual shape:

```json
{
  "kind": "NODE_CONSTRAINT",
  "source": "USER_EXPLICIT",
  "nodeId": 1,
  "dofs": ["UX", "UY", "RZ"],
  "evidence": {"sourceId": "source_1", "quote": "1号节点固定"}
}
```

Allowed DOFs remain `UX`, `UY`, and `RZ`.

V1 deterministic evidence forms may include:

- explicit DOF labels such as `约束UX和UY` / `fix UX UY`;
- exact controlled aliases such as `固定` / `fixed`, which map to all three planar DOFs.

V1 does not interpret arbitrary support prose as constraints. Terms such as `铰支`, `滚动支座`, or vague geometric descriptions do not become explicit no-template constraints unless they are handled by a controlled template or a future versioned alias rule.

### 6.10 NODAL_MASS

Conceptual shape:

```json
{
  "kind": "NODAL_MASS",
  "source": "USER_EXPLICIT",
  "nodeId": 2,
  "mUX": 1000,
  "mUY": 1000,
  "evidence": {"sourceId": "source_1", "quote": "节点2的mUX和mUY均为1000"}
}
```

Rules:

- node ID must be positive;
- mass values must be finite and non-negative;
- PR24 does not infer nodal mass from material density, self-weight, section area, or geometry.

Absence of `NODAL_MASS` facts produces `nodalMasses=[]` in the V1 candidate ModelSpec. This means only that no nodal mass entries were declared in this ModelSpec; it must not be described as proof that the physical structure has zero mass.

## 7. Evidence Validation

Evidence validation is kind-specific and fail-closed.

### 7.1 Source containment

For every fact and template intent:

```text
evidence.sourceId must resolve to exactly one source
evidence.quote must be non-empty
evidence.quote must be an exact substring of source.text
```

A missing source, empty quote, or non-contained quote produces `INVALID_DRAFT`.

### 7.2 Numeric consistency

For numeric fact kinds, the deterministic parser must recover the submitted numeric token from the quote. Supported V1 forms include ordinary decimal and scientific notation.

Examples:

```text
value=15, evidence="15m"          → admissible
value=12, evidence="15m"          → invalid
value=2.06e11, evidence="2.06e11" → admissible
value=8e-5, evidence="8e-5m⁴"     → admissible
```

The parser must not use fuzzy numerical matching.

### 7.3 Unit consistency

When a fact requires a unit, the quote must contain an allow-listed unit token matching the submitted unit after only deterministic Unicode/case normalization defined by V1.

No magnitude-based unit inference is allowed.

### 7.4 Structural evidence consistency

For node coordinates, element connectivity, and constraints, V1 uses allow-listed deterministic evidence grammars/aliases. If the quote contains the numbers but the structural relation cannot be validated by a supported grammar, the claim is `AMBIGUOUS`, not silently accepted.

This gives the Agent flexible extraction while keeping the Python admission rule narrower than general-language interpretation.

### 7.5 Normalization

Evidence alias matching may apply only:

- Unicode NFKC normalization;
- trimming of surrounding whitespace;
- ASCII/English case-folding;
- deterministic whitespace collapsing for English multi-word aliases.

There is no semantic similarity, embedding lookup, edit-distance matching, or LLM validation inside the core.

## 8. Controlled Template Registry

PR24 V1 includes exactly three versioned templates:

```text
SIMPLY_SUPPORTED_BEAM_2D_V1
CANTILEVER_BEAM_2D_V1
FIXED_FIXED_BEAM_2D_V1
```

Templates are code-defined, versioned engineering rules. They are not RAG documents and are not LLM prose.

### 8.1 Template intent shape

Conceptual form:

```json
{
  "templateId": "SIMPLY_SUPPORTED_BEAM_2D_V1",
  "evidence": {
    "sourceId": "source_1",
    "quote": "简支梁"
  }
}
```

Only one template intent is allowed in V1.

### 8.2 Alias registry

`SIMPLY_SUPPORTED_BEAM_2D_V1` aliases:

```text
简支梁
simply supported beam
```

`CANTILEVER_BEAM_2D_V1` aliases:

```text
悬臂梁
cantilever beam
```

`FIXED_FIXED_BEAM_2D_V1` aliases:

```text
两端固支梁
双端固支梁
fixed-fixed beam
fixed fixed beam
```

The broad Chinese alias `固支梁` is intentionally **not** accepted in the written V1 specification because it can be interpreted ambiguously in ordinary engineering conversation. This is a safety tightening from the brainstorming example, not a feature expansion.

A template ID whose evidence quote does not match its alias registry produces `INVALID_DRAFT`.

## 9. Template Semantics

All three V1 beam templates use a canonical local geometry convention:

```text
node 1 = left / fixed-end reference at (0, 0)
node 2 = right / free-end reference at (span, 0)
element 1 connects node 1 → node 2
```

The span must be provided explicitly as a `SPAN` fact. Templates never invent span length.

### 9.1 SIMPLY_SUPPORTED_BEAM_2D_V1

Template-derived topology:

```text
nodes:    1, 2
element:  1 → 2
```

Template-derived support contract:

```text
node 1: UX, UY constrained; RZ free
node 2: UY constrained; UX, RZ free
```

This is the versioned FEMagent V1 convention for the phrase `简支梁` / `simply supported beam`.

### 9.2 CANTILEVER_BEAM_2D_V1

Template-derived support contract:

```text
node 1: UX, UY, RZ constrained
node 2: free
```

The canonical template places the fixed end at x=0 and free end at x=span. If the user explicitly states the opposite orientation or coordinates, V1 reports a conflict rather than silently flipping the template.

### 9.3 FIXED_FIXED_BEAM_2D_V1

Template-derived support contract:

```text
node 1: UX, UY, RZ constrained
node 2: UX, UY, RZ constrained
```

## 10. Provenance of Derived Template Facts

Template application must preserve provenance at fact level.

Examples:

```text
node IDs and single-member topology
→ source = TEMPLATE_DERIVED
→ templateId = ...

support constraints
→ source = TEMPLATE_DERIVED
→ templateId = ...

node 1 coordinate (0,0)
node 2 coordinate (span,0)
→ source = DETERMINISTIC_DERIVED
→ ruleId = BEAM_SPAN_COORDINATES_V1
→ dependencies = [accepted SPAN fact, templateId]

schemaVersion/kind/dimension/family/coordinateSystem
→ source = DETERMINISTIC_DERIVED
→ ruleId = FRAME_2D_PROFILE_FIELDS_V1
```

No derived fact may be relabeled as `USER_EXPLICIT`.

## 11. Deterministic Derivation Rules

PR24 V1 allows only named rules.

### 11.1 FRAME_2D_PROFILE_FIELDS_V1

Produces:

```text
schemaVersion = 1.0
kind = engineering_model_spec
dimension = 2D
family = FRAME
coordinateSystem = CARTESIAN_XY
material.type = LINEAR_ELASTIC
section.type = FRAME_2D
element.type = ELASTIC_FRAME_2D
element.formulation = EULER_BERNOULLI
```

These are profile contract fields, not inferred engineering choices.

### 11.2 CONSISTENT_LENGTH_UNIT_V1

If there is no explicit `UNIT_DECLARATION(length=...)`, and all accepted length-bearing explicit facts use the same supported length unit, derive `units.length` from that unit.

For:

```text
“15m简支梁”
```

`units.length = m` is therefore deterministic from the explicit span unit.

Mixed length units are not converted. They cause a conflict unless the submitted values already use one identical unit system.

### 11.3 BEAM_SPAN_COORDINATES_V1

For a controlled single-span beam template and accepted positive span `L`:

```text
node 1 = (0, 0)
node 2 = (L, 0)
```

in the accepted length unit.

### 11.4 SINGLETON_ENTITY_ID_V1

When a V1 template request supplies exactly one modulus property set without a material ID, assign material ID `1`.

When it supplies exactly one area/Iz property set without a section ID, assign section ID `1`.

This rule is not allowed when multiple materials or sections are present.

### 11.5 SINGLETON_ELEMENT_BINDING_V1

When exactly one material and one section exist, a template-derived beam element may bind to those singleton IDs.

For explicit no-template element facts, omitted material/section references may be derived only when exactly one material and exactly one section exist. Otherwise the references are `AMBIGUOUS` and completion cannot be `COMPLETE`.

### 11.6 EMPTY_NODAL_MASS_COLLECTION_V1

If no nodal-mass facts are present, assemble `nodalMasses=[]`.

This is a ModelSpec collection default and is not a physical mass inference.

No other deterministic derivation rules are permitted in V1.

## 12. Conflict Policy

The conceptual precedence is:

```text
USER_EXPLICIT
    >
TEMPLATE_DERIVED
    >
DETERMINISTIC_DERIVED
```

However, precedence does **not** mean silent overwrite.

V1 policy is:

```text
consistent facts   → merge
inconsistent facts → CONFLICT
```

Examples:

### 12.1 User constraint conflicts with template

User request includes a simple-support template plus an explicit right-end `UX, UY` constraint.

Template says:

```text
right node = UY only
```

Explicit fact says:

```text
right node = UX, UY
```

Result:

```text
status = CONFLICT
candidateModelSpec = null
```

The engine must report both provenance records.

### 12.2 Explicit unit conflicts with span unit

```text
SPAN = 15 m
UNIT_DECLARATION(length) = mm
```

No conversion is performed. Result is `CONFLICT`.

### 12.3 Duplicate explicit numerical facts

Two accepted facts for the same property with different values are `CONFLICT`.

### 12.4 No template override in V1

There is no `overrideTemplate=true` mechanism in PR24 V1. A user who wants a non-standard support arrangement should use the explicit no-template path or a future template version rather than mutating a V1 template silently.

## 13. Missing and Ambiguous Facts

`MISSING` means a required fact is absent.

`AMBIGUOUS` means the draft contains information that cannot be deterministically admitted to one V1 meaning.

Examples of missing facts for:

```text
“建立一个15m简支梁”
```

are expected to include:

```text
units.force
units.time
material.youngsModulus
section.area
section.iz
```

`units.length` is not missing because the explicit `15m` span supports `CONSISTENT_LENGTH_UNIT_V1`.

Examples of ambiguity include:

- an unsupported support phrase in no-template mode;
- omitted material references when multiple materials exist;
- an evidence quote containing numbers but no deterministically validated structural relation;
- a broad phrase such as `固支梁` that does not uniquely select a V1 template alias.

## 14. Completion Status Contract

PR24 returns schema:

```text
FEMAGENT_ENGINEERING_REQUIREMENT_COMPLETION_V1
```

Top-level status is exactly one of:

```text
COMPLETE
INCOMPLETE
CONFLICT
INVALID_DRAFT
```

### 14.1 COMPLETE

`COMPLETE` means:

- draft schema is valid;
- all submitted explicit facts passed evidence admission;
- optional template intent is valid;
- no conflicts remain;
- no required ModelSpec assembly facts are missing or ambiguous;
- the deterministic compiler assembled a candidate V1 ModelSpec;
- the assembled candidate passes an internal PR21 validation invariant check.

Only `COMPLETE` returns a non-null `candidateModelSpec`.

### 14.2 INCOMPLETE

`INCOMPLETE` means admissible facts exist but required information is missing or unresolved.

```text
candidateModelSpec = null
```

### 14.3 CONFLICT

`CONFLICT` means two or more admissible facts/rules disagree in a way V1 refuses to resolve automatically.

```text
candidateModelSpec = null
```

### 14.4 INVALID_DRAFT

`INVALID_DRAFT` means the draft schema or evidence integrity is invalid, for example:

- unknown fact kind;
- unknown field;
- missing referenced source;
- evidence quote not present in source text;
- submitted scalar value does not match its evidence quote;
- template evidence does not match the selected template alias.

```text
candidateModelSpec = null
```

Unexpected I/O is not expected because PR24 is read-only. Internal compiler invariants use stable `FemCoreError` exceptions rather than returning a fake user-level status.

## 15. Completion Report Shape

Conceptual report:

```json
{
  "schema": "FEMAGENT_ENGINEERING_REQUIREMENT_COMPLETION_V1",
  "profile": "FRAME_2D_REQUIREMENT_V1",
  "status": "INCOMPLETE",
  "acceptedFacts": [],
  "derivedFacts": [],
  "template": null,
  "missing": [],
  "ambiguous": [],
  "conflicts": [],
  "candidateModelSpec": null,
  "modelSpecValidation": null,
  "modelSpecFingerprint": null,
  "requirementFingerprint": "..."
}
```

### 15.1 requirementFingerprint

The completion engine computes a deterministic SHA256 fingerprint from the normalized V1 draft content that materially affects completion:

- profile;
- source texts;
- evidence references;
- normalized admitted facts;
- template intent.

Source IDs are included because they bind evidence references within the normalized draft.

Equivalent collection ordering is canonicalized before hashing where order is not semantically meaningful.

### 15.2 ModelSpec fingerprint

On `COMPLETE`, the result includes the PR21 `modelSpecFingerprint` returned from authoritative validation of the assembled candidate.

This creates an identity chain:

```text
requirementFingerprint
        ↓
accepted + derived provenance
        ↓
candidate ModelSpec
        ↓
modelSpecFingerprint
        ↓
PR23 renderFingerprint (later stage)
```

## 16. Candidate ModelSpec Assembly

A V1 candidate ModelSpec is assembled only from:

```text
accepted USER_EXPLICIT facts
+ controlled TEMPLATE_DERIVED facts
+ allow-listed DETERMINISTIC_DERIVED facts
```

The compiler never reads RAG output or free-form LLM prose as engineering truth.

### 16.1 Template single-beam assembly

For one beam template with complete E/A/Iz and units, the compiler creates canonical singleton namespaces unless explicit IDs are already admissible and consistent:

```text
nodes      = 1, 2
material   = 1
section    = 1
element    = 1
```

### 16.2 Explicit no-template assembly

When `templateIntent = null`, explicit facts may define arbitrary V1 2D frame topology within PR21's existing schema limits.

The completion engine does not require a template. It requires enough admissible facts to assemble:

- at least two nodes;
- at least one material;
- at least one section;
- at least one element;
- complete unit declarations/derivations;
- any supplied constraints and nodal masses.

The ModelSpec constraint collection may be empty at completion time; PR22 remains responsible for deciding whether the model is structurally ready for rendering. PR24 `COMPLETE` therefore does not imply PR22 `READY`.

## 17. PR21 / PR22 / PR23 Boundaries

PR24 must not duplicate later meanings.

```text
PR24 COMPLETE
```

means only that a source-backed, controlled-completion draft can be assembled into a PR21-valid candidate ModelSpec.

It does not mean:

- structurally stable;
- renderer-ready;
- solver-domain valid;
- numerically adequate;
- physically correct;
- successfully solved.

The downstream sequence remains:

```text
PR24 completion
    ↓
PR21 validate (re-run by public workflow)
    ↓
PR22 readiness
    ↓
PR23 render
    ↓
Model Intelligence
    ↓
OpenSees build-only / preflight
```

Even though PR24 internally validates an assembled candidate as an invariant check before returning `COMPLETE`, downstream consumers must still call the public PR21 validator. No layer trusts a stale or caller-provided validation claim.

## 18. Public Python API

New package:

```text
fem_core/requirements/
├─ __init__.py
├─ schema.py
├─ templates.py
├─ evidence.py
└─ completion.py
```

Public entry point:

```python
complete_engineering_requirement(
    draft: dict[str, Any],
) -> dict[str, Any]
```

The function is deterministic and read-only.

It does not accept:

- workspace output paths;
- solver names;
- LLM clients;
- RAG clients;
- arbitrary template definitions supplied by the caller.

Template and derivation registries are code-owned V1 contracts.

## 19. Bridge Contract

New bridge command:

```text
requirement.complete
```

Request payload:

```json
{
  "draft": {}
}
```

The bridge performs transport only. It must not implement template selection, evidence parsing, conflict resolution, or ModelSpec assembly in Python bridge dispatch code.

Stable user-facing completion statuses are returned as normal results. Non-object payload and internal invariant failures use existing stable `FemCoreError` patterns.

## 20. TypeScript Contract

Add typed transport concepts:

```text
FemEngineeringRequirementDraft
FemRequirementSource
FemRequirementFact
FemTemplateIntent
FemEngineeringRequirementCompletion
```

Transport helper:

```ts
runFemRequirementComplete(
  workspace: string,
  draft: FemEngineeringRequirementDraft,
  signal?: AbortSignal,
): Promise<FemEngineeringRequirementCompletion>
```

TypeScript is not an engineering authority. It does not:

- choose templates;
- validate aliases;
- derive constraints;
- calculate missing facts;
- resolve conflicts;
- calculate fingerprints independently.

## 21. Pi Agent Tool

Register a new SAFE/read-only tool:

```text
fem_requirement_complete
```

Purpose:

> Admit source-backed natural-language engineering facts into the controlled V1 requirement-completion engine and report whether a candidate EngineeringModelSpec can be assembled.

Prompt guidance must require the Agent to:

- copy source segments exactly rather than paraphrasing them;
- attach evidence for every `USER_EXPLICIT` fact;
- never label retrieved knowledge or Agent assumptions as `USER_EXPLICIT`;
- use only supported template IDs;
- report `missing`, `ambiguous`, and `conflicts` exactly;
- never fill missing E/A/Iz/units merely to obtain `COMPLETE`;
- never describe `COMPLETE` as readiness or solver success;
- call public PR21 and PR22 tools before rendering.

The tool is read-only and does not require solver execution permission.

## 22. Agent Workflow

Preferred workflow:

```text
1. Read user's engineering request.
2. Preserve exact relevant user-message text as draft sources.
3. Extract supported explicit facts with exact evidence.
4. Select a controlled template only when an exact V1 alias is evidenced.
5. Call fem_requirement_complete.
6. If INVALID_DRAFT:
     repair only extraction/schema/evidence representation.
7. If CONFLICT:
     surface the conflicting facts and ask the user to resolve them.
8. If INCOMPLETE:
     surface only the actual missing/ambiguous engineering facts.
9. If COMPLETE:
     pass candidateModelSpec to fem_model_spec_validate.
10. Run fem_model_spec_readiness.
11. Render only if READY and the user workflow calls for model authoring.
```

The Agent must not change user engineering values while repairing an invalid draft representation.

## 23. End-to-End Example — 15 m Simply Supported Beam

### User turn 1

```text
建立一个15m简支梁
```

Draft contains:

```text
source_1 = exact user text
SPAN = 15 m, evidence "15m"
templateIntent = SIMPLY_SUPPORTED_BEAM_2D_V1, evidence "简支梁"
```

Completion derives:

```text
units.length = m
node 1 = (0,0)
node 2 = (15,0)
element 1 = node 1 → node 2
node 1 constraints = UX, UY
node 2 constraints = UY
```

Completion result:

```text
status = INCOMPLETE
candidateModelSpec = null
missing:
- units.force
- units.time
- material.youngsModulus
- section.area
- section.iz
```

### User turn 2

```text
单位用m、N、s，E=2.06e11 Pa，A=0.02m²，Iz=8e-5m⁴
```

The next draft includes both exact source segments and evidence references to the relevant source.

When all evidence and units are identity-compatible:

```text
status = COMPLETE
candidateModelSpec != null
modelSpecFingerprint != null
```

The candidate then proceeds through PR21, PR22, and PR23.

## 24. Explicit No-Template Example

User provides an explicit frame description such as:

```text
节点1在(0,0)m，节点2在(5,3)m，节点3在(10,0)m；
单元1连接节点1和节点2，单元2连接节点2和节点3；
1号节点固定，3号节点约束UY；
E=...，A=...，Iz=...，单位为m、N、s。
```

The Agent submits supported typed facts with `templateIntent = null`.

If all required ModelSpec assembly facts are admitted, PR24 may return `COMPLETE` without any template.

This path demonstrates that templates are convenience mechanisms rather than a structural whitelist.

## 25. Error / Issue Codes

The implementation should use stable codes grouped under PR24, including at least:

```text
REQUIREMENT_DRAFT_INVALID_SCHEMA
REQUIREMENT_DRAFT_UNKNOWN_FIELD
REQUIREMENT_DRAFT_INVALID_SOURCE
REQUIREMENT_EVIDENCE_SOURCE_NOT_FOUND
REQUIREMENT_EVIDENCE_QUOTE_NOT_FOUND
REQUIREMENT_EVIDENCE_NUMERIC_MISMATCH
REQUIREMENT_EVIDENCE_UNIT_MISMATCH
REQUIREMENT_EVIDENCE_RELATION_AMBIGUOUS
REQUIREMENT_TEMPLATE_UNSUPPORTED
REQUIREMENT_TEMPLATE_EVIDENCE_MISMATCH
REQUIREMENT_FACT_CONFLICT
REQUIREMENT_UNIT_CONFLICT
REQUIREMENT_MISSING_FACT
REQUIREMENT_AMBIGUOUS_FACT
REQUIREMENT_INTERNAL_INVARIANT
```

User-level `missing`, `ambiguous`, and `conflicts` arrays carry structured records with stable code, field/subject, message, and relevant provenance references.

## 26. Test Matrix

### 26.1 Template happy paths

Cover:

- 15 m simply supported beam;
- 5 m cantilever beam;
- 8 m fixed-fixed beam.

Verify:

- template ID and alias admission;
- canonical node IDs and coordinates;
- element topology;
- exact constraint mapping;
- fact provenance;
- deterministic length-unit derivation.

### 26.2 Evidence integrity

Must reject or mark ambiguous as designed:

```text
value=12 with evidence "15m"
unit=mm with evidence "15m"
evidence quote absent from source
sourceId absent from sources
templateId=CANTILEVER... with evidence "简支梁"
unsupported structural relation evidence
```

### 26.3 Missing facts

`15m简支梁` alone must produce:

```text
INCOMPLETE
candidateModelSpec = null
```

with force/time/E/A/Iz missing and length unit not missing.

### 26.4 Conflict behavior

Cover:

- explicit right-end constraints conflict with simple-support template;
- explicit length unit conflicts with span unit;
- duplicate E facts disagree;
- duplicate node IDs disagree;
- mixed units that would require conversion.

Every case must return `CONFLICT` with no candidate ModelSpec.

### 26.5 Explicit no-template path

A complete explicit 2D frame requirement with `templateIntent=null` must produce `COMPLETE` and a PR21-valid candidate.

A no-template request with insufficient topology must return `INCOMPLETE` or `AMBIGUOUS`, never invent mesh connectivity.

### 26.6 Determinism

Equivalent draft collection ordering must produce the same:

```text
accepted/derived normalized facts
requirementFingerprint
candidate ModelSpec bytes/structure
modelSpecFingerprint
```

where semantically irrelevant collection order is canonicalized.

### 26.7 Downstream PR21 / PR22 integration

For a `COMPLETE` result:

```text
complete_engineering_requirement()
→ validate_engineering_model_spec()
→ evaluate_engineering_model_readiness()
```

must use the real production functions.

Template happy-path fixtures that are fully specified should reach PR22 `READY`.

### 26.8 PR23 integration

A fully specified template request must support the real chain:

```text
RequirementDraft
→ PR24 COMPLETE
→ PR21 VALID
→ PR22 READY
→ PR23 RENDERED
```

Then existing OpenSees inspection should continue to report literal/static topology as already guaranteed by PR23.

### 26.9 Bridge tests

Cover:

- `requirement.complete` COMPLETE result;
- INCOMPLETE as typed normal result;
- CONFLICT as typed normal result;
- INVALID_DRAFT as typed normal result;
- malformed bridge payload uses stable error behavior.

### 26.10 TypeScript and Pi registration

Verify:

- typed transport crosses the real Python bridge;
- `fem_requirement_complete` is registered;
- Agent entrypoint allows it;
- tool remains read-only;
- tool does not call renderer or `fem_solver_run`.

## 27. Non-Goals

PR24 V1 does not implement:

- an LLM inside `fem_core`;
- arbitrary free-form NLP inside Python;
- direct natural-language-to-ModelSpec generation without the draft boundary;
- material databases;
- `Q355 → E` lookup;
- section databases;
- `H500×300×11×18 → A/Iz` calculation;
- unit conversion;
- magnitude-based unit inference;
- load interpretation or load generation;
- distributed-load modeling;
- gravity/self-weight generation;
- analysis settings;
- damping;
- result requests;
- 3D frames;
- truss, shell, or solid models;
- portal-frame templates;
- continuous-beam templates;
- template override/mutation;
- fuzzy template matching;
- embedding/RAG-based template selection;
- automatic conflict repair;
- automatic ModelSpec repair;
- automatic rendering;
- solver execution;
- Semantic Role generation.

## 28. Capability Claim After PR24

After PR24, FEMagent may accurately claim:

> FEMagent can convert supported natural-language 2D frame requirements into a source-backed, provenance-carrying requirement draft, apply versioned controlled templates and deterministic derivations, report missing/ambiguous/conflicting engineering facts, and produce a candidate EngineeringModelSpec only when the controlled completion contract is satisfied.

It must not claim:

> FEMagent can infer arbitrary engineering models or missing engineering properties from vague natural language.

For a request such as `建立一个15m简支梁`, PR24 may automatically admit the explicit span, apply the versioned simple-support topology/support template, and derive the length unit from the explicit span unit, but it must stop at `INCOMPLETE` until force/time units and required E/A/Iz properties are explicitly supplied or introduced by a future separately controlled engineering data source.

## 29. Implementation Boundary

The intended implementation footprint is limited to:

```text
fem_core/requirements/*
fem_core/bridge.py
packages/fem-tools/src/* requirement types/transport
.pi/extensions/* requirement tool registration
apps/agent/src/main.ts tool allow-list
tests/python/* PR24 tests
tests/ts/* PR24 bridge/tool tests
docs/* PR24 architecture/verification docs during implementation
```

PR24 must not modify PR21 validation semantics, PR22 readiness semantics, PR23 renderer engineering mappings, solver adapters, ANSYS behavior, Result Intelligence, Load Intelligence, Knowledge/RAG truth separation, Semantic Roles, cross-solver validation, or optimization logic except where a narrow import/export is strictly required for integration tests.

## 30. Review Gate

This document is the architectural written-spec gate.

No PR24 production implementation should begin until the user reviews and approves this written specification. After written-spec approval, the next step is the Superpowers `writing-plans` workflow, followed by TDD implementation and final exact-head verification.
