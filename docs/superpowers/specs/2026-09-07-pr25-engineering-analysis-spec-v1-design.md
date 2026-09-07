# PR25 — Engineering Analysis Specification V1 Design

## 1. Purpose

PR25 introduces a deterministic, solver-neutral `EngineeringAnalysisSpec` layer for FEMagent.

The goal is to separate **what the structural model is** from **what analysis should be performed on that model**.

```text
EngineeringModelSpec
= model truth

EngineeringAnalysisSpec
= analysis intent bound to one exact model identity
```

PR25 does not execute OpenSees or ANSYS, does not generate solver-specific analysis code, and does not repair or infer missing engineering facts. It establishes the contract that later Analysis Readiness and solver renderers will consume.

The intended chain is:

```text
Natural-language requirement
        |
        v
EngineeringModelSpec
        |
        v
modelSpecFingerprint
        |
        v
EngineeringAnalysisSpec
        |
        v
analysisSpec.validate
  strict schema validation
  deterministic normalization
  analysisSpecFingerprint
        |
        v
VALID / INVALID
```

PR26 will combine `EngineeringModelSpec` and `EngineeringAnalysisSpec` to determine analysis readiness and render controlled OpenSees analysis code.

## 2. Architectural decision

PR25 follows the FEMagent architecture constitution:

1. The LLM/Agent understands user intent and organizes information.
2. Python `fem_core` owns deterministic engineering truth, validation, normalization, and fingerprints.
3. Solver adapters own actual numerical execution.
4. Result/Evidence layers own numerical-result truth and provenance.
5. Knowledge/RAG may provide guidance, but retrieved knowledge cannot silently become executable engineering truth.

Therefore the authoritative `EngineeringAnalysisSpec` validator belongs in Python `fem_core`.

TypeScript mirrors the contract for transport and Agent integration but does not become a second engineering validator.

### 2.1 Long-term Agent tool-surface constraint

**Internal capability growth does not imply permanent LLM-visible tool growth.**

PR25 may introduce a deterministic `analysisSpec.validate` capability in `fem_core` and expose a TypeScript bridge wrapper so the capability can be tested and composed. A temporary fine-grained Agent tool may also be registered during this development phase if useful for validation and integration testing.

However, PR25 does **not** establish a requirement that every internal bridge command remain exposed as a permanent independent LLM-visible tool.

FEMagent should progressively converge its long-term Agent-facing interface into a small number of high-level capability domains such as:

```text
Modeling
Analysis
Result
Evidence
Knowledge
```

Fine-grained validation, readiness, normalization, rendering, solver, and evidence functions remain inside the deterministic engineering core.

The desired long-term relationship is:

```text
many internal capabilities
        |
        v
small high-level Agent tool surface
```

This constraint exists to reduce Agent context growth, tool-selection ambiguity, and duplicated orchestration logic.

## 3. Scope

PR25 V1 supports only:

```text
model family         = 2D FRAME (through bound ModelSpec identity)
analysis type        = LINEAR_STATIC
load source          = explicit nodal loads only
load components      = FX, FY, MZ
force units          = N | kN
load cases           = exactly one explicit load case
result requests      = explicit controlled requests
normalization        = deterministic
identity             = analysisSpecFingerprint
solver execution     = none
```

### 3.1 Explicitly out of scope

PR25 does not implement:

- solver execution;
- OpenSees analysis-code generation;
- ANSYS analysis-code generation;
- distributed member loads;
- gravity inference;
- self-weight inference;
- unit conversion;
- load-direction inference;
- automatic load-node selection;
- automatic load summation;
- dynamic analysis;
- response-spectrum analysis;
- earthquake time-history analysis;
- nonlinear analysis;
- modal analysis;
- load combinations;
- automatic repair;
- optimization;
- natural-language analysis completion.

These remain separate later concerns.

## 4. Relationship to existing FEMagent layers

### 4.1 EngineeringModelSpec remains model truth

`EngineeringModelSpec` answers:

> What model is intended to exist?

It owns geometry, topology, materials, sections, constraints, masses, model units, and canonical model identity.

PR25 must not move loads or analysis controls into `EngineeringModelSpec`.

### 4.2 EngineeringAnalysisSpec owns analysis intent

`EngineeringAnalysisSpec` answers:

