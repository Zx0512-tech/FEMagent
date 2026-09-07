# PR23 — OpenSees Frame 2D Renderer Design

Date: 2026-09-07
Status: approved design candidate
Roadmap label: PR23 — OpenSees Renderer

## 1. Purpose

PR23 introduces the first controlled model-authoring renderer in FEMagent. It converts a PR21-valid and PR22-ready `EngineeringModelSpec` for a 2D elastic frame into a deterministic OpenSeesPy model script, while preserving the project's existing trust boundaries:

- the Agent/LLM may propose engineering intent;
- PR21 decides whether the ModelSpec is valid;
- PR22 decides whether the ModelSpec is ready for deterministic rendering;
- PR23 performs solver-specific translation only;
- existing Model Intelligence inspects the generated script;
- existing OpenSees build-only inspection proves the realized solver domain;
- solver execution remains a separate, permission-gated stage.

PR23 does not treat generated source text as solver truth. A successful render means only that deterministic artifacts were produced from a ready ModelSpec.

## 2. Architecture Position

```text
Engineering facts
      ↓
EngineeringModelSpec
      ↓
PR21 validate
      ↓
VALID
      ↓
PR22 readiness
      ↓
READY
      ↓
PR23 OpenSees Frame 2D Renderer
      ↓
.femagent/generated-models/<renderId>/
├─ model.py
└─ render_manifest.json
      ↓
existing fem_model_inspect
      ↓
OpenSees AST / Model Bundle evidence
      ↓
existing OpenSees build-only inspection
      ↓
realized solver-domain evidence
```

The renderer is a new solver-specific authoring layer. It must not duplicate or bypass ModelSpec validation, readiness evaluation, Model Intelligence, or solver preflight.

## 3. V1 Supported Input Contract

PR23 V1 supports exactly the PR21/PR22 frame profile:

```text
dimension        = 2D
family           = FRAME
coordinateSystem = CARTESIAN_XY
node DOFs        = UX, UY, RZ
element type     = ELASTIC_FRAME_2D
formulation      = EULER_BERNOULLI
readinessProfile = FRAME_2D_ELASTIC_READINESS_V1
```

The renderer must call `evaluate_engineering_model_readiness(spec)` itself and must proceed only when:

```text
readiness.status  == READY
readiness.profile == FRAME_2D_ELASTIC_READINESS_V1
```

It must not trust a caller-supplied readiness boolean, readiness document, or prose assertion.

## 4. Artifact Boundary

Generated files are written only below FEMagent's controlled artifact directory:

```text
.femagent/generated-models/<renderId>/
├─ model.py
└─ render_manifest.json
```

`<renderId>` is an instance identifier of the form:

```text
render_<16 lowercase hexadecimal characters>
```

The renderer must not:

- accept a user-selected output path in V1;
- overwrite user source files;
- write outside `.femagent/generated-models/`;
- overwrite an existing render directory;
- use an existing render directory as a continuation target.

A render instance and the rendered content have different identities:

- `renderId`: identity of one artifact-generation event;
- `modelSpecFingerprint`: identity of the normalized engineering specification;
- `modelSha256`: identity of the generated `model.py` bytes;
- `renderFingerprint`: deterministic identity of the renderer result content.

The same ModelSpec may therefore produce different `renderId` values across invocations while producing identical `model.py` bytes, `modelSha256`, and `renderFingerprint` for the same renderer version.

## 5. Renderer Implementation Strategy

PR23 uses direct deterministic source generation with literal OpenSeesPy calls.

Rejected alternatives:

1. Building a Python AST and unparsing it. This adds unnecessary machinery for the V1 mapping and may couple output formatting to Python-version behavior.
2. Generating a generic runtime loop that reads model data from JSON. This would introduce file dependencies and dynamic generation, weakening existing static Model Intelligence evidence.

V1 therefore deliberately expands nodes, constraints, masses, and elements into literal `ops.*` calls. Auditability and static topology evidence are prioritized over compact source size.

## 6. Generated Script Contract

### 6.1 Header and Model Initialization

Every generated script starts with:

```python
import openseespy.opensees as ops

ops.wipe()
ops.model("basic", "-ndm", 2, "-ndf", 3)
```

The DOF mapping is fixed:

```text
UX → OpenSees DOF 1
UY → OpenSees DOF 2
RZ → OpenSees DOF 3
```

