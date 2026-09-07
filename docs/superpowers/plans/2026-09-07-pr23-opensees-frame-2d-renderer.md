# PR23 — OpenSees Frame 2D Renderer Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Deterministically render a PR22-ready 2D elastic-frame `EngineeringModelSpec` into an auditable OpenSeesPy `model.py` plus manifest under FEMagent's controlled generated-model artifact directory, then expose the path through the existing Python bridge, TypeScript client, Pi Agent tool, Model Intelligence, and build-only verification chain.

**Architecture:** Python `fem_core` remains the only engineering/rendering authority. The renderer re-runs PR22 readiness, translates only the fixed `FRAME_2D_ELASTIC_READINESS_V1` profile into literal construction-only OpenSeesPy calls, atomically publishes artifacts below `.femagent/generated-models/<renderId>/`, and returns deterministic hashes. TypeScript and Pi remain transport/tool surfaces only; existing AST inspection and OpenSees build-only remain the post-render proof layers.

**Tech Stack:** Python 3.11+, pytest, Ruff, TypeScript, Node test runner, TypeBox, existing `femagent.bridge/v1`, existing OpenSeesPy AST/build-only infrastructure.

**Spec:** `docs/superpowers/specs/2026-09-07-pr23-opensees-frame-2d-renderer-design.md`

## Global Constraints

- V1 supports only `2D / FRAME / CARTESIAN_XY / ELASTIC_FRAME_2D / EULER_BERNOULLI` and readiness profile `FRAME_2D_ELASTIC_READINESS_V1`.
- Renderer MUST call `evaluate_engineering_model_readiness(spec)` itself and proceed only for `READY`.
- Renderer MUST NOT infer or modify E, A, Iz, constraints, masses, topology, units, support semantics, loads, analysis settings, damping, or Semantic Roles.
- Renderer MUST NOT perform unit conversion.
- Generated source MUST contain literal construction calls only and MUST NOT contain analysis/load calls.
- Node and element tags are identity mappings from ModelSpec IDs.
- `UX/UY/RZ` map to OpenSees DOFs `1/2/3`; mass maps to `(mUX, mUY, 0.0)`.
- V1 uses exactly one `ops.geomTransf("Linear", 1)` and `elasticBeamColumn` with resolved A/E/Iz.
- Source ordering and numeric rendering MUST be deterministic; `-0.0` renders as `0.0`; other floats use Python `repr(float(value))`.
- Generated artifacts may be created only under `.femagent/generated-models/render_<16 hex>/`; no user output path is accepted and no existing directory is overwritten.
- Same ModelSpec + renderer version MUST produce identical `model.py` bytes, `modelSha256`, and `renderFingerprint`; `renderId` may differ.
- The renderer tool is a controlled internal artifact write, not solver execution; PR23 MUST NOT broaden `permission-gate.ts` or run a solver.
- Render success means `RENDERED`, not realized solver-domain correctness; existing Model Intelligence and build-only remain required proof layers.

---

### Task 1: Python Renderer Core and Atomic Artifact Contract

**Files:**
- Create: `fem_core/model_spec/opensees_renderer.py`
- Modify: `fem_core/model_spec/__init__.py`
- Test: `tests/python/test_opensees_model_renderer.py`

**Interfaces:**
- Consumes: `evaluate_engineering_model_readiness(spec: dict[str, Any]) -> dict[str, Any]` and the PR21 normalized spec available by re-validating the ready input.
- Produces: `render_opensees_frame_2d(workspace: Path, spec: dict[str, Any]) -> dict[str, Any]` with schema `FEMAGENT_OPENSEES_RENDER_V1` and statuses `RENDERED | BLOCKED`.

- [ ] **Step 1: Write RED tests for the golden render and exact source mapping**

Create tests that load `tests/fixtures/model_spec/simple-portal-frame.json`, render into `tmp_path`, then assert:

```python
report["schema"] == "FEMAGENT_OPENSEES_RENDER_V1"
report["status"] == "RENDERED"
report["renderer"] == {"name": "OPENSEES_FRAME_2D_V1", "version": "1.0"}
report["input"]["readinessProfile"] == "FRAME_2D_ELASTIC_READINESS_V1"
report["mapping"]["nodeTagPolicy"] == "IDENTITY"
report["mapping"]["elementTagPolicy"] == "IDENTITY"
report["mapping"]["geomTransfTag"] == 1
```

Read the generated `model.py` and assert it contains:

```text
import openseespy.opensees as ops
ops.wipe()
ops.model("basic", "-ndm", 2, "-ndf", 3)
ops.geomTransf("Linear", 1)
```

