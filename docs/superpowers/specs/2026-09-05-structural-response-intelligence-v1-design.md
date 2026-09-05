# PR15 — Structural Response Intelligence V1 Design

Date: 2026-09-05
Status: Proposed design approved in chat; written-spec review required before implementation
Base: `main` after PR14 Cross-Solver Validation V1
Branch: `feat/pr15-structural-response-intelligence-v1`

## 1. Goal

PR15 expands FEMagent from primarily node-response post-processing into a deterministic structural-response layer that can represent, query, verify, and project common engineering responses at nodes and elements without allowing the LLM to invent result semantics.

The V1 priority is bridge/structural engineering response intelligence rather than generic coverage of every solver result type.

Primary engineering questions to enable include:

- What is the maximum reaction moment at a declared support/tower-base node?
- What is the peak beam/column axial force, shear force, bending moment, or torque for a declared element?
- What is the peak stress or equivalent stress at a declared node/element when the solver artifact proves that result channel?
- What is the maximum force, deformation/stroke, velocity, and—only when derivable from complete recorded channels—dissipated energy of a declared damper element?
- Can those responses be projected through Engineering Evidence and, when comparable, through Cross-Solver Validation?

PR15 is not an optimization feature and does not choose design parameters.

## 2. Existing system boundary

Current FEMagent already has:

- Model Intelligence and Model Bundle identity;
- Load Intelligence and canonical load application;
- OpenSees and ANSYS solver adapters;
- Result Intelligence with artifact-integrity checks;
- Engineering Evidence;
- explicit Semantic Roles V1 bound to model bundle fingerprints;
- Cross-Solver Validation V1 using role-backed VERIFIED evidence.

Current Result Intelligence is strongest for node responses:

- DISPLACEMENT;
- VELOCITY;
- ACCELERATION;
- REACTION_FORCE.

ANSYS MAPDL binary results retain richer post-processing data than the current reader exposes. OpenSees, by contrast, does not guarantee that arbitrary historical element responses remain queryable after a script has completed. Therefore PR15 must not pretend the two solvers have identical post-run retrieval semantics.

## 3. Design principles

### 3.1 Evidence before semantics

A structural response is available only when FEMagent can point to a verified artifact or a verified deterministic solver-native extraction from a recorded artifact.

The LLM must never manufacture:

- a unit;
- a local-axis meaning;
- an element-end meaning;
- a force-vector component mapping;
- a stress location;
- a damper response channel.

### 3.2 Result availability is solver-specific; the response contract is canonical

The canonical response model is shared. Acquisition is solver-specific.

ANSYS may extract many responses from the recorded binary result after the run.

OpenSees must record responses during the run whenever OpenSees cannot prove that the response is safely recoverable after analysis.

### 3.3 Unknown units remain unknown

PR15 preserves the established ANSYS unit rule: if the recorded artifact and FEMagent provenance do not prove the physical unit system, result `unit` remains `null`.

No implicit MPa, N, kN, mm, m, N·m, or other physical unit may be assigned from convention, model appearance, or solver defaults.

### 3.4 Canonical names only when semantics are proven

Canonical components such as `N`, `VY`, `VZ`, `T`, `MY`, `MZ`, `SEQV`, or `END_I` may be emitted only when the solver response definition and element formulation prove the mapping.

If the native vector meaning cannot be proven, the response remains solver-native or is reported unavailable. PR15 must not cosmetically rename an unknown vector into engineering forces.

### 3.5 Read-only post-processing stays read-only

Result inspection/query, Evidence projection, Semantic resolution, and Cross-Solver Validation remain read-only.

OpenSees response recording is part of an explicitly requested solver run, not a hidden post-processing execution.

## 4. Architectural approach

PR15 uses a **Recorded Structural Response Contract with solver-specific extractors**.

```text
Recorded solver run
      |
      +-- ANSYS binaryResult (.rst/...)
      |       |
      |       +-- deterministic structural extractor
      |
      +-- OpenSees recorded structural response artifact
              |
              +-- controlled structural artifact reader
                      |
                      v
          Canonical Structural Response
                      |
             Result Intelligence
                      |
              Engineering Evidence
                      |
               Semantic Roles
                      |
            Cross-Solver Validation
```

The canonical layer is intentionally independent from solver parser details.

## 5. Canonical structural response model

A structural response channel has the following logical identity:

```json
{
  "quantity": "GENERALIZED_FORCE",
  "target": {"type": "ELEMENT", "id": 320},
  "component": "MY",
  "location": "END_I",
  "unit": null,
  "referenceFrame": "ELEMENT_LOCAL",
  "sourceSemantics": "PROVEN"
}
```

A query extends the current Result Intelligence request rather than replacing it:

```json
{
  "quantity": "GENERALIZED_FORCE",
  "target": {"type": "ELEMENT", "id": 320},
  "component": "MY",
  "location": "END_I",
  "operation": "SUMMARY"
}
```

