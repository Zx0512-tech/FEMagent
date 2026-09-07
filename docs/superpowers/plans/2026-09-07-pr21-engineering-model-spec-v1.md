# PR21 — Engineering Model Specification V1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a deterministic, solver-neutral validator for 2D planar elastic frame `EngineeringModelSpec` objects, with stable issue codes, canonical normalization, a SHA256 fingerprint, bridge/TypeScript transport, and a SAFE Pi validation tool.

**Architecture:** Python `fem_core.model_spec` owns all authoritative engineering validation and fingerprinting. TypeScript only transports typed data through the existing bridge, and Pi exposes one SAFE/read-only `fem_model_spec_validate` tool. PR21 does not render solver files, write models, execute solvers, infer units, infer semantic roles, or consume RAG output as model truth.

**Tech Stack:** Python 3.13, pytest 8.x, Ruff, TypeScript 5.9, Node 22, TypeBox, existing `@femagent/fem-tools` bridge.

**Spec:** `docs/superpowers/specs/2026-09-07-pr21-engineering-model-spec-v1-design.md`

## Global Constraints

- V1 accepts only `dimension="2D"`, `family="FRAME"`, `coordinateSystem="CARTESIAN_XY"`.
- V1 accepts only `ELASTIC_FRAME_2D` + `EULER_BERNOULLI` elements and `LINEAR_ELASTIC` materials.
- Allowed node DOFs are exactly `UX`, `UY`, `RZ`.
- Supported units are exactly: length `m|cm|mm`, force `N|kN`, time `s|ms`.
- Unknown fields are rejected recursively; no permissive extra metadata.
- Invalid ModelSpec content returns a normal validation result with `status="INVALID"`; malformed bridge payloads remain `FemCoreError` failures.
- No hidden unit conversion, geometric tolerance, stability inference, support inference, material defaults, semantic-role inference, file writes, network calls, or solver execution.
- A VALID spec requires at least 2 nodes and at least 1 material, 1 section, and 1 element.
- Canonical fingerprint input uses UTF-8 JSON with `sort_keys=True`, `separators=(",", ":")`, `ensure_ascii=False`, `allow_nan=False`; SHA256 output is lowercase 64-hex.

---

### Task 1: Python ModelSpec validation core

**Files:**
- Create: `fem_core/model_spec/__init__.py`
- Create: `fem_core/model_spec/validator.py`
- Create: `tests/python/test_model_spec.py`
- Create: `tests/fixtures/model_spec/simple-portal-frame.json`

**Interfaces:**
- Produces: `validate_engineering_model_spec(spec: dict[str, Any]) -> dict[str, Any]`
- Result schema: `FEMAGENT_MODEL_SPEC_VALIDATION_V1`

- [ ] **Step 1: Add the Golden Spec fixture**

Create `tests/fixtures/model_spec/simple-portal-frame.json` exactly as a 4-node, 3-element portal frame:

```json
{
  "schemaVersion": "1.0",
  "kind": "engineering_model_spec",
  "dimension": "2D",
  "family": "FRAME",
  "coordinateSystem": "CARTESIAN_XY",
  "units": {"length": "m", "force": "N", "time": "s"},
  "nodes": [
    {"id": 1, "x": 0.0, "y": 0.0},
    {"id": 2, "x": 6.0, "y": 0.0},
    {"id": 3, "x": 6.0, "y": 4.0},
    {"id": 4, "x": 0.0, "y": 4.0}
  ],
  "materials": [
    {"id": 1, "type": "LINEAR_ELASTIC", "youngsModulus": 206000000000.0}
  ],
  "sections": [
    {"id": 1, "type": "FRAME_2D", "area": 0.02, "iz": 0.00008}
  ],
  "elements": [
    {"id": 1, "type": "ELASTIC_FRAME_2D", "formulation": "EULER_BERNOULLI", "nodeI": 1, "nodeJ": 4, "materialId": 1, "sectionId": 1},
    {"id": 2, "type": "ELASTIC_FRAME_2D", "formulation": "EULER_BERNOULLI", "nodeI": 4, "nodeJ": 3, "materialId": 1, "sectionId": 1},
    {"id": 3, "type": "ELASTIC_FRAME_2D", "formulation": "EULER_BERNOULLI", "nodeI": 3, "nodeJ": 2, "materialId": 1, "sectionId": 1}
  ],
  "constraints": [
    {"nodeId": 1, "dofs": ["UX", "UY", "RZ"]},
    {"nodeId": 2, "dofs": ["UX", "UY", "RZ"]}
  ],
  "nodalMasses": []
}
```

