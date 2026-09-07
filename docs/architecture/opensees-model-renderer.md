# OpenSees Model Renderer

## Purpose

PR23 introduces FEMagent's first deterministic solver-specific model authoring layer. It converts an explicit 2D elastic-frame `EngineeringModelSpec` into a construction-only OpenSeesPy model artifact without changing engineering facts or executing an analysis.

```text
EngineeringModelSpec
        ↓
PR21 validation
        ↓
PR22 readiness
        ↓
READY
        ↓
OpenSees Frame 2D Renderer
        ↓
.femagent/generated-models/<renderId>/
├─ model.py
└─ render_manifest.json
        ↓
Model Intelligence
        ↓
OpenSees build-only inspection
        ↓
realized solver-domain evidence
```

## Trust boundary

The renderer is translation authority, not engineering or numerical truth.

- PR21 owns ModelSpec validity.
- PR22 owns renderer-admission readiness.
- PR23 maps only explicit normalized facts into OpenSees construction calls.
- Model Intelligence owns source/bundle inspection evidence.
- OpenSees build-only inspection proves the realized domain.
- Real solver execution remains separately permission gated.

A `RENDERED` result means deterministic artifacts were produced. It does not prove stability, structural adequacy, solver-domain construction, analysis success, or numerical results.

## V1 mapping

V1 supports exactly `FRAME_2D_ELASTIC_READINESS_V1`:

- 2D Cartesian frame;
- node DOFs `UX`, `UY`, `RZ` → OpenSees DOFs 1, 2, 3;
- literal `ops.node()` calls with identity node tags;
- explicit constraints → `ops.fix()`;
- nodal mass `(mUX, mUY)` → `ops.mass(tag, mUX, mUY, 0.0)`;
- one `ops.geomTransf("Linear", 1)`;
- `ELASTIC_FRAME_2D` + `EULER_BERNOULLI` → `elasticBeamColumn` using exact referenced `A`, `E`, and `Iz`;
- identity element tags.

The renderer does not create hidden nodes/elements, renumber entities, mesh, infer supports, calculate section properties, convert units, or synthesize missing material properties.

## Deterministic source

Generated topology is deliberately expanded into literal calls instead of runtime loops or data-file readers. This keeps existing OpenSees AST inspection able to report `dynamicGeneration = false` and literal node/element tags.

For equivalent normalized specs and renderer version `OPENSEES_FRAME_2D_V1/1.0`:

- `model.py` bytes are identical;
- `modelSha256` is identical;
- `renderFingerprint` is identical;
- `renderId` may differ because it identifies a generation event rather than engineering content.

Numeric literals use Python round-trippable float representation with negative zero normalized to `0.0`; no engineering rounding or tolerance cleanup is applied.

## Artifact identity and isolation

Artifacts are published only below:

```text
.femagent/generated-models/render_<16hex>/
```

The public renderer tool exposes no output-path parameter. Existing directories are never reused or overwritten. A write failure removes the newly-created render directory before returning an error.

Identity chain:

```text
modelSpecFingerprint
        ↓
renderer name/version
        ↓
model.py SHA256
        ↓
renderFingerprint
```

The `renderFingerprint` excludes the random render ID and path.

## Construction-only rule

Generated source may use model-building calls such as `wipe`, `model`, `node`, `fix`, `mass`, `geomTransf`, and `element`.

It must not generate loads or analysis commands such as `timeSeries`, `pattern`, `constraints`, `system`, `integrator`, `algorithm`, `analysis`, `analyze`, or `eigen`.

## Product tool surface

The Agent tool is:

```text
fem_model_render_opensees
```

It writes only controlled FEMagent artifacts and does not call `fem_solver_run`. The existing real-solver confirmation gate is unchanged.

Recommended chain after rendering:

```text
fem_model_spec_validate
→ fem_model_spec_readiness
→ fem_model_render_opensees
→ fem_model_inspect
→ fem_solver_preflight(opensees)
→ build-only evidence
```

## Explicit V1 non-goals

PR23 does not add ANSYS rendering, 3D frames, trusses, shells/solids, Timoshenko beams, nonlinear transformations, releases/hinges, loads, gravity, analysis configuration, damping, response-plan authoring, Semantic Roles, solver execution, automatic repair, automatic meshing, or unit conversion.