> What should be done to this exact model?

It owns:

- bound model identity;
- analysis type;
- explicit analysis-level force unit;
- explicit load cases;
- explicit nodal loads;
- explicit result requests;
- canonical analysis identity.

### 4.3 Load Intelligence remains distinct

Existing Load Intelligence handles external/file/time-series load data inspection and deterministic standardization. Its canonical artifacts are not the same thing as `EngineeringAnalysisSpec`.

PR25 V1 supports inline explicit nodal loads only.

A future AnalysisSpec revision may reference canonical load artifacts, but PR25 does not collapse external load ingestion into the analysis contract.

### 4.4 Structural Response semantics are reused

PR25 does not invent a second result vocabulary.

Where possible, result requests reuse the existing Structural Response identity:

```text
quantity
target
component
location
```

PR25 applies a narrower V1 whitelist appropriate to 2D linear-static frame analysis.

## 5. EngineeringAnalysisSpec V1 contract

A V1 spec has exactly these top-level fields:

```json
{
  "schemaVersion": "1.0",
  "kind": "engineering_analysis_spec",
  "modelSpecFingerprint": "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef",
  "analysisType": "LINEAR_STATIC",
  "units": {
    "force": "kN"
  },
  "loadCases": [
    {
      "loadCaseId": "LC1",
      "nodalLoads": [
        {
          "nodeId": 2,
          "FX": 0,
          "FY": -10,
          "MZ": 0
        }
      ]
    }
  ],
  "resultRequests": [
    {
      "requestId": "R1",
      "loadCaseId": "LC1",
      "quantity": "DISPLACEMENT",
      "target": {
        "type": "NODE",
        "id": 2
      },
      "component": "Y"
    }
  ]
}
```

Unknown fields are rejected at every object level. V1 is fail-closed.

## 6. Model binding

`modelSpecFingerprint` is mandatory.

It must match exactly:

```text
^[0-9a-f]{64}$
```

The value therefore represents a canonical lowercase SHA-256 fingerprint of one exact normalized `EngineeringModelSpec`.

PR25 rejects:

- missing fingerprints;
- uppercase hexadecimal fingerprints;
- non-hex strings;
- non-64-character strings;
- file paths;
- model names;
- aliases such as `current`, `latest`, or `active`.

PR25 validates only the fingerprint **shape**. It does not resolve the fingerprint to a real ModelSpec artifact.

The later Analysis Readiness layer is responsible for checking that the bound model identity actually exists and matches the supplied model.

## 7. Analysis type

V1 accepts exactly:

```text
LINEAR_STATIC
```

Any other analysis type is invalid.

This is intentional YAGNI scope control. PR25 first establishes a stable static-analysis contract before transient, modal, spectrum, nonlinear, or combination semantics are introduced.

## 8. Units

A V1 analysis spec contains exactly:

```json
{
  "force": "N"
}
```

or:

```json
{
  "force": "kN"
}
```

No other force unit is supported in V1.

PR25 performs no unit conversion and never infers a force unit from numerical magnitude or engineering convention.

### 8.1 Nodal moment unit

`MZ` does not receive a separate moment-unit field.

Its unit is defined as:

```text
AnalysisSpec force unit × bound ModelSpec length unit
```

Examples:

```text
AnalysisSpec.force = kN
ModelSpec.length   = m
MZ unit            = kN·m
```

```text
AnalysisSpec.force = N
ModelSpec.length   = mm
MZ unit            = N·mm
```

PR25 cannot validate cross-spec unit compatibility because it intentionally validates `EngineeringAnalysisSpec` in isolation. That check belongs in PR26 Analysis Readiness.

## 9. Load-case contract

V1 requires exactly one load case:

```text
len(loadCases) == 1
```

The data model still uses `loadCases[]` so future revisions can add multiple load cases or combinations without replacing the top-level shape.

Each load case has exactly:

```json
{
  "loadCaseId": "LC1",
  "nodalLoads": []
}
```

`loadCaseId` must match:

```text
^[A-Za-z][A-Za-z0-9_-]{0,63}$
```

`nodalLoads` must be non-empty.

## 10. Nodal-load contract

Each nodal load has exactly:

```json
{
  "nodeId": 3,
  "FX": 0,
  "FY": -10,
  "MZ": 0
}
```