For SERIES-compatible recorded channels, `operation: "SERIES"` may return the controlled series under the existing sample-limit rules.

For SUMMARY, the normalized metric remains:

```json
{
  "sampleCount": 1001,
  "min": -1.2,
  "max": 1.5,
  "absolutePeak": 1.5,
  "abscissaAtAbsolutePeak": 6.42
}
```

The canonical response must preserve:

- `quantity`;
- `target`;
- `component`;
- optional `location`;
- `unit` (nullable);
- `referenceFrame`;
- `abscissaSemantic`;
- `abscissaUnit` (nullable);
- exact source artifact/provenance;
- solver-native metadata needed for audit.

## 6. V1 controlled response vocabulary

PR15 V1 supports a deliberately bounded vocabulary.

### 6.1 Existing node responses retained

- `DISPLACEMENT` — X/Y/Z where available;
- `VELOCITY` — X/Y/Z where available;
- `ACCELERATION` — X/Y/Z where available;
- `REACTION_FORCE` — X/Y/Z where available.

### 6.2 New node response

- `REACTION_MOMENT` — X/Y/Z only when the recorded solver response exposes rotational reaction components with provable component identity.

### 6.3 Stress responses

`STRESS` components, only where the source proves the stress convention:

- `SX`;
- `SY`;
- `SZ`;
- `SXY`;
- `SYZ`;
- `SXZ`.

`PRINCIPAL_STRESS` components:

- `S1`;
- `S2`;
- `S3`;
- `SINT`;
- `SEQV`.

Stress location/averaging semantics must be explicit. V1 must not merge nodal-averaged and element/integration-point stress under an indistinguishable identity.

### 6.4 Element generalized force

`GENERALIZED_FORCE` controlled components:

- `N`;
- `VY`;
- `VZ`;
- `T`;
- `MY`;
- `MZ`.

Controlled locations:

- `END_I`;
- `END_J`;
- `SECTION` only when a solver-native section/index identity is retained and documented.

V1 canonical mappings are allowed only for element formulations whose response vector semantics are explicitly supported by the extractor. Unsupported formulations fail closed with a stable unavailability reason.

### 6.5 Damper response

`DAMPER_RESPONSE` controlled components:

- `FORCE`;
- `DEFORMATION`;
- `VELOCITY`;
- `DISSIPATED_ENERGY`.

The canonical damper axis is the explicitly recorded element/device axis, not an inferred global axis.

`DISSIPATED_ENERGY` is available only when either:

1. the solver exposes a documented dissipated-energy response channel directly; or
2. FEMagent has complete, direction-consistent, verified force and deformation/velocity histories and applies a deterministic documented integration method.

If those conditions are not met, energy is unavailable. FEMagent must not approximate it from peak force × peak stroke.

## 7. ANSYS acquisition

### 7.1 Source of truth

ANSYS structural-response queries use the recorded MAPDL binary result artifact already integrity-checked by Result Intelligence.

PR15 extends the ANSYS reader behind a solver-specific structural extractor rather than building a second independent `.rst` parser.

### 7.2 Node reaction moment

Reaction moment support is added only if the binary result exposes rotational reaction DOF entries and their labels can be mapped deterministically to X/Y/Z rotational components.

If rotational reaction labels are absent or ambiguous, the capability is not advertised.

### 7.3 Stress

ANSYS extraction may expose supported nodal and/or element stress channels from the binary result where the installed reader provides deterministic data and entity identity.

The canonical result must identify whether stress is:

- nodal/averaged;
- element-based;
- element-nodal;
- integration-point/native location.

No silent averaging or location collapse is allowed.

### 7.4 Generalized element forces

ANSYS element-force canonicalization is the highest-risk V1 area because MAPDL element result layouts depend on element formulation/type.

Therefore PR15 does **not** create a universal `element_solution_data` → `N/V/M/T` mapping.

Instead:

- supported element formulations get explicit mapping tables/tests;
- unsupported element types remain solver-native/unavailable;
- component labels and end/section locations are emitted only from proven mappings;
- no guessing from array position is permitted without a documented formulation contract.

The first supported formulations should be those already present in FEMagent bridge examples/golden paths and bridge/beam use cases, subject to what the available test fixtures can prove.

### 7.5 ANSYS units

Unless the run manifest contains independently proven model/result unit metadata that is within an approved FEMagent unit contract, ANSYS structural-response units remain `null`.

PR15 does not introduce a model-unit inference engine.

## 8. OpenSees acquisition

### 8.1 Why recording is required

OpenSees Python scripts may construct arbitrary models and may discard or mutate state. Post-run `result_summary.json` currently records topology metadata but not arbitrary element response histories.

PR15 therefore introduces an explicit **Structural Response Plan** for controlled response recording.

