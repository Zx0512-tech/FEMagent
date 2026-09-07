# PR21 — Engineering Model Specification V1 Design

## 1. Purpose

PR21 introduces a deterministic, solver-neutral engineering-model specification layer for **2D planar elastic frame models**.

The goal is to create a controlled intermediate representation between natural-language engineering requirements and later solver-specific renderers.

PR21 does **not** generate OpenSees or ANSYS input files and does **not** execute any solver. It establishes the contract that later authoring PRs must consume.

```text
Natural-language requirement
        |
        v
Agent proposes EngineeringModelSpec
        |
        v
fem_model_spec_validate
        |
        v
Python fem_core.model_spec
  strict schema validation
  deterministic engineering consistency checks
  canonical normalization
  modelSpecFingerprint
        |
        v
VALID / INVALID
```

## 2. Architectural decision

PR21 follows the existing FEMagent trust boundary:

- Pi/TypeScript owns agent/tool registration and transport.
- Python `fem_core` owns deterministic engineering logic.
- solver adapters own solver execution.
- Result Intelligence owns numerical-result truth.
- Semantic Roles own explicit engineering-role declarations.
- Knowledge Evidence may provide guidance but cannot become model truth automatically.

Therefore the authoritative PR21 validator lives in Python `fem_core`.

Rejected alternatives:

1. **TypeScript-owned validation** — faster to implement, but conflicts with the repository rule that deterministic engineering logic belongs in Python.
2. **Shared JSON Schema with independent Python/TypeScript validation** — attractive structurally, but creates two validator implementations that can drift. PR21 keeps one authoritative validator and typed TypeScript transport only.

## 3. Scope

V1 supports only:

```text
dimension        = 2D
family           = FRAME
coordinateSystem = CARTESIAN_XY
node DOFs        = UX, UY, RZ
element behavior = elastic 2D frame
formulation      = Euler-Bernoulli
```

Typical supported structures include:

- simply supported or continuous beams represented as planar frames;
- portal frames;
- multistory planar frames;
- simplified 2D bridge longitudinal frames;
- simplified 2D tower/frame systems.

PR21 is intentionally not a general-purpose FEM schema.

## 4. Trust boundary

PR21 describes **intended structural model truth**, not existing solver-file truth.

Existing Model Intelligence continues to answer:

> What solver model currently exists in the workspace?

PR21 answers:

> What deterministic engineering specification does the Agent intend to author later?

These identities must remain distinct.

Likewise, PR21 does not infer engineering semantic roles. Node coordinates, names, positions, supports, or element orientation do not automatically create roles such as `LEFT_SUPPORT`, `TOWER_BASE`, `GIRDER_END`, or `COLUMN`.

Semantic Roles remain explicit and model-bound through the existing Semantic Role Manifest mechanism.

## 5. EngineeringModelSpec V1 contract

A V1 spec has the following top-level shape:

```json
{
  "schemaVersion": "1.0",
  "kind": "engineering_model_spec",
  "dimension": "2D",
  "family": "FRAME",
  "coordinateSystem": "CARTESIAN_XY",
  "units": {
    "length": "m",
    "force": "N",
    "time": "s"
  },
  "nodes": [],
  "materials": [],
  "sections": [],
  "elements": [],
  "constraints": [],
  "nodalMasses": []
}
```

Unknown fields are rejected at every object level. V1 is fail-closed rather than permissive.

For a spec to be `VALID`, V1 additionally requires at least:

- 2 nodes;
- 1 material;
- 1 section;
- 1 frame element.

`constraints` and `nodalMasses` may be empty because PR21 validates model specification consistency, not global structural stability or analysis readiness.

### 5.1 Units

Supported V1 unit declarations:

```text
length: m | cm | mm
force:  N | kN
time:   s | ms
```

The ModelSpec uses a **consistent engineering unit system**. PR21 does not infer, convert, or repair physical units.

Derived quantities follow directly from the declared base units:

```text
Young's modulus      force / length^2
Area                 length^2
Second moment Iz     length^4
Translational mass   force * time^2 / length
```

For example, with `length=mm` and `force=N`, Young's modulus values are interpreted as `N/mm^2`.

The validator must never see `2.06e11` and guess that it means Pa.

### 5.2 Nodes

```json
{
  "id": 1,
  "x": 0.0,
  "y": 0.0
}
```

Rules:

- exactly `id`, `x`, and `y` are accepted;
- `id` is a positive integer;
- `x` and `y` are finite numbers;
- node IDs are unique;
- identical coordinates on different node IDs are not automatically merged.

