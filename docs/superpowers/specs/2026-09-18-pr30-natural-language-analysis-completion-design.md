# PR30 — Controlled Natural-Language Analysis Completion Design

Date: 2026-09-18

## Purpose

PR30 fills the gap between flexible user analysis requests and deterministic `EngineeringAnalysisSpec V2` construction.

The LLM may extract an evidence-backed analysis requirement draft. Python remains the engineering truth boundary and decides whether the request is complete, consistent with deterministic context, and safe to materialize as an AnalysisSpec.

```text
user language
   ↓
LLM extraction only
   ↓
AnalysisRequirementDraft V1
   ↓
deterministic completion
   ├─ exact source/quote evidence checks
   ├─ valid ModelSpec binding
   ├─ canonical load artifact re-read/hash
   ├─ dt/duration derivation from artifact
   ├─ explicit damping admission
   ├─ explicit node / semantic-role target resolution
   ├─ conflict / missing / ambiguity reporting
   └─ AnalysisSpec V2 validation
   ↓
COMPLETE → candidate EngineeringAnalysisSpec V2
otherwise → no candidate
```

PR30 is read-only. It never renders and never starts OpenSees or ANSYS.

## V1 scope

V1 intentionally supports the common denominator needed by PR28 + PR29:

- `TRANSIENT`
- `UNIFORM_BASE_EXCITATION`
- X or Y acceleration
- one canonical `FEMAGENT_LOAD_CSV_V1` earthquake channel
- explicit `NONE` or explicit `RAYLEIGH(alphaM,betaK)`
- NODE `DISPLACEMENT` X/Y
- restrained NODE `REACTION_FORCE` X/Y
- direct node targets or deterministic semantic-role-type resolution

Deferred:

- static/modal natural-language completion
- nodal-force transient
- ABSOLUTE/RELATIVE acceleration requests
- response spectrum
- damping-ratio → Rayleigh coefficient inference
- unit guessing
- automatic Semantic Role Manifest creation
- role inference from geometry
- element generalized-force completion
- nonlinear analysis
- optimization

## Trust model

There is no `LLM_INFERRED` engineering truth.

Input user claims use exact source snippets and quote evidence. Concrete model/load/semantic identities enter separately as deterministic context:

- ModelSpec → validated + fingerprinted by Python.
- load artifact → workspace-local bytes re-read and SHA-256 computed by Python.
- semantic roles → explicit manifest bound to exact Model Bundle fingerprint.

The output records whether facts are:

- `USER_EXPLICIT`
- `CONTEXT_BOUND`
- `DETERMINISTIC_DERIVED`

## Draft contract

```json
{
  "schema": "FEMAGENT_ANALYSIS_REQUIREMENT_DRAFT_V1",
  "profile": "TRANSIENT_UNIFORM_BASE_REQUIREMENT_V1",
  "sources": [
    {"sourceId":"s1","kind":"USER_MESSAGE","text":"..."}
  ],
  "intent": {
    "type": "TRANSIENT_UNIFORM_BASE",
    "evidence": {"sourceId":"s1","quote":"X向地震时程分析"}
  },
  "facts": []
}
```

Allowed facts:

- `EXCITATION_COMPONENT` — X/Y
- `LOAD_SELECTION` — confirms the user selected the context-bound earthquake record
- `DAMPING_NONE`
- `RAYLEIGH_DAMPING` — exact alphaM / betaK
- `RESULT_REQUEST`

Result target forms:

```json
{"type":"NODE","id":3}
```

or:

```json
{"type":"SEMANTIC_ROLE_TYPE","roleType":"GIRDER_END"}
```

Role-type aliases are closed and versioned. V1 supports:

- `GIRDER_END` ← 梁端 / girder end
- `TOWER_BASE` ← 塔底 / tower base
- `MIDSPAN` ← 跨中 / midspan
- `SUPPORT` ← 支座 / support
- `BEARING` ← 支承 / bearing
- `DAMPER_ATTACHMENT` ← 阻尼器连接点 / damper attachment

A role type resolves only when the supplied Semantic Role Manifest contains exactly one matching role and the entity is a NODE. Multiple matching roles produce ambiguity; Python never chooses one heuristically.

## Deterministic context

The completion call also carries:

```json
{
  "modelSpec": {...},
  "loadArtifactPath": "loads/earthquake.csv",
  "semanticContext": {
    "modelPath": "...",
    "manifestPath": "..."
  }
}
```

`semanticContext` is optional unless a result target uses `SEMANTIC_ROLE_TYPE`.

The canonical load path is not trusted from the LLM. Python resolves it inside the workspace, hashes the bytes, then parses it with the existing transient-artifact reader.

## Deterministic derivations

Allowed V1 derivations:

1. `MODEL_SPEC_BINDING_V1`
   - validate ModelSpec;
   - copy its exact `modelSpecFingerprint`.

2. `CANONICAL_LOAD_IDENTITY_V1`
   - compute artifact SHA-256;
   - verify one canonical earthquake uniform-excitation acceleration channel.

3. `TRANSIENT_TIME_FROM_ARTIFACT_V1`
   - require artifact start time = 0;
   - derive AnalysisSpec `timeStep` and `duration` from artifact times;
   - convert seconds only through the ModelSpec's explicit time unit.

4. `SEMANTIC_ROLE_TYPE_RESOLUTION_V1`
   - exact manifest/model binding;
   - exactly one matching role type;
   - NODE entity only.

5. `ANALYSIS_REQUEST_ID_V1`
   - assign deterministic request IDs `R1`, `R2`, ... after accepted-result ordering.

No other values are invented.

## Damping policy

PR30 never assumes zero damping.

- explicit “无阻尼 / 不考虑阻尼 / no damping” → `NONE`
- explicit `alphaM` and `betaK` → `RAYLEIGH`
- “5% damping” alone is insufficient and remains incomplete
- missing damping remains incomplete

## Result policy

V1 accepts only NODE displacement and reaction force.

A reaction request must point to a ModelSpec node whose corresponding `UX` or `UY` DOF is explicitly constrained. Otherwise the requirement conflicts with deterministic model context.

PR30 intentionally does not reinterpret “塔底剪力” as one nodal reaction. Base shear may require aggregation or element-force semantics, so that phrase must be clarified in V1 rather than silently mapped.

## Completion report

Schema:

`FEMAGENT_ANALYSIS_REQUIREMENT_COMPLETION_V1`

Statuses:

- `COMPLETE`
- `INCOMPLETE`
- `CONFLICT`
- `INVALID_DRAFT`
- `INVALID_CONTEXT`

`COMPLETE` means only that a candidate AnalysisSpec V2 passed intrinsic AnalysisSpec validation. It does not mean Analysis Readiness is READY and does not mean a solver has run.

## Public surface

Python:
`complete_engineering_analysis_requirement(...)`

Bridge:
`analysisRequirement.complete`

TypeScript:
`runFemAnalysisRequirementComplete(...)`

Pi:
`fem_analysis_requirement_complete`

The Pi tool is SAFE/read-only and does not bypass the existing solver execution permission gate.