- [ ] **Step 2: Write RED tests for import and valid result**

In `tests/python/test_model_spec.py`, load the fixture and assert:

```python
from fem_core.model_spec import validate_engineering_model_spec


def test_valid_portal_frame_returns_normalized_spec_and_fingerprint() -> None:
    spec = json.loads(FIXTURE.read_text(encoding="utf-8"))
    result = validate_engineering_model_spec(spec)
    assert result["schema"] == "FEMAGENT_MODEL_SPEC_VALIDATION_V1"
    assert result["status"] == "VALID"
    assert result["issues"] == []
    assert result["normalizedSpec"] is not None
    assert re.fullmatch(r"[0-9a-f]{64}", result["modelSpecFingerprint"])
```

Run: `python -m pytest tests/python/test_model_spec.py -q`
Expected RED: import/module failure because `fem_core.model_spec` does not exist.

- [ ] **Step 3: Add RED coverage for schema and engineering issues**

Add tests that mutate deep copies of the Golden Spec and assert stable issue codes for:

```text
MODEL_SPEC_INVALID_SCHEMA
MODEL_SPEC_UNKNOWN_FIELD
MODEL_SPEC_EMPTY_COLLECTION
MODEL_SPEC_INVALID_ID
MODEL_SPEC_INVALID_NUMBER
MODEL_SPEC_UNSUPPORTED_DIMENSION
MODEL_SPEC_UNSUPPORTED_FAMILY
MODEL_SPEC_UNSUPPORTED_VALUE
MODEL_SPEC_UNSUPPORTED_UNIT
MODEL_SPEC_DUPLICATE_ID
MODEL_SPEC_ELEMENT_NODE_NOT_FOUND
MODEL_SPEC_ELEMENT_MATERIAL_NOT_FOUND
MODEL_SPEC_ELEMENT_SECTION_NOT_FOUND
MODEL_SPEC_ELEMENT_SELF_CONNECTION
MODEL_SPEC_ZERO_LENGTH_ELEMENT
MODEL_SPEC_NONPOSITIVE_MATERIAL_PROPERTY
MODEL_SPEC_NONPOSITIVE_SECTION_PROPERTY
MODEL_SPEC_CONSTRAINT_NODE_NOT_FOUND
MODEL_SPEC_DUPLICATE_CONSTRAINT
MODEL_SPEC_DUPLICATE_DOF
MODEL_SPEC_MASS_NODE_NOT_FOUND
MODEL_SPEC_DUPLICATE_MASS
MODEL_SPEC_INVALID_MASS
MODEL_SPEC_UNUSED_NODE
```

Every invalid-content test must assert `status == "INVALID"`, `normalizedSpec is None`, and `modelSpecFingerprint is None`. `MODEL_SPEC_UNUSED_NODE` must be WARNING-only and preserve `status == "VALID"` when no ERROR exists.

- [ ] **Step 4: Implement the minimal authoritative validator**

Create `fem_core/model_spec/validator.py` with focused helpers for:

```python
_validate_exact_keys(...)
_validate_positive_int(...)
_validate_finite_number(...)
_issue(severity, code, path, message)
_normalize_spec(...)
_fingerprint(...)
validate_engineering_model_spec(...)
```

Implementation requirements:

- collect all independent detectable ModelSpec content issues where practical;
- never raise for ordinary invalid ModelSpec content;
- use Python `math.isfinite()` and explicitly reject `bool` where numeric/integer values are required;
- preserve original engineering numbers, IDs, and coordinates in normalized output;
- sort entity arrays by ID/nodeId and constraint DOFs in `UX, UY, RZ` order;
- use exact endpoint coordinate equality for zero-length detection;
- do not merge coincident nodes;
- compute a fingerprint only if there are no ERROR issues.

Export the function from `fem_core/model_spec/__init__.py`.

- [ ] **Step 5: Verify Python core GREEN**

Run:

```bash
python -m pytest tests/python/test_model_spec.py -q
python -m ruff check fem_core/model_spec tests/python/test_model_spec.py
```

Expected: all ModelSpec tests pass and Ruff is clean.

- [ ] **Step 6: Commit Task 1**

Commit message:

```text
feat: add deterministic 2D frame ModelSpec validator
```

---

### Task 2: Deterministic normalization and fingerprint regression contract

**Files:**
- Modify: `tests/python/test_model_spec.py`
- Modify: `fem_core/model_spec/validator.py`

