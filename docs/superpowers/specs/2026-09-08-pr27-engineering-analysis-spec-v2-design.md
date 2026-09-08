# PR27 — EngineeringAnalysisSpec V2 Design

## 1. Purpose

PR27 upgrades FEMagent's solver-neutral analysis language from a static-only V1 contract into a versioned multi-analysis specification that supports three structural analysis families:

- `LINEAR_STATIC`
- `MODAL`
- `TRANSIENT`

The goal is to expand the engineering language without collapsing schema design, solver readiness, renderer implementation, execution, or result interpretation into one change.

PR27 therefore defines and validates the analysis intent. It does not by itself make all three profiles executable.

The central distinction remains:

- `EngineeringModelSpec` = what the structural model is.
- `EngineeringAnalysisSpec` = what analysis should be performed on that model.
- AnalysisSpec validation = whether the analysis specification is intrinsically valid and normalized.
- Analysis Readiness = whether a validated ModelSpec + AnalysisSpec pair is executable by a concrete solver profile.
- Renderer = deterministic compilation into solver-specific artifacts.
- SolverAdapter / solver = execution and numerical truth.
- Result Intelligence / Evidence = recorded result interpretation and provenance.

`VALID` must never be treated as equivalent to `READY`, `RENDERED`, `SOLVER_READY`, `COMPLETED`, or `VERIFIED`.

## 2. Architectural principles

PR27 follows the FEMagent constitution:

1. The Agent decides what to do.
2. Deterministic engineering capabilities decide what is true.
3. Solvers decide numerical results.
4. Artifacts preserve what happened.

Additional PR27 principles:

- Use one shared AnalysisSpec envelope with a discriminated, analysis-specific `definition`.
- Avoid a giant universal schema containing many unrelated optional fields.
- Preserve V1 behavior and fingerprints exactly.
- V2 introduces its own semantic fingerprint identity.
- AnalysisSpec expresses solver-neutral engineering intent, not OpenSees or ANSYS commands.
- Result requests remain whitelist-based.
- No silent unit inference, load summation, target repair, default damping, or solver configuration guessing.
- External artifact content identity is represented by SHA-256; filesystem path is provenance/locator metadata, not engineering identity.
- PR27 expands the specification layer. Modal and transient readiness/rendering are separate later work.
- Internal capability growth does not imply permanent LLM-visible tool growth.

## 3. Scope

### 3.1 In scope

PR27 supports `EngineeringAnalysisSpec` schema versions `1.0` and `2.0`.

V2 supports exactly:

1. `LINEAR_STATIC`
2. `MODAL`
3. `TRANSIENT`

`TRANSIENT` in PR27 means:

> linear structural direct-integration time-history analysis.

Transient excitation types:

- `NODAL_TIME_HISTORY`
- `UNIFORM_BASE_EXCITATION`

Transient damping types:

- `NONE`
- `RAYLEIGH`

PR27 also adds deterministic V1-to-V2 migration for valid V1 linear-static AnalysisSpecs.

### 3.2 Explicitly out of scope

PR27 does not add:

- nonlinear static analysis;
- nonlinear transient analysis;
- pushover;
- response spectrum;
- buckling;
- harmonic analysis;
- random vibration;
- moving loads;
- thermal or multiphysics analysis;
- distributed or gravity loads to the new solver-neutral static profile;
- multiple static load cases or load combinations;
- modal participation factors, effective modal mass, mass participation ratios, or modal strain energy;
- modal solver selection or normalization controls;
- modal or transient OpenSees readiness/renderers;
- ANSYS renderers for V2;
- natural-language Analysis Requirement Completion;
- Controlled Repair;
- generic Semantic Role resolution;
- automatic engineering target inference;
- automatic unit conversion;
- implicit 5% damping or any other damping default.

## 4. Versioning and compatibility strategy

### 4.1 V1 remains authoritative for existing PR25/PR26 artifacts

Existing schema:

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

V1 validation, normalization, canonical serialization, and `analysisSpecFingerprint` must remain byte-for-byte behavior compatible with PR25.

