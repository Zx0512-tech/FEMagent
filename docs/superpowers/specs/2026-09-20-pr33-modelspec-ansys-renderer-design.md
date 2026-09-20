# PR33 — Deterministic ModelSpec → ANSYS Renderer Design

## Purpose

PR33 removes the largest remaining ANSYS provenance gap in the controlled earthquake workflow.

For the supported V1 2D elastic-frame domain, FEMagent can now deterministically render the validated EngineeringModelSpec into an ANSYS MAPDL bundle and bind PR29 execution back to the exact ModelSpec fingerprint.

The legacy arbitrary-APDL path remains supported and continues to report `semanticEquivalence=NOT_MACHINE_PROVEN`.

## Supported model domain

Exactly the existing EngineeringModelSpec V1 domain:

- dimension: 2D
- family: FRAME
- Cartesian XY
- LINEAR_ELASTIC materials
- FRAME_2D sections with A and Iz
- ELASTIC_FRAME_2D / EULER_BERNOULLI elements
- UX/UY/RZ constraints
- explicit nodal masses mUX/mUY

No section geometry, Poisson ratio, density, shear area, torsion constant, or other absent engineering properties are invented.

## ANSYS mapping

Frame element:

- MAPDL archive element `BEAM3`
- node IDs: identity
- element IDs: identity
- material IDs: identity
- real-constant section IDs: identity
- Real constants: AREA=A, IZZ=Iz
- HEIGHT/SHEARZ/ISTRN/ADDMAS intentionally omitted because V1 does not define them and current workflow requests only nodal displacement/reaction output.

The renderer selects BEAM3 because the V1 model is a planar 3-DOF Euler-Bernoulli frame with only A and Iz. A modern 3D BEAM188 section would require additional cross-section properties not present in ModelSpec; PR33 must not invent them.

Nodal mass:

- `MASS21` with explicit MASSX/MASSY from mUX/mUY;
- auxiliary mass-element and real-constant IDs are deterministic and recorded in the render manifest;
- auxiliary UZ/ROTX/ROTY DOFs introduced only by MASS21 are deterministically restrained, outside the ModelSpec 2D DOF domain;
- no rotational mass is invented.

## Controlled execution scaffold

The rendered APDL contains exactly one controlled transient injection scaffold:

```text
/SOLU
ANTYPE,TRANS
SOLVE
FINISH
/EXIT,NOSAVE
```

It contains no ACEL, damping, time-step, duration, result-control, or generated load commands. PR29 still owns all transient analysis/load injection immediately before the verified solve hook.

The renderer itself never executes ANSYS.

## Render artifact

Schema:

`FEMAGENT_ANSYS_MODEL_RENDER_V1`

Renderer:

`ANSYS_FRAME_2D_BEAM3_V1` version `1.0`

A successful report records:

- modelSpecFingerprint;
- exact units;
- readiness profile;
- deterministic tag mappings;
- auxiliary mass mapping;
- model source SHA-256;
- ANSYS Model Bundle fingerprint;
- render manifest path;
- renderFingerprint.

## Machine-proven binding

PR29 accepts an optional `solverOptions.ansysV2.renderManifestPath`.

When present, admission verifies:

1. current model path equals the rendered model artifact path;
2. current source SHA equals the render manifest;
3. current bundle fingerprint equals the render manifest;
4. render fingerprint recomputes exactly;
5. render manifest ModelSpec fingerprint equals AnalysisSpec.modelSpecFingerprint;
6. ModelSpec length/time units equal solverOptions.modelUnits;
7. identity node/element mapping is declared by the renderer.

Only then PR29 reports:

- binding.mode = `DETERMINISTIC_MODEL_SPEC_RENDER`
- semanticEquivalence = `MACHINE_PROVEN_RENDER_BINDING`

Without the render manifest, existing explicit-bundle behavior remains unchanged.

## PR31 behavior

For solver=ansys:

- if solverModelPath is supplied, preserve legacy arbitrary-APDL workflow and its NOT_MACHINE_PROVEN warning;
- if solverModelPath is omitted, render the ModelSpec deterministically and use that generated bundle automatically;
- pass the render manifest into PR29 admission;
- freeze the machine-proven render identity into the workflow manifest.

## Non-goals

- ANSYS static/modal AnalysisSpec V2 execution;
- 3D frame ModelSpec;
- BEAM188/189 section-geometry inference;
- distributed mass/density inference;
- shell/solid elements;
- nonlinear analysis;
- response spectrum;
- optimization;
- real ANSYS licensing/runtime in CI.
