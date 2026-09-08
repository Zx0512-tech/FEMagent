# PR27 — EngineeringAnalysisSpec V2 Design

## 1. Purpose

PR27 upgrades FEMagent's solver-neutral analysis language from the static-only V1 contract into a versioned multi-analysis specification supporting exactly three structural analysis families:

- `LINEAR_STATIC`
- `MODAL`
- `TRANSIENT`

PR27 defines and validates analysis intent. It does **not** make the new V2 profiles executable. Readiness, renderer, worker/result extraction, and solver execution for V2 are follow-on work.

The architecture remains:

- `EngineeringModelSpec` = what the structural model is.
- `EngineeringAnalysisSpec` = what analysis should be performed.
- AnalysisSpec validation = whether the specification is intrinsically valid and deterministically normalized.
- Analysis Readiness = whether a validated ModelSpec + AnalysisSpec pair is executable by a concrete solver profile.
- Renderer = deterministic solver-specific compilation.
- SolverAdapter / solver = execution and numerical truth.
- Result Intelligence / Evidence = interpretation and provenance of recorded solver results.

`VALID` is never equivalent to `READY`, `RENDERED`, `SOLVER_READY`, `COMPLETED`, or `VERIFIED`.

## 2. Architectural principles

PR27 follows the FEMagent constitution:

1. The Agent decides what to do.
2. Deterministic engineering capabilities decide what is true.
3. Solvers decide numerical results.
4. Artifacts preserve what happened.

Additional principles:

- Use one shared V2 envelope with an analysis-type-discriminated `definition`.
- Do not create a giant universal schema with many unrelated optional fields.
- Preserve all previously proven V1 normalized semantics and fingerprints.
- V2 has an independent semantic fingerprint identity.
- AnalysisSpec expresses solver-neutral engineering intent, never OpenSees/ANSYS commands.
- Result requests remain whitelist-based.
- No silent unit inference, load summation, target repair, default damping, or solver configuration guessing.
- External artifact content identity is represented by SHA-256; filesystem path is locator/provenance metadata, not engineering identity.
- PR27 expands only the specification/validation layer for V2. All V2 profiles stop at `VALID` in this PR.
- Internal capability growth does not imply permanent LLM-visible tool growth.

## 3. Scope

### 3.1 In scope

PR27 supports AnalysisSpec schema versions `1.0` and `2.0` through one public validation entry point.

V2 supports exactly:

1. `LINEAR_STATIC`
2. `MODAL`
3. `TRANSIENT`

`TRANSIENT` means linear structural direct-integration time-history analysis.

Transient excitation types:

- `NODAL_TIME_HISTORY`
- `UNIFORM_BASE_EXCITATION`

Transient damping types:

- `NONE`
- `RAYLEIGH`

PR27 also adds deterministic migration from a valid V1 linear-static AnalysisSpec to V2 linear-static AnalysisSpec.

### 3.2 Out of scope

PR27 does not add:

- V2 Analysis Readiness or V2 renderer admission, including V2 static;
- modal or transient OpenSees renderers/workers/results;
- ANSYS V2 renderers;
- nonlinear static/transient analysis;
- pushover, response spectrum, buckling, harmonic, random vibration, moving load, thermal, or multiphysics analysis;
- distributed/gravity loads in the new static profile;
- multiple static load cases or combinations;
- modal participation/effective-mass metrics;
- modal solver selection or normalization controls;
- natural-language Analysis Requirement Completion;
- Controlled Repair;
- generic Semantic Role resolution;
- automatic target inference;
- automatic unit conversion;
- implicit 5% damping or any other damping default.

## 4. Versioning and compatibility

### 4.1 V1 remains authoritative for PR25/PR26 execution

Existing V1:

```json
{
  "schemaVersion": "1.0",
  "kind": "engineering_analysis_spec",
  "modelSpecFingerprint": "...",
  "analysisType": "LINEAR_STATIC",
  "units": {"force": "N"},
  "loadCases": [],
  "resultRequests": []
}
```

