# PR26 — Analysis Readiness + OpenSees Analysis Renderer Design

## 1. Purpose

PR26 connects the solver-neutral `EngineeringModelSpec` and `EngineeringAnalysisSpec` contracts to a deterministic, auditable OpenSees linear-static analysis bundle.

The central distinction remains:

- `EngineeringModelSpec` = what the model is.
- `EngineeringAnalysisSpec` = what analysis should be performed on that model.
- `Analysis Readiness` = whether the two specifications form a valid executable engineering combination for the PR26 OpenSees profile.
- `OpenSees Analysis Renderer` = deterministic compilation of a READY pair into solver-specific artifacts.
- `SolverAdapter` / OpenSees = execution and numerical truth.
- Result Intelligence / Evidence = recorded result interpretation and provenance.

PR26 must not collapse VALID, READY, RENDERED, SOLVER_READY, COMPLETED, or VERIFIED into one status.

## 2. Architectural principles

PR26 follows the FEMagent constitution:

1. The Agent decides what to do.
2. Deterministic engineering capabilities decide what is true.
3. OpenSees decides numerical results.
4. Artifacts preserve what happened.

Additional PR26 principles:

- A valid AnalysisSpec is not automatically ready for a particular ModelSpec or solver profile.
- Internal capability growth does not imply permanent LLM-visible tool growth.
- Model compilation must have one deterministic truth path shared by PR23 and PR26.
- Response semantics and solver mappings must be resolved deterministically, not inferred by the renderer or worker ad hoc.
- `response_plan.json` describes what to observe, not trusted units or arbitrary solver commands.
- Generated analysis artifacts must be hash-bound and verified before solver execution.
- Renderer artifact creation is not solver execution and does not bypass the existing execution permission gate.

## 3. Scope

PR26 supports exactly the PR25 V1 analysis domain:

- Model: V1 2D Cartesian elastic frame ModelSpec.
- Analysis: `LINEAR_STATIC` only.
- Exactly one explicit load case.
- Explicit nodal loads only.
- Load components: `FX`, `FY`, `MZ`.
- Force units: `N` or `kN`.
- Result requests:
  - NODE `DISPLACEMENT` X/Y.
  - NODE `REACTION_FORCE` X/Y.
  - NODE `REACTION_MOMENT` Z.
  - ELEMENT `GENERALIZED_FORCE` N/VY/MZ at END_I/END_J.
- OpenSees frame formulation: current PR23 `elasticBeamColumn` / `ElasticBeam2d` path.

## 4. End-to-end flow

```text
EngineeringModelSpec ─────┐
                          ├─> Analysis Readiness
EngineeringAnalysisSpec ──┘          │
                                     │ READY only
                                     v
                         shared PR23 model compiler
                                     │
                                     v
                      OpenSees Analysis Renderer
                                     │
                                     v
                 generated standalone analysis bundle
                                     │
                                     v
                       SolverAdapter preflight
                                     │
                                     v
                         execution permission
                                     │
                                     v
                       isolated OpenSees worker
                                     │
                                     v
                     structural_response.json
                                     │
                                     v
                    Result Intelligence / Evidence
```

## 5. Analysis Readiness contract

### 5.1 Public meaning

`READY` means the current ModelSpec and AnalysisSpec are both intrinsically valid and, when combined, are deterministically executable by the PR26 OpenSees V1 profile. It also means every requested response has a proven deterministic OpenSees mapping.

`READY` does not mean artifacts have been rendered, OpenSees is installed, solver preflight has passed, a solve has run, or a result has been verified.

### 5.2 Output

```json
{
  "schema": "FEMAGENT_ANALYSIS_READINESS_V1",
  "status": "READY",
  "profile": "OPENSEES_FRAME_2D_LINEAR_STATIC_V1",
  "modelSpecFingerprint": "...",
  "analysisSpecFingerprint": "...",
  "validation": {
    "modelSpec": {},
    "analysisSpec": {}
  },
  "checks": {
    "modelReadiness": {},
    "modelBinding": {},
    "unitCompatibility": {},
    "loadTargets": {},
    "resultTargets": {},
    "responseMapping": {}
  },
  "issues": []
}
```