Coordinate coincidence alone is not an error because intentional duplicate-location nodes may be required by later modeling features.

### 5.3 Materials

V1 supports one material type:

```json
{
  "id": 1,
  "type": "LINEAR_ELASTIC",
  "youngsModulus": 206000000000.0
}
```

Rules:

- exactly `id`, `type`, and `youngsModulus` are accepted;
- material ID is a positive integer and unique;
- `type` must equal `LINEAR_ELASTIC`;
- `youngsModulus` must be finite and strictly positive.

Poisson ratio, density, yielding, plasticity, damping, temperature dependence, and nonlinear material behavior are outside PR21 V1.

### 5.4 Sections

V1 supports one planar-frame section contract:

```json
{
  "id": 1,
  "type": "FRAME_2D",
  "area": 0.02,
  "iz": 0.00008
}
```

Rules:

- exactly `id`, `type`, `area`, and `iz` are accepted;
- section ID is a positive integer and unique;
- `type` must equal `FRAME_2D`;
- `area` must be finite and strictly positive;
- `iz` must be finite and strictly positive.

The section contract is property-based, not shape-based. PR21 does not calculate area or inertia from I-section, box-section, rectangle, or other geometric dimensions.

### 5.5 Elements

V1 supports one element type:

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

Rules:

- exactly `id`, `type`, `formulation`, `nodeI`, `nodeJ`, `materialId`, and `sectionId` are accepted;
- element ID is a positive integer and unique;
- `type` must equal `ELASTIC_FRAME_2D`;
- `formulation` must equal `EULER_BERNOULLI`;
- `nodeI` and `nodeJ` must reference existing nodes;
- `nodeI != nodeJ`;
- referenced material and section must exist;
- realized node coordinates must not produce a zero-length element.

The validator does not classify an element as a beam or column based on orientation.

V1 does not support:

- Timoshenko shear deformation;
- truss behavior;
- releases or hinges;
- rigid offsets;
- rigid links;
- geometric transformations as user-selectable solver concepts;
- material/geometric nonlinearity.

### 5.6 Constraints

```json
{
  "nodeId": 1,
  "dofs": ["UX", "UY", "RZ"]
}
```

Only `nodeId` and `dofs` are accepted.

Allowed DOFs:

```text
UX
UY
RZ
```

Rules:

- referenced node must exist;
- a node may appear in at most one constraint record;
- DOFs may not be duplicated within one record;
- at least one DOF must be listed;
- unknown DOFs are rejected.

Constraint labels such as `FIXED`, `PINNED`, `ROLLER`, or `SUPPORT` are deliberately not stored because they are convenience semantics rather than primitive boundary-condition truth.

### 5.7 Nodal masses

```json
{
  "nodeId": 3,
  "mUX": 1000.0,
  "mUY": 1000.0
}
```

Exactly `nodeId`, `mUX`, and `mUY` are accepted.

Rules:

- referenced node must exist;
- a node may appear in at most one nodal-mass record;
- `mUX` and `mUY` must be finite and nonnegative;
- at least one translational mass component must be greater than zero.

Rotational mass/inertia is outside V1.

## 6. Loads and analysis are intentionally excluded

PR21 does not embed load cases or analysis configuration into `EngineeringModelSpec`.

The ownership boundaries are:

```text
EngineeringModelSpec  = structural model truth
Load Intelligence     = load truth
EngineeringAnalysisSpec (future) = analysis truth
```

External time histories, canonical earthquake CSV files, nodal forces, acceleration histories, and load mappings remain outside PR21.

This prevents ModelSpec from becoming a second load pipeline.

## 7. Agent behavior

The Agent may organize explicit user-provided engineering facts into a proposed ModelSpec, but must not silently invent missing critical parameters.

Example user statement:

> Build a 10 m steel beam.

This does not justify inventing:

- Young's modulus;
- area;
- inertia;
- support conditions;
- mesh/topology;
- nodal masses.

If the user has not supplied a required engineering fact, the Agent must identify the missing field rather than convert common practice into hidden truth.

A future Knowledge Provider may retrieve recommended values or procedures, but retrieved knowledge remains guidance and must not automatically populate unconfirmed ModelSpec truth.

PR21 deliberately exposes **validation**, not deterministic natural-language-to-spec creation.

## 8. Public API

### 8.1 Python core

```python
validate_engineering_model_spec(
    spec: dict[str, Any],
) -> dict[str, Any]
```

The function performs no filesystem I/O, solver execution, network access, or model-file generation.

### 8.2 Bridge command

```text
modelSpec.validate
```

Payload:

```json
{
  "spec": {}
}
```

