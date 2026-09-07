# PR24 — Controlled Natural-Language Requirement Completion Design

Date: 2026-09-07
Status: written spec pending user review
Roadmap label: PR24 — Natural Language Requirement → EngineeringModelSpec Controlled Completion

## 1. Purpose

PR24 fills the gap between natural-language engineering requests and the deterministic `EngineeringModelSpec` introduced by PR21.

The goal is **not** to let an LLM directly write engineering truth. The Agent may interpret flexible language into a typed requirement draft, but deterministic Python code decides:

- whether submitted claims are admissible;
- whether evidence is self-consistent;
- whether a controlled template may be applied;
- which deterministic derivations are allowed;
- whether facts conflict;
- which facts remain missing or ambiguous;
- whether a candidate ModelSpec can be assembled.

The trust chain is:

```text
User natural-language requirement
        ↓
Agent / LLM extraction
        ↓
EngineeringRequirementDraft V1
        ↓
PR24 Python Controlled Completion Engine
        ├─ draft schema validation
        ├─ source/evidence validation
        ├─ controlled template admission
        ├─ deterministic derivation
        ├─ conflict detection
        └─ missing / ambiguity reporting
        ↓
COMPLETE → candidate EngineeringModelSpec
otherwise → no candidate ModelSpec
        ↓
PR21 Validate
        ↓
PR22 Readiness
        ↓
PR23 Renderer
```

PR24 is deterministic and read-only. It does not render or solve models.

## 2. Core Trust Rule

PR24 distinguishes engineering facts by provenance:

```text
USER_EXPLICIT
TEMPLATE_DERIVED
DETERMINISTIC_DERIVED
MISSING / AMBIGUOUS
```

There is intentionally no `LLM_INFERRED` fact class that may enter a candidate ModelSpec.

`USER_EXPLICIT` is used only for facts submitted with evidence that passes the V1 deterministic admission rules. `TEMPLATE_DERIVED` and `DETERMINISTIC_DERIVED` are output provenance values generated only by Python.

## 3. Selected Architecture

PR24 uses a two-stage hybrid architecture.

### 3.1 Agent extraction

The Agent may extract:

- explicit numerical values;
- explicit unit declarations;
- explicit node coordinates;
- explicit element connectivity;
- explicit material/section properties and references;
- explicit support DOFs and nodal masses;
- one optional controlled template intent.

Every submitted fact must include evidence copied from a supplied source segment.

### 3.2 Python controlled completion

Python does not run general-purpose NLP or an LLM. It uses:

- a closed input schema;
- kind-specific evidence parsers;
- a versioned template registry;
- a versioned deterministic-derivation registry;
- fail-closed conflict and ambiguity rules.

Rejected alternatives:

1. **Pure regex NLP for the whole user request** — safe but too brittle for flexible language.
2. **LLM directly emits ModelSpec** — convenient but loses the boundary between user facts and invented engineering facts.

## 4. V1 Engineering Scope

PR24 V1 targets the existing PR21–PR23 profile:

```text
profile          = FRAME_2D_REQUIREMENT_V1
dimension        = 2D
family           = FRAME
coordinateSystem = CARTESIAN_XY
DOFs             = UX, UY, RZ
material         = LINEAR_ELASTIC
section          = FRAME_2D
element          = ELASTIC_FRAME_2D
formulation      = EULER_BERNOULLI
```

V1 supports both:

1. three controlled single-span beam templates;
2. explicit no-template 2D frame authoring.

Templates are an optional convenience mechanism, not a model-type whitelist.

## 5. Multi-Turn Source Segments

The draft uses `sources[]` rather than one concatenated `sourceText`, so multiple user turns keep separate provenance.

Conceptual form:

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

Rules:

- `sourceId` is unique within one draft;
- V1 accepts only `kind = USER_MESSAGE`;
- source text is preserved exactly as submitted;
- evidence references one source and an exact quote.

Evidence form:

```json
{
  "sourceId": "source_1",
  "quote": "15m"
}
```

The quote must be a literal substring of the referenced source.

### 5.1 Provenance limitation

PR24 V1 provides **self-contained evidence integrity**, not cryptographic authentication of the chat transcript. The Python core can verify the internal relationship between submitted sources, quotes, values, aliases, and supported structural grammar. It cannot independently prove that the Agent did not alter an entire source segment before the tool call because the current tool boundary does not expose an authenticated transcript to `fem_core`.

