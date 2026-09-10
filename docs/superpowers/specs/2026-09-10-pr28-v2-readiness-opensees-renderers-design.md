# PR28 — V2 Analysis Readiness + OpenSees Renderers Design

## 1. Purpose

PR28 makes the three solver-neutral EngineeringAnalysisSpec V2 profiles introduced by PR27 executable through FEMagent's controlled OpenSees pipeline while preserving all proven PR26 V1 behavior.

PR28 supports exactly:

- V2 `LINEAR_STATIC`;
- V2 `MODAL`;
- V2 `TRANSIENT` with `NODAL_TIME_HISTORY`;
- V2 `TRANSIENT` with `UNIFORM_BASE_EXCITATION`.

The execution chain is:

```text
EngineeringModelSpec + EngineeringAnalysisSpec V2
                ↓
         OpenSees Readiness
                ↓
              READY
                ↓
      Deterministic Renderer
                ↓
      Generated-Analysis Bundle
                ↓
        Deterministic Verifier
                ↓
       Isolated OpenSees Worker
                ↓
      Canonical Result Artifacts
```

`VALID` remains distinct from `READY`, `RENDERED`, `VERIFIED`, and `COMPLETED`.

## 2. Architectural principles

PR28 follows the FEMagent constitution:

1. The Agent decides what to do.
2. Deterministic engineering capabilities decide what is true.
3. Solvers decide numerical results.
4. Artifacts preserve what happened.

Additional principles:

- Use one public preparation path and one internal profile registry.
- Profile growth must not create permanent LLM-visible tool growth.
- V2 Static may reuse proven PR26 static compiler primitives, but V2 identity must never be rewritten as V1 identity.
- Readiness owns cross-model, cross-artifact, and concrete solver-profile truth.
- Renderer owns deterministic source generation and bundle publication only.
- Generated-analysis verification is mandatory before solver execution.
- Solver workers produce numerical truth; renderers never fabricate modal frequencies, periods, mode shapes, or transient responses.
- External load artifact SHA-256 is engineering content identity. Artifact path is transport/provenance identity.
- Unsupported or unproven response semantics fail closed.

## 3. Scope

### 3.1 In scope

PR28 adds OpenSees readiness/render/execution for:

1. `OPENSEES_FRAME_2D_LINEAR_STATIC_V2`
2. `OPENSEES_FRAME_2D_MODAL_V2`
3. `OPENSEES_FRAME_2D_TRANSIENT_NODAL_FORCE_V2`
4. `OPENSEES_FRAME_2D_TRANSIENT_UNIFORM_BASE_V2`

The existing `OPENSEES_FRAME_2D_LINEAR_STATIC_V1` profile remains supported unchanged.

PR28 also adds:

- a readiness profile registry;
- a renderer profile registry;
- a shared generated-analysis bundle contract for V2 profiles;
- deterministic generated-analysis verification for V2;
- worker support for modal execution and transient velocity/acceleration sampling;
- canonical modal result artifacts;
- Result Intelligence support required to query PR28 modal and transient outputs;
- TypeScript/bridge contract widening so the existing OpenSees preparation path accepts V1 or supported V2 AnalysisSpec inputs.

### 3.2 Out of scope

PR28 does not add:

- natural-language Analysis Requirement Completion;
- Controlled Repair;
- ANSYS V2 readiness or renderers;
- nonlinear static/transient analysis;
- pushover, response spectrum, buckling, harmonic, random vibration, moving-load, thermal, or multiphysics analysis;
- distributed/gravity loads beyond the PR27 V2 static contract;
- multiple static load cases or combinations;
- modal participation factors, effective modal mass, mass participation ratio, or modal strain energy;
- user-selectable eigensolvers, shifts, linear systems, algorithms, convergence tests, or integration schemes;
- automatic damping-ratio-to-Rayleigh conversion;
- automatic target repair or semantic-role guessing;
- absolute-acceleration reconstruction for base excitation.

## 4. Public capability surface

PR28 keeps the existing high-level Agent tool:

```text
fem_analysis_prepare_opensees
```

Input remains:

```text
mode = CHECK | RENDER
modelSpec
analysisSpec
```

PR28 widens `analysisSpec` from V1-only to:

- V1 `LINEAR_STATIC`;
- V2 `LINEAR_STATIC`;
- V2 `MODAL`;
- V2 `TRANSIENT`.

Behavior:

```text
CHECK  → readiness only, no writes
RENDER → readiness first; writes only when READY
```

No profile-specific Agent tools are introduced.