### 8.2 Response Plan

A response plan is deterministic input to a solver run, conceptually:

```json
{
  "schemaVersion": "1.0",
  "kind": "structural_response_plan",
  "channels": [
    {
      "channelId": "girder_midspan_my_i",
      "quantity": "GENERALIZED_FORCE",
      "target": {"type": "ELEMENT", "id": 41},
      "component": "MY",
      "location": "END_I"
    }
  ]
}
```

The plan does not allow free-form OpenSees command strings. It selects from a controlled FEMagent response vocabulary.

The response plan is fingerprinted/recorded as run provenance.

### 8.3 Recorded artifact

OpenSees produces a controlled structural-response artifact under the run directory. The V1 storage form may be CSV plus a JSON channel manifest or one normalized JSON/CSV pair; the implementation plan may choose the simplest format that preserves deterministic channel identity and efficient series reading.

The artifact must be SHA256-declared in `run_manifest.json`, and Result Intelligence must verify it before querying.

### 8.4 Supported OpenSees element responses

V1 supports only element formulations for which FEMagent can prove response-vector semantics.

Beam/column generalized force support should begin with a narrow known formulation set. Damper support should begin with the actual damper element/material pattern used by FEMagent examples/tests, if available.

Arbitrary user-defined element responses are not canonicalized automatically.

### 8.5 Existing Python model execution safety

The response plan must not weaken PR6 static safety/model-bundle checks.

No dynamic code injection from LLM-authored recorder strings is permitted.

## 9. Semantic Roles V1 extension

PR13 currently supports NODE roles. PR15 extends explicit Semantic Role entities to support `ELEMENT` while retaining the same trust model.

Example:

```json
{
  "roleId": "DAMPER_LEFT",
  "roleType": "DAMPER_ATTACHMENT",
  "entity": {
    "type": "ELEMENT",
    "id": 875
  }
}
```

The role resolver must:

- accept NODE and ELEMENT only;
- preserve bundle-fingerprint binding;
- statically confirm element existence when the current model inspection exposes a complete element tag set;
- otherwise return `RESOLVED + NOT_STATICALLY_ENUMERABLE` rather than inventing confirmation;
- return `SEMANTIC_ROLE_ENTITY_NOT_FOUND` when a complete statically enumerable topology proves the declared element is absent.

PR15 does not add automatic geometric/name-based role inference.

## 10. Engineering Evidence integration

PR12 Engineering Evidence must remain the provenance authority for projected structural-response claims.

A structural Evidence claim must preserve at least:

- run ID;
- case fingerprint;
- solver;
- model bundle fingerprint where recorded;
- semantic role provenance when used;
- target entity;
- quantity/component/location;
- unit/reference frame;
- source artifact hash;
- normalized summary metric.

The deterministic core should continue to use restrained generic claim text. Rich engineering interpretation remains an agent responsibility and may only reference verified structured fields.

## 11. Cross-Solver Validation integration

PR14 remains unchanged in principle: it compares two independently VERIFIED Evidence objects only when the query identity is compatible.

PR15 extends the query identity considered by Cross-Solver Validation to include structural-response fields such as:

- target semantic role;
- quantity;
- component;
- location;
- unit;
- reference frame;
- stress location/averaging semantics where applicable.

A mismatch returns `NOT_COMPARABLE`; it must not be normalized away.

Examples that must not be declared comparable without an explicit future transformation layer:

- nodal-averaged stress vs integration-point stress;
- END_I moment vs END_J moment;
- global-axis force vs element-local force;
- known N·m vs unknown unit;
- solver-native force vector with unproven component semantics vs canonical `MY`.

PR15 does not add tolerances, PASS/FAIL, solver ranking, or unit conversion.

## 12. Result Intelligence API evolution

The existing `result.inspect` and `result.query` remain the public concepts.

`result.inspect` gains structural `queryCapabilities` only when a deterministic extractor/recorded channel proves them.

`result.query` accepts NODE or ELEMENT targets and optional structural fields such as `location`.

Existing node-response queries remain backwards-compatible.

A query for an unsupported structural response returns a stable domain error such as `RESULT_SERIES_UNAVAILABLE` or a more specific PR15 structural unavailability code defined in implementation, rather than an empty successful result.

## 13. Bridge and Pi tools

PR15 should avoid proliferating solver-specific public tools.

Preferred public surface:

- existing `result.inspect`;
- existing `result.query` with expanded controlled request schema;
- existing `evidence.project` / role-backed evidence flow extended for ELEMENT targets;
- semantic inspect/resolve extended for ELEMENT;
- an explicit response-plan input on supported solver-run/preflight paths when OpenSees structural recording is requested.

TypeScript types must represent the expanded union without `any`-based escape hatches.

Pi tool descriptions must make the following explicit:

- never invent element IDs;
- never invent role mappings;
- never infer physical units;
- never map solver-native element vectors to `N/V/M/T` unless the tool reports canonical semantics;
- never treat unavailable structural channels as zero;
- never run a solver merely to answer a read-only result question without normal solver-run confirmation/permission boundaries.

## 14. Fail-closed behavior

Hard integrity/identity failures remain hard failures, including:

- result artifact hash mismatch;
- semantic manifest/model fingerprint mismatch;
- role/run model mismatch;
- declared static entity absent from completely enumerable topology;
- invalid response-plan schema;
- recorded structural artifact hash mismatch;
- invalid/non-finite structural series;
- source vector semantics inconsistent with the supported mapping contract.

Absence of a structural channel is not converted into a numerical zero.

## 15. Scope

### In PR15 V1

- canonical structural-response vocabulary/schema;
- NODE + ELEMENT result targets;
- ANSYS reaction-moment support where provable;
- ANSYS stress/principal/equivalent-stress extraction where deterministic;
- narrow, explicitly supported ANSYS generalized-force mappings where fixtures/formulations prove them;
- explicit OpenSees Structural Response Plan;
- controlled hashed OpenSees structural response artifacts;
- narrow supported OpenSees beam/damper response mappings;
- ELEMENT Semantic Roles;
- Engineering Evidence integration;
- Cross-Solver Validation compatibility-field extension;
- Python/TypeScript/Pi contracts;
- TDD, architecture docs, verification docs, exact-head CI.

### Explicitly out of PR15 V1

- optimization/search;
- automatic semantic-role inference;
- arbitrary element-type force-vector guessing;
- arbitrary user-supplied OpenSees recorder command strings;
- shell/solid stress tensor homogenization across incompatible formulations;
- stress extrapolation/averaging transformations not already deterministically supplied by the reader;
- unit inference or unit conversion;
- local/global coordinate transformation engine;
- code-check/design-code utilization ratios;
- fatigue/rainflow counting;
- response spectrum/envelope combination logic;
- contour UI/visual post-processing;
- PDF report generation;
- hidden engineering tolerances or automatic PASS/FAIL judgments.

## 16. TDD strategy

Implementation must proceed RED → GREEN in small slices.

Minimum required behavioral coverage:

1. Canonical structural query validation and summary normalization.
2. Existing node queries remain unchanged.
3. ANSYS reaction moment is advertised only when rotational reaction semantics exist.
4. ANSYS stress query preserves entity/location/averaging semantics and unknown units.
5. Unsupported ANSYS element formulation cannot be mislabeled as canonical generalized force.
6. Valid ELEMENT semantic role resolves and retains bundle provenance.
7. Missing ELEMENT in completely enumerable topology fails `SEMANTIC_ROLE_ENTITY_NOT_FOUND`.
8. Dynamic/non-enumerable topology gives `RESOLVED + NOT_STATICALLY_ENUMERABLE` for explicit ELEMENT roles.
9. OpenSees response plan rejects free-form/native recorder injection.
10. Recorded OpenSees structural artifact is hashed and integrity-checked.
11. Supported beam/damper channels can be queried through production Result Intelligence.
12. Damper energy is unavailable unless the required verified channels/direct solver response exist.
13. Structural response projects into VERIFIED Engineering Evidence with target/component/location provenance.
14. Cross-Solver Validation refuses location/reference/unit/semantic mismatches.
15. Artifact tampering continues to fail closed.
16. TypeScript Bridge and Pi tool schemas round-trip the expanded query model.
17. Full existing suite remains green.

Every production capability must have at least one negative test proving the fail-closed boundary.

## 17. Verification boundary

Hosted CI may use deterministic fixtures and OpenSees runtime execution available in CI.

For ANSYS binary structural responses, CI may use existing/synthetic readable `.rst` fixtures only where those fixtures genuinely contain the response channel. The verification document must distinguish:

- parser/contract verification against fixtures;
- OpenSees real runtime verification;
- any licensed real ANSYS solver execution, if not performed.

PR15 must not claim a real licensed ANSYS beam/damper structural-response run unless one was actually executed and its exact artifacts were verified.

## 18. Completion criteria

PR15 is complete only when:

- the approved controlled response vocabulary is implemented without semantic guessing;
- existing Result Intelligence behavior remains backwards-compatible;
- ELEMENT roles work under the same PR13 trust model;
- at least one real supported OpenSees structural element response path is recorded and queried end-to-end in CI;
- ANSYS structural extraction capabilities are honestly limited to what test artifacts and reader APIs prove;
- structural responses project into Engineering Evidence;
- PR14 compatibility logic accounts for structural-response identity;
- TypeScript/Pi contracts are type-safe and read/write permissions remain correct;
- architecture and verification documents describe exact support and limitations;
- final exact-head CI is fully green;
- PR remains unmerged until explicit user instruction.