Assert literal `ops.node`, `ops.fix`, `ops.mass` where present, and `ops.element("elasticBeamColumn", ...)` commands preserve ModelSpec IDs and resolve the exact referenced E/A/Iz. Assert forbidden analysis/load tokens (`timeSeries`, `pattern`, `analysis`, `analyze`, `eigen`, etc.) are absent.

- [ ] **Step 2: Add RED tests for blocking, determinism, numeric formatting, and cleanup**

Cover:

```python
# invalid spec -> BLOCKED, artifacts is None, no generated-model directory published
# PR22 NOT_READY -> BLOCKED with reason MODEL_NOT_READY
# reordered semantically identical collections -> identical model.py bytes/hash/renderFingerprint
# repeated render -> different renderId allowed, same deterministic content/hash/fingerprint
# -0.0 source literal -> 0.0
# exact constraint DOF vectors and mass third component 0.0
```

Monkeypatch the internal file-write helper to fail after render directory creation and assert the new render directory is removed and a stable `FemCoreError("OPENSEES_RENDER_WRITE_FAILED", ...)` escapes.

Run:

```bash
pytest tests/python/test_opensees_model_renderer.py -q
```

Expected RED: import/module/function missing.

- [ ] **Step 3: Implement minimal deterministic renderer**

Create `fem_core/model_spec/opensees_renderer.py` with focused helpers:

```python
RENDER_SCHEMA = "FEMAGENT_OPENSEES_RENDER_V1"
RENDERER_NAME = "OPENSEES_FRAME_2D_V1"
RENDERER_VERSION = "1.0"
SUPPORTED_READINESS_PROFILE = "FRAME_2D_ELASTIC_READINESS_V1"

def render_opensees_frame_2d(workspace: Path, spec: dict[str, Any]) -> dict[str, Any]: ...
```

Implementation requirements:

```text
1. Reject non-dict input with OPENSEES_RENDER_SPEC_NOT_OBJECT.
2. Re-run evaluate_engineering_model_readiness(spec).
3. Return BLOCKED with embedded readiness and no artifacts for INVALID_SPEC/NOT_READY.
4. Require the exact supported readiness profile.
5. Use the normalized spec returned by validate_engineering_model_spec(spec) after READY.
6. Build complete source bytes in memory before filesystem publication.
7. Sort nodes/elements/constraints/masses explicitly.
8. Resolve referenced material and section by exact ID.
9. Map constraints UX/UY/RZ -> 1/0 vector and masses -> mUX,mUY,0.0.
10. Emit one Linear geomTransf and literal elasticBeamColumn calls.
11. Render numbers via one canonical helper: -0.0 => 0.0, otherwise repr(float(value)).
12. Compute modelSha256 from UTF-8 bytes.
13. Compute renderFingerprint from canonical JSON of rendererName/version/modelSpecFingerprint/modelSha256.
14. Create a fresh render_<16hex> directory below workspace/.femagent/generated-models.
15. Write model.py and render_manifest.json; remove the fresh directory on any failed publication.
16. Never accept/output an arbitrary destination parameter.
```

Export `render_opensees_frame_2d` from `fem_core/model_spec/__init__.py`.

- [ ] **Step 4: Run renderer tests and full Python suite**