Execution continues through the existing generic solver path:

```text
fem_solver_preflight
fem_solver_run
```

using verified generated-analysis artifacts and manifest admission.

## 5. OpenSees profile registry

The readiness and renderer layers route by exact AnalysisSpec identity:

```text
schemaVersion=1.0 + LINEAR_STATIC
→ OPENSEES_FRAME_2D_LINEAR_STATIC_V1

schemaVersion=2.0 + LINEAR_STATIC
→ OPENSEES_FRAME_2D_LINEAR_STATIC_V2

schemaVersion=2.0 + MODAL
→ OPENSEES_FRAME_2D_MODAL_V2

schemaVersion=2.0 + TRANSIENT + NODAL_TIME_HISTORY
→ OPENSEES_FRAME_2D_TRANSIENT_NODAL_FORCE_V2

schemaVersion=2.0 + TRANSIENT + UNIFORM_BASE_EXCITATION
→ OPENSEES_FRAME_2D_TRANSIENT_UNIFORM_BASE_V2
```

Unsupported combinations fail closed with a stable readiness issue. Routing must happen only after intrinsic ModelSpec/AnalysisSpec validation succeeds.

## 6. Common readiness contract

Public readiness schema remains versioned and deterministic. PR28 may extend checks while preserving existing V1 fields and semantics.

Every supported V2 readiness profile must verify:

- ModelSpec intrinsic validity;
- AnalysisSpec intrinsic validity;
- exact ModelSpec fingerprint binding;
- Model Readiness;
- required node/element target existence;
- response-request mapping availability;
- reaction restraint semantics where reactions are requested;
- analysis-profile-specific prerequisites;
- no hidden mutation or repair.

Statuses remain:

```text
INVALID_SPEC | NOT_READY | READY
```

`INVALID_SPEC` means intrinsic spec validation failed.

`NOT_READY` means valid specs cannot be proven executable for the selected OpenSees profile.

`READY` means all deterministic pre-execution checks required by that profile passed. It is not a numerical convergence guarantee.

## 7. V2 LINEAR_STATIC readiness

V2 Static reuses the proven PR26 engineering checks through shared deterministic primitives, not V1 identity conversion.

Checks include:

- Model Readiness;
- exact ModelSpec fingerprint binding;
- force-unit compatibility;
- load-node existence;
- result target existence;
- reaction restraint semantics;
- proven OpenSees response mappings.

V2 Static retains its own:

- `analysisSpecFingerprint`;
- readiness profile name;
- normalized AnalysisSpec;
- renderer identity;
- manifest identity.

Semantically equivalent V1 and V2 specs may compile to identical OpenSees commands while remaining distinct engineering identities.

## 8. V2 MODAL readiness

Modal readiness verifies:

- bound ModelSpec is READY;
- ModelSpec contains at least one positive translational nodal mass;
- positive-mass free translational DOFs exist;
- requested `modeCount` does not exceed the deterministic upper bound of positive-mass free translational DOFs;
- every requested MODE_SHAPE target node exists;
- every requested MODE_SHAPE component X/Y/RZ has a proven OpenSees DOF mapping.

Readiness does not attempt to prove matrix nonsingularity, repeated-eigenvalue behavior, eigensolver convergence, or mode-shape normalization. Those are solver outcomes.

Stable modal readiness issue families include:

- `ANALYSIS_READINESS_MODAL_MASS_REQUIRED`
- `ANALYSIS_READINESS_MODAL_FREE_MASS_DOF_REQUIRED`
- `ANALYSIS_READINESS_MODAL_MODE_COUNT_EXCEEDS_DOF_BOUND`
- `ANALYSIS_READINESS_RESULT_NODE_NOT_FOUND`
- `ANALYSIS_READINESS_RESPONSE_MAPPING_UNAVAILABLE`

## 9. V2 TRANSIENT load-artifact readiness

Transient readiness reads the external artifact referenced by `definition.excitation.loadArtifact`.

It must verify:

- path resolves inside the active workspace;
- file exists and is readable;
- actual SHA-256 equals the AnalysisSpec-declared SHA-256;
- file conforms to controlled `FEMAGENT_LOAD_CSV_V1` long-form structure;
- exactly one excitation channel matches the AnalysisSpec excitation;
- time is strictly increasing and uniformly spaced;
- artifact sampling interval matches AnalysisSpec `time.timeStep` after deterministic time-unit conversion;
- artifact end time matches AnalysisSpec `time.duration` after deterministic time-unit conversion;
- target/component/quantity/application semantics match the AnalysisSpec;
- response targets and response mappings are executable by the selected profile.