Therefore `USER_EXPLICIT` means:

> accepted as an explicit user claim within the submitted draft after deterministic V1 evidence checks.

It must not be described as cryptographically authenticated conversation evidence.

## 6. EngineeringRequirementDraft V1

Top-level contract:

```json
{
  "schema": "FEMAGENT_ENGINEERING_REQUIREMENT_DRAFT_V1",
  "profile": "FRAME_2D_REQUIREMENT_V1",
  "sources": [],
  "templateIntent": null,
  "facts": []
}
```

Unknown fields are rejected recursively.

## 7. Closed Fact Union

The earlier brainstorming examples used arbitrary `facts[].path` strings. The written spec deliberately replaces that with a closed tagged union so arbitrary paths cannot become a schema-bypass surface.

V1 input fact kinds are exactly:

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

Every input fact has:

```text
source = USER_EXPLICIT
kind = one allowed kind
evidence = {sourceId, quote}
```

`TEMPLATE_DERIVED` and `DETERMINISTIC_DERIVED` cannot be supplied by the Agent as authoritative input facts.

## 8. Scalar and Property Facts

### 8.1 SPAN

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

- finite and strictly positive;
- unit `m | cm | mm`;
- numeric value and unit must be recoverable from the quote;
- conflicting duplicate spans produce `CONFLICT`.

### 8.2 UNIT_DECLARATION

```json
{
  "kind": "UNIT_DECLARATION",
  "source": "USER_EXPLICIT",
  "dimension": "force",
  "value": "N",
  "evidence": {"sourceId": "source_2", "quote": "单位用m、N、s"}
}
```

Allowed values mirror PR21:

```text
length: m | cm | mm
force:  N | kN
time:   s | ms
```

V1 accepts unit evidence only through deterministic forms such as:

- labeled declarations: `长度单位m`, `力单位N`, `时间单位s`;
- English labeled equivalents;
- canonical triple form such as `单位用m、N、s`, interpreted in fixed order `length, force, time`.

A quote merely containing the token `N` is not sufficient by itself to prove a force-unit declaration.

### 8.3 YOUNGS_MODULUS

```json
{
  "kind": "YOUNGS_MODULUS",
  "source": "USER_EXPLICIT",
  "value": 2.06e11,
  "unit": "Pa",
  "evidence": {"sourceId": "source_2", "quote": "E=2.06e11 Pa"}
}
```

An optional `materialId` may be supplied **only** if the same evidence quote deterministically identifies that material ID, for example `材料2的E=...`. Otherwise the Agent must omit the ID and allow a singleton deterministic rule to assign it where valid.

Rules:

- finite and strictly positive;
- evidence must label the value as `E`, Young's modulus, or an allow-listed equivalent;
- no material lookup such as `Q355 → E`;
- no unit conversion.

Identity-compatible modulus units depend on the accepted ModelSpec units:

```text
force=N,   length=m  → Pa or N/m²
force=N,   length=mm → N/mm²
force=kN,  length=m  → kN/m²
force=kN,  length=mm → kN/mm²
```

A numeric conversion requirement produces `CONFLICT`, not silent conversion.

### 8.4 SECTION_AREA

```json
{
  "kind": "SECTION_AREA",
  "source": "USER_EXPLICIT",
  "value": 0.02,
  "unit": "m²",
  "evidence": {"sourceId": "source_2", "quote": "A=0.02m²"}
}
```

Optional `sectionId` follows the same evidence rule as `materialId`: if the quote does not explicitly identify the section, omit the ID.

Rules:

- finite and strictly positive;
- evidence must identify area `A` or an allow-listed equivalent;
- unit must be the square of the accepted length unit;
- no unit conversion.

### 8.5 SECTION_IZ

```json
{
  "kind": "SECTION_IZ",
  "source": "USER_EXPLICIT",
  "value": 8e-5,
  "unit": "m⁴",
  "evidence": {"sourceId": "source_2", "quote": "Iz=8e-5m⁴"}
}
```

Optional `sectionId` is admissible only when evidenced.

Rules:

- finite and strictly positive;
- evidence must identify `Iz` or an allow-listed equivalent;
- unit must be the fourth power of the accepted length unit;
- no unit conversion.

## 9. Explicit Geometry and Topology Facts

### 9.1 NODE_COORDINATE

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

- positive integer node ID;
- finite coordinates;
- supported length unit;
- deterministic evidence grammar must recover node ID and coordinate pair;
- same node ID with different coordinates is `CONFLICT`.

### 9.2 ELEMENT_CONNECTIVITY

```json
{
  "kind": "ELEMENT_CONNECTIVITY",
  "source": "USER_EXPLICIT",
  "elementId": 1,
  "nodeI": 1,
  "nodeJ": 2,
  "evidence": {
    "sourceId": "source_1",
    "quote": "单元1连接节点1和节点2"
  }
}
```

This fact deliberately contains **only connectivity**. It cannot smuggle material or section references whose evidence quote does not prove them.

Rules:

- positive integer IDs;
- `nodeI != nodeJ`;
- deterministic evidence grammar must recover element ID and both node IDs;
- PR24 never invents arbitrary mesh connectivity.

### 9.3 ELEMENT_MATERIAL_REF

```json
{
  "kind": "ELEMENT_MATERIAL_REF",
  "source": "USER_EXPLICIT",
  "elementId": 1,
  "materialId": 2,
  "evidence": {
    "sourceId": "source_1",
    "quote": "单元1使用材料2"
  }
}
```

Both IDs must be deterministically evidenced.

### 9.4 ELEMENT_SECTION_REF

```json
{
  "kind": "ELEMENT_SECTION_REF",
  "source": "USER_EXPLICIT",
  "elementId": 1,
  "sectionId": 3,
  "evidence": {
    "sourceId": "source_1",
    "quote": "单元1使用截面3"
  }
}
```

Both IDs must be deterministically evidenced.

## 10. Constraint and Mass Facts

### 10.1 NODE_CONSTRAINT

```json
{
  "kind": "NODE_CONSTRAINT",
  "source": "USER_EXPLICIT",
  "nodeId": 1,
  "dofs": ["UX", "UY", "RZ"],
  "evidence": {"sourceId": "source_1", "quote": "1号节点固定"}
}
```

Allowed DOFs: `UX`, `UY`, `RZ`.

V1 deterministic evidence forms include:

- explicit DOF labels such as `约束UX和UY` / `fix UX UY`;
- exact controlled aliases `固定` / `fixed`, mapping to all three planar DOFs.

V1 does **not** interpret arbitrary support prose in no-template mode. Terms such as `铰支` or `滚动支座` do not become explicit constraints unless a controlled template handles the structural term or a future versioned alias rule is added.

### 10.2 NODAL_MASS

```json
{
  "kind": "NODAL_MASS",
  "source": "USER_EXPLICIT",
  "nodeId": 2,
  "mUX": 1000,
  "mUY": 1000,
  "evidence": {
    "sourceId": "source_1",
    "quote": "节点2的mUX和mUY均为1000"
  }
}
```

Rules:

- positive integer node ID;
- finite, non-negative mass values;
- no density/self-weight/geometry inference.

If no mass facts are present, V1 may assemble `nodalMasses=[]`. This means only “no nodal-mass entries were declared”, not “the physical structure has zero mass”.

## 11. Evidence Validation

Evidence validation is kind-specific and fail-closed.

### 11.1 Containment

For every fact and template intent:

```text
evidence.sourceId must resolve exactly once
evidence.quote must be non-empty
evidence.quote must be an exact substring of source.text
```

Failure gives `INVALID_DRAFT`.

### 11.2 Numeric consistency

The deterministic parser must recover the submitted numeric token from evidence. Supported V1 numeric syntax includes ordinary decimal and scientific notation.

```text
value=15, evidence="15m"          → admissible
value=12, evidence="15m"          → invalid
value=2.06e11, evidence="2.06e11" → admissible where kind grammar also matches
```

No fuzzy numeric matching.

### 11.3 Unit consistency

A fact requiring a unit must carry an allow-listed unit token matching the submitted unit after only V1 normalization. No magnitude-based unit inference.

### 11.4 Structural relation consistency

Node-coordinate, connectivity, reference, and constraint facts must match deterministic V1 relation grammars. Merely containing the right numbers is insufficient.