A non-object `spec` is a bridge/request contract failure and raises the existing stable `FemCoreError` path.

A syntactically valid JSON object that is not a valid EngineeringModelSpec returns a normal successful bridge envelope whose result status is `INVALID`.

### 8.3 TypeScript client

```ts
runFemModelSpecValidate(
  cwd: string,
  spec: FemEngineeringModelSpecInput,
  signal?: AbortSignal,
): Promise<FemModelSpecValidation>
```

TypeScript provides transport typing but is not the authoritative validator.

### 8.4 Pi tool

PR21 adds a SAFE/read-only Pi tool:

```text
fem_model_spec_validate
```

The tool:

- accepts only a ModelSpec JSON object;
- does not accept solver commands;
- does not accept shell/APDL/Python source;
- does not accept load paths;
- does not write model files;
- does not execute a solver.

## 9. Validation result contract

Schema:

```text
FEMAGENT_MODEL_SPEC_VALIDATION_V1
```

Valid example:

```json
{
  "schema": "FEMAGENT_MODEL_SPEC_VALIDATION_V1",
  "status": "VALID",
  "issues": [],
  "normalizedSpec": {},
  "modelSpecFingerprint": "<64-hex sha256>"
}
```

Invalid example:

```json
{
  "schema": "FEMAGENT_MODEL_SPEC_VALIDATION_V1",
  "status": "INVALID",
  "issues": [
    {
      "severity": "ERROR",
      "code": "MODEL_SPEC_ELEMENT_NODE_NOT_FOUND",
      "path": "elements[3].nodeJ",
      "message": "Element 4 references missing node 99"
    }
  ],
  "normalizedSpec": null,
  "modelSpecFingerprint": null
}
```

Status values:

```text
VALID
INVALID
```

Issue severity values:

```text
ERROR
WARNING
```

Rules:

- any ERROR => `INVALID`, no normalized spec, no fingerprint;
- warnings alone do not invalidate the spec;
- V1 does not introduce `PARTIAL`, `READY`, or `PASS/FAIL` engineering judgments.

## 10. Validation philosophy

The validator should return all deterministically detectable independent issues in one call where practical, rather than failing after the first ModelSpec-content issue.

This is important for future controlled repair because stable issue codes can be mapped to explicit ModelSpec patches.

Bridge/protocol failures remain hard errors through the existing `FemCoreError` mechanism.

## 11. Stable ModelSpec issue codes

### 11.1 Schema and field issues

```text
MODEL_SPEC_INVALID_SCHEMA
MODEL_SPEC_UNKNOWN_FIELD
MODEL_SPEC_EMPTY_COLLECTION
MODEL_SPEC_INVALID_ID
MODEL_SPEC_INVALID_NUMBER
MODEL_SPEC_UNSUPPORTED_VALUE
```

### 11.2 Reference issues

```text
MODEL_SPEC_ELEMENT_NODE_NOT_FOUND
MODEL_SPEC_ELEMENT_MATERIAL_NOT_FOUND
MODEL_SPEC_ELEMENT_SECTION_NOT_FOUND
MODEL_SPEC_CONSTRAINT_NODE_NOT_FOUND
MODEL_SPEC_MASS_NODE_NOT_FOUND
```

### 11.3 Engineering consistency issues

```text
MODEL_SPEC_DUPLICATE_ID
MODEL_SPEC_ELEMENT_SELF_CONNECTION
MODEL_SPEC_ZERO_LENGTH_ELEMENT
MODEL_SPEC_NONPOSITIVE_MATERIAL_PROPERTY
MODEL_SPEC_NONPOSITIVE_SECTION_PROPERTY
MODEL_SPEC_DUPLICATE_CONSTRAINT
MODEL_SPEC_DUPLICATE_DOF
MODEL_SPEC_DUPLICATE_MASS
MODEL_SPEC_INVALID_MASS
```

### 11.4 V1 scope/compatibility issues

```text
MODEL_SPEC_UNSUPPORTED_DIMENSION
MODEL_SPEC_UNSUPPORTED_FAMILY
MODEL_SPEC_UNSUPPORTED_ELEMENT_TYPE
MODEL_SPEC_UNSUPPORTED_FORMULATION
MODEL_SPEC_UNSUPPORTED_UNIT
```

### 11.5 Warning-level issues

```text
MODEL_SPEC_UNUSED_NODE
```

An unused node is warning-only. PR21 does not assume that every explicitly declared node must already participate in a frame element.

## 12. Deterministic checks

V1 must validate at least:

### Top-level/schema

