# Engineering Model Specification V1

## Purpose

PR21 introduces `EngineeringModelSpec` as the first controlled model-authoring intermediate representation in FEMagent.

The ModelSpec describes **intended engineering model truth** before any solver-specific file exists. It is deliberately separate from Model Intelligence, which inspects solver-native models that already exist in the workspace.

```text
Natural-language requirement
        |
        v
Agent proposes explicit ModelSpec JSON
        |
        v
fem_model_spec_validate
        |
        v
TypeScript/Python bridge
        |
        v
fem_core.model_spec
  authoritative deterministic validation
        |
        +--> INVALID + stable issues
        |
        `--> VALID + normalizedSpec + modelSpecFingerprint
```

PR21 stops at this boundary. It does not render, write, build, or solve a model.

## Ownership boundary

FEMagent keeps model-authoring responsibilities separated:

```text
EngineeringModelSpec
  intended structural model truth

Model Intelligence
  existing solver-model inspection truth

Load Intelligence
  load-source and canonical-load truth

Semantic Roles
  explicit engineering-role declarations

Solver Adapters
  solver preflight and execution

Result Intelligence
  numerical result truth
```

A ModelSpec is not a solver model, and a `modelSpecFingerprint` is not a Model Bundle fingerprint.

Later renderers may preserve both identities:

```text
EngineeringModelSpec
  modelSpecFingerprint
        |
        v
solver-specific renderer
        |
        v
OpenSees / ANSYS model bundle
  bundleFingerprint
```

The two fingerprints answer different questions and must never be substituted for one another.

## V1 supported model family

V1 intentionally supports one narrow, auditable family:

```text
dimension        = 2D
family           = FRAME
coordinateSystem = CARTESIAN_XY
node DOFs        = UX, UY, RZ
material         = LINEAR_ELASTIC
section          = FRAME_2D
element          = ELASTIC_FRAME_2D
formulation      = EULER_BERNOULLI
```

This represents planar elastic frame behavior with axial deformation and Euler-Bernoulli bending.

Typical V1 uses include beams represented in a planar frame domain, portal frames, multistory planar frames, and simplified bridge/tower longitudinal frame models.

V1 is not a general FEM schema.

## ModelSpec contract

The authoritative V1 object contains exactly:

```text
schemaVersion
kind
dimension
family
coordinateSystem
units
nodes[]
materials[]
sections[]
elements[]
constraints[]
nodalMasses[]
```

Unknown fields are rejected recursively.

A structurally meaningful V1 input requires at least:

- 2 nodes;
- 1 material;
- 1 section;
- 1 frame element.

Constraints and nodal masses may be empty.

### Units

Supported base units are:

```text
length: m | cm | mm
force:  N | kN
time:   s | ms
```

The spec uses one explicit consistent engineering unit system. Derived quantities are interpreted from those declarations:

```text
Young's modulus    force / length^2
Area               length^2
Iz                 length^4
Translational mass force * time^2 / length
```

PR21 performs no unit inference and no unit conversion. Numeric magnitude is never used to guess units.

### Nodes

A node contains a positive integer `id` and finite `x`, `y` coordinates.

Coincident coordinates on different node IDs are not automatically merged. Entity identity is explicit.

### Materials

V1 material:

```json
{
  "id": 1,
  "type": "LINEAR_ELASTIC",
  "youngsModulus": 206000000000.0
}
```

`youngsModulus` must be finite and strictly positive.

### Sections

V1 section:

```json
{
  "id": 1,
  "type": "FRAME_2D",
  "area": 0.02,
  "iz": 0.00008
}
```

`area` and `iz` must be finite and strictly positive. The section is property-based; PR21 does not derive properties from named section shapes.

### Elements

V1 element:

```json
{
  "id": 1,
  "type": "ELASTIC_FRAME_2D",
  "formulation": "EULER_BERNOULLI",
  "nodeI": 1,
  "nodeJ": 2,
  "materialId": 1,
  "sectionId": 1
}
```

The validator requires all references to exist, endpoint IDs to differ, and endpoint coordinates not to be exactly coincident.

No hidden geometric tolerance is introduced.

### Constraints

Constraints express primitive restrained DOFs only:

```text
UX
UY
RZ
```

Terms such as `fixed`, `pinned`, `roller`, `support`, `left support`, or `tower base` are not stored as inferred semantics.

### Nodal masses

V1 supports nonnegative translational masses `mUX` and `mUY`, with at least one positive component in each declared mass record. Rotational inertia is outside V1.

## Validation semantics

Public Python entrypoint:

```python
validate_engineering_model_spec(spec)
```

Bridge command:

```text
modelSpec.validate
```

TypeScript client:

```text
runFemModelSpecValidate(...)
```

Pi tool:

```text
fem_model_spec_validate
```

The Python implementation is the only authoritative engineering validator.

TypeScript types and TypeBox parameters describe the V1 transport shape. They do not duplicate or replace engineering consistency checks.

### ModelSpec-content failures

A JSON object that violates ModelSpec rules returns a normal bridge success envelope with:

```json
{
  "schema": "FEMAGENT_MODEL_SPEC_VALIDATION_V1",
  "status": "INVALID",
  "issues": [],
  "normalizedSpec": null,
  "modelSpecFingerprint": null
}
```

Stable issue codes identify deterministic repair targets such as missing references, duplicate IDs, invalid units, nonpositive properties, duplicate constraints, and zero-length elements.

### Bridge-contract failures

A non-object `spec` is not a ModelSpec-content issue. It violates the bridge command contract and uses the existing `INVALID_ARGUMENT` error path.

This distinction preserves future repair behavior:

```text
valid bridge request + invalid engineering content
  -> inspect issues and propose controlled repair later