Rules:

- `nodeId` is a positive integer and boolean values are rejected;
- `FX`, `FY`, and `MZ` are all mandatory;
- `FX`, `FY`, and `MZ` must be finite JSON numbers;
- strings such as `"10"` are invalid;
- booleans are invalid numbers;
- NaN and infinities are invalid;
- at least one of `FX`, `FY`, and `MZ` must be nonzero for each nodal-load record;
- a node may appear at most once within a load case.

### 10.1 No automatic summation

The following input is invalid:

```json
[
  {"nodeId": 3, "FX": 0, "FY": -10, "MZ": 0},
  {"nodeId": 3, "FX": 5, "FY": 0, "MZ": 0}
]
```

The validator must not silently convert it to one combined load.

Automatic summation would modify engineering intent and therefore violates the fail-closed boundary.

### 10.2 No target inference

PR25 never maps words such as `midspan`, `left support`, `tower top`, or `girder end` to node IDs.

Semantic interpretation and controlled requirement completion remain separate layers.

## 11. Result-request contract

Each result request contains:

```text
requestId
loadCaseId
quantity
target
component
[location]
```

`requestId` must match:

```text
^[A-Za-z][A-Za-z0-9_-]{0,63}$
```

and must be unique inside the spec.

`loadCaseId` must refer to the sole load case present in this AnalysisSpec. This is internal AnalysisSpec referential integrity, so PR25 validates it directly.

Target IDs are positive integers. PR25 does **not** verify that the node or element actually exists in the bound ModelSpec.

### 11.1 V1 result whitelist

PR25 V1 allows exactly these combinations:

| Quantity | Target | Component | Location |
| --- | --- | --- | --- |
| `DISPLACEMENT` | `NODE` | `X`, `Y` | forbidden |
| `REACTION_FORCE` | `NODE` | `X`, `Y` | forbidden |
| `REACTION_MOMENT` | `NODE` | `Z` | forbidden |
| `GENERALIZED_FORCE` | `ELEMENT` | `N`, `VY`, `MZ` | `END_I`, `END_J` required |

The whitelist is intentionally narrower than the global Structural Response system.

PR25 does not add:

- velocity;
- acceleration;
- stress;
- principal stress;
- damper response;
- generalized-force `SECTION` location;
- out-of-plane components;
- paging;
- time-series operations.

### 11.2 Rotation is not disguised as displacement

PR25 does not reinterpret `DISPLACEMENT/Z` as 2D frame rotation `RZ`.

The existing Structural Response vocabulary treats displacement as Cartesian translation. A future rotation query should receive an explicit, unambiguous response quantity rather than overloading a translational component.

## 12. Validation boundary

PR25 validation answers only:

> Is this AnalysisSpec intrinsically valid and deterministic under the V1 contract?

It does not answer:

> Can this analysis actually be performed on the referenced ModelSpec?

Therefore a spec may be PR25 `VALID` even if it refers to:

```text
nodeId = 999999
```

or:

```text
elementId = 999999
```

when those targets do not exist in the actual model.

PR26 Analysis Readiness is responsible for cross-object checks such as:

- bound fingerprint matches the supplied ModelSpec;
- load target node exists;
- result target node/element exists;
- ModelSpec is ready;
- analysis/model dimensional assumptions are compatible;
- unit relationship is compatible;
- renderer prerequisites are satisfied.

This separation is a deliberate architecture invariant and must be covered by tests.

## 13. Canonical normalization

Normalization is deterministic and intentionally conservative.

The normalized spec preserves engineering values but normalizes collection order:

```text
loadCases      sorted by loadCaseId
nodalLoads     sorted by nodeId within each load case
resultRequests sorted by requestId
```

The validator does not:

- convert units;
- sum loads;
- flip signs;
- infer zero components;
- coerce strings to numbers;
- map targets;
- infer missing `location`;
- repair unsupported requests;
- resolve ModelSpec references.

Object key order is irrelevant to identity because the fingerprint serialization sorts keys.

## 14. analysisSpecFingerprint

A valid normalized spec receives a stable SHA-256 fingerprint using the same canonical serialization strategy as `EngineeringModelSpec`:

```python
json.dumps(
    normalized_spec,
    sort_keys=True,
    separators=(",", ":"),
    ensure_ascii=False,
    allow_nan=False,
)
```