The renderer must not alter this mapping.

### 6.2 Nodes

Each normalized ModelSpec node:

```json
{"id": 12, "x": 3.0, "y": 4.0}
```

maps directly to:

```python
ops.node(12, 3.0, 4.0)
```

Policy:

```text
ModelSpec node.id == OpenSees node tag
```

No node renumbering, compression, hidden nodes, coordinate transformation, or coincident-node merging is permitted.

### 6.3 Constraints

A constraint is translated only from its explicit DOF list.

Examples:

```json
{"nodeId": 1, "dofs": ["UX", "UY"]}
```

becomes:

```python
ops.fix(1, 1, 1, 0)
```

and:

```json
{"nodeId": 1, "dofs": ["UX", "UY", "RZ"]}
```

becomes:

```python
ops.fix(1, 1, 1, 1)
```

The renderer does not infer semantic support labels such as `FIXED`, `PINNED`, or `ROLLER`.

Nodes without a constraint record receive no `ops.fix()` call.

### 6.4 Nodal Masses

A V1 nodal mass:

```json
{"nodeId": 3, "mUX": 1000.0, "mUY": 1000.0}
```

maps to:

```python
ops.mass(3, 1000.0, 1000.0, 0.0)
```

V1 ModelSpec has no rotational mass field. Therefore the third OpenSees mass component is deterministically `0.0` by contract; this is not an inferred engineering property.

Nodes without a `nodalMasses` record receive no `ops.mass()` call.

### 6.5 Material and Section Resolution

PR23 does not create OpenSees material or section entities for `ELASTIC_FRAME_2D` elements.

For each element, the renderer resolves:

- `youngsModulus` from the referenced `LINEAR_ELASTIC` material;
- `area` and `iz` from the referenced `FRAME_2D` section.

These properties are passed directly to OpenSees `elasticBeamColumn`.

This avoids creating solver entities that are unnecessary for the selected OpenSees element signature.

### 6.6 Geometric Transformation

V1 emits exactly one geometric transformation:

```python
ops.geomTransf("Linear", 1)
```

All V1 frame elements reference geometric transformation tag `1`.

This is fixed because PR23 supports only linear elastic 2D Euler–Bernoulli frame elements and excludes P-Delta, corotational transformations, rigid offsets, and element releases.

OpenSees transformation tags use their own namespace, so transformation tag `1` does not conflict with node tag `1` or element tag `1`.

### 6.7 Frame Elements

A ModelSpec element:

```json
{
  "id": 101,
  "type": "ELASTIC_FRAME_2D",
  "formulation": "EULER_BERNOULLI",
  "nodeI": 1,
  "nodeJ": 2,
  "materialId": 4,
  "sectionId": 7
}
```

with resolved properties `E`, `A`, and `Iz` maps to the OpenSees equivalent of:

```python
ops.element(
    "elasticBeamColumn",
    101,
    1,
    2,
    A,
    E,
    Iz,
    1,
)
```

Policy:

```text
ModelSpec element.id == OpenSees element tag
```

No element renumbering, splitting, meshing, release generation, hidden links, or topology mutation is permitted.

## 7. Deterministic Source Ordering

The generated source order is fixed:

1. import;
2. `ops.wipe()`;
3. `ops.model(...)`;
4. nodes sorted by node `id`;
5. constraints sorted by `nodeId`;
6. nodal masses sorted by `nodeId`;
7. one `ops.geomTransf("Linear", 1)`;
8. elements sorted by element `id`.

Materials and sections are lookup data and do not produce standalone OpenSees calls.

PR21 normalization already provides deterministic collection ordering, but the renderer must still sort explicitly at the translation boundary rather than rely on caller ordering.

## 8. Canonical Numeric Rendering

Generated Python numeric literals must be deterministic for the same normalized numeric value.

V1 rules:

- inputs must already be finite because PR21 rejects NaN and infinity;
- negative zero must render as `0.0`;
- integer-valued engineering floats retain a valid floating-point representation where appropriate;
- floating-point literals use one canonical formatter with enough precision to round-trip the Python float value;
- the renderer must not apply engineering-unit conversion, magnitude rounding, or tolerance-based cleanup.

The exact formatter is an implementation detail but must be fixed by golden tests and must not depend on locale.

## 9. Units

The renderer performs no unit conversion.