### 5.3 Statuses

- `INVALID_SPEC`: either intrinsic ModelSpec or AnalysisSpec validation fails.
- `NOT_READY`: both specs are intrinsically valid, but their combination fails one or more PR26 readiness checks.
- `READY`: all required checks pass.

If status is `INVALID_SPEC`, dependent combination checks are `SKIPPED`.

### 5.4 Model readiness reuse

PR26 reuses `evaluate_engineering_model_readiness()` rather than duplicating connectivity, rigid-body restraint, or repeated-connectivity logic.

A ModelSpec that is not READY cannot produce Analysis Readiness `READY`.

### 5.5 Model binding

The AnalysisSpec must bind exactly to the current normalized ModelSpec identity:

```text
AnalysisSpec.modelSpecFingerprint
==
validated current ModelSpec.modelSpecFingerprint
```

Mismatch produces `NOT_READY` with issue code:

- `ANALYSIS_READINESS_MODEL_FINGERPRINT_MISMATCH`

PR26 never silently rebinds the AnalysisSpec.

### 5.6 Unit compatibility

PR26 V1 performs no unit conversion.

Required:

```text
AnalysisSpec.units.force == ModelSpec.units.force
```

Mismatch produces:

- `ANALYSIS_READINESS_FORCE_UNIT_MISMATCH`

Response units are derived deterministically from validated ModelSpec units:

- displacement = ModelSpec length unit.
- reaction force = ModelSpec force unit.
- reaction moment = force × length.
- generalized N/VY = force.
- generalized MZ = force × length.

Machine-readable moment unit strings use `*`, for example `N*m`, `kN*m`, `N*mm`, `kN*mm`.

### 5.7 Load target existence

Every `loadCases[*].nodalLoads[*].nodeId` must exist in the normalized ModelSpec node set.

Missing target produces:

- `ANALYSIS_READINESS_LOAD_NODE_NOT_FOUND`

PR26 does not choose a nearest node, infer a target from geometry, skip the load, or redistribute it.

### 5.8 Result target existence

NODE result target IDs must exist in ModelSpec nodes.

ELEMENT result target IDs must exist in ModelSpec elements.

Missing targets produce:

- `ANALYSIS_READINESS_RESULT_NODE_NOT_FOUND`
- `ANALYSIS_READINESS_RESULT_ELEMENT_NOT_FOUND`

### 5.9 Reaction semantic constraint

Reaction requests are valid for execution only on a genuinely restrained requested DOF:

- `REACTION_FORCE X` requires `UX` constrained.
- `REACTION_FORCE Y` requires `UY` constrained.
- `REACTION_MOMENT Z` requires `RZ` constrained.

A reaction request on an unrestrained DOF produces:

- `ANALYSIS_READINESS_REACTION_DOF_UNRESTRAINED`

PR26 intentionally does not return an apparently meaningful numerical zero for a free-DOF reaction request.

## 6. Proven OpenSees response mapping

PR26 must cover every PR25 V1 result request.

| AnalysisSpec request | OpenSees access | Selector | Reference frame | Unit |
| --- | --- | --- | --- | --- |
| NODE DISPLACEMENT X | `nodeDisp` | DOF 1 | GLOBAL | length |
| NODE DISPLACEMENT Y | `nodeDisp` | DOF 2 | GLOBAL | length |
| NODE REACTION_FORCE X | `nodeReaction` after `reactions()` | DOF 1 | GLOBAL | force |
| NODE REACTION_FORCE Y | `nodeReaction` after `reactions()` | DOF 2 | GLOBAL | force |
| NODE REACTION_MOMENT Z | `nodeReaction` after `reactions()` | DOF 3 | GLOBAL | force*length |
| ELEMENT GENERALIZED_FORCE N END_I | `eleResponse("localForce")` | index 0 | ELEMENT_LOCAL | force |
| ELEMENT GENERALIZED_FORCE VY END_I | `eleResponse("localForce")` | index 1 | ELEMENT_LOCAL | force |
| ELEMENT GENERALIZED_FORCE MZ END_I | `eleResponse("localForce")` | index 2 | ELEMENT_LOCAL | force*length |
| ELEMENT GENERALIZED_FORCE N END_J | `eleResponse("localForce")` | index 3 | ELEMENT_LOCAL | force |
| ELEMENT GENERALIZED_FORCE VY END_J | `eleResponse("localForce")` | index 4 | ELEMENT_LOCAL | force |
| ELEMENT GENERALIZED_FORCE MZ END_J | `eleResponse("localForce")` | index 5 | ELEMENT_LOCAL | force*length |