- exact supported schema version and kind;
- exact supported dimension/family/coordinate system;
- required fields present;
- unknown fields rejected recursively;
- required arrays are arrays;
- `nodes` contains at least 2 entries;
- `materials`, `sections`, and `elements` each contain at least 1 entry.

### IDs

- positive integer IDs;
- uniqueness within each ID namespace.

### Numeric fields

- all engineering scalars finite;
- positive/nonnegative rules as defined by each object type.

### References

- element node/material/section references exist;
- constraint node references exist;
- nodal-mass node references exist.

### Connectivity

- `nodeI != nodeJ`;
- referenced endpoint coordinates do not produce zero length.

PR21 uses exact coordinate equality for zero-length detection. It does not introduce a hidden geometric tolerance or alter coordinates.

### Constraints

- only `UX`, `UY`, `RZ`;
- no duplicate constraint record for a node;
- no duplicate DOF in one record.

### Masses

- nonnegative translational masses;
- at least one positive component;
- no duplicate nodal-mass record for a node.

### Usage warning

- nodes referenced by no element produce `MODEL_SPEC_UNUSED_NODE` warning only.

## 13. Checks PR21 intentionally does not perform

PR21 must not pretend to prove structural adequacy beyond the explicit deterministic contract.

It does not:

- determine whether the global structure is stable;
- perform rank/singularity analysis;
- determine whether supports are sufficient;
- infer support type;
- infer beam/column semantics;
- infer gravity direction;
- merge coincident nodes;
- infer or convert units;
- calculate section properties from shape dimensions;
- apply hidden geometric tolerances;
- execute a solver to validate the structure.

These omissions are deliberate trust boundaries, not missing implementation details.

## 14. Canonical normalization

Only a `VALID` spec obtains a normalized representation.

Normalization is deterministic and engineering-preserving:

- nodes sorted by `id`;
- materials sorted by `id`;
- sections sorted by `id`;
- elements sorted by `id`;
- constraints sorted by `nodeId`;
- nodal masses sorted by `nodeId`;
- constraint DOFs ordered canonically as `UX`, `UY`, `RZ`;
- no IDs are renumbered;
- no engineering values are defaulted or converted.

For fingerprint serialization, the normalized Python object is encoded as UTF-8 JSON with these exact settings:

```python
json.dumps(
    normalized_spec,
    sort_keys=True,
    separators=(",", ":"),
    ensure_ascii=False,
    allow_nan=False,
)
```

This removes ambiguity about object-key order and whitespace. The validator must already have rejected non-finite numbers before this step.

Normalization must not:

- renumber IDs;
- change coordinates;
- merge entities;
- rewrite material/section values;
- add defaults for engineering properties.

## 15. ModelSpec fingerprint

For a `VALID` spec:

```text
canonicalBytes = UTF8(canonical JSON from section 14)
modelSpecFingerprint = SHA256(canonicalBytes)
```

The fingerprint is 64 lowercase hexadecimal characters.

Semantically identical specs that differ only in list ordering must yield the same fingerprint after normalization.

Examples that must **not** change the fingerprint when all engineering content is otherwise identical:

```text
nodes [2, 1] -> [1, 2]
materials [3, 1] -> [1, 3]
constraint DOFs [RZ, UX, UY] -> [UX, UY, RZ]
```

Engineering changes that must change the fingerprint include:

- node coordinates;
- unit declaration;
- material E;
- section A or Iz;
- element connectivity;
- material/section assignment;
- constraints;
- nodal masses.

The ModelSpec fingerprint is **not** a Model Bundle fingerprint.

Future renderer provenance should preserve both identities:

```text
ModelSpec fingerprint
      |
      v
solver renderer
      |
      v
Solver Model Bundle fingerprint
```

## 16. Golden fixture

PR21 should add a deterministic fixture:

```text
tests/fixtures/model_spec/simple-portal-frame.json
```

The fixture represents a simple planar portal frame:

```text
(4)------(3)
 |        |
 |        |
(1)      (2)
```

Suggested properties:

- four nodes;
- two columns and one beam;
- one linear elastic material;
- one planar frame section;
- fixed base DOFs at nodes 1 and 2;
- no required nodal mass unless explicitly included by the fixture contract.

This fixture becomes the canonical first input for a future OpenSees renderer PR.

## 17. Test strategy

PR21 follows RED -> GREEN TDD.

### 17.1 Python schema tests

At minimum:

- missing required top-level field;
- empty required collection;
- unknown top-level and nested fields;
- invalid primitive type;
- unsupported schema/kind;
- unsupported dimension/family/coordinate system;
- unsupported units;
- invalid IDs and non-finite numbers.