OpenSees accepts a consistent user-selected unit system. PR23 therefore preserves ModelSpec numerical values exactly and records the explicit ModelSpec unit declaration in the manifest.

Examples of supported ModelSpec unit declarations remain those already allowed by PR21, including combinations such as `m/N/s` or `mm/N/s`.

PR23 must not infer whether a numerical magnitude looks like Pa, MPa, N, kN, m, or mm.

## 10. Analysis Commands Are Forbidden

The generated V1 model script is construction-only.

Allowed call families include:

```text
ops.wipe
ops.model
ops.node
ops.fix
ops.mass
ops.geomTransf
ops.element
```

PR23 must not generate analysis/load commands, including:

```text
ops.timeSeries
ops.pattern
ops.constraints
ops.numberer
ops.system
ops.test
ops.algorithm
ops.integrator
ops.analysis
ops.analyze
ops.eigen
```

A rendered script therefore cannot itself advance an analysis.

## 11. Python Authoritative API

The Python API is:

```python
render_opensees_frame_2d(
    workspace: Path,
    spec: dict[str, Any],
) -> dict[str, Any]
```

Python `fem_core` owns all renderer engineering translation and artifact-generation truth.

The TypeScript layer must not implement a second OpenSees mapping or readiness algorithm.

## 12. Render Result Contract

Top-level schema:

```text
FEMAGENT_OPENSEES_RENDER_V1
```

Normal result statuses:

```text
RENDERED
BLOCKED
```

### 12.1 RENDERED

A successful result has the form:

```json
{
  "schema": "FEMAGENT_OPENSEES_RENDER_V1",
  "status": "RENDERED",
  "renderId": "render_ab12cd34ef56abcd",
  "renderer": {
    "name": "OPENSEES_FRAME_2D_V1",
    "version": "1.0"
  },
  "input": {
    "modelSpecFingerprint": "...",
    "readinessProfile": "FRAME_2D_ELASTIC_READINESS_V1",
    "units": {
      "length": "m",
      "force": "N",
      "time": "s"
    }
  },
  "mapping": {
    "nodeTagPolicy": "IDENTITY",
    "elementTagPolicy": "IDENTITY",
    "geomTransfTag": 1,
    "nodeCount": 4,
    "elementCount": 3
  },
  "artifacts": {
    "modelPath": ".femagent/generated-models/render_ab12cd34ef56abcd/model.py",
    "modelSha256": "...",
    "manifestPath": ".femagent/generated-models/render_ab12cd34ef56abcd/render_manifest.json"
  },
  "renderFingerprint": "..."
}
```

### 12.2 BLOCKED

If the input object reaches ModelSpec evaluation but readiness is not `READY`, no artifact directory is committed and the renderer returns:

```json
{
  "schema": "FEMAGENT_OPENSEES_RENDER_V1",
  "status": "BLOCKED",
  "reason": "MODEL_NOT_READY",
  "readiness": {"...": "PR22 readiness result"},
  "renderId": null,
  "artifacts": null,
  "renderFingerprint": null
}
```

`INVALID_SPEC` and `NOT_READY` both block rendering. The embedded readiness result remains the detailed source of diagnostic truth.

A readiness profile other than `FRAME_2D_ELASTIC_READINESS_V1` is also blocked/fail-closed as unsupported.

## 13. Render Fingerprint

The renderer computes `modelSha256` from the exact UTF-8 bytes of `model.py`.

`renderFingerprint` is SHA256 over a canonical JSON payload containing exactly:

```json
{
  "rendererName": "OPENSEES_FRAME_2D_V1",
  "rendererVersion": "1.0",
  "modelSpecFingerprint": "...",
  "modelSha256": "..."
}
```

Canonical JSON uses sorted keys and compact separators.

`renderId` and output path are intentionally excluded so repeated renders of the same ModelSpec with the same renderer version have the same `renderFingerprint`.

## 14. Atomic Artifact Publication

PR23 must not leave a partial render that resembles a successful artifact.

Required sequence:

1. validate/readiness evaluation completes;
2. complete `model.py` content is constructed in memory;
3. hashes and manifest payload are constructed;
4. a fresh render directory is created under `.femagent/generated-models/`;
5. `model.py` and `render_manifest.json` are written;
6. if any write fails, the new render directory is removed and a stable error is returned/raised.

An existing target render directory is never reused or overwritten.

## 15. Stable Error Semantics