The existing ElasticBeam2d local-force mapping remains fail-closed for unsupported formulations.

NODE mappings become part of the proven mapping set only after a real pinned-OpenSeesPy runtime test demonstrates expected values for displacement, reaction force, and reaction moment.

### 6.1 Resolved mapping output

Analysis Readiness emits deterministic mappings rather than only a PASS flag. Example:

```json
{
  "requestId": "R2",
  "quantity": "GENERALIZED_FORCE",
  "target": {"type": "ELEMENT", "id": 7},
  "component": "MZ",
  "location": "END_J",
  "access": "ELEMENT_LOCAL_FORCE",
  "index": 5,
  "referenceFrame": "ELEMENT_LOCAL",
  "unit": "kN*m"
}
```

Renderer and worker consume resolved mapping facts; they do not independently reinterpret engineering semantics.

## 7. Shared PR23 model compiler

PR26 must not duplicate the ModelSpec-to-OpenSees model generation logic from PR23.

The current PR23 pure source-construction logic should be refactored into an internal reusable pure function, conceptually:

```python
build_opensees_frame_2d_model_source(normalized_model_spec)
```

Both the PR23 construction-only renderer and PR26 analysis renderer call the same function.

PR23 public behavior, artifact semantics, and renderer-admission checks remain unchanged.

## 8. Standalone OpenSees analysis bundle

A successful PR26 render writes only under FEMagent's controlled generated-analysis root:

```text
.femagent/generated-analyses/<analysisRenderId>/
├── analysis.py
├── response_plan.json
├── analysis_readiness.json
└── analysis_manifest.json
```

The caller cannot select an arbitrary output path.

### 8.1 `analysis.py`

`analysis.py` is a complete standalone OpenSeesPy entrypoint containing:

1. The shared PR23 model source.
2. One `Linear` time series.
3. One `Plain` load pattern.
4. Explicit `ops.load(nodeId, FX, FY, MZ)` calls.
5. Fixed PR26 V1 linear-static analysis controls.
6. Exactly one `ops.analyze(1)` call.

PR26 V1 solver configuration is fixed by the renderer profile:

```python
ops.constraints("Plain")
ops.numberer("Plain")
ops.system("BandGeneral")
ops.algorithm("Linear")
ops.integrator("LoadControl", 1.0)
ops.analysis("Static")
code = int(ops.analyze(1))
if code != 0:
    raise RuntimeError(...)
```

These are renderer-profile facts, not new AnalysisSpec fields.

`analysis.py` must not contain result extraction such as `nodeDisp`, `nodeReaction`, `eleResponse`, result JSON writing, or solver subprocess logic.

### 8.2 Load compilation

Because readiness already proves force-unit compatibility, renderer writes normalized `FX`, `FY`, and `MZ` numerical values directly into `ops.load()`.

PR26 does not convert units, combine duplicate loads, infer signs, or alter target IDs.

### 8.3 `response_plan.json`

The renderer compiles each AnalysisSpec result request into the existing strict `structural_response_plan` identity format.

`channelId` equals the AnalysisSpec `requestId`.

`response_plan.json` carries only response identity fields. It must not carry trusted unit, DOF/index, arbitrary recorder commands, solver arguments, or user-defined mapping metadata.

### 8.4 `analysis_readiness.json`

This file contains the exact READY report used for renderer admission and becomes part of the rendered trust chain.

### 8.5 `analysis_manifest.json`

The manifest records at minimum:

- schema: `FEMAGENT_OPENSEES_ANALYSIS_RENDER_V1`.
- status: `RENDERED`.
- analysisRenderId.
- renderer name/version.
- modelSpecFingerprint.
- analysisSpecFingerprint.
- readiness profile.
- validated model units.
- loadCaseId.
- resolved response mappings.
- workspace-relative artifact paths.
- SHA256 for `analysis.py`, `response_plan.json`, and `analysis_readiness.json`.
- `analysisRenderFingerprint`.