If the quote cannot be deterministically admitted to the submitted structural relation, the fact is `AMBIGUOUS`, not silently accepted.

### 11.5 Allowed normalization

Evidence/template matching may use only:

- Unicode NFKC;
- surrounding whitespace trim;
- deterministic whitespace collapse for English phrases;
- English case-folding.

There is no embedding similarity, edit distance, fuzzy NLP, RAG, or LLM call inside Python.

## 12. Controlled Template Registry

PR24 V1 contains exactly:

```text
SIMPLY_SUPPORTED_BEAM_2D_V1
CANTILEVER_BEAM_2D_V1
FIXED_FIXED_BEAM_2D_V1
```

Templates are code-owned versioned engineering rules, not knowledge-base prose.

Template intent:

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

### 12.1 Exact alias registry

`SIMPLY_SUPPORTED_BEAM_2D_V1`:

```text
简支梁
simply supported beam
```

`CANTILEVER_BEAM_2D_V1`:

```text
悬臂梁
cantilever beam
```

`FIXED_FIXED_BEAM_2D_V1`:

```text
两端固支梁
双端固支梁
fixed-fixed beam
fixed fixed beam
```

The broad alias `固支梁` is intentionally excluded because it can be ambiguous in ordinary engineering conversation. This is a safety tightening from the brainstorming example.

Template evidence must exactly match the selected template alias after allowed normalization. Otherwise the draft is invalid.

## 13. Template Semantics

All templates require an explicit positive `SPAN` fact and use the canonical local beam convention:

```text
node 1 = (0,0)
node 2 = (span,0)
element 1 = node 1 → node 2
```

### 13.1 SIMPLY_SUPPORTED_BEAM_2D_V1

```text
node 1: UX, UY constrained; RZ free
node 2: UY constrained; UX, RZ free
```

### 13.2 CANTILEVER_BEAM_2D_V1

```text
node 1: UX, UY, RZ constrained
node 2: free
```

Canonical orientation is fixed end at x=0 and free end at x=span. Explicit contradictory orientation/coordinates cause `CONFLICT`; the template is not silently flipped.

### 13.3 FIXED_FIXED_BEAM_2D_V1

```text
node 1: UX, UY, RZ constrained
node 2: UX, UY, RZ constrained
```

## 14. Derived Provenance

Examples:

```text
beam node IDs + single element topology
→ TEMPLATE_DERIVED
→ templateId = ...

support constraints
→ TEMPLATE_DERIVED
→ templateId = ...

node coordinates from span
→ DETERMINISTIC_DERIVED
→ ruleId = BEAM_SPAN_COORDINATES_V1

profile fields
→ DETERMINISTIC_DERIVED
→ ruleId = FRAME_2D_PROFILE_FIELDS_V1
```

Derived facts are never relabeled as `USER_EXPLICIT`.

## 15. Allow-Listed Deterministic Derivations

Only named V1 rules may add facts.

### 15.1 FRAME_2D_PROFILE_FIELDS_V1

Produces fixed profile fields:

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

### 15.2 CONSISTENT_LENGTH_UNIT_V1

If no explicit length-unit declaration exists and every accepted length-bearing fact uses the same supported unit, derive `units.length` from those explicit facts.

Thus `15m简支梁` may deterministically yield `units.length=m`.

Mixed length units are not converted and produce a unit conflict.

### 15.3 BEAM_SPAN_COORDINATES_V1

For a controlled beam template and accepted span `L`:

```text
node 1 = (0,0)
node 2 = (L,0)
```

### 15.4 SINGLETON_ENTITY_ID_V1

When exactly one material property set exists without an explicitly evidenced material ID, assign material ID `1`.

When exactly one section property set exists without an explicitly evidenced section ID, assign section ID `1`.

Not allowed with multiple materials/sections.

### 15.5 SINGLETON_ELEMENT_BINDING_V1

If exactly one material and one section exist, an element lacking explicit reference facts may bind to those singleton entities.

If multiple materials/sections exist, missing references are `AMBIGUOUS`.

### 15.6 EMPTY_NODAL_MASS_COLLECTION_V1

No mass facts → `nodalMasses=[]`, with the limited semantic meaning defined above.