invalid bridge request
  -> hard request error
```

## Warnings versus errors

Any validation issue with severity `ERROR` makes the result `INVALID` and prevents normalization/fingerprinting.

Warning-only results remain `VALID`.

V1 warning example:

```text
MODEL_SPEC_UNUSED_NODE
```

An unused declared node is not automatically deleted or treated as invalid, because future controlled modeling features may use explicitly declared nodes for constraints, masses, couplings, or later additions.

## Canonical normalization

Only VALID specs are normalized.

Normalization performs engineering-preserving ordering only:

- nodes/materials/sections/elements by `id`;
- constraints/nodal masses by `nodeId`;
- constraint DOFs in `UX`, `UY`, `RZ` order.

It does not:

- renumber entities;
- change coordinates;
- change physical values;
- merge coincident nodes;
- add defaults;
- convert units.

## ModelSpec identity

A VALID normalized spec receives:

```text
modelSpecFingerprint = SHA256(canonical normalized JSON)
```

Canonical JSON uses:

```python
json.dumps(
    normalized,
    sort_keys=True,
    separators=(",", ":"),
    ensure_ascii=False,
    allow_nan=False,
)
```

As a result, list-order and constraint-DOF-order differences that do not change engineering content produce the same fingerprint.

Changes to coordinates, material properties, section properties, connectivity, constraints, nodal masses, or unit declarations change the fingerprint.

## Agent trust rules

The Agent may organize explicit engineering facts into a proposed ModelSpec. It must not invent missing critical facts merely to satisfy validation.

For example, `build a 10 m steel beam` does not establish:

- Young's modulus;
- section area;
- section inertia;
- support constraints;
- model topology/mesh intent;
- nodal masses.

Knowledge retrieval can support a recommendation or explain engineering practice, but retrieved values do not become confirmed ModelSpec truth automatically.

A VALID result means only:

> The supplied V1 ModelSpec satisfies the deterministic PR21 contract.

It does not mean:

- the structure is globally stable;
- restraints are sufficient;
- the design is adequate;
- the model is solver-ready;
- numerical results are correct;
- a solver has validated the topology.

## Semantic-role boundary

PR21 does not create or infer Semantic Roles.

Coordinates, orientation, constraints, node IDs, element IDs, or Agent reasoning do not create roles such as:

```text
SUPPORT
COLUMN
GIRDER_END
TOWER_BASE
MIDSPAN
```

Those remain explicit declarations governed by the existing Semantic Role Manifest and Model Bundle identity rules.

## Solver boundary

`fem_model_spec_validate` is SAFE/read-only.

It performs no:

- OpenSees invocation;
- ANSYS invocation;
- build-only preflight;
- model-file write;
- shell execution;
- network access.

The dedicated Pi extension imports the ModelSpec bridge client and does not import solver-run functionality.

## PR21 non-goals

PR21 does not add:

- OpenSees renderer;
- ANSYS APDL renderer;
- solver-model generation;
- model-file persistence;
- solver preflight or execution;
- loads or load cases;
- analysis settings;
- automatic meshing;
- CAD/BIM geometry;
- 3D frame behavior;
- truss, shell, solid, or contact elements;
- Timoshenko shear deformation;
- plastic hinges, releases, rigid links, or nonlinear materials;
- automatic material/section defaults;
- automatic support inference;
- structural stability/rank analysis;
- unit inference/conversion;
- Semantic Role generation;
- RAG-to-model automatic promotion;
- ModelSpec patch/repair.

These boundaries keep PR21 auditable and make the next renderer layer independently testable.

## Next authoring boundary

The first renderer should consume only a VALID ModelSpec and preserve the source `modelSpecFingerprint` as provenance:

```text
VALID EngineeringModelSpec
        |
        v
OpenSees renderer
        |
        v
model.py
        |
        v
Model Intelligence
        |
        v
build-only preflight
```

A failed ModelSpec validation must block rendering rather than being bypassed with ad-hoc solver code.