Expected normal engineering blockage is represented as `status = BLOCKED`, not as a generic exception.

Stable renderer error codes cover abnormal transport/artifact failures and invariant violations, including:

```text
OPENSEES_RENDER_SPEC_NOT_OBJECT
OPENSEES_RENDER_MODEL_NOT_READY
OPENSEES_RENDER_UNSUPPORTED_PROFILE
OPENSEES_RENDER_ARTIFACT_EXISTS
OPENSEES_RENDER_WRITE_FAILED
OPENSEES_RENDER_INTERNAL_INVARIANT
```

`MODEL_NOT_READY` is the normal `reason` field in a `BLOCKED` result.

Unexpected faults remain subject to the existing bridge `INTERNAL_ERROR` boundary.

## 16. Bridge Contract

The bridge command is:

```text
modelSpec.renderOpenSees
```

Payload:

```json
{
  "spec": {"...": "EngineeringModelSpec"}
}
```

The existing bridge invocation already has a working-directory/workspace boundary, so workspace must remain the bridge's controlled current workspace rather than becoming an arbitrary path supplied inside the engineering payload.

The bridge delegates directly to the Python renderer and does not reimplement mapping logic.

## 17. TypeScript Transport

`@femagent/fem-tools` adds renderer result types and a transport helper equivalent to:

```typescript
runFemModelSpecRenderOpenSees(cwd, spec, signal?)
```

TypeScript is responsible for transport typing only.

It must not:

- recalculate readiness;
- map constraints to OpenSees DOFs;
- resolve material/section properties;
- generate Python source;
- calculate engineering hashes independently from Python.

## 18. Pi Tool and Permission Boundary

The public Agent tool is:

```text
fem_model_render_opensees
```

Unlike PR21/22 validation tools, PR23 writes artifacts. It is therefore not classified as pure read-only.

The permission boundary is a controlled artifact-write capability, conceptually:

```text
WRITE_ARTIFACT
```

It is strictly weaker than solver execution permission.

The tool may only create a fresh `.femagent/generated-models/<renderId>/` artifact bundle. It may not:

- execute shell commands;
- run OpenSees;
- write arbitrary user-selected paths;
- overwrite workspace source files;
- patch an existing model;
- bypass readiness.

If the current permission-gate implementation does not yet have a reusable named `WRITE_ARTIFACT` class, PR23 may use the nearest existing controlled-write mechanism, but the implementation must preserve this behavior boundary rather than granting solver-run or arbitrary-write capability.

## 19. Agent Workflow

Recommended product workflow after PR23:

```text
1. User supplies/approves engineering facts
2. Agent constructs candidate ModelSpec
3. fem_model_spec_validate
4. fem_model_spec_readiness
5. require READY
6. fem_model_render_opensees
7. require RENDERED
8. fem_model_inspect(generated model.py)
9. fem_solver_preflight(opensees, generated model.py)
10. existing isolated build-only inspection proves realized domain
11. later permission-gated solver workflow may proceed
```

The Agent must not render a `NOT_READY` model merely to see what the solver reports.

## 20. Existing Model Intelligence Compatibility

PR23-generated source must intentionally fit the existing OpenSees Python inspection contract:

- direct `import openseespy.opensees as ops`;
- literal `ops.model(...)` call;
- literal node tags in `ops.node(...)`;
- literal element tags in `ops.element(...)`;
- no loops/comprehensions for topology generation;
- no blocked imports;
- no external file reads;
- no analysis commands.

Expected static inspection for the golden portal-frame render:

```text
classification          = MODEL_CONFIRMED
dynamicGeneration       = false
staticTopology.nodeCount    = expected ModelSpec node count
staticTopology.elementCount = expected ModelSpec element count
staticTopology.nodeTags     = ModelSpec node IDs
staticTopology.elementTags  = ModelSpec element IDs
```

PR23 does not weaken AST safety rules to accommodate generated output. The generated output must satisfy the existing rules.

## 21. Existing Build-Only Compatibility

Where OpenSeesPy is available, the generated `model.py` must pass the existing `OpenSeesBundleAdapter.build_inspect()` path.

Expected build-only evidence includes:

```text
analysisAdvanced = false
nodeTags          = ModelSpec node IDs
elementTags       = ModelSpec element IDs
nodeCoordinates   = rendered coordinates
```