PR27 must not silently rewrite a V1 spec to V2 during validation, readiness, rendering, or provenance verification.

### 4.2 V2 has independent identity

V2 uses:

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

A V1 linear-static spec and a semantically equivalent V2 linear-static spec have different AnalysisSpec fingerprints because the schema identity and canonical representation differ.

This is intentional.

## 5. V2 shared envelope

V2 top-level exact keys are:

```text
schemaVersion
kind
modelSpecFingerprint
analysisType
units
definition
resultRequests
```

No additional top-level fields are accepted.

Required identities:

```text
schemaVersion = "2.0"
kind = "engineering_analysis_spec"
analysisType in {LINEAR_STATIC, MODAL, TRANSIENT}
modelSpecFingerprint = lowercase 64-character SHA-256 hex
```

`analysisType` is the discriminator that determines the exact legal shapes of `units`, `definition`, and `resultRequests`.

A spec that combines one analysis type with another type's definition is intrinsically invalid.

Example invalid combination:

```json
{
  "analysisType": "MODAL",
  "definition": {
    "time": {"timeStep": 0.01, "duration": 30.0}
  }
}
```

## 6. LINEAR_STATIC V2 profile

### 6.1 Units

Exact shape:

```json
{
  "force": "N"
}
```

Allowed force units:

- `N`
- `kN`

PR27 performs no unit conversion.

### 6.2 Definition

Exact shape:

```json
{
  "loadCases": [
    {
      "loadCaseId": "LC1",
      "nodalLoads": [
        {
          "nodeId": 2,
          "FX": 0,
          "FY": -10000,
          "MZ": 0
        }
      ]
    }
  ]
}
```

V2 static V1-profile rules remain:

- exactly one load case;
- at least one nodal load;
- `loadCaseId` must satisfy the existing identifier token contract;
- `nodeId` must be a positive integer;
- `FX`, `FY`, and `MZ` must all be explicitly present finite numbers;
- each nodal-load record must contain at least one non-zero component;
- duplicate `nodeId` records in one load case are invalid rather than automatically summed.

### 6.3 Result request whitelist

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

## 7. MODAL V2 profile

### 7.1 Units

Exact shape:

```json
{}
```

Modal AnalysisSpec introduces no independent model-unit declaration. Modal response units are derived later from validated ModelSpec units and solver/result semantics.

### 7.2 Definition

Exact shape:

```json
{
  "modeCount": 10
}
```

Rules:

- `modeCount` is an integer;
- `modeCount > 0`.

PR27 does not expose eigen solver selection, shifts, normalization controls, or frequency ranges.

### 7.3 Result request whitelist

Supported modal quantities:

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

`EIGENVALUE`, `NATURAL_FREQUENCY`, and `PERIOD`:

- require `requestId`, `quantity`, and `mode`;
- do not accept `target`, `component`, `location`, or `loadCaseId`.

Mode-shape request:

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
- target ID must be positive;
- component must be `X`, `Y`, or `RZ`;
- no `loadCaseId`.

For every modal request:

```text
1 <= mode <= definition.modeCount
```

This is intrinsic validation because it depends only on the AnalysisSpec itself.

### 7.4 Modal unit semantics

Result-unit semantics are defined for later readiness/result mapping:

- `EIGENVALUE` = inverse time squared;
- `NATURAL_FREQUENCY` = Hz canonical presentation;
- `PERIOD` = ModelSpec time dimension;
- `MODE_SHAPE` = normalization/convention dependent and must not be presented as a physical displacement without explicit normalization semantics.

PR27 validates the request language only; it does not claim a solver mapping.

## 8. TRANSIENT V2 profile

### 8.1 Meaning

`TRANSIENT` means linear structural direct-integration time-history analysis.

It does not imply nonlinear dynamics.

### 8.2 Units

The V2 transient `units` object is exact and profile-dependent.

For `NODAL_TIME_HISTORY` with quantity `FORCE`:

```json
{
  "force": "N"
}
```