### 8.6 Analysis render fingerprint

`analysisRenderFingerprint` is deterministic over content identity, not random artifact directory identity.

Its canonical hash input includes:

- renderer name.
- renderer version.
- modelSpecFingerprint.
- analysisSpecFingerprint.
- analysis.py SHA256.
- response_plan.json SHA256.
- analysis_readiness.json SHA256.

Different `analysisRenderId` values must not change this content fingerprint.

## 9. Renderer result contract

Blocked render:

```json
{
  "schema": "FEMAGENT_OPENSEES_ANALYSIS_RENDER_V1",
  "status": "BLOCKED",
  "reason": "ANALYSIS_NOT_READY",
  "readiness": {},
  "analysisRenderId": null,
  "artifacts": null,
  "analysisRenderFingerprint": null
}
```

Successful render:

```text
status = RENDERED
```

Renderer must rerun intrinsic validation and Analysis Readiness on the current inputs. It cannot trust a prior CHECK result supplied by the Agent.

Engineering BLOCKED is a normal successful bridge response. Filesystem corruption, path escape, impossible internal invariants, or write failure use `FemCoreError`.

## 10. Result collection and unit provenance

### 10.1 `response_plan.json` is not a unit authority

Trusted units must never be accepted from the user-editable response plan.

Unit provenance comes from:

```text
validated ModelSpec units
+ validated AnalysisSpec
+ deterministic response semantics
```

and is recorded in Analysis Readiness and the analysis manifest.

### 10.2 Generated-analysis manifest verification

The existing OpenSees SolverAdapter remains the execution path.

For generated PR26 analyses, `solverOptions` adds a controlled optional field:

```text
analysisManifestPath
```

A generated analysis run uses:

- `modelPath` = manifest analysis path.
- no external loadPath; the generated script owns its explicit static load.
- `solverOptions.responsePlanPath` = manifest response-plan path.
- `solverOptions.analysisManifestPath` = manifest path.

Preflight validates:

- manifest schema and renderer identity.
- declared artifact paths.
- analysis.py SHA256.
- response-plan SHA256.
- readiness-report SHA256.
- analysisRenderFingerprint.
- input path equality with manifest paths.
- modelSpecFingerprint and analysisSpecFingerprint presence/format.

Tampering or cross-bundle mixing is fail-closed.

Representative error codes:

- `GENERATED_ANALYSIS_MANIFEST_INVALID`
- `GENERATED_ANALYSIS_ARTIFACT_MISMATCH`
- `GENERATED_ANALYSIS_PATH_MISMATCH`
- `GENERATED_ANALYSIS_FINGERPRINT_MISMATCH`

### 10.3 Private response execution context

After successful adapter verification, FEMagent generates a private staged execution context for the isolated worker. This is not a public Engineering Spec and not an Agent tool payload.

It carries verified resolved mapping facts such as:

- channelId.
- access kind.
- target ID.
- DOF or vector index.
- unit.
- reference frame.

The worker consumes this context rather than independently deriving mapping semantics from the response plan.

### 10.4 Sampling

The existing worker instrumentation around `ops.analyze()` remains the sampling boundary.

For a successful static `analyze(1)`:

1. If any reaction channel exists, call `ops.reactions()` once.
2. Sample all configured response channels.
3. Write one canonical `structural_response.json`.

A single solve may therefore produce mixed displacement, reaction, and element generalized-force channels.

### 10.5 Canonical result format

PR26 continues using `kind = structural_response_series`.

A linear static V1 run produces a single sample per channel. The OpenSees static pseudo-time/load state is recorded as solver-native abscissa, not seconds:

```text
abscissaSemantic = SOLVER_NATIVE_RESULT_ABSCISSA
abscissaUnit = null
```

PR26 does not introduce a new static-result artifact format.

### 10.6 Unit trust boundary for arbitrary OpenSees scripts

Existing arbitrary/user OpenSees Python bundles remain on the current response-plan path. Their result unit remains `null` unless separate trusted engineering evidence establishes units.