Transient readiness never silently rewrites the AnalysisSpec SHA or path.

Stable artifact issue families include:

- `ANALYSIS_READINESS_LOAD_ARTIFACT_NOT_FOUND`
- `ANALYSIS_READINESS_LOAD_ARTIFACT_HASH_MISMATCH`
- `ANALYSIS_READINESS_LOAD_ARTIFACT_INVALID`
- `ANALYSIS_READINESS_LOAD_CHANNEL_MISMATCH`
- `ANALYSIS_READINESS_TIME_STEP_MISMATCH`
- `ANALYSIS_READINESS_DURATION_MISMATCH`

## 10. NODAL_TIME_HISTORY readiness

For `NODAL_TIME_HISTORY`, readiness requires the canonical load channel to represent:

```text
application_type = NODAL_FORCE
quantity         = FORCE
target_type      = NODE
target_id        = AnalysisSpec nodeId
component        = X | Y matching AnalysisSpec
```

The target node must exist.

Artifact force values are standardized in N. They are deterministically converted to the bound ModelSpec force unit for rendered execution. The conversion factor is recorded in readiness and the manifest.

## 11. UNIFORM_BASE_EXCITATION readiness

For `UNIFORM_BASE_EXCITATION`, readiness requires:

```text
application_type = UNIFORM_EXCITATION
quantity         = ACCELERATION
component        = X | Y matching AnalysisSpec
```

The canonical artifact acceleration unit is `m/s2`.

Acceleration is deterministically converted to the bound ModelSpec unit system `length/time^2` for rendered execution. The conversion factor is recorded.

PR28 admits:

- `RELATIVE_ACCELERATION` requests;
- shared displacement/velocity/reaction/generalized-force requests.

PR28 does not admit `ABSOLUTE_ACCELERATION` because a proven canonical reconstruction path is not yet defined. A valid AnalysisSpec containing an absolute-acceleration request returns `NOT_READY` with:

```text
ANALYSIS_READINESS_ABSOLUTE_ACCELERATION_MAPPING_UNPROVEN
```

No renderer may bypass this readiness outcome.

## 12. Deterministic unit conversions

PR28 allows deterministic execution-time conversion where the engineering meaning is fully known.

Conversions are performed by `fem_core`, not the LLM.

Required conversions include:

- canonical force N → ModelSpec force unit N/kN;
- canonical time s → ModelSpec time unit s/ms;
- canonical acceleration m/s² → ModelSpec `length/time²`.

Every conversion record includes at least:

```text
quantity
sourceUnit
targetUnit
factor
```

These records participate in readiness evidence and generated-analysis manifest identity.

No unsupported unit is inferred or guessed.

## 13. Renderer registry and shared bundle publisher

Each internal profile implements only profile-specific deterministic compilation:

```text
evaluate_profile_readiness(...)
build_analysis_source(...)
build_response_contract(...)
```

The shared renderer owns:

- profile selection;
- artifact root resolution;
- canonical JSON serialization;
- SHA-256 calculation;
- manifest construction;
- render fingerprint construction;
- atomic/fail-closed publication;
- cleanup on publication failure.

The standard generated-analysis bundle remains:

```text
.femagent/generated-analyses/<analysisRenderId>/
├── analysis.py
├── response_plan.json
├── analysis_readiness.json
└── analysis_manifest.json
```

For Modal, `response_plan.json` carries a modal response contract rather than a structural time-series contract.

## 14. Renderer identities

Renderer names are:

```text
OPENSEES_FRAME_2D_LINEAR_STATIC_V1
OPENSEES_FRAME_2D_LINEAR_STATIC_V2
OPENSEES_FRAME_2D_MODAL_V2
OPENSEES_FRAME_2D_TRANSIENT_NODAL_FORCE_V2
OPENSEES_FRAME_2D_TRANSIENT_UNIFORM_BASE_V2
```

V1 renderer version remains unchanged.

V2 renderer version starts at `2.0`.

The manifest records both renderer name and renderer version.

## 15. V2 Static renderer

V1 and V2 static compilation share lower-level primitives for:

- deterministic nodal load emission;
- fixed static analysis configuration;
- structural response mapping.

The V2 Static renderer reads `definition.loadCases` directly from the normalized V2 spec.

It does not call V1 migration and does not replace the V2 fingerprint with a V1 fingerprint.