```bash
pytest tests/python/test_opensees_model_renderer.py -q
pytest tests/python -q
ruff check fem_core tests/python
```

Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add fem_core/model_spec/opensees_renderer.py fem_core/model_spec/__init__.py tests/python/test_opensees_model_renderer.py
git commit -m "feat: add deterministic OpenSees frame renderer"
```

---

### Task 2: Existing Model Intelligence and Build-Only Compatibility

**Files:**
- Modify: `tests/python/test_opensees_model_renderer.py`
- Do not modify existing OpenSees inspector/worker unless a genuine compatibility bug is proven by the test.

**Interfaces:**
- Consumes: `render_opensees_frame_2d`, `inspect_opensees_python`, `OpenSeesBundleAdapter.build_inspect`.
- Produces: integration proof that rendered source fits existing trust layers without weakening them.

- [ ] **Step 1: Add RED/green integration assertions against the existing AST inspector**

After rendering the golden fixture, pass the returned `artifacts.modelPath` to `inspect_opensees_python(tmp_path, model_path)` and assert:

```python
inspection["classification"] == "MODEL_CONFIRMED"
inspection["dynamicGeneration"] is False
inspection["staticTopology"]["nodeTags"] == sorted(expected_node_ids)
inspection["staticTopology"]["elementTags"] == sorted(expected_element_ids)
inspection["staticTopology"]["nodeCount"] == len(expected_node_ids)
inspection["staticTopology"]["elementCount"] == len(expected_element_ids)
inspection["safetyFindings"] == []
```

- [ ] **Step 2: Add build-only integration where OpenSeesPy is available**

Use the existing adapter status to skip only when OpenSeesPy is genuinely unavailable. Otherwise:

```python
build = OpenSeesBundleAdapter().build_inspect(tmp_path, model_path=model_path)
assert build["analysisAdvanced"] is False
assert build["nodeTags"] == sorted(expected_node_ids)
assert build["elementTags"] == sorted(expected_element_ids)
```

Also compare returned node coordinates to the ModelSpec coordinates.

- [ ] **Step 3: Run integration tests**

```bash
pytest tests/python/test_opensees_model_renderer.py -q
```

Expected: PASS without changing existing AST/build-only rules.

- [ ] **Step 4: Commit**

```bash
git add tests/python/test_opensees_model_renderer.py
git commit -m "test: verify rendered OpenSees model trust chain"
```

---

### Task 3: Python Bridge Contract

**Files:**
- Modify: `fem_core/bridge.py`
- Create or modify: `tests/python/test_model_spec_render_bridge.py`

**Interfaces:**
- Consumes: `render_opensees_frame_2d(workspace, spec)`.
- Produces bridge command `modelSpec.renderOpenSees` with payload `{ "spec": {...} }`.

- [ ] **Step 1: Write bridge RED tests**

Cover:

```python
# READY fixture -> success envelope with result.status == RENDERED
# NOT_READY fixture -> success envelope with result.status == BLOCKED
# non-object spec -> stable INVALID_ARGUMENT from _required_object
# generated artifact path remains workspace-relative under .femagent/generated-models/
```

Run:

```bash
pytest tests/python/test_model_spec_render_bridge.py -q
```

Expected RED: `UNKNOWN_COMMAND` for `modelSpec.renderOpenSees`.

- [ ] **Step 2: Implement minimal bridge registration**

In `fem_core/bridge.py` import `render_opensees_frame_2d` and add adjacent to PR21/22 commands:

```python
elif command == "modelSpec.renderOpenSees":
    result = render_opensees_frame_2d(workspace, _required_object(payload, "spec"))