No other deterministic derivation is allowed in V1.

## 16. Conflict Policy

Conceptual precedence:

```text
USER_EXPLICIT > TEMPLATE_DERIVED > DETERMINISTIC_DERIVED
```

But V1 never uses precedence for silent overwrite.

```text
consistent → merge
inconsistent → CONFLICT
```

Examples:

- simple-support template says right node `UY`, explicit fact says `UX,UY` → `CONFLICT`;
- span is `15m`, explicit model length unit is `mm` → `CONFLICT`;
- duplicate E values disagree → `CONFLICT`;
- same node ID has different coordinates → `CONFLICT`;
- values require unit conversion → `CONFLICT`.

There is no template override flag in PR24 V1. A non-standard support arrangement must use explicit no-template authoring or a future template version.

## 17. Missing and Ambiguous Facts

`MISSING` means required assembly information is absent.

`AMBIGUOUS` means information exists but cannot be admitted to one deterministic V1 meaning.

For:

```text
建立一个15m简支梁
```

expected missing facts include:

```text
units.force
units.time
material.youngsModulus
section.area
section.iz
```

`units.length` is not missing because `15m` supports `CONSISTENT_LENGTH_UNIT_V1`.

Examples of ambiguity:

- unsupported structural-relation evidence;
- omitted element material reference when multiple materials exist;
- broad `固支梁` phrase that selects no exact V1 template;
- unsupported support prose in no-template mode.

## 18. Completion Status Contract

Schema:

```text
FEMAGENT_ENGINEERING_REQUIREMENT_COMPLETION_V1
```

Statuses:

```text
COMPLETE
INCOMPLETE
CONFLICT
INVALID_DRAFT
```

### 18.1 COMPLETE

Requires:

- valid draft schema;
- all input facts admitted;
- valid optional template intent;
- no conflicts;
- no required assembly facts missing/ambiguous;
- candidate V1 ModelSpec assembled;
- candidate passes an internal PR21 validation invariant check.

Only `COMPLETE` returns non-null `candidateModelSpec`.

### 18.2 INCOMPLETE

Admissible request but required facts are missing/unresolved.

```text
candidateModelSpec = null
```

### 18.3 CONFLICT

Admissible facts disagree and V1 refuses automatic resolution.

```text
candidateModelSpec = null
```

### 18.4 INVALID_DRAFT

Schema/evidence integrity is malformed, for example:

- unknown fact kind/field;
- missing evidence source;
- evidence quote absent from source;
- numeric mismatch;
- template evidence mismatch.

```text
candidateModelSpec = null
```

Unexpected internal invariants use stable `FemCoreError` rather than a fake user status.

## 19. Completion Report

Conceptual shape:

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

### 19.1 requirementFingerprint

Deterministic SHA256 of canonical normalized draft content that affects completion:

- profile;
- source text;
- evidence references;
- normalized facts;
- template intent.

Semantically irrelevant collection order is canonicalized.

### 19.2 Identity chain

On `COMPLETE`, include authoritative PR21 `modelSpecFingerprint`:

```text
requirementFingerprint
        ↓
accepted + derived provenance
        ↓
candidate ModelSpec
        ↓
modelSpecFingerprint
        ↓
future PR23 renderFingerprint
```

## 20. Candidate ModelSpec Assembly

Candidate facts may come only from:

```text
admitted USER_EXPLICIT
+ controlled TEMPLATE_DERIVED
+ allow-listed DETERMINISTIC_DERIVED
```

### 20.1 Template beam path

With complete units/E/A/Iz, canonical singleton namespaces may be created where IDs are not explicitly evidenced:

```text
nodes    = 1,2
material = 1
section  = 1
element  = 1
```

### 20.2 Explicit no-template path

With `templateIntent=null`, explicit facts may define arbitrary PR21-V1 2D frame topology.

To assemble a candidate, V1 requires enough facts for:

- at least two nodes;
- at least one material;
- at least one section;
- at least one element;
- complete model units;
- element material/section bindings, either explicit or singleton-derived.

Constraints may be empty at completion time. PR22 remains responsible for rigid-body restraint/readiness. Therefore:

```text
PR24 COMPLETE ≠ PR22 READY
```

## 21. PR21 / PR22 / PR23 Boundaries