### 17.2 Python reference/consistency tests

At minimum:

- duplicate IDs;
- missing element node;
- missing material;
- missing section;
- self-connected element;
- zero-length element;
- invalid material/section properties;
- missing constraint node;
- duplicate constraint;
- duplicate DOF;
- missing mass node;
- duplicate mass;
- negative/all-zero mass;
- unused node warning.

### 17.3 Determinism tests

At minimum:

- array-order differences normalize identically;
- DOF-order differences normalize identically;
- equivalent specs produce identical fingerprints;
- coordinate change changes fingerprint;
- unit change changes fingerprint;
- material change changes fingerprint;
- section change changes fingerprint;
- connectivity change changes fingerprint;
- constraint change changes fingerprint;
- mass change changes fingerprint.

### 17.4 Bridge/TypeScript tests

Tests must prove:

```text
TypeScript
  -> modelSpec.validate
  -> Python core
  -> strict validation response
```

And specifically:

- invalid ModelSpec content returns a successful bridge envelope with `status=INVALID`;
- non-object `spec` remains a hard stable bridge/core error;
- the public TypeScript result types match the Python contract.

### 17.5 Pi tool tests

The SAFE tool must be shown to:

- forward only the ModelSpec object;
- expose validation issues and fingerprint;
- perform no solver run;
- perform no file write;
- perform no network retrieval.

## 18. Proposed repository changes

Expected implementation locations:

```text
fem_core/model_spec/
  __init__.py
  validator.py
  normalization.py
  fingerprint.py

fem_core/bridge.py

packages/fem-tools/src/modelSpecTypes.ts
packages/fem-tools/src/pythonBridge.ts
packages/fem-tools/src/index.ts

.pi/extensions/model-authoring-tools.ts
apps/agent/src/main.ts

tests/python/test_model_spec.py
tests/ts/model-spec.test.ts
tests/fixtures/model_spec/simple-portal-frame.json

docs/architecture/engineering-model-spec.md
docs/verification/pr21-engineering-model-spec-v1.md
```

Exact file names may be adjusted during implementation if existing repository patterns require it, but ownership boundaries must not change.

## 19. PR21 non-goals

PR21 explicitly excludes:

- `fem_model_spec_create` as a deterministic engineering tool;
- OpenSees renderer;
- ANSYS/APDL renderer;
- model file persistence;
- solver execution;
- build-only solver preflight;
- loads or load mapping;
- analysis settings;
- automatic meshing;
- geometry generation from CAD/BIM;
- 3D frames;
- truss, shell, or solid models;
- nonlinear materials;
- plastic hinges;
- end releases;
- rigid links/offsets;
- contacts;
- automatic support inference;
- automatic material defaults;
- automatic Semantic Role generation;
- RAG lookup;
- ModelSpec patch/repair;
- optimization;
- UI/reporting changes.

## 20. Acceptance criteria

PR21 is complete only when all of the following are true:

1. A stable 2D `FRAME` EngineeringModelSpec V1 contract exists.
2. Python `fem_core` is the sole authoritative engineering validator.
3. Schema validation is strict and unknown fields fail closed recursively.
4. Required V1 structural collections cannot be empty.
5. Deterministic ID, property, connectivity, and cross-reference checks are implemented.
6. Units are explicit and never guessed or converted.
7. A valid spec produces a canonical normalized spec.
8. A valid spec produces a deterministic SHA256 ModelSpec fingerprint using the canonical serialization in section 14.
9. Equivalent engineering content with only ordering differences produces the same fingerprint.
10. Engineering-content changes alter the fingerprint.
11. Invalid ModelSpec content returns structured validation issues rather than crashing the bridge.
12. `fem_model_spec_validate` is exposed as a SAFE/read-only Pi tool.
13. No solver model is generated.
14. No solver is executed.
15. Existing Model Intelligence, Load Intelligence, Semantic Roles, Result Intelligence, Evidence, and Knowledge trust boundaries remain unchanged.
16. Full repository CI passes on the exact final PR head.

## 21. Forward path

PR21 is the prerequisite for controlled model authoring.

The intended next sequence is:

```text
PR21
EngineeringModelSpec + validation + fingerprint
        |
        v
PR22
OpenSees 2D Frame renderer
        |
        v
Model Intelligence
        |
        v
OpenSees build-only preflight
        |
        v
later ANSYS renderer / controlled repair
```

The key design principle is:

> The Agent may propose a model specification, but deterministic engineering code decides whether that specification is structurally well-formed enough to enter the authoring pipeline.