PR27 must preserve:

- V1 validation semantics;
- V1 normalized AnalysisSpec representation;
- V1 canonicalization;
- V1 `analysisSpecFingerprint`;
- the existing PR26 V1 readiness/render/generated-analysis verification path.

PR27 never silently rewrites V1 to V2.

The existing validation report protocol stays `FEMAGENT_ANALYSIS_SPEC_VALIDATION_V1`; PR27 does not require a new report field merely to expose the input schema version. Consumers can read `normalizedSpec.schemaVersion` when validation succeeds, while invalid-version issues remain explicit in `issues`.

### 4.2 V2 has independent identity

V2 envelope:

```json
{
  "schemaVersion": "2.0",
  "kind": "engineering_analysis_spec",
  "modelSpecFingerprint": "...",
  "analysisType": "LINEAR_STATIC | MODAL | TRANSIENT",
  "units": {},
  "definition": {},
  "resultRequests": []
}
```

Semantically equivalent V1 and V2 static specs intentionally have different fingerprints because schema identity and canonical representation differ.

## 5. V2 shared envelope

Exact top-level keys:

```text
schemaVersion
kind
modelSpecFingerprint
analysisType
units
definition
resultRequests
```

Required identities:

```text
schemaVersion = "2.0"
kind = "engineering_analysis_spec"
analysisType in {LINEAR_STATIC, MODAL, TRANSIENT}
modelSpecFingerprint = lowercase 64-character SHA-256 hex
```

`analysisType` discriminates the exact legal shapes of `units`, `definition`, and `resultRequests`.

A mismatched profile is invalid, for example `analysisType="MODAL"` with a transient time definition.

## 6. LINEAR_STATIC V2

### 6.1 Units

Exact shape:

```json
{"force": "N"}
```

Allowed force units: `N`, `kN`.

No unit conversion occurs during intrinsic validation.

### 6.2 Definition

Exact shape:

```json
{
  "loadCases": [
    {
      "loadCaseId": "LC1",
      "nodalLoads": [
        {"nodeId": 2, "FX": 0, "FY": -10000, "MZ": 0}
      ]
    }
  ]
}
```

Rules:

- exactly one load case;
- at least one nodal load;
- `loadCaseId` uses the existing identifier-token contract;
- `nodeId` is a positive integer;
- `FX`, `FY`, `MZ` are all explicitly present finite numbers;
- each nodal-load record has at least one non-zero component;
- duplicate node targets in one load case are invalid rather than summed.

### 6.3 Result requests

Whitelist:

NODE:

- `DISPLACEMENT` X/Y
- `REACTION_FORCE` X/Y
- `REACTION_MOMENT` Z

ELEMENT:

- `GENERALIZED_FORCE` N/VY/MZ at `END_I` or `END_J`

Static requests retain `loadCaseId`.

Example:

```json
{
  "requestId": "R1",
  "loadCaseId": "LC1",
  "quantity": "DISPLACEMENT",
  "target": {"type": "NODE", "id": 2},
  "component": "Y"
}
```

## 7. MODAL V2

### 7.1 Units

Exact shape:

```json
{}
```

Modal AnalysisSpec introduces no independent unit declaration.

### 7.2 Definition

Exact shape:

```json
{"modeCount": 10}
```

Rules:

- integer;
- `modeCount > 0`.

No eigen solver, shift, normalization, or frequency-range controls are exposed in PR27.

### 7.3 Result requests

Supported quantities:

- `EIGENVALUE`
- `NATURAL_FREQUENCY`
- `PERIOD`
- `MODE_SHAPE`

Scalar modal request:

```json
{
  "requestId": "FREQ_1",
  "quantity": "NATURAL_FREQUENCY",
  "mode": 1
}
```

`EIGENVALUE`, `NATURAL_FREQUENCY`, `PERIOD`:

- require `requestId`, `quantity`, `mode`;
- reject `target`, `component`, `location`, `loadCaseId`.