Only a verified PR26 generated-analysis bundle may promote ModelSpec-derived response units into the worker result.

## 11. Run-manifest provenance

Generated-analysis runs extend the OpenSees run manifest with a `generatedAnalysis` identity block containing at least:

- analysisRenderFingerprint.
- modelSpecFingerprint.
- analysisSpecFingerprint.
- analysisManifest SHA256.

The desired provenance chain is:

```text
response value
→ structural_response artifact
→ run manifest
→ solver package/engine version
→ analysisRenderFingerprint
→ analysisSpecFingerprint
→ modelSpecFingerprint
```

## 12. Python bridge

PR26 adds internal commands:

```text
analysis.readiness
analysis.renderOpenSees
```

Both accept:

```json
{
  "modelSpec": {},
  "analysisSpec": {}
}
```

Malformed transport payloads produce bridge errors. Engineering `INVALID_SPEC`, `NOT_READY`, and renderer `BLOCKED` remain normal `ok=true` domain results.

## 13. TypeScript transport and contracts

TypeScript remains a thin mirror of Python truth.

Extend AnalysisSpec-related types with:

- `FemAnalysisReadinessStatus`.
- `FemAnalysisReadinessIssue`.
- `FemAnalysisResponseMapping`.
- `FemAnalysisReadiness`.
- `FemOpenSeesAnalysisRenderArtifacts`.
- `FemOpenSeesAnalysisRenderResult`.

Add thin `pythonBridge.ts` wrappers:

- `runFemAnalysisReadiness()`.
- `runFemAnalysisRenderOpenSees()`.

TypeScript must not calculate units, target existence, reaction restraints, response DOFs, response vector indices, fingerprints, or readiness.

## 14. Agent tool surface

PR26 does not add one permanent Agent tool per internal capability.

It adds one high-level tool to the existing Analysis extension:

```text
fem_analysis_prepare_opensees
```

Parameters:

```json
{
  "mode": "CHECK | RENDER",
  "modelSpec": {},
  "analysisSpec": {}
}
```

Behavior:

- `CHECK` calls Analysis Readiness and is SAFE/read-only.
- `RENDER` calls the renderer, which reruns readiness and may write only controlled generated-analysis artifacts.
- Neither mode executes OpenSees.
- `READY` does not mean solver preflight or execution succeeded.
- `RENDERED` does not mean OpenSees ran.
- The Agent must not mutate engineering facts merely to force READY.

The existing temporary `fem_analysis_spec_validate` tool remains in PR26. Tool-surface cleanup is a separate concern and is not mixed into this feature PR.

## 15. Permission boundary

`fem_analysis_prepare_opensees(mode=RENDER)` writes internal artifacts but is not solver execution and does not use the real-solver execution permission gate.

The existing permission gate remains attached to `fem_solver_run` only.

PR26 must not introduce an alternate solver execution path.

## 16. Test strategy

### 16.1 Analysis Readiness tests

Cover at least:

- valid pair -> READY.
- invalid ModelSpec -> INVALID_SPEC.
- invalid AnalysisSpec -> INVALID_SPEC.
- ModelSpec not model-ready -> analysis NOT_READY.
- model fingerprint mismatch -> NOT_READY.
- force unit mismatch -> NOT_READY.
- missing load node -> NOT_READY.
- missing displacement/reaction node -> NOT_READY.
- missing generalized-force element -> NOT_READY.
- reaction X on unrestrained UX -> NOT_READY.
- reaction Y on unrestrained UY -> NOT_READY.
- reaction moment Z on unrestrained RZ -> NOT_READY.
- all PR25 V1 response classes -> response mapping PASS.
- a PR25-intrinsically-VALID nonexistent target remains VALID in PR25 but becomes NOT_READY in PR26.

### 16.2 Proven mapping runtime test

Use a real pinned OpenSeesPy elastic frame/cantilever case to prove:

- tip displacement mapping.
- support reaction force mapping.
- support reaction moment mapping.
- ElasticBeam2d local force mapping.
- expected equilibrium relationships within explicit numerical tolerances.

NODE response mappings are not considered proven until this test passes.