The UTF-8 bytes of that canonical JSON are hashed with SHA-256.

The result is returned as:

```text
analysisSpecFingerprint
```

Properties:

- collection-order changes do not change the fingerprint;
- engineering-fact changes do change the fingerprint;
- invalid specs receive no normalized spec and no fingerprint;
- no solver-specific content participates in the fingerprint.

A later run identity may combine:

```text
modelSpecFingerprint
+
analysisSpecFingerprint
```

but PR25 does not define or persist that combined run identity.

## 15. Validation result contract

A valid result has the shape:

```json
{
  "schema": "FEMAGENT_ANALYSIS_SPEC_VALIDATION_V1",
  "status": "VALID",
  "issues": [],
  "normalizedSpec": {},
  "analysisSpecFingerprint": "..."
}
```

An invalid result has the shape:

```json
{
  "schema": "FEMAGENT_ANALYSIS_SPEC_VALIDATION_V1",
  "status": "INVALID",
  "issues": [
    {
      "severity": "ERROR",
      "code": "ANALYSIS_SPEC_...",
      "message": "..."
    }
  ],
  "normalizedSpec": null,
  "analysisSpecFingerprint": null
}
```

V1 may reserve `WARNING` severity for future use, but validation failures required by this contract are errors.

## 16. Issue-code policy

Issue codes must be stable and namespace the AnalysisSpec layer.

The initial controlled set is:

```text
ANALYSIS_SPEC_INVALID_SCHEMA
ANALYSIS_SPEC_UNKNOWN_FIELD
ANALYSIS_SPEC_INVALID_MODEL_FINGERPRINT
ANALYSIS_SPEC_UNSUPPORTED_ANALYSIS_TYPE
ANALYSIS_SPEC_UNSUPPORTED_UNIT
ANALYSIS_SPEC_INVALID_ID
ANALYSIS_SPEC_DUPLICATE_ID
ANALYSIS_SPEC_INVALID_TARGET_ID
ANALYSIS_SPEC_INVALID_NUMBER
ANALYSIS_SPEC_INVALID_LOAD_CASE_COUNT
ANALYSIS_SPEC_DUPLICATE_NODAL_LOAD_TARGET
ANALYSIS_SPEC_ZERO_NODAL_LOAD
ANALYSIS_SPEC_RESULT_LOAD_CASE_NOT_FOUND
ANALYSIS_SPEC_UNSUPPORTED_RESULT_REQUEST
```

The implementation may include path/details metadata for diagnostics, but it should avoid proliferating field-specific error codes when one stable category is sufficient.

## 17. Deterministic core and bridge boundary

The authoritative Python capability is:

```text
analysisSpec.validate
```

Conceptually:

```text
TypeScript / Agent
        |
        v
Python bridge
        |
        v
fem_core.analysis_spec validator
        |
        +-- strict schema checks
        +-- internal referential checks
        +-- canonical normalization
        +-- SHA-256 fingerprint
        |
        v
validation report
```

The capability is SAFE and read-only:

- no file writes;
- no solver invocation;
- no generated model artifacts;
- no permission gate required;
- no engineering auto-repair.

A TypeScript bridge wrapper may be named:

```text
runFemAnalysisSpecValidate
```

A fine-grained Agent tool may temporarily be named:

```text
fem_analysis_spec_validate
```

but its existence is not a permanent architecture commitment because of the tool-surface constraint in Section 2.1.

## 18. Expected implementation boundaries

The likely implementation is intentionally small and composable.

### Python

Likely additions:

```text
fem_core/analysis_spec/__init__.py
fem_core/analysis_spec/validator.py
```

Likely integration change:

```text
fem_core/bridge.py
```

### TypeScript

Likely additions:

```text
packages/fem-tools/src/analysisSpecTypes.ts
```

Likely integration changes:

```text
packages/fem-tools/src/pythonBridge.ts
packages/fem-tools/src/index.ts
```

### Agent extension

If a temporary fine-grained validation tool is retained for PR25 integration testing, it should live in a dedicated AnalysisSpec extension or another narrowly scoped registration file rather than enlarging an unrelated result or solver extension.

No renderer, solver-runner, filesystem artifact writer, or optimizer is added in PR25.

## 19. Testing strategy