**Interfaces:**
- Consumes: `validate_engineering_model_spec()` from Task 1.
- Produces: stable ordering-insensitive `modelSpecFingerprint` contract for PR22 renderers.

- [ ] **Step 1: Write RED determinism tests**

Add tests proving:

```python
assert validate_engineering_model_spec(reordered_spec)["modelSpecFingerprint"] == baseline_fp
assert validate_engineering_model_spec(changed_E)["modelSpecFingerprint"] != baseline_fp
assert validate_engineering_model_spec(changed_node_coordinate)["modelSpecFingerprint"] != baseline_fp
assert validate_engineering_model_spec(changed_units)["modelSpecFingerprint"] != baseline_fp
assert validate_engineering_model_spec(changed_constraint)["modelSpecFingerprint"] != baseline_fp
```

Reorder all top-level entity arrays and reverse constraint DOF input order for the equivalence case.

Run the focused tests and confirm they fail if normalization is incomplete.

- [ ] **Step 2: Complete canonical normalization**

Ensure the implementation serializes the normalized object with:

```python
canonical = json.dumps(
    normalized,
    sort_keys=True,
    separators=(",", ":"),
    ensure_ascii=False,
    allow_nan=False,
).encode("utf-8")
fingerprint = hashlib.sha256(canonical).hexdigest()
```

- [ ] **Step 3: Verify and commit Task 2**

Run `python -m pytest tests/python/test_model_spec.py -q`.

Commit message:

```text
test: lock ModelSpec fingerprint determinism
```

---

### Task 3: Python bridge command

**Files:**
- Modify: `fem_core/bridge.py`
- Modify: `tests/python/test_bridge.py`

**Interfaces:**
- Adds bridge command: `modelSpec.validate`
- Payload: `{ "spec": <object> }`

- [ ] **Step 1: Write RED bridge tests**

Add tests asserting:

```python
response = handle_request(
    {
        "protocol": BRIDGE_PROTOCOL,
        "requestId": "req-model-spec",
        "command": "modelSpec.validate",
        "payload": {"spec": valid_spec},
    },
    workspace=tmp_path,
)
assert response["ok"] is True
assert response["result"]["status"] == "VALID"
```

Also assert a content-invalid object returns `ok is True` + `status == "INVALID"`, while `payload={"spec": "not-an-object"}` returns `ok is False` + `INVALID_ARGUMENT`.

Run: `python -m pytest tests/python/test_bridge.py -q`
Expected RED: `UNKNOWN_COMMAND` for `modelSpec.validate`.

- [ ] **Step 2: Add bridge dispatch**

Import `validate_engineering_model_spec` and add:

```python
elif command == "modelSpec.validate":
    result = validate_engineering_model_spec(_required_object(payload, "spec"))
```

No workspace or solver adapter is passed to the validator.

- [ ] **Step 3: Verify and commit Task 3**

Run:

```bash
python -m pytest tests/python/test_bridge.py tests/python/test_model_spec.py -q
python -m ruff check fem_core tests/python
```

Commit message:

```text
feat: expose ModelSpec validation through FEM bridge
```

---

### Task 4: TypeScript contract and bridge client

**Files:**
- Create: `packages/fem-tools/src/modelSpecTypes.ts`
- Modify: `packages/fem-tools/src/pythonBridge.ts`
- Modify: `packages/fem-tools/src/index.ts`
- Create: `tests/ts/model-spec.test.ts`

**Interfaces:**
- Adds `FemEngineeringModelSpecInput`
- Adds `FemModelSpecValidation`, `FemModelSpecIssue`, `FemModelSpecStatus`
- Adds `runFemModelSpecValidate(cwd, spec, signal?)`

- [ ] **Step 1: Write RED TypeScript bridge test**

Create `tests/ts/model-spec.test.ts` that imports `runFemModelSpecValidate`, reads `tests/fixtures/model_spec/simple-portal-frame.json`, validates it, and asserts:

```ts
assert.equal(report.schema, "FEMAGENT_MODEL_SPEC_VALIDATION_V1");
assert.equal(report.status, "VALID");
assert.match(report.modelSpecFingerprint ?? "", /^[0-9a-f]{64}$/);
```

Also mutate an element node reference and assert `status === "INVALID"` with issue code `MODEL_SPEC_ELEMENT_NODE_NOT_FOUND`.

Run:

```bash
pnpm typecheck
pnpm test:ts
```

Expected RED: missing exported ModelSpec types/client.

- [ ] **Step 2: Add TypeScript transport types**

