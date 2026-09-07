# PR23 — OpenSees Frame 2D Renderer Verification

Date: 2026-09-07
PR: #19
Branch: `feat/pr23-opensees-frame-2d-renderer`
Base: `main`

## Scope verified

PR23 adds the controlled authoring path:

```text
PR21 VALID EngineeringModelSpec
→ PR22 READY
→ deterministic OpenSees Frame 2D renderer
→ internal model.py + render_manifest.json
→ existing OpenSees Model Intelligence
→ existing build-only inspection
```

The renderer does not execute an analysis, infer engineering facts, convert units, generate loads, or replace solver-domain evidence.

## TDD evidence

Implementation followed staged RED/GREEN gates.

- Renderer core tests were introduced before the production renderer and exercised deterministic source generation, blocking, explicit constraint/mass mapping, numeric canonicalization, collision protection, and failed-write cleanup.
- Bridge RED: commit `69f349fa40109dd328766a3a0512528ba807acdf`; CI #369 failed only because `modelSpec.renderOpenSees` was still unknown, while the existing Python suite passed.
- Bridge GREEN: commit `569108b0df52c4f5071d2645b36521a69572f5cd`; CI #370 completed successfully.
- TypeScript RED: commit `865630561432a19e0222c6d7fb74b8e05e8087f3`; CI #371 failed because `runFemModelSpecRenderOpenSees` and `FemOpenSeesRenderResult` did not yet exist.
- Pi registration RED: commit `ec4876da904b1e94312e4f2ccad8fcd5c154dd2d`; CI #375 ran 38 TypeScript tests with 36 passing and exactly the two new renderer registration/allow-list assertions failing.
- Pi GREEN: renderer tool registration and Agent allow-list were then added without changing the real-solver permission gate.

## Deterministic renderer assertions

Tests prove that V1:

- re-runs PR22 readiness and blocks invalid/NOT_READY inputs before artifact publication;
- emits construction-only OpenSeesPy source;
- preserves node and element IDs as OpenSees tags;
- maps `UX/UY/RZ` explicitly to OpenSees DOFs 1/2/3;
- maps nodal mass to `(mUX, mUY, 0.0)`;
- resolves each element's exact referenced `A`, `E`, and `Iz` into `elasticBeamColumn`;
- uses exactly one `geomTransf("Linear", 1)`;
- normalizes negative zero without engineering rounding or unit conversion;
- produces identical `model.py` bytes, `modelSha256`, and `renderFingerprint` for equivalent normalized specs while allowing different render instance IDs;
- never overwrites an existing render directory;
- removes a fresh partial render directory after publication failure.

## Existing evidence-chain integration

The generated portal-frame model is passed to the existing OpenSees Python inspector. Regression tests require:

```text
classification = MODEL_CONFIRMED
dynamicGeneration = false
safetyFindings = []
staticTopology.nodeTags = [1,2,3,4]
staticTopology.elementTags = [1,2,3]
bundle.integrity = VALID
```

The same generated artifact is then passed to `OpenSeesBundleAdapter.build_inspect()` where OpenSeesPy is available. Regression tests require:

```text
analysisAdvanced = false
interceptedAnalyzeCalls = 0
nodeTags = [1,2,3,4]
elementTags = [1,2,3]
```

Thus renderer output is not self-certified; existing Model Intelligence and build-only evidence remain the proof layers.

## Pre-closeout full CI

CI #377 (`34090645645`) on implementation head `a10911700e8f6945ba8a2feada76db76dfe79a91` completed successfully with:

```text
TypeScript typecheck: PASS
TypeScript tests: 38/38 PASS
Python tests: 222 passed, 300 existing third-party warnings
Ruff: All checks passed!
OpenSees adapter availability smoke: PASS
ANSYS result reader import smoke: PASS
fem:health: status = ok
```

The 300 Python warnings are the existing VTK/NumPy deprecation warnings from ANSYS/result tests and are not renderer failures.

## Final exact-head gate

This verification document and the architecture document change the PR head after CI #377. Therefore PR23 is not considered Ready for Review until GitHub CI for the final documentation head completes successfully. The final head SHA and CI run are recorded in PR #19 metadata/comment after that run rather than pre-writing a stale SHA into this file.

## Authority boundary

A renderer result with `status = RENDERED` proves deterministic artifact generation only. It does not prove structural adequacy, solver success, analysis readiness beyond PR22's limited readiness profile, or numerical results.