Fixed OpenSees analysis configuration remains the proven linear-static profile:

```text
constraints = Plain
numberer    = Plain
system      = BandGeneral
algorithm   = Linear
integrator  = LoadControl(1.0)
analysis    = Static
```

## 16. MODAL renderer

The modal renderer deterministically emits the validated ModelSpec followed by a fixed modal execution configuration.

The generated source requests exactly `definition.modeCount` eigenvalues from OpenSees.

PR28 does not expose eigensolver selection, spectral shift, or normalization controls.

Numerical modal results are not computed by the renderer.

The modal response contract carries the requested:

- `EIGENVALUE`;
- `NATURAL_FREQUENCY`;
- `PERIOD`;
- `MODE_SHAPE`.

The worker executes real OpenSees eigenanalysis and extracts requested mode-shape components using `ops.nodeEigenvector(...)`.

## 17. TRANSIENT renderer

Both transient profiles share a deterministic linear direct-integration backbone:

```text
constraints = Plain
numberer    = Plain
system      = BandGeneral
algorithm   = Linear
integrator  = Newmark(0.5, 0.25)
analysis    = Transient
```

The renderer emits one `ops.analyze(1, dt)` step per required time increment.

Damping behavior:

```text
NONE
→ no ops.rayleigh call

RAYLEIGH(alphaM, betaK)
→ ops.rayleigh(alphaM, betaK, 0.0, 0.0)
```

For PR28, `betaK` is explicitly defined as the OpenSees current-stiffness Rayleigh coefficient. PR28 does not reinterpret it as initial- or committed-stiffness damping.

### 17.1 Nodal force renderer

The renderer uses a deterministic Path timeSeries plus Plain pattern and applies the force history to the requested node/component.

Canonical force values are converted to the ModelSpec force unit before OpenSees consumption.

### 17.2 Uniform base renderer

The renderer uses a deterministic Path timeSeries plus UniformExcitation pattern in the requested translational DOF.

Canonical acceleration values are converted to ModelSpec `length/time²` before OpenSees consumption.

Rotational ground excitation remains unsupported.

## 18. Response mappings

Static mappings retain the proven PR26 mappings.

Transient adds:

- `NODE_VEL` for NODE `VELOCITY` X/Y;
- `NODE_ACCEL` for NODE `ACCELERATION` X/Y under nodal-force excitation;
- `NODE_ACCEL` for NODE `RELATIVE_ACCELERATION` X/Y under uniform-base excitation.

Existing mappings remain:

- `NODE_DISP`;
- `NODE_REACTION`;
- `ELEMENT_LOCAL_FORCE`.

Every mapping records reference frame and unit.

For transient result series, abscissa semantic is `TIME` and abscissa unit is the bound ModelSpec time unit.

## 19. Worker execution modes

Existing worker modes remain:

- `build-inspect`;
- `script-run`.

PR28 adds:

- `modal-run`.

`script-run` owns Static and Transient generated Python execution and response sampling around successful `ops.analyze(...)` calls.

`modal-run` owns real `ops.eigen(...)` execution and modal result extraction. Modal is not forced through analyze-call instrumentation.

The worker remains isolated and fail closed.

## 20. Canonical structural response artifact

Static and Transient use:

```text
schemaVersion = 1.0
kind          = structural_response_series
```

Each channel preserves:

- channel/request identity;
- quantity;
- target;
- component;
- optional location;
- unit;
- referenceFrame;
- time abscissa for transient;
- numerical values.

Static may continue to produce one sampled solver-state value where appropriate; Transient produces a time series.

## 21. Canonical modal result artifact

PR28 introduces:

```text
schemaVersion = 1.0
kind          = modal_result_set
```

The artifact contains the solver-returned eigenvalue for each solved mode and deterministic derived presentations:

- `eigenvalue`;
- `naturalFrequencyHz`;
- `period` in ModelSpec time units.

Requested mode-shape values are stored by request identity and include:

- mode index;
- NODE target;
- component X/Y/RZ;
- scalar eigenvector value;
- explicit semantic marker `NORMALIZATION_DEPENDENT_MODE_SHAPE`;
- unit `null`.

Mode-shape values must never be represented as physical displacement.

Frequency and period are derived from actual solver eigenvalues in the worker/result canonicalization path, never the renderer.

## 22. Generated-analysis manifest V2

V2 generated-analysis manifests record at least:

- schema/status;
- renderer name/version;
- readiness profile;
- normalized ModelSpec;
- normalized AnalysisSpec;
- ModelSpec fingerprint;
- AnalysisSpec fingerprint;
- analysis type;
- response mappings/response contract;
- deterministic conversion records;
- external load artifact path + SHA when applicable;
- analysis source path + SHA;
- response plan path + SHA;
- readiness path + SHA;
- manifest path;
- analysis render fingerprint.

The V2 render fingerprint includes concrete execution identity, including external artifact path and SHA when applicable.

Therefore:

- AnalysisSpec fingerprint may remain identical when identical load bytes move paths;
- rendered execution identity changes when the locator path changes, because the concrete executable bundle provenance changed.

## 23. Generated-analysis verification

Before solver execution, verifier must recompute and prove:

- embedded ModelSpec still validates and fingerprints identically;
- embedded AnalysisSpec still validates and fingerprints identically;
- readiness recomputation returns READY for the same profile;
- response mappings/contract match recomputation;
- generated analysis source exactly matches deterministic regeneration;
- response plan exactly matches deterministic regeneration;
- readiness artifact exactly matches deterministic regeneration;
- all declared artifact hashes match bytes;
- external load artifact path still resolves inside workspace;
- external load artifact SHA still matches AnalysisSpec and manifest;
- render fingerprint recomputes identically.

Any mismatch blocks execution.

The verifier outputs a trusted execution/response context consumed by the worker. The worker does not trust arbitrary user-provided mapping metadata.

## 24. Solver admission

The existing generic OpenSees solver preflight/run path remains authoritative.

Generated-analysis execution is admitted through existing solver options such as:

```text
analysisManifestPath
responsePlanPath
```

PR28 may extend the verified context shape or worker mode metadata, but it does not add a second solver execution API.

Direct arbitrary script execution remains outside the controlled AnalysisSpec golden path.

## 25. Result Intelligence

PR28 extends Result Intelligence only as required for new canonical artifacts.

Static/Transient continue through structural-response querying.

Transient supported query quantities include the PR28 executable subset:

- `DISPLACEMENT`;
- `VELOCITY`;
- `ACCELERATION` for nodal-force excitation;
- `RELATIVE_ACCELERATION` for uniform-base excitation;
- `REACTION_FORCE`;
- `REACTION_MOMENT`;
- `GENERALIZED_FORCE`.

Modal query support includes:

- `EIGENVALUE`;
- `NATURAL_FREQUENCY`;
- `PERIOD`;
- `MODE_SHAPE`.

No unsupported modal metric is synthesized.

## 26. Error-handling principles

- Invalid intrinsic specs return `INVALID_SPEC` through readiness.
- Valid but unsupported/unproven execution semantics return `NOT_READY`.
- Renderer never writes artifacts unless readiness is `READY`.
- Publication failure removes partial bundle output.
- Generated-analysis verification failures block solver execution.
- Solver numerical failures are recorded as solver failures, not rewritten as readiness errors.
- Result Intelligence rejects malformed/tampered canonical result artifacts.

## 27. TypeScript and bridge contract

PR28 widens the existing TypeScript preparation input from `FemEngineeringAnalysisSpecV1Input` to the PR27 union `FemEngineeringAnalysisSpecInput`.

Readiness and render result types must represent the V1 and V2 profile names without collapsing them into untyped strings where a discriminated union is practical.

No new migration or profile-specific Agent tool is registered.

The generic solver tool contract remains the execution surface.

## 28. Testing strategy

### 28.1 V1 regression

Prove the full PR26 V1 static golden path remains green, including:

- readiness;
- renderer;
- generated-analysis verification;
- isolated solver execution;
- structural response;
- Result Intelligence.

### 28.2 V2 Static

Test:

- READY model/spec pair;
- model fingerprint mismatch;
- force-unit mismatch;
- missing load/result targets;
- unrestrained reaction request;
- deterministic rendering;
- V2 identity preserved through manifest and verifier;
- real OpenSees solve produces controlled response.

### 28.3 V2 Modal

Test:

- positive mass required;
- free positive-mass translational DOF required;
- modeCount bound;
- mode-shape target existence;
- deterministic renderer;
- verified bundle;
- real OpenSees eigenanalysis;
- finite positive eigenvalues for a stable golden model;
- frequency/period consistency with eigenvalue;
- requested mode-shape extraction;
- mode-shape semantic/unit contract.

### 28.4 V2 Transient common

Test:

- missing artifact;
- artifact path escape;
- SHA mismatch;
- malformed canonical load;
- multi-channel mismatch;
- nonuniform time step;
- timeStep mismatch;
- duration mismatch;
- deterministic conversion records;
- bundle tamper detection;
- load artifact tamper detection.