Allowed force units:

- `N`
- `kN`

For `UNIFORM_BASE_EXCITATION`:

```json
{}
```

The standardized load artifact owns excitation quantity/unit identity. Time units are inherited from the bound ModelSpec rather than duplicated in AnalysisSpec.

### 8.3 Time definition

Exact shape:

```json
{
  "timeStep": 0.01,
  "duration": 30.0
}
```

Rules:

- both values must be finite numbers;
- `timeStep > 0`;
- `duration > 0`.

PR27 does not inspect the load artifact to prove that its sampling interval or final time matches this definition. Those are readiness responsibilities.

### 8.4 Damping union

No damping:

```json
{
  "type": "NONE"
}
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

- `alphaM` and `betaK` must be finite;
- both must be non-negative;
- zero/zero is valid and is not automatically rewritten to `NONE`.

PR27 does not accept a bare `dampingRatio` because converting a modal damping ratio into Rayleigh coefficients requires additional engineering choices.

No damping default exists.

### 8.5 Load artifact reference

Exact transport shape:

```json
{
  "path": ".femagent/loads/eq.csv",
  "sha256": "64-char-lowercase-sha256"
}
```

Rules:

- `path` must be a non-empty workspace-relative locator string;
- `sha256` must be lowercase 64-character SHA-256 hex.

PR27 validation does not read the path or verify file bytes.

`sha256` participates in AnalysisSpec semantic fingerprinting.

`path` does not participate in semantic fingerprinting.

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

PR27 does not support nodal moment time history.

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

### 8.7 Transient definition exact shape

```json
{
  "time": {
    "timeStep": 0.01,
    "duration": 30.0
  },
  "damping": {
    "type": "NONE"
  },
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

No extra integration-algorithm, solver-tolerance, or recorder-control fields are part of PR27.

## 9. TRANSIENT result request whitelist

Common transient structural responses:

NODE:

- `DISPLACEMENT` X/Y
- `VELOCITY` X/Y
- `REACTION_FORCE` X/Y
- `REACTION_MOMENT` Z

ELEMENT:

- `GENERALIZED_FORCE` N/VY/MZ at `END_I` or `END_J`

Acceleration semantics depend on excitation type.

### 9.1 NODAL_TIME_HISTORY acceleration

`ACCELERATION` X/Y is allowed because there is no base-excitation reference ambiguity.

### 9.2 UNIFORM_BASE_EXCITATION acceleration

Bare `ACCELERATION` is invalid.

The request must explicitly choose:

- `RELATIVE_ACCELERATION` X/Y
- `ABSOLUTE_ACCELERATION` X/Y

PR27 only validates this solver-neutral distinction. A later readiness profile may reject a quantity if no proven solver mapping exists.

Transient requests do not carry `loadCaseId` in V2 because one AnalysisSpec contains exactly one controlled excitation definition.

## 10. Intrinsic validation versus readiness

PR27 validation checks only facts contained in the AnalysisSpec itself.

Examples of PR27 validation responsibilities:

- exact keys;
- discriminator correctness;
- supported analysis type;
- identifiers;
- finite numeric values;
- static duplicate load targets;
- modal mode-range validity;
- transient damping shape;
- transient excitation shape;
- SHA syntax;
- transient acceleration request semantics;
- deterministic normalization and fingerprinting.

The following belong to later Analysis Readiness and must not be guessed or checked by intrinsic validation through hidden model/artifact reads:

- whether a node/element target exists in the ModelSpec;
- whether modal mass is defined and sufficient;
- whether a requested reaction DOF is restrained;
- whether a transient excitation target exists;
- whether load artifact bytes match the declared SHA;
- whether artifact quantity/unit matches excitation declaration;
- whether transient artifact time axis matches `timeStep` / `duration`;
- whether a solver can map absolute/relative acceleration correctly;
- whether a concrete solver supports the requested profile.

## 11. Normalization

All valid specs follow:

```text
validate
  ↓
normalize
  ↓
fingerprint projection
  ↓
SHA-256
```

### 11.1 Common normalization

Canonical normalized V2 top-level order is conceptually:

```text
schemaVersion
kind
modelSpecFingerprint
analysisType
units
definition
resultRequests
```

JSON object source ordering does not affect identity.

`resultRequests` are sorted by `requestId`.

Duplicate semantic requests with different request IDs remain distinct and valid. PR27 does not deduplicate requested evidence intent.

### 11.2 Static normalization

- load cases sorted by `loadCaseId`;
- nodal loads sorted by `nodeId`;
- result requests sorted by `requestId`.

### 11.3 Modal normalization

- `modeCount` preserved;
- result requests sorted by `requestId`.

### 11.4 Transient normalization

- time object canonicalized;
- damping object canonicalized;
- excitation object canonicalized;
- result requests sorted by `requestId`.

The normalized spec retains load artifact `path` for transport/provenance.

## 12. Fingerprint projection and identity

V2 `analysisSpecFingerprint` is:

```text
SHA256(canonical JSON fingerprint payload)
```

Canonical JSON uses:

- UTF-8;
- sorted object keys;
- compact separators;
- `allow_nan = false`.

For static and modal, the fingerprint payload is the normalized spec.

For transient, the fingerprint payload is derived from the normalized spec but removes `loadArtifact.path` and retains `loadArtifact.sha256`.

Therefore two transient specs that reference the same artifact bytes under different workspace paths have the same engineering AnalysisSpec identity.

Filesystem location remains provenance, not engineering truth.

V1 fingerprint behavior remains unchanged and separate.

## 13. Validation report contract

The existing validation report protocol remains:

```text
FEMAGENT_ANALYSIS_SPEC_VALIDATION_V1
```

PR27 adds explicit input schema-version identity:

```json
{
  "schema": "FEMAGENT_ANALYSIS_SPEC_VALIDATION_V1",
  "analysisSpecSchemaVersion": "2.0",
  "status": "VALID",
  "issues": [],
  "normalizedSpec": {},
  "analysisSpecFingerprint": "..."
}
```

For a V1 input:

```text
analysisSpecSchemaVersion = "1.0"
```

The report protocol version is not the same thing as the AnalysisSpec schema version.

## 14. Validator module architecture

The public Python API remains:

```python
validate_engineering_analysis_spec(spec)
```

PR27 refactors implementation boundaries into version/profile modules rather than growing the existing static validator indefinitely.

Target structure:

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

- `validator.py`: schema-version router only.
- `v1.py`: preserved PR25 V1 behavior.
- `v2/validator.py`: V2 envelope/discriminator router.
- `v2/static.py`: V2 static intrinsic rules.
- `v2/modal.py`: V2 modal intrinsic rules.
- `v2/transient.py`: V2 transient intrinsic rules.
- `v2/normalization.py`: canonical V2 normalization/fingerprint projection.
- `v2/migration.py`: deterministic V1 static to V2 static migration.

If implementation discovers a cleaner equivalent file split, responsibilities must remain isolated even if exact filenames differ.

## 15. V1 to V2 migration

Public deterministic Python API:

```python
migrate_engineering_analysis_spec_v1_to_v2(spec)
```

Only a valid V1 `LINEAR_STATIC` spec can migrate.

Migration:

1. validates source V1;
2. preserves `modelSpecFingerprint`;
3. preserves force units;
4. moves top-level `loadCases` into `definition.loadCases`;
5. preserves result requests semantically;
6. changes `schemaVersion` to `2.0`;
7. validates target V2;
8. returns both source and target fingerprints.

Migration never reads a model, reads a load artifact, writes files, renders, repairs, or executes a solver.

Report shape:

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

Keep the existing validation command:

```text
analysisSpec.validate
```

It accepts V1 or V2 and routes internally.

Add one deterministic migration command:

```text
analysisSpec.migrateV1ToV2
```

Do not add profile-specific bridge commands such as:

- `analysisSpec.validateV2`
- `analysisSpec.validateModal`
- `analysisSpec.validateTransient`

## 17. TypeScript contract

Current public type must become a versioned discriminated union rather than widening the existing V1 interface unsafely.

Required structure:

```ts
export interface FemEngineeringAnalysisSpecV1Input {
  schemaVersion: "1.0";
  // existing PR25 fields unchanged
}

export interface FemEngineeringLinearStaticAnalysisSpecV2Input {
  schemaVersion: "2.0";
  analysisType: "LINEAR_STATIC";
  // V2 static fields
}

export interface FemEngineeringModalAnalysisSpecV2Input {
  schemaVersion: "2.0";
  analysisType: "MODAL";
  // V2 modal fields
}

export interface FemEngineeringTransientAnalysisSpecV2Input {
  schemaVersion: "2.0";
  analysisType: "TRANSIENT";
  // V2 transient fields
}

export type FemEngineeringAnalysisSpecV2Input =
  | FemEngineeringLinearStaticAnalysisSpecV2Input
  | FemEngineeringModalAnalysisSpecV2Input
  | FemEngineeringTransientAnalysisSpecV2Input;

export type FemEngineeringAnalysisSpecInput =
  | FemEngineeringAnalysisSpecV1Input
  | FemEngineeringAnalysisSpecV2Input;
```

Validation response type gains:

```ts
analysisSpecSchemaVersion: "1.0" | "2.0";
```

Existing PR26 readiness/render result types remain explicitly linear-static until later work.

## 18. Agent tool surface

Keep one LLM-visible fine-grained validation tool:

```text
fem_analysis_spec_validate
```

Its schema becomes a union of:

- V1 `LINEAR_STATIC`;
- V2 `LINEAR_STATIC`;
- V2 `MODAL`;
- V2 `TRANSIENT`.

The tool guidance must state:

> `VALID` V2 MODAL or TRANSIENT means only that the solver-neutral AnalysisSpec is intrinsically valid. PR27 does not prove OpenSees or ANSYS readiness/render support for those profiles.

The migration capability may be exposed through transport/library APIs but should not automatically become a permanent high-level LLM-visible tool unless an actual Agent workflow needs it.

## 19. PR26 compatibility

### 19.1 Existing V1 path

Existing V1 PR26 readiness/render behavior must remain unchanged.

All existing V1 golden-path fingerprints and generated-analysis verification semantics remain authoritative.

### 19.2 V2 LINEAR_STATIC compatibility

PR27 may admit V2 static into the existing PR26 static execution path through a deterministic internal projection.

Conceptually:

```text
V2 LINEAR_STATIC
      ↓
V2 validation / V2 fingerprint
      ↓
internal static execution projection
      ↓
existing PR26 static readiness/compiler logic
```

The projection is an implementation reuse mechanism only.

It must not relabel the V2 spec or fingerprint as V1.

If this compatibility path cannot preserve the existing PR26 generated-analysis verification invariants cleanly, PR27 must leave V2 static at VALID and defer V2 readiness/render admission rather than weaken provenance guarantees.

### 19.3 MODAL and TRANSIENT

PR27 must not report them READY through the current PR26 OpenSees profile.

They remain valid solver-neutral specifications awaiting later profile-specific readiness/renderers.

## 20. Issue-code families

Shared intrinsic validation codes reuse/extend the existing family:

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

Cross-model, cross-artifact, and solver-mapping failures must use readiness/profile-specific codes later, not intrinsic AnalysisSpec codes.

## 21. Testing strategy

### 21.1 V1 regression

Must prove:

- existing V1 valid fixtures remain valid;
- existing normalized V1 output is unchanged;
- existing V1 fingerprints are unchanged;
- PR26 V1 golden path remains green.

### 21.2 V2 static

Test:

- valid static spec;
- exact-key rejection;
- one-load-case rule;
- duplicate nodal target rejection;
- zero-load rejection;
- deterministic ordering;
- same semantics with reordered JSON produce same V2 fingerprint;
- V1 to V2 migration is deterministic;
- source fingerprint and target fingerprint are distinct.

### 21.3 Modal

Test:

- positive `modeCount` valid;
- `modeCount <= 0` invalid;
- mode 0 invalid;
- request mode above `modeCount` invalid;
- scalar modal requests reject targets/components;
- mode shape requires NODE target;
- mode shape accepts X/Y/RZ only;
- reordered requests retain deterministic fingerprint.

### 21.4 Transient

Test:

- positive finite `timeStep` and `duration`;
- non-positive or non-finite time values invalid;
- `NONE` damping exact shape;
- Rayleigh non-negative finite coefficients;
- malformed SHA invalid;
- unsupported excitation invalid;
- nodal force excitation unit contract;
- uniform base excitation unit contract;
- bare base-excitation `ACCELERATION` request invalid;
- relative/absolute acceleration requests valid intrinsically;
- different artifact paths with identical SHA produce identical AnalysisSpec fingerprint;
- different artifact SHA produces different fingerprint.

### 21.5 Discriminator safety

Each analysis type must reject another profile's definition and result-request-only fields where forbidden.

Examples:

- `MODAL` + transient time definition -> INVALID;
- `TRANSIENT` + static loadCases definition -> INVALID;
- `LINEAR_STATIC` + modal result `PERIOD` -> INVALID.

### 21.6 TypeScript / bridge

Test:

- V1 transport remains accepted;
- V2 three-profile union is type-safe;
- validation transport includes `analysisSpecSchemaVersion`;
- migration transport works and does not write artifacts;
- no new solver execution permissions are introduced.

## 22. Completion criteria

PR27 is complete only when all of the following are true:

1. V1 AnalysisSpec behavior and fingerprints are regression-proven unchanged.
2. V2 exact envelope is implemented.
3. V2 `LINEAR_STATIC` validates and normalizes deterministically.
4. V2 `MODAL` validates and normalizes deterministically.
5. V2 `TRANSIENT` validates and normalizes deterministically.
6. V2 result-request whitelists are enforced.
7. Transient relative/absolute acceleration semantics are explicit for base excitation.
8. Transient artifact path is excluded from semantic fingerprint while SHA remains included.
9. Deterministic V1-to-V2 static migration exists.
10. Python public validation API remains one version-routing entry point.
11. TypeScript public AnalysisSpec input becomes a safe V1/V2 discriminated union.
12. Current PR26 V1 static execution path remains fully green.
13. MODAL/TRANSIENT are never mislabeled READY or RENDERED by PR27.
14. No natural-language completion, repair, ANSYS rendering, nonlinear analysis, or optimization work leaks into scope.
15. Standard repository verification remains green:
    - `pnpm typecheck`
    - `pnpm test:ts`
    - `python -m pytest`
    - Ruff
    - `pnpm fem:health`

## 23. Follow-on roadmap

After PR27:

### PR28 — OpenSees Modal + Transient Readiness/Renderer

Add profile-specific readiness and deterministic OpenSees render/extraction paths for validated V2 `MODAL` and `TRANSIENT` specs.

### PR29 — Controlled Natural-Language Analysis Completion

Add evidence-backed natural-language Analysis Requirement Draft and deterministic completion for Static, Modal, and Transient.

Controlled deterministic target resolution may use uniquely provable model/template facts, but must not guess generic geometric roles.

### PR30 — Controlled Repair

Turn missing, ambiguous, conflict, and readiness findings into explicit repair proposals requiring user/project adoption rather than silent engineering mutation.

### Later

- ANSYS renderer parity for the same analysis profiles;
- dual-solver golden paths;
- parameter/optimization specifications;
- broader modeling/analysis families.

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
               ┌──────────────┴──────────────┐
               │                             │
               v                             v
      existing static path        future profile readiness
        remains proven             (PR28 and later)
```

PR27's success is not that FEMagent can already execute every new analysis profile. Its success is that FEMagent gains a stable, versioned, solver-neutral engineering language in which static, modal, and transient analyses can be represented without ambiguity or schema sprawl, while preserving all previously proven V1 static behavior.