```

No new workspace path is accepted in payload.

- [ ] **Step 3: Run bridge and full Python tests**

```bash
pytest tests/python/test_model_spec_render_bridge.py -q
pytest tests/python -q
ruff check fem_core tests/python
```

Expected: PASS.

- [ ] **Step 4: Commit**

```bash
git add fem_core/bridge.py tests/python/test_model_spec_render_bridge.py
git commit -m "feat: expose OpenSees renderer through bridge"
```

---

### Task 4: TypeScript Transport Types and Client

**Files:**
- Modify: `packages/fem-tools/src/modelSpecTypes.ts`
- Modify: `packages/fem-tools/src/pythonBridge.ts`
- Modify: `packages/fem-tools/src/index.ts`
- Create: `tests/ts/model-spec-render.test.ts`

**Interfaces:**
- Consumes bridge command `modelSpec.renderOpenSees`.
- Produces `FemOpenSeesRenderResult` types and `runFemModelSpecRenderOpenSees(cwd, spec, signal?)`.

- [ ] **Step 1: Write TypeScript RED test**

Import the not-yet-existing API:

```typescript
import {
  runFemModelSpecRenderOpenSees,
  type FemEngineeringModelSpecInput,
  type FemOpenSeesRenderResult,
} from "@femagent/fem-tools";
```

Load the portal fixture, call the helper, and assert `schema`, `status`, renderer identity, workspace-relative artifact paths, and 64-hex hashes. Add a NOT_READY case asserting typed `BLOCKED` rather than an exception.

Run:

```bash
pnpm typecheck
pnpm test
```

Expected RED: missing type/helper exports.

- [ ] **Step 2: Add transport-only TypeScript contract**

Extend `modelSpecTypes.ts` with discriminated renderer result types sufficient to represent `RENDERED | BLOCKED`, including renderer/input/mapping/artifacts/renderFingerprint/readiness. Do not encode any OpenSees mapping algorithm.

Add to `pythonBridge.ts`:

```typescript
export async function runFemModelSpecRenderOpenSees(
  cwd: string,
  spec: FemEngineeringModelSpecInput,
  signal?: AbortSignal,
): Promise<FemOpenSeesRenderResult> {
  return await runFemCoreRequest<FemOpenSeesRenderResult>(
    cwd,
    "modelSpec.renderOpenSees",
    { spec },
    { signal },
  );
}
```

Export types/helper from `index.ts`.

- [ ] **Step 3: Run TypeScript tests**

```bash
pnpm typecheck
pnpm test
```

Expected: PASS.

- [ ] **Step 4: Commit**

```bash
git add packages/fem-tools/src/modelSpecTypes.ts packages/fem-tools/src/pythonBridge.ts packages/fem-tools/src/index.ts tests/ts/model-spec-render.test.ts
git commit -m "feat: add OpenSees renderer TypeScript transport"
```

---

### Task 5: Pi Agent Tool and Controlled Write Boundary

**Files:**
- Modify: `.pi/extensions/model-spec-tools.ts`
- Modify: `apps/agent/src/main.ts`
- Modify: `tests/ts/model-spec-tool-registration.test.ts`

**Interfaces:**
- Consumes: `runFemModelSpecRenderOpenSees`.
- Produces public tool `fem_model_render_opensees`.

- [ ] **Step 1: Write Pi registration RED tests**

Extend static registration tests to require:

```text
fem_model_render_opensees
```

in the model-spec extension and Agent allow-list. Assert the extension calls `runFemModelSpecRenderOpenSees`, does not import solver-run helpers, exposes only `spec` as a parameter, and has no `outputPath` field.

Run:

```bash
pnpm test
```

Expected RED: two new registration assertions fail.

- [ ] **Step 2: Register the controlled renderer tool**

In `.pi/extensions/model-spec-tools.ts`, import `runFemModelSpecRenderOpenSees` and register:

```text
name: fem_model_render_opensees
```

Reuse the existing strict ModelSpec TypeBox schema. Prompt rules must say:

- call only after explicit engineering facts are assembled; Python rechecks readiness anyway;
- `RENDERED` means artifact generation only, not solver-domain verification;
- inspect and build-preflight the generated model before claiming it constructs successfully;
- do not invent/repair engineering facts to force readiness;
- generated path is internal and cannot be user-selected;
- tool does not run OpenSees or any solver.

Add `fem_model_render_opensees` to `apps/agent/src/main.ts` tool allow-list. Do not alter `permission-gate.ts`.

- [ ] **Step 3: Run TypeScript suite**

```bash
pnpm typecheck
pnpm test
```

Expected: PASS.

- [ ] **Step 4: Commit**

```bash
git add .pi/extensions/model-spec-tools.ts apps/agent/src/main.ts tests/ts/model-spec-tool-registration.test.ts
git commit -m "feat: register controlled OpenSees model renderer tool"
```

---

### Task 6: Architecture/Verification Documentation and Final Gates

**Files:**
- Create: `docs/architecture/opensees-model-rendering.md`
- Create: `docs/verification/pr23-opensees-frame-2d-renderer.md`
- Update PR #19 body only after exact-head verification.

**Interfaces:**
- Consumes all PR23 functionality/tests.
- Produces durable architecture and verification records; no new runtime behavior.

- [ ] **Step 1: Write architecture document**

Document the chain:

```text
ModelSpec -> PR21 -> PR22 -> PR23 RENDERED artifact -> Model Intelligence -> build-only -> later solver execution
```

Explicitly distinguish `modelSpecFingerprint`, `modelSha256`, `renderFingerprint`, and `renderId`; state that renderer does no loads/analysis/unit conversion/repair and does not weaken AST/build-only trust boundaries.

- [ ] **Step 2: Run full repository verification on the implementation head**

Use the repository CI-equivalent commands:

```bash
pnpm typecheck
pnpm test
pytest tests/python -q
ruff check fem_core tests/python
# existing OpenSees adapter availability smoke
# existing ANSYS result-reader import smoke
pnpm fem:health
```

Record exact counts/results in the verification document. Include the TDD RED/GREEN sequence and the final implementation head used for the functional gate.

- [ ] **Step 3: Commit docs and trigger exact-final-head CI**

```bash
git add docs/architecture/opensees-model-rendering.md docs/verification/pr23-opensees-frame-2d-renderer.md
git commit -m "docs: close out PR23 renderer verification"
```

- [ ] **Step 4: Perform final diff/scope review**

Compare `main...feat/pr23-opensees-frame-2d-renderer`. Confirm changed files are limited to renderer core/bridge/TS/Pi/tests/docs and there are no unrelated Result Intelligence, RAG, Semantic Role, optimization, ANSYS, or permission-gate behavior changes.

- [ ] **Step 5: Verify exact final head before completion claim**

Use the latest PR-triggered CI run for the exact final SHA. Require `completed/success`; inspect job steps/logs and record TypeScript/Python pass counts plus Ruff, OpenSees smoke, ANSYS smoke, and health success. Do not claim completion from an older SHA.

- [ ] **Step 6: Update PR metadata**

Update PR #19 body to implementation-complete status with exact final head/CI evidence. Mark Draft -> Ready for Review only after the exact final head is green. Do not merge without explicit user authorization.