Mode shape:

```json
{
  "requestId": "MODE_1_NODE_3_Y",
  "quantity": "MODE_SHAPE",
  "mode": 1,
  "target": {"type": "NODE", "id": 3},
  "component": "Y"
}
```

`MODE_SHAPE`:

- requires NODE target;
- target ID positive integer;
- component `X`, `Y`, or `RZ`;
- no `loadCaseId`.

Every modal request must satisfy:

```text
1 <= mode <= definition.modeCount
```

This is intrinsic validation.

### 7.4 Modal result semantics for later layers

- `EIGENVALUE` = inverse time squared;
- `NATURAL_FREQUENCY` = Hz canonical presentation;
- `PERIOD` = time;
- `MODE_SHAPE` = normalization/convention dependent and must not be represented as a physical displacement without proven normalization semantics.

PR27 defines request semantics only; it does not claim solver mapping or result units are executable.

## 8. TRANSIENT V2

### 8.1 Meaning

`TRANSIENT` means linear structural direct-integration time-history analysis, not nonlinear dynamics.

### 8.2 Units

For `NODAL_TIME_HISTORY` quantity `FORCE`, exact `units` shape is:

```json
{"force": "N"}
```

Allowed force units: `N`, `kN`.

For `UNIFORM_BASE_EXCITATION`, exact shape is:

```json
{}
```

The standardized load artifact owns acceleration quantity/unit identity. Analysis time values inherit the bound ModelSpec time unit; PR27 does not duplicate time-unit declarations.

### 8.3 Time definition

Exact shape:

```json
{
  "timeStep": 0.01,
  "duration": 30.0
}
```

Rules:

- finite numbers;
- `timeStep > 0`;
- `duration > 0`.

PR27 does not read the artifact to compare sampling interval or final time. Those are later readiness checks.

### 8.4 Damping union

No damping:

```json
{"type": "NONE"}
```

Rayleigh damping:

```json
{
  "type": "RAYLEIGH",
  "alphaM": 0.0,
  "betaK": 0.002
}
```

Rules:

- `alphaM`, `betaK` finite;
- both non-negative;
- zero/zero remains a valid explicit Rayleigh definition and is not rewritten to `NONE`.

Bare damping ratio is out of scope because converting a damping ratio to Rayleigh coefficients requires additional engineering choices.

No damping default exists.

### 8.5 Load artifact reference

Transport/provenance shape:

```json
{
  "path": ".femagent/loads/eq.csv",
  "sha256": "64-char-lowercase-sha256"
}
```

Rules:

- `path` is a non-empty workspace-relative locator string;
- `sha256` is lowercase 64-character SHA-256 hex;
- intrinsic validation does not read file bytes.

`sha256` participates in semantic fingerprinting; `path` does not.

### 8.6 Excitation union

#### NODAL_TIME_HISTORY

```json
{
  "type": "NODAL_TIME_HISTORY",
  "nodeId": 5,
  "component": "Y",
  "quantity": "FORCE",
  "loadArtifact": {
    "path": ".femagent/loads/load.csv",
    "sha256": "..."
  }
}
```

Rules:

- `nodeId` positive integer;
- component `X` or `Y`;
- quantity exactly `FORCE`.

Nodal moment time history is out of scope.

#### UNIFORM_BASE_EXCITATION

```json
{
  "type": "UNIFORM_BASE_EXCITATION",
  "component": "X",
  "quantity": "ACCELERATION",
  "loadArtifact": {
    "path": ".femagent/loads/eq.csv",
    "sha256": "..."
  }
}
```

Rules:

- component `X` or `Y`;
- quantity exactly `ACCELERATION`.

Rotational ground motion is out of scope.

### 8.7 Definition

Exact shape:

```json
{
  "time": {"timeStep": 0.01, "duration": 30.0},
  "damping": {"type": "NONE"},
  "excitation": {
    "type": "UNIFORM_BASE_EXCITATION",
    "component": "X",
    "quantity": "ACCELERATION",
    "loadArtifact": {
      "path": ".femagent/loads/eq.csv",
      "sha256": "..."
    }
  }
}
```

