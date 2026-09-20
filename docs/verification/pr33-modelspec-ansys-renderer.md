# PR33 Verification — Deterministic ModelSpec → ANSYS Renderer

## Implementation status

PR33 adds a deterministic ANSYS MAPDL model renderer for the existing EngineeringModelSpec V1 planar elastic-frame domain and connects that provenance to PR29 admission and PR31 earthquake workflow preparation.

Implementation CI #707:

- run id: `35506177339`
- implementation head: `46fd4465061b2e84f530c2b462071d7036120f64`
- conclusion: SUCCESS

## Deterministic mapping

The renderer maps:

- 2D FRAME / CARTESIAN_XY;
- LINEAR_ELASTIC material E → `MP,EX`;
- FRAME_2D A/Iz → BEAM3 real constants;
- ELASTIC_FRAME_2D / EULER_BERNOULLI → `BEAM3`;
- node IDs → ANSYS node IDs by identity;
- frame element IDs → ANSYS frame element IDs by identity;
- material IDs and section real-constant IDs by identity;
- explicit mUX/mUY → `MASS21` with deterministic auxiliary IDs;
- ModelSpec RZ → ANSYS ROTZ.

No section geometry, density, Poisson ratio, torsional inertia, shear area, or missing mass is inferred.

The generated source owns only model construction plus one `ANTYPE,TRANS` / `SOLVE` scaffold. It contains no ACEL, Rayleigh damping, time-step, duration, or result-control values. Those remain PR29 responsibilities.

## Machine-proven render binding

The render manifest retains the normalized ModelSpec used for generation.

PR29 verification now proves all of the following before using the generated binding:

1. exact model path;
2. exact source SHA-256;
3. exact current ANSYS bundle fingerprint;
4. retained normalized ModelSpec is intrinsically valid;
5. retained ModelSpec reproduces the declared ModelSpec fingerprint;
6. deterministic regeneration reproduces the current APDL source SHA;
7. render fingerprint recomputes;
8. AnalysisSpec.modelSpecFingerprint matches the render ModelSpec fingerprint;
9. model length/time units match;
10. identity node/frame-element mapping and deterministic auxiliary-mass mapping remain intact.

Successful generated admission reports:

- `mode=DETERMINISTIC_MODEL_SPEC_RENDER`
- `semanticEquivalence=MACHINE_PROVEN_RENDER_BINDING`

This wording proves deterministic ModelSpec→APDL render binding; it is not a claim that ANSYS itself has been mathematically verified by FEMagent.

## Backward compatibility

Existing external/arbitrary APDL remains supported.

Without a PR33 render manifest, PR29 preserves:

- `mode=EXPLICIT_BUNDLE_CONFIRMATION`
- `semanticEquivalence=NOT_MACHINE_PROVEN`

The external APDL path remains exact-byte bound but is not promoted to ModelSpec equivalence.

## PR31 workflow behavior

For solver=ANSYS:

- omit `solverModelPath` → PR31 deterministically renders the ModelSpec and carries `renderManifestPath` into PR29 preflight;
- supply `solverModelPath` → PR31 intentionally uses the existing external APDL path and preserves the NOT_MACHINE_PROVEN warning.

Generated ANSYS uniform-base workflows also require positive explicit nodal mass in the excited direction; PR32 recognizes this failure and only accepts a complete revised ModelSpec rather than inventing mass.

The existing permission gate now shows whether ANSYS execution uses deterministic ModelSpec rendering or external APDL byte binding.

## Verification coverage

Tests cover:

- deterministic source identity across independent render directories;
- path-bound bundle identity kept separate from path-independent render identity;
- BEAM3/MASS21 mapping and no analysis-control leakage;
- blocked non-ready ModelSpec;
- source tamper rejection;
- retained-ModelSpec provenance forgery rejection;
- PR29 machine-proven generated binding;
- legacy PR29 NOT_MACHINE_PROVEN fallback;
- mismatched AnalysisSpec/ModelSpec fingerprint rejection;
- machine binding transported through ANSYS SolverAdapter preflight;
- generated model execution through the existing PR29 fake-runtime path;
- PR31 generated ANSYS auto-render handoff;
- PR31 legacy external APDL compatibility;
- generated ANSYS excited-direction mass guard;
- PR32 recovery classification for generated ANSYS missing mass;
- TypeScript bridge and SAFE Agent render tool.

## CI #707

Passed:

- Typecheck
- TypeScript engineering bridge tests
- Python engineering core tests
- Ruff
- OpenSees adapter availability smoke
- ANSYS result-reader import smoke
- FEM health smoke

## Scope audit

PR33 production changes are limited to:

- deterministic ANSYS ModelSpec renderer and verifier;
- optional PR29 render-manifest admission binding;
- PR31 automatic generated-ANSYS preparation;
- PR32 integration for the new ANSYS mass-readiness code;
- TypeScript/bridge/tool contracts;
- execution-confirmation provenance display.

No changes are made to:

- ANSYS numerical algorithms;
- OpenSees numerical algorithms;
- PR29 earthquake load/control mathematics;
- Result Intelligence numerical algorithms;
- nonlinear analysis;
- response spectrum;
- optimization.

## Runtime limitation

CI validates deterministic rendering, static inspection, staged PR29 integration, and the existing fake ANSYS runtime/result pipeline. It does not claim a licensed commercial ANSYS installation executed BEAM3/MASS21 in CI.

## Final-head rule

The closeout commit changes documentation only. PR33 may move to Ready for Review only after that exact final head passes the same full CI suite.