This is the second proof layer after rendering. PR23 itself must not claim realized OpenSees domain correctness before build-only evidence exists.

## 22. TDD / Verification Matrix

### 22.1 Golden Render

Use:

```text
tests/fixtures/model_spec/simple-portal-frame.json
```

Verify:

- readiness is `READY`;
- render status is `RENDERED`;
- `model.py` and manifest exist;
- node and element tag policies are identity;
- initialization is 2D/3DOF;
- one linear geometric transformation exists;
- no analysis/load calls exist.

### 22.2 Determinism

For semantically identical specs with different input collection ordering:

```text
model.py bytes      identical
modelSha256         identical
renderFingerprint   identical
```

`renderId` may differ.

### 22.3 Constraint Mapping

Cover explicit mappings such as:

```text
UX          → (1,0,0)
UY          → (0,1,0)
RZ          → (0,0,1)
UX+UY       → (1,1,0)
UX+UY+RZ    → (1,1,1)
```

### 22.4 Mass Mapping

Verify:

```text
mUX/mUY → ops.mass(nodeId, mUX, mUY, 0.0)
```

and absence of a mass record produces no mass call.

### 22.5 Element Resolution

Verify each element receives `A`, `E`, and `Iz` from its exact referenced section/material and cannot silently borrow another entity's properties.

### 22.6 Blocked Paths

Cover:

- invalid ModelSpec;
- PR22 `NOT_READY`;
- unsupported readiness profile/invariant;
- artifact collision;
- write failure cleanup.

No blocked/failed path may leave a successfully published `model.py` artifact bundle.

### 22.7 Model Intelligence Integration

Immediately inspect a generated golden script with existing `inspect_opensees_python()` and prove `MODEL_CONFIRMED`, literal static topology, and `dynamicGeneration = false`.

### 22.8 Build-Only Integration

Where OpenSeesPy is present, invoke existing `OpenSeesBundleAdapter.build_inspect()` and prove the realized node/element tags match the ModelSpec and that analysis has not advanced.

### 22.9 Bridge / TypeScript / Pi Tests

Follow existing PR21/22 TDD pattern:

- Python core RED/GREEN;
- bridge unknown-command RED/GREEN;
- TypeScript missing-export RED/GREEN;
- Pi registration/permission RED/GREEN;
- final full CI on exact PR head.

## 23. Explicit Non-Goals

PR23 does not implement:

- ANSYS rendering;
- 3D frames;
- truss elements;
- shell or solid elements;
- Timoshenko beams;
- P-Delta or corotational transformations;
- end releases or hinges;
- rigid links/diaphragms;
- distributed loads;
- nodal loads;
- gravity;
- load combinations;
- analysis settings;
- damping;
- response-plan authoring;
- Semantic Role generation;
- solver execution;
- automatic ModelSpec repair;
- automatic meshing;
- section-shape calculation;
- unit conversion;
- arbitrary output paths;
- overwriting generated artifacts.

These belong to later roadmap work.

## 24. Completion Claim Boundary

After PR23, FEMagent may accurately claim:

> FEMagent can deterministically generate an auditable OpenSeesPy model script from a validated and engineering-ready 2D frame EngineeringModelSpec, then pass that generated model into its existing inspection and build-only verification chain.

It must not claim that arbitrary natural-language engineering descriptions can yet be converted into arbitrary finite element models without explicit engineering facts or later controlled authoring/repair capabilities.

## 25. Acceptance Criteria

PR23 is complete only when all of the following are true:

1. a PR22-ready portal-frame ModelSpec renders to a fresh controlled artifact bundle;
2. generated source uses only the approved construction-only OpenSees mapping;
3. IDs are preserved exactly for nodes/elements;
4. source generation is deterministic across equivalent normalized inputs;
5. manifest hashes and `renderFingerprint` are deterministic and verified;
6. `NOT_READY`/invalid inputs cannot publish model artifacts;
7. existing OpenSees static inspection proves literal topology without dynamic generation;
8. existing build-only inspection proves the realized domain where OpenSeesPy is available;
9. no renderer path executes an analysis or solver run;
10. TypeScript and Pi layers delegate to Python engineering truth rather than duplicating it;
11. full repository typecheck/tests/lint/smokes pass on the exact final PR head;
12. the final diff contains no unrelated solver, Result Intelligence, RAG, Semantic Role, or optimization changes.