PR24 `COMPLETE` means only:

> the source-backed, controlled-completion draft can be assembled into a PR21-valid candidate ModelSpec.

It does not mean:

- renderer-ready;
- stable or adequate;
- solver-domain valid;
- numerically correct;
- physically correct;
- solved.

Public workflow still re-runs:

```text
PR24 complete
→ PR21 validate
→ PR22 readiness
→ PR23 render
→ Model Intelligence
→ OpenSees build-only / preflight
```

PR24 may internally call PR21 only as an invariant check before returning `COMPLETE`; consumers must still use public PR21 validation.

## 22. Public Python API

New package:

```text
fem_core/requirements/
├─ __init__.py
├─ schema.py
├─ evidence.py
├─ templates.py
└─ completion.py
```

Public entry point:

```python
complete_engineering_requirement(
    draft: dict[str, Any],
) -> dict[str, Any]
```

The function is deterministic and read-only.

It accepts no:

- output path;
- solver;
- LLM client;
- RAG client;
- caller-defined template.

## 23. Bridge, TypeScript, and Pi Tool

### 23.1 Bridge

Command:

```text
requirement.complete
```

Payload:

```json
{"draft": {}}
```

Bridge code performs transport only.

### 23.2 TypeScript

Types:

```text
FemEngineeringRequirementDraft
FemRequirementSource
FemRequirementFact
FemTemplateIntent
FemEngineeringRequirementCompletion
```

Helper:

```ts
runFemRequirementComplete(
  workspace: string,
  draft: FemEngineeringRequirementDraft,
  signal?: AbortSignal,
): Promise<FemEngineeringRequirementCompletion>
```

TypeScript does not implement engineering decisions or fingerprints.

### 23.3 Pi tool

Register SAFE/read-only:

```text
fem_requirement_complete
```

Agent guidance must require:

- exact source copying, not paraphrase;
- evidence for every explicit fact;
- no retrieved knowledge or Agent assumption labeled `USER_EXPLICIT`;
- no missing E/A/Iz/units invented to force `COMPLETE`;
- exact reporting of `missing`, `ambiguous`, and `conflicts`;
- public PR21/PR22 checks before render;
- no claim that `COMPLETE` means solver success.

## 24. Preferred Agent Workflow

```text
1. Read engineering request.
2. Preserve exact relevant user messages as draft sources.
3. Extract supported facts with exact evidence.
4. Select a template only on exact V1 alias evidence.
5. Call fem_requirement_complete.
6. INVALID_DRAFT → repair representation/evidence only.
7. CONFLICT → surface conflict; user must resolve it.
8. INCOMPLETE → ask only for actual missing/ambiguous engineering facts.
9. COMPLETE → pass candidate to fem_model_spec_validate.
10. Run fem_model_spec_readiness.
11. Render only if READY and model authoring is requested.
```

Repairing a draft must never change the user's engineering values.

## 25. End-to-End Beam Example

User turn 1:

```text
建立一个15m简支梁
```

Admitted input:

```text
SPAN = 15m → USER_EXPLICIT
template = SIMPLY_SUPPORTED_BEAM_2D_V1 → exact alias evidence
```

Derived:

```text
units.length = m
node 1 = (0,0)
node 2 = (15,0)
element 1 = 1→2
node 1 constraints = UX,UY
node 2 constraints = UY
```

Result:

```text
status = INCOMPLETE
candidateModelSpec = null
missing = units.force, units.time, E, A, Iz
```

User turn 2:

```text
单位用m、N、s，E=2.06e11 Pa，A=0.02m²，Iz=8e-5m⁴
```

The next draft includes both source segments. When evidence and units are identity-compatible:

```text
status = COMPLETE
candidateModelSpec != null
modelSpecFingerprint != null
```

Then the normal PR21→PR22→PR23 chain runs.

## 26. Explicit No-Template Example

Example request:

```text
节点1在(0,0)m，节点2在(5,3)m，节点3在(10,0)m；
单元1连接节点1和节点2，单元2连接节点2和节点3；
1号节点固定，3号节点约束UY；
E=...，A=...，Iz=...，单位为m、N、s。
```

The Agent submits typed facts with:

```text
templateIntent = null
```