### 28.5 V2 Transient nodal force

Test:

- correct NODAL_FORCE target/component/quantity mapping;
- incorrect node/component rejected;
- real OpenSees execution;
- displacement/velocity/acceleration/reaction/generalized-force sampling as requested;
- finite values and correct time axis.

### 28.6 V2 Transient uniform base

Test:

- correct UNIFORM_EXCITATION acceleration mapping;
- relative acceleration READY;
- absolute acceleration NOT_READY with stable issue code;
- real OpenSees execution;
- finite response time series;
- correct reference-frame semantics.

### 28.7 Tool surface and boundary

Prove:

- one `fem_analysis_prepare_opensees` tool accepts V1 + V2 profiles;
- no profile-specific preparation tools are added;
- generic solver tools remain the execution path;
- no ANSYS V2 changes;
- no natural-language Analysis Completion;
- no Controlled Repair;
- invalid/NOT_READY requests produce zero generated-analysis writes.

## 29. Golden cases

PR28 must include four real OpenSees golden cases:

1. V2 linear static;
2. V2 modal;
3. V2 transient nodal force;
4. V2 transient uniform base excitation.

Golden models and load histories must be intentionally small so CI remains practical while still exercising the real solver.

## 30. Completion criteria

PR28 is complete only when:

1. V1 static PR26 golden path remains fully green.
2. V2 Static reaches READY → RENDERED → VERIFIED → COMPLETED.
3. V2 Modal reaches READY → RENDERED → VERIFIED → COMPLETED.
4. V2 Transient Nodal Force reaches READY → RENDERED → VERIFIED → COMPLETED.
5. V2 Transient Uniform Base reaches READY → RENDERED → VERIFIED → COMPLETED.
6. All four V2 execution profiles preserve original V2 ModelSpec/AnalysisSpec fingerprints through manifest and run provenance.
7. Transient external artifact SHA and path provenance are verified before execution.
8. Deterministic unit conversion records are preserved.
9. Relative base acceleration is queryable with proven semantics.
10. Absolute base acceleration fails closed as NOT_READY.
11. Modal numerical values originate from real OpenSees eigenanalysis.
12. Mode shapes are labeled normalization-dependent and are not assigned displacement units.
13. Generated bundle tampering fails verification.
14. External load artifact tampering fails verification.
15. The existing Agent tool surface does not grow by analysis profile.
16. ANSYS V2, NL Analysis Completion, Controlled Repair, nonlinear analysis, and optimization remain out of scope.
17. Standard verification is green:
    - `pnpm typecheck`
    - `pnpm test:ts`
    - `python -m pytest`
    - `python -m ruff check fem_core tests/python examples/ansys/golden_path`
    - OpenSees availability smoke
    - ANSYS result-reader smoke
    - `pnpm fem:health`

## 31. Branching and integration

PR28 is developed as a stacked branch from PR27 HEAD because PR27 is not yet merged at design time.

Branch:

```text
feat/pr28-v2-readiness-opensees-renderers
```

Initial base commit:

```text
c25422b6467257d7b270aae6f19b4f476afa0174
```

Implementation must not rewrite PR27 history. When PR27 lands in `main`, PR28 can be retargeted/rebased in a controlled step before integration.

## 32. Final architecture after PR28

```text
                 EngineeringAnalysisSpec
                         │
        ┌────────────────┼────────────────┐
        │                │                │
        v                v                v
 LINEAR_STATIC         MODAL          TRANSIENT
   V1 / V2              V2                V2
        │                │          ┌──────┴──────┐
        │                │          │             │
        │                │       NODAL         UNIFORM
        │                │       FORCE           BASE
        └────────────────┴──────────┴─────────────┘
                         │
                         v
             OpenSees Profile Readiness
                         │
                         v
                 deterministic READY
                         │
                         v
                Renderer Registry
                         │
                         v
             Generated-Analysis Bundle
                         │
                         v
              Deterministic Verifier
                         │
                         v
               Isolated OpenSees Worker
                         │
              ┌──────────┴──────────┐
              v                     v
 structural_response_series   modal_result_set
              │                     │
              └──────────┬──────────┘
                         v
                Result Intelligence
```

PR28 succeeds when FEMagent can execute V2 Static, Modal, and both V2 Transient excitation families through one controlled OpenSees preparation/execution architecture, while preserving all prior V1 guarantees and refusing unproven engineering semantics.