No integration algorithm, solver tolerance, or recorder controls are exposed in PR27.

## 9. TRANSIENT result requests

Common whitelist:

NODE:

- `DISPLACEMENT` X/Y
- `VELOCITY` X/Y
- `REACTION_FORCE` X/Y
- `REACTION_MOMENT` Z

ELEMENT:

- `GENERALIZED_FORCE` N/VY/MZ at `END_I` or `END_J`

Transient requests do not contain `loadCaseId`; one V2 transient AnalysisSpec contains exactly one controlled excitation definition.

### 9.1 NODAL_TIME_HISTORY acceleration

`ACCELERATION` X/Y is allowed because there is no base-excitation reference ambiguity.

### 9.2 UNIFORM_BASE_EXCITATION acceleration

Bare `ACCELERATION` is invalid.

The request must explicitly choose:

- `RELATIVE_ACCELERATION` X/Y
- `ABSOLUTE_ACCELERATION` X/Y

PR27 validates only the solver-neutral distinction. A later readiness profile can reject either quantity if a concrete solver lacks a proven mapping.

## 10. Intrinsic validation versus readiness

PR27 validation checks only information contained in the AnalysisSpec.

Intrinsic validation includes:

- exact keys;
- schema version and discriminator;
- supported analysis type;
- identifier and target-ID syntax;
- finite numeric values;
- static duplicate load targets;
- modal mode-range checks;
- transient damping/excitation shapes;
- SHA syntax;
- acceleration-request semantics;
- deterministic normalization/fingerprinting.

Readiness later owns cross-model, cross-artifact, and solver-profile truth, including:

- target node/element existence;
- modal mass sufficiency;
- reaction restraint semantics;
- transient target existence;
- artifact bytes versus declared SHA;
- artifact quantity/unit compatibility;
- artifact time axis versus `timeStep`/`duration`;
- solver mapping for absolute/relative acceleration;
- concrete solver support.

Intrinsic validation must not perform hidden model/artifact reads to answer these questions.

## 11. Normalization

All valid V2 specs follow:

```text
validate
  ↓
normalize
  ↓
fingerprint projection
  ↓
SHA-256
```

Common normalized top-level fields:

```text
schemaVersion
kind
modelSpecFingerprint
analysisType
units
definition
resultRequests
```

Object source ordering does not affect identity.

`resultRequests` are sorted by `requestId`.

Duplicate semantic requests with distinct request IDs remain distinct and valid; PR27 does not deduplicate evidence intent.

Static normalization:

- load cases by `loadCaseId`;
- nodal loads by `nodeId`;
- requests by `requestId`.

Modal normalization:

- `modeCount` preserved;
- requests by `requestId`.

Transient normalization:

- time canonicalized;
- damping canonicalized;
- excitation canonicalized;
- requests by `requestId`;
- normalized spec retains artifact `path` for transport/provenance.

## 12. Fingerprint projection

V2 fingerprint:

```text
SHA256(canonical JSON fingerprint payload)
```

Canonical JSON:

- UTF-8;
- sorted object keys;
- compact separators;
- `allow_nan = false`.

For static and modal, fingerprint payload equals normalized spec.

For transient, fingerprint payload is derived from normalized spec but removes `loadArtifact.path` and retains `loadArtifact.sha256`.

Therefore two otherwise identical transient specs referencing identical artifact bytes at different paths have the same AnalysisSpec engineering identity.

V1 fingerprint behavior remains unchanged.

## 13. Validation report

Public API remains:

```python
validate_engineering_analysis_spec(spec)
```

Existing report protocol remains:

```json
{
  "schema": "FEMAGENT_ANALYSIS_SPEC_VALIDATION_V1",
  "status": "VALID | INVALID",
  "issues": [],
  "normalizedSpec": {},
  "analysisSpecFingerprint": "..."
}
```