Define literal unions for the fixed V1 enums while keeping the input object structurally typed. The types must not perform runtime engineering validation.

- [ ] **Step 3: Add bridge client and exports**

Implement:

```ts
export async function runFemModelSpecValidate(
  cwd: string,
  spec: FemEngineeringModelSpecInput,
  signal?: AbortSignal,
): Promise<FemModelSpecValidation> {
  return await runFemCoreRequest<FemModelSpecValidation>(
    cwd,
    "modelSpec.validate",
    { spec },
    { signal },
  );
}
```

Export all public ModelSpec types and the client from `packages/fem-tools/src/index.ts`.

- [ ] **Step 4: Verify and commit Task 4**

Run:

```bash
pnpm typecheck
pnpm test:ts
```

Commit message:

```text
feat: add typed ModelSpec bridge client
```

---

### Task 5: SAFE Pi Tool and Agent registration

**Files:**
- Create: `.pi/extensions/model-spec-tools.ts`
- Modify: `apps/agent/src/main.ts`
- Modify: `tests/ts/model-spec.test.ts`

**Interfaces:**
- Adds SAFE/read-only tool: `fem_model_spec_validate`

- [ ] **Step 1: Add the Pi extension**

Register `fem_model_spec_validate` with a TypeBox schema for the V1 object shape. Prompt guidelines must explicitly state:

```text
- do not invent missing E/A/Iz/support/mass values;
- do not infer units from numeric magnitude;
- do not treat knowledge retrieval as confirmed model truth;
- validation does not mean the structure is stable or solver-ready;
- the tool never writes or executes a model.
```

The execute function must call `runFemModelSpecValidate(ctx.cwd, params.spec, signal)` and return the report unchanged.

- [ ] **Step 2: Register the extension and tool in the agent entrypoint**

Add `.pi/extensions/model-spec-tools.ts` to `additionalExtensionPaths` and add `fem_model_spec_validate` to the agent tool allow-list.

- [ ] **Step 3: Add static registration assertions**

In `tests/ts/model-spec.test.ts`, read the extension and agent entrypoint as text and assert both contain `fem_model_spec_validate`; this prevents accidental omission from the product entrypoint without starting a live LLM session.

- [ ] **Step 4: Verify and commit Task 5**

Run:

```bash
pnpm typecheck
pnpm test:ts
```

Commit message:

```text
feat: expose SAFE ModelSpec validation tool
```

---

### Task 6: Architecture docs, full regression, and PR closeout

**Files:**
- Create: `docs/architecture/engineering-model-spec.md`
- Create: `docs/verification/pr21-engineering-model-spec-v1.md`
- Update: PR #17 body/status after exact-head verification.

**Interfaces:**
- Documents the boundary `EngineeringModelSpec != solver model != Semantic Role Manifest`.

- [ ] **Step 1: Document the production architecture**

Record:

```text
Agent proposed JSON
→ fem_model_spec_validate
→ Python authoritative validation
→ normalizedSpec + modelSpecFingerprint
```

Explicitly document all PR21 non-goals and that PR22 will be the first renderer.

- [ ] **Step 2: Run the complete repository gate**

Use the same checks as `.github/workflows/ci.yml`:

```bash
pnpm typecheck
pnpm test:ts
python -m pytest
python -m ruff check fem_core tests/python examples/ansys/golden_path
python -c "from fem_core.solvers import get_solver_adapter; s=get_solver_adapter('opensees').status(); assert s['available'], s"
python -c "from ansys.mapdl import reader; assert callable(reader.read_binary)"
pnpm fem:health
```

Expected: all pass. Existing third-party NumPy/VTK warnings are acceptable only if they remain warnings and no PR21 code adds new failures.

- [ ] **Step 3: Review the final diff for scope creep**

Confirm there are no changes to:

```text
solver adapters
Result Intelligence numerical semantics
Semantic Role inference rules
RAG provider behavior
load application
ANSYS/OpenSees renderers
```

- [ ] **Step 4: Record exact-head verification**

Write the final commit SHA, GitHub Actions run ID/number, TypeScript pass count, Python pass count, Ruff result, and smoke results in `docs/verification/pr21-engineering-model-spec-v1.md`.

- [ ] **Step 5: Re-run exact-head CI after verification docs are committed**

Only declare implementation complete when CI for the exact final head is `completed / success`.

- [ ] **Step 6: Update Draft PR #17 to implementation-complete status**

Keep the PR unmerged. Mark ready for review only after exact-head CI succeeds.