PR25 must be test-driven.

### 19.1 Python validator tests

Required cases include:

1. valid V1 linear-static nodal-load spec returns `VALID`;
2. valid result includes normalized spec and 64-character lowercase fingerprint;
3. top-level unknown field returns `INVALID`;
4. nested unknown field returns `INVALID`;
5. unsupported analysis type returns `INVALID`;
6. unsupported force unit returns `INVALID`;
7. malformed model fingerprint returns `INVALID`;
8. uppercase model fingerprint returns `INVALID`;
9. non-finite numbers return `INVALID`;
10. boolean-as-number returns `INVALID`;
11. invalid or nonpositive target IDs return `INVALID`;
12. zero nodal load returns `INVALID`;
13. duplicate node target in one load case returns `INVALID`;
14. zero or multiple load cases return `INVALID`;
15. duplicate request IDs return `INVALID`;
16. missing result load-case reference returns `INVALID`;
17. unsupported quantity/target/component/location combination returns `INVALID`;
18. generalized force without `END_I`/`END_J` returns `INVALID`;
19. node displacement with a `location` field returns `INVALID`;
20. target IDs not present in a real ModelSpec are still intrinsically `VALID` if all AnalysisSpec-local rules pass.

### 19.2 Fingerprint tests

Required identity tests include:

- reordering nodal loads does not change the fingerprint;
- reordering result requests does not change the fingerprint;
- changing `FY` changes the fingerprint;
- changing a target ID changes the fingerprint;
- changing a result request changes the fingerprint;
- changing the bound model fingerprint changes the AnalysisSpec fingerprint.

### 19.3 Bridge tests

Bridge tests must prove:

- `analysisSpec.validate` is routed correctly;
- a structurally invalid AnalysisSpec returns a successful bridge envelope whose engineering report status is `INVALID` rather than turning deterministic validation failure into a transport failure;
- bridge protocol behavior remains unchanged.

### 19.4 TypeScript tests

Tests must prove:

- V1 TypeScript transport types mirror the intended schema;
- `runFemAnalysisSpecValidate` calls the correct bridge command;
- exports are available through the package public surface;
- any temporary Agent validation tool remains read-only and never invokes solver permission or solver execution.

## 20. Acceptance criteria

PR25 is complete only when all of the following are true:

- `EngineeringAnalysisSpec V1` exists as a solver-neutral deterministic contract;
- the Python validator is authoritative;
- V1 supports only `LINEAR_STATIC`;
- V1 supports exactly one explicit load case;
- only explicit nodal `FX/FY/MZ` loads are accepted;
- force units are explicit and restricted to `N` or `kN`;
- duplicate nodal targets are rejected rather than combined;
- result requests use the controlled V1 Structural Response subset;
- cross-ModelSpec existence/readiness checks are not accidentally pulled into PR25;
- normalization is deterministic;
- `analysisSpecFingerprint` is stable and order-insensitive for normalized collections;
- bridge integration is read-only and solver-free;
- tests cover both positive behavior and deliberate non-responsibilities;
- production tests and type checks pass;
- documentation records the long-term Agent tool-surface convergence principle.

## 21. Explicit non-goals for future maintainers

Future changes must not reinterpret PR25 validation as proof that an analysis can execute.

Specifically:

```text
VALID AnalysisSpec
!=
READY analysis
!=
RENDERED solver analysis
!=
SUCCESSFUL solver run
!=
VERIFIED engineering conclusion
```

Those states belong to separate layers.

Likewise, future internal capability growth must not automatically multiply permanent LLM-visible tools. Tool registration is an orchestration choice; deterministic core capabilities are the source of engineering truth.

## 22. Follow-on roadmap

The intended next sequence is:

```text
PR25 EngineeringAnalysisSpec V1
        |
        v
PR26 Analysis Readiness + OpenSees Analysis Renderer
        |
        v
PR27 Controlled Natural-Language Analysis Completion
        |
        v
PR28 Controlled Repair
        |
        v
PR29 ANSYS Analysis Renderer
        |
        v
PR30 dual-solver golden path
        |
        v
PR31+ optimization loop
```

This sequence preserves the same principle used by the ModelSpec path: first define solver-neutral truth, then prove readiness, then render deterministically, then add natural-language completion and more automated workflows.