If enough facts are deterministically admitted, PR24 returns `COMPLETE` without a template. If topology/reference evidence is missing or ambiguous, it stops rather than inventing mesh relations.

## 27. Stable Issue Codes

At minimum:

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

Structured missing/ambiguous/conflict records include code, subject, message, and relevant provenance references.

## 28. Test Matrix

### Template happy paths

Cover fully specified:

- 15m simple-support beam;
- 5m cantilever;
- 8m fixed-fixed beam.

Verify template ID, topology, constraints, provenance, and length-unit derivation.

### Evidence integrity

Cover:

```text
value=12 with evidence "15m"
unit=mm with evidence "15m"
quote absent from source
missing sourceId
wrong template ID for "简支梁"
unsupported structural relation
material/section ID submitted without evidence
```

### Missing facts

`15m简支梁` alone must be `INCOMPLETE`, candidate null, with force/time/E/A/Iz missing.

### Conflicts

Cover template-vs-explicit support, unit mismatch, duplicate E mismatch, duplicate coordinate mismatch, and conversion-required units.

### Explicit no-template path

A complete explicit 2D frame with `templateIntent=null` must reach `COMPLETE` and yield a PR21-valid candidate. Missing topology must never be invented.

### Determinism

Equivalent semantically unordered draft collections must yield the same normalized facts, `requirementFingerprint`, candidate structure, and `modelSpecFingerprint`.

### Downstream integration

Real production chain:

```text
complete_engineering_requirement
→ validate_engineering_model_spec
→ evaluate_engineering_model_readiness
→ render_opensees_frame_2d
```

Fully specified beam fixtures should reach `READY` then `RENDERED`.

### Bridge / TypeScript / Pi

Verify:

- typed COMPLETE / INCOMPLETE / CONFLICT / INVALID_DRAFT bridge results;
- real TS→Python transport;
- tool registration and Agent allow-list;
- read-only behavior;
- no renderer or solver-run call from the completion tool.

## 29. Non-Goals

PR24 V1 does not implement:

- an LLM inside `fem_core`;
- arbitrary free-form NLP inside Python;
- direct unguarded natural-language-to-ModelSpec generation;
- material databases or `Q355 → E`;
- section databases or `H500×300×11×18 → A/Iz`;
- unit conversion;
- magnitude-based unit inference;
- loads, gravity, distributed loads, analysis settings, damping, or result requests;
- 3D, truss, shell, or solid models;
- portal-frame or continuous-beam templates;
- template mutation/override;
- fuzzy/embedding/RAG template matching;
- automatic conflict repair;
- automatic ModelSpec repair;
- automatic rendering;
- solver execution;
- Semantic Role generation.

## 30. Capability Claim After PR24

Allowed claim:

> FEMagent can convert supported natural-language 2D frame requirements into a source-backed requirement draft, apply versioned controlled templates and deterministic derivations, report missing/ambiguous/conflicting engineering facts, and produce a candidate EngineeringModelSpec only when the controlled completion contract is satisfied.

Not allowed:

> FEMagent can infer arbitrary engineering models or missing engineering properties from vague language.

For `建立一个15m简支梁`, PR24 may admit the explicit span, apply the simple-support topology/support template, and derive the length unit from the explicit span unit, but must stop at `INCOMPLETE` until force/time units and required E/A/Iz are supplied or introduced by a future separately controlled engineering data source.

## 31. Implementation Boundary

Expected implementation footprint:

```text
fem_core/requirements/*
fem_core/bridge.py
packages/fem-tools/src/* requirement types/transport
.pi/extensions/* requirement tool
apps/agent/src/main.ts tool allow-list
tests/python/* PR24 tests
tests/ts/* PR24 tests
docs/* PR24 implementation/verification docs
```

PR24 must not alter PR21 validation semantics, PR22 readiness semantics, PR23 renderer mappings, solver adapters, ANSYS behavior, Result Intelligence, Load Intelligence, Knowledge/RAG truth separation, Semantic Roles, cross-solver validation, or optimization logic except narrow imports/exports required by integration tests.

## 32. Review Gate

This document is the PR24 architectural written-spec gate.

No production implementation begins until the user reviews and approves this spec. After written-spec approval, the next step is `writing-plans`, followed by TDD implementation and final exact-head verification.