### 16.3 Renderer tests

Successful render must create all four bundle files.

Generated `analysis.py` must contain model construction, load definition, fixed V1 static analysis controls, and exactly one solve call.

It must not contain result extraction, result file writing, or solver subprocess logic.

Blocked readiness must write no partial bundle.

### 16.4 Determinism tests

Reordering canonicalizable ModelSpec/AnalysisSpec collections must preserve:

- modelSpecFingerprint.
- analysisSpecFingerprint.
- analysis.py SHA256.
- response-plan SHA256.
- analysisRenderFingerprint.

Random render IDs may differ.

### 16.5 Tamper tests

After rendering, separately tamper with:

- analysis.py.
- response_plan.json.
- readiness artifact.
- manifest artifact paths.
- manifest hashes/fingerprint.

Solver preflight must fail closed before worker execution.

### 16.6 Full golden path

An integration test must demonstrate:

```text
ModelSpec VALID
→ AnalysisSpec VALID
→ Analysis READY
→ OpenSees analysis RENDERED
→ solver preflight READY
→ isolated worker COMPLETED
→ structural_response.json
→ Result Intelligence
```

The same solve must cover mixed PR25 V1 responses including:

- node displacement.
- node reaction force.
- node reaction moment.
- element N.
- element VY.
- element MZ.

## 17. Error and responsibility boundaries

PR26 maintains:

```text
VALID AnalysisSpec
!= READY analysis
!= RENDERED OpenSees analysis
!= READY solver preflight
!= successful solver run
!= VERIFIED engineering conclusion
```

The renderer never repairs engineering facts.

The worker never becomes a second engineering interpretation layer.

The Agent never invents unsupported mappings or units.

## 18. Explicit non-goals

PR26 does not add:

- multiple load cases.
- load combinations.
- distributed loads.
- gravity/self-weight inference.
- thermal loads.
- imposed displacement/support settlement.
- modal analysis.
- transient analysis.
- response spectrum.
- nonlinear static/pushover.
- geometric/material nonlinearity.
- caller-selected solver controls, step count, tolerance, algorithm, integrator, or equation system.
- ANSYS analysis renderer.
- cross-solver execution.
- natural-language AnalysisSpec completion.
- automatic AnalysisSpec repair.
- optimization.
- new AnalysisSpec V1 fields.

## 19. PR27 boundary

PR27 owns controlled natural-language analysis completion:

```text
Natural Language
→ EngineeringAnalysisRequirementDraft
→ deterministic completion
→ COMPLETE
→ EngineeringAnalysisSpec
```

PR27 must still pass the resulting AnalysisSpec through PR26 Analysis Readiness and rendering. It cannot bypass PR26 by emitting solver code directly.

## 20. Acceptance criteria

PR26 is complete only when all of the following are true:

1. A deterministic Analysis Readiness capability binds ModelSpec and AnalysisSpec and enforces the full V1 joint checks.
2. Every PR25 V1 result request has a proven deterministic OpenSees mapping.
3. Reaction requests on unrestrained DOFs are NOT_READY.
4. Model and Analysis force units must match; no hidden conversion occurs.
5. PR23 and PR26 share one deterministic ModelSpec-to-OpenSees model compiler.
6. READY pairs render a standalone four-file OpenSees analysis bundle.
7. Renderer never extracts numerical results and never executes the solver.
8. Generated bundle identity is hash-bound and verified before execution.
9. Trusted result units for generated analyses come only from verified ModelSpec/AnalysisSpec provenance.
10. The isolated worker produces canonical `structural_response_series` for mixed node and element requests.
11. Existing SolverAdapter preflight/run and execution permission boundaries remain the only solver execution path.
12. One high-level `fem_analysis_prepare_opensees` Agent tool exposes CHECK/RENDER without multiplying permanent LLM-visible tools.
13. Real OpenSees runtime tests prove node displacement/reaction and existing ElasticBeam2d mappings.
14. Tampered generated-analysis bundles fail closed before execution.
15. The full ModelSpec → AnalysisSpec → READY → RENDERED → solver preflight → solver run → Result Intelligence golden path passes.
16. PR27 natural-language analysis completion remains outside PR26.