PR27 does not require a report-protocol version change or an additional mandatory report field. A successful caller can inspect `normalizedSpec.schemaVersion`.

## 14. Validator architecture

Target responsibility split:

```text
fem_core/analysis_spec/
├── __init__.py
├── validator.py
├── common.py
├── v1.py
└── v2/
    ├── __init__.py
    ├── validator.py
    ├── static.py
    ├── modal.py
    ├── transient.py
    ├── normalization.py
    └── migration.py
```

Responsibilities:

- `validator.py`: schema-version router;
- `v1.py`: preserved PR25 V1 validation/normalization/fingerprint behavior;
- `v2/validator.py`: envelope/discriminator routing;
- profile modules: intrinsic rules only;
- `normalization.py`: V2 normalization and fingerprint projection;
- `migration.py`: pure V1 static to V2 static migration.

Equivalent file naming is acceptable if responsibilities stay isolated and the public API remains stable.

Router semantics:

```python
if schemaVersion == "1.0":
    return validate_v1(spec)
if schemaVersion == "2.0":
    return validate_v2(spec)
return INVALID
```

## 15. V1 to V2 migration

Public deterministic API:

```python
migrate_engineering_analysis_spec_v1_to_v2(spec)
```

Only a valid V1 `LINEAR_STATIC` spec can migrate.

Migration:

1. validates V1 source;
2. preserves `modelSpecFingerprint`;
3. preserves force units;
4. moves top-level `loadCases` to `definition.loadCases`;
5. preserves result requests semantically;
6. sets `schemaVersion="2.0"`;
7. validates V2 candidate;
8. returns source and target fingerprints.

It never reads a model/artifact, writes files, renders, repairs, or executes a solver.

Report:

```json
{
  "schema": "FEMAGENT_ANALYSIS_SPEC_MIGRATION_V1_TO_V2",
  "status": "MIGRATED",
  "source": {
    "schemaVersion": "1.0",
    "analysisSpecFingerprint": "..."
  },
  "target": {
    "schemaVersion": "2.0",
    "analysisSpecFingerprint": "..."
  },
  "candidateSpec": {}
}
```

Failure statuses:

- `INVALID_SOURCE`
- `UNSUPPORTED_SOURCE`

## 16. Bridge API

Keep:

```text
analysisSpec.validate
```

It accepts V1 or V2 and routes internally.

Add:

```text
analysisSpec.migrateV1ToV2
```

Do not add profile-specific validation commands.

## 17. TypeScript contract

Do not widen the existing V1 interface in place. Use a versioned discriminated union:

```ts
export interface FemEngineeringAnalysisSpecV1Input {
  schemaVersion: "1.0";
  // existing fields unchanged
}

export interface FemEngineeringLinearStaticAnalysisSpecV2Input {
  schemaVersion: "2.0";
  analysisType: "LINEAR_STATIC";
  // V2 static exact fields
}

export interface FemEngineeringModalAnalysisSpecV2Input {
  schemaVersion: "2.0";
  analysisType: "MODAL";
  // V2 modal exact fields
}

export interface FemEngineeringTransientAnalysisSpecV2Input {
  schemaVersion: "2.0";
  analysisType: "TRANSIENT";
  // V2 transient exact fields
}

export type FemEngineeringAnalysisSpecV2Input =
  | FemEngineeringLinearStaticAnalysisSpecV2Input
  | FemEngineeringModalAnalysisSpecV2Input
  | FemEngineeringTransientAnalysisSpecV2Input;

export type FemEngineeringAnalysisSpecInput =
  | FemEngineeringAnalysisSpecV1Input
  | FemEngineeringAnalysisSpecV2Input;
```

Existing PR26 readiness/render result types remain explicitly V1 linear-static in PR27.

## 18. Agent tool surface

Keep one validation tool:

```text
fem_analysis_spec_validate
```

Its input schema becomes a union of:

- V1 `LINEAR_STATIC`;
- V2 `LINEAR_STATIC`;
- V2 `MODAL`;
- V2 `TRANSIENT`.

Guidance must explicitly state:

> `VALID` V2 Static, Modal, or Transient proves only intrinsic solver-neutral validity. PR27 does not make any V2 spec READY/RENDERED for OpenSees or ANSYS.

Migration remains an internal/bridge/library capability unless a later Agent workflow demonstrates a need for a permanent LLM-visible migration tool.

## 19. PR26 compatibility

Existing V1 PR26 readiness, renderer, generated-analysis verifier, worker, result path, fingerprints, and golden path remain unchanged.

PR27 does **not** route V2 static into PR26 readiness/render.

If a V2 spec is submitted to the existing V1 preparation path, the path must fail closed with a stable unsupported-profile/version outcome rather than reinterpret the spec as V1.

All V2 profiles therefore stop at:

```text
VALID
```

PR28 will introduce V2 readiness/render admission and may reuse existing PR26 static compiler logic through a deterministic internal projection while preserving V2 identity.

## 20. Issue-code families

Shared:

- `ANALYSIS_SPEC_INVALID_SCHEMA`
- `ANALYSIS_SPEC_UNKNOWN_FIELD`
- `ANALYSIS_SPEC_INVALID_ID`
- `ANALYSIS_SPEC_INVALID_TARGET_ID`
- `ANALYSIS_SPEC_INVALID_NUMBER`
- `ANALYSIS_SPEC_UNSUPPORTED_ANALYSIS_TYPE`
- `ANALYSIS_SPEC_UNSUPPORTED_RESULT_REQUEST`
- `ANALYSIS_SPEC_DUPLICATE_ID`

Static:

- `ANALYSIS_SPEC_INVALID_LOAD_CASE_COUNT`
- `ANALYSIS_SPEC_DUPLICATE_NODAL_LOAD_TARGET`
- `ANALYSIS_SPEC_ZERO_NODAL_LOAD`
- `ANALYSIS_SPEC_RESULT_LOAD_CASE_NOT_FOUND`

Modal:

- `ANALYSIS_SPEC_INVALID_MODE_COUNT`
- `ANALYSIS_SPEC_INVALID_MODE_INDEX`
- `ANALYSIS_SPEC_MODE_EXCEEDS_REQUESTED_COUNT`

Transient:

- `ANALYSIS_SPEC_INVALID_TIME_STEP`
- `ANALYSIS_SPEC_INVALID_DURATION`
- `ANALYSIS_SPEC_INVALID_DAMPING`
- `ANALYSIS_SPEC_INVALID_EXCITATION`
- `ANALYSIS_SPEC_INVALID_LOAD_ARTIFACT`
- `ANALYSIS_SPEC_UNSUPPORTED_TRANSIENT_RESPONSE`

Cross-model, cross-artifact, and solver-mapping failures belong to later readiness/profile-specific code families.

## 21. Testing strategy

### 21.1 V1 regression

Prove:

- V1 valid fixtures remain valid;
- normalized V1 output unchanged;
- V1 fingerprints unchanged;
- PR26 V1 golden path remains green.

### 21.2 V2 static

Test:

- valid exact schema;
- unknown-field rejection;
- one-load-case rule;
- duplicate nodal target rejection;
- zero-load rejection;
- deterministic normalization;
- reordered equivalent input gives same V2 fingerprint;
- V1-to-V2 migration deterministic;
- V1/V2 fingerprints distinct;
- V2 static is rejected by existing V1 readiness/render admission.

### 21.3 Modal

Test:

- positive `modeCount` valid;
- non-positive `modeCount` invalid;
- mode zero invalid;
- mode above `modeCount` invalid;
- scalar modal request rejects target/component;
- mode shape requires NODE target;
- mode shape accepts X/Y/RZ only;
- deterministic request ordering/fingerprint.

### 21.4 Transient

Test:

- positive finite `timeStep`/`duration`;
- invalid time values rejected;
- exact `NONE` damping;
- non-negative finite Rayleigh coefficients;
- malformed SHA rejected;
- excitation union discriminator enforced;
- nodal force excitation units contract;
- uniform base excitation units contract;
- bare base-excitation `ACCELERATION` result rejected;
- relative/absolute acceleration valid intrinsically;
- same SHA + different artifact path => same fingerprint;
- different SHA => different fingerprint.

### 21.5 Discriminator safety

Examples:

- MODAL + transient definition => INVALID;
- TRANSIENT + static `loadCases` => INVALID;
- LINEAR_STATIC + modal `PERIOD` request => INVALID.

### 21.6 TypeScript / bridge

Test:

- V1 transport remains accepted;
- V2 union is type-safe;
- V1-to-V2 migration transport is pure/read-only;
- no new solver execution permission;
- existing V1 readiness/render rejects V2 rather than reinterpreting it.

## 22. Completion criteria

PR27 is complete only when:

1. V1 normalized semantics and fingerprints are regression-proven unchanged.
2. V2 shared envelope is implemented.
3. V2 `LINEAR_STATIC` validates/normalizes/fingerprints deterministically.
4. V2 `MODAL` validates/normalizes/fingerprints deterministically.
5. V2 `TRANSIENT` validates/normalizes/fingerprints deterministically.
6. All result-request whitelists are enforced.
7. Base-excitation relative/absolute acceleration semantics are explicit.
8. Transient artifact path is excluded from semantic fingerprint while SHA is included.
9. Deterministic V1-to-V2 static migration exists.
10. Python validation remains one version-routing entry point.
11. TypeScript AnalysisSpec is a safe V1/V2 discriminated union.
12. Current PR26 V1 static execution path remains fully green.
13. Every V2 profile, including V2 static, stops at `VALID` in PR27 and cannot be mislabeled READY/RENDERED.
14. No natural-language completion, repair, ANSYS rendering, nonlinear analysis, or optimization leaks into scope.
15. Standard verification is green:
    - `pnpm typecheck`
    - `pnpm test:ts`
    - `python -m pytest`
    - Ruff
    - `pnpm fem:health`

## 23. Follow-on roadmap

### PR28 — V2 Analysis Readiness + OpenSees Renderers

Admit V2 profiles into solver-specific readiness/rendering:

- V2 `LINEAR_STATIC` via deterministic reuse/projection of the proven PR26 static compiler while preserving V2 identity;
- V2 `MODAL` readiness + renderer + canonical modal results;
- V2 `TRANSIENT` readiness + renderer + structural response extraction.

### PR29 — Controlled Natural-Language Analysis Completion

Add evidence-backed Analysis Requirement Draft and deterministic completion for Static, Modal, and Transient. Controlled target resolution may use uniquely provable model/template facts but must not guess generic geometric roles.

### PR30 — Controlled Repair

Convert missing/ambiguous/conflict/readiness findings into explicit repair proposals requiring user/project adoption rather than silent engineering mutation.

### Later

- ANSYS parity for the same profiles;
- dual-solver golden paths;
- parameter/optimization specifications;
- broader modeling and analysis families.

## 24. Final architecture after PR27

```text
                     EngineeringAnalysisSpec
                              │
            ┌─────────────────┼─────────────────┐
            │                 │                 │
            v                 v                 v
     LINEAR_STATIC          MODAL           TRANSIENT
       V1 / V2              V2                 V2
            │                 │                 │
            └────────── intrinsic validation ──┘
                              │
                              v
                            VALID
                              │
           ┌──────────────────┴──────────────────┐
           │                                     │
           v                                     v
   V1 static only                       every V2 profile
 existing PR26 path                   stops at VALID in PR27
```

PR27 succeeds when FEMagent has a stable, versioned, solver-neutral engineering language for static, modal, and transient analysis without schema sprawl, while all previously proven V1 static behavior remains intact and no V2 profile is prematurely treated as executable.
