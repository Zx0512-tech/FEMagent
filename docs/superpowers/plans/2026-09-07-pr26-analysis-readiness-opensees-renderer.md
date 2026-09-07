# PR26 — Analysis Readiness + OpenSees Analysis Renderer Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Bind a valid `EngineeringModelSpec` and `EngineeringAnalysisSpec` through deterministic OpenSees V1 Analysis Readiness, render a standalone linear-static OpenSees analysis bundle, verify that bundle before execution, and record every PR25 V1 requested response through the existing isolated OpenSees worker and Result Intelligence path.

**Architecture:** Python `fem_core` remains the only engineering truth path. PR23 and PR26 share one pure ModelSpec-to-OpenSees source builder; PR26 adds a solver-specific joint readiness gate, deterministic resolved response mappings, a controlled four-file generated-analysis bundle, semantic manifest verification before execution, and a private worker response context. TypeScript and Pi expose only thin transport plus one high-level `fem_analysis_prepare_opensees` CHECK/RENDER tool; real solver execution remains exclusively behind the existing `fem_solver_preflight` / permission-gated `fem_solver_run` path.

**Tech Stack:** Python >=3.13, pytest >=8.4,<9, Ruff >=0.12,<1, OpenSeesPy pinned through the existing `[opensees]` extra, TypeScript, Node >=22, pnpm, TypeBox, existing `femagent.bridge/v1`, existing OpenSees Python bundle adapter/worker, existing `structural_response_series` Result Intelligence.

**Spec:** `docs/superpowers/specs/2026-09-07-pr26-analysis-readiness-opensees-renderer-design.md`

## Global Constraints

- V1 supports only ModelSpec `2D / FRAME / CARTESIAN_XY / ELASTIC_FRAME_2D / EULER_BERNOULLI` and AnalysisSpec `LINEAR_STATIC` with exactly one explicit load case.
- Analysis Readiness statuses are exactly `INVALID_SPEC | NOT_READY | READY`; renderer statuses are exactly `BLOCKED | RENDERED`.
- `READY` requires intrinsic ModelSpec/AnalysisSpec validity, Model Readiness, exact ModelSpec fingerprint binding, exact force-unit equality, existing load/result targets, valid reaction restraint semantics, and proven OpenSees response mappings for every request.
- PR26 performs no unit conversion, load summation, target inference, sign correction, model repair, AnalysisSpec repair, Semantic Role inference, or solver-control inference.
- Reaction requests are executable only on genuinely restrained DOFs: X→UX, Y→UY, Z moment→RZ.
- Machine-readable moment units use `force*length` strings such as `N*m` and `kN*mm`; arbitrary OpenSees scripts retain `unit: null` unless separate trusted evidence exists.
- PR23 and PR26 must share one deterministic ModelSpec-to-OpenSees construction source builder; PR23 public behavior and rendered bytes must remain unchanged.
- PR26 generated `analysis.py` contains model construction, explicit nodal loads, fixed linear-static controls, and exactly one `ops.analyze(1)`; it contains no result extraction or subprocess execution.
- Fixed OpenSees V1 static controls are: `Plain` constraints, `Plain` numberer, `BandGeneral` system, `Linear` algorithm, `LoadControl(1.0)`, `Static`, and one `analyze(1)`.
- A successful render writes only under `.femagent/generated-analyses/analysis_render_<16 hex>/`; callers cannot choose an output path.
- `response_plan.json` contains response identity only and is never a trusted source for unit, DOF/index, recorder commands, or solver arguments.
- Generated-analysis execution must semantically revalidate the normalized ModelSpec and AnalysisSpec embedded in the manifest, recompute fingerprints/readiness, regenerate expected source/plan, and compare artifact hashes before worker execution.
- Hash consistency is an integrity check, not cryptographic authenticity; PR26 guarantees deterministic semantic consistency with embedded normalized specs, not protection against a malicious actor who can replace all workspace artifacts and code.
- SolverAdapter preflight/run remains the only execution path; `fem_analysis_prepare_opensees(mode=RENDER)` may write controlled artifacts but never executes OpenSees and never broadens the existing execution permission gate.
- The worker consumes a private verified response execution context for generated analyses and must not independently reinterpret trusted engineering units or mappings.
- PR26 continues emitting `kind = structural_response_series`; one linear-static solve produces one solver-native abscissa sample and must not label it seconds.
- PR26 does not add ANSYS rendering, natural-language AnalysisSpec completion, multiple load cases, distributed/gravity/thermal loads, modal/transient/spectrum/nonlinear analysis, customizable solver controls, automatic repair, optimization, or new AnalysisSpec V1 fields.

---

## File Map

### Create

- `fem_core/model_spec/opensees_source.py` — pure deterministic ModelSpec→OpenSees model construction source shared by PR23 and PR26.
- `fem_core/opensees_response_mapping.py` — shared proven OpenSees response access mapping without trusting user-supplied units.
- `fem_core/analysis_spec/readiness.py` — joint ModelSpec+AnalysisSpec readiness and resolved trusted response mappings.
- `fem_core/analysis_spec/opensees_renderer.py` — standalone PR26 four-file generated-analysis renderer.
- `fem_core/solvers/opensees_generated_analysis.py` — semantic generated-analysis manifest verification and private response-context construction.
- `tests/python/test_analysis_readiness.py` — joint readiness contract and PR25/PR26 boundary.
- `tests/python/test_opensees_analysis_renderer.py` — generated bundle content, blocking, determinism, cleanup.
- `tests/python/test_analysis_render_bridge.py` — `analysis.readiness` / `analysis.renderOpenSees` bridge contract.
- `tests/python/test_generated_opensees_analysis.py` — generated manifest integrity/semantic verification and tamper fail-closed tests.
- `tests/python/test_pr26_golden_path.py` — end-to-end READY→RENDERED→preflight→run→Result Intelligence integration.
- `tests/ts/analysis-readiness.test.ts` — TypeScript readiness/render transport contract.
- `tests/ts/analysis-prepare-tool-registration.test.ts` — high-level CHECK/RENDER Agent surface and safety boundary.

### Modify

- `fem_core/model_spec/opensees_renderer.py` — replace private source builder with shared pure compiler while preserving PR23 behavior.
- `fem_core/analysis_spec/__init__.py` — export readiness and renderer.
- `fem_core/opensees_response_plan.py` — consume shared untrusted response-access mapping for arbitrary OpenSees plans.
- `fem_core/bridge.py` — add Analysis Readiness/render commands and allow controlled OpenSees `analysisManifestPath` solver option.
- `fem_core/solvers/opensees_python.py` — verify generated bundles, add preflight check/provenance, stage private response context, pass it to worker.
- `fem_core/solvers/opensees_worker.py` — sample NODE and ELEMENT channels from verified execution context; keep arbitrary response-plan units untrusted.
- `tests/python/test_opensees_model_renderer.py` — regression-lock PR23 rendered bytes/hash after shared-compiler extraction.
- `tests/python/test_opensees_response_plan.py` — shared access resolver compatibility for arbitrary plans.
- `tests/python/test_opensees_structural_response.py` — real pinned-OpenSeesPy proof for node displacement/reactions plus existing element force mapping.
- `packages/fem-tools/src/analysisSpecTypes.ts` — readiness/render result types.
- `packages/fem-tools/src/pythonBridge.ts` — thin `analysis.readiness` / `analysis.renderOpenSees` wrappers.
- `packages/fem-tools/src/index.ts` — export new types/wrappers.
- `.pi/extensions/analysis-spec-tools.ts` — add one high-level `fem_analysis_prepare_opensees` CHECK/RENDER tool.
- `.pi/extensions/fem-tools.ts` — allow `solverOptions.analysisManifestPath` for OpenSees preflight/run schema and guidance.
- `apps/agent/src/main.ts` — allow the new high-level Analysis tool; do not add separate readiness/render tools.

---

### Task 1: Extract and Regression-Lock the Shared PR23 Model Compiler

**Files:**
- Create: `fem_core/model_spec/opensees_source.py`
- Modify: `fem_core/model_spec/opensees_renderer.py`
- Modify: `tests/python/test_opensees_model_renderer.py`

**Interfaces:**
- Consumes: PR21-normalized ModelSpec `dict[str, Any]`.
- Produces: `build_opensees_frame_2d_model_source(spec: dict[str, Any]) -> str` and `format_opensees_number(value: Any) -> str` for PR23/PR26 reuse.
- PR23 `render_opensees_frame_2d(workspace, spec)` public report, source bytes, hashes, and manifest semantics remain unchanged.

- [ ] **Step 1: Add a RED regression test proving a public shared compiler does not yet exist**

Add to `tests/python/test_opensees_model_renderer.py`:

```python
from fem_core.model_spec.opensees_source import build_opensees_frame_2d_model_source
from fem_core.model_spec.validator import validate_engineering_model_spec


def test_shared_model_source_matches_pr23_rendered_model(tmp_path: Path) -> None:
    spec = load_model_fixture("simple-portal-frame.json")
    validation = validate_engineering_model_spec(spec)
    assert validation["status"] == "VALID"
    expected = build_opensees_frame_2d_model_source(validation["normalizedSpec"])

    report = render_opensees_frame_2d(tmp_path, spec)
    model_path = tmp_path / report["artifacts"]["modelPath"]
    assert model_path.read_text(encoding="utf-8") == expected
```

Run:

```bash
python -m pytest tests/python/test_opensees_model_renderer.py::test_shared_model_source_matches_pr23_rendered_model -q
```

Expected RED: `ModuleNotFoundError: fem_core.model_spec.opensees_source`.

- [ ] **Step 2: Create the pure compiler by moving—not rewriting—the existing PR23 source logic**

Create `fem_core/model_spec/opensees_source.py` with these exact public helpers:

```python
from __future__ import annotations

from typing import Any

from fem_core.errors import FemCoreError

GEOM_TRANSF_TAG = 1


def format_opensees_number(value: Any) -> str:
    number = float(value)
    if number == 0.0:
        return "0.0"
    return repr(number)


def build_opensees_frame_2d_model_source(spec: dict[str, Any]) -> str:
    ...
```

Move the current `_lookup_by_id`, `_constraint_flags`, and `_render_source` behavior into this file without changing ordering, literals, `GEOM_TRANSF_TAG`, numeric formatting, or final newline. Raise `FemCoreError("OPENSEES_RENDER_INTERNAL_INVARIANT", ...)` for impossible lost material/section references exactly as PR23 does today.

Modify `fem_core/model_spec/opensees_renderer.py` to import the new pure builder and `GEOM_TRANSF_TAG`, and remove the duplicated private source-building helpers.

- [ ] **Step 3: Run focused and byte-level PR23 regression tests**

```bash
python -m pytest tests/python/test_opensees_model_renderer.py -q
python -m ruff check fem_core/model_spec/opensees_source.py fem_core/model_spec/opensees_renderer.py tests/python/test_opensees_model_renderer.py
```

Expected: PASS; existing PR23 deterministic render tests prove no public behavior drift.

- [ ] **Step 4: Commit the isolated compiler extraction**

```bash
git add fem_core/model_spec/opensees_source.py fem_core/model_spec/opensees_renderer.py tests/python/test_opensees_model_renderer.py
git commit -m "refactor: share deterministic OpenSees model source compiler"
```

---

### Task 2: Proven Response Access Mapping and Joint Analysis Readiness

**Files:**
- Create: `fem_core/opensees_response_mapping.py`
- Create: `fem_core/analysis_spec/readiness.py`
- Modify: `fem_core/analysis_spec/__init__.py`
- Modify: `fem_core/opensees_response_plan.py`
- Create: `tests/python/test_analysis_readiness.py`
- Modify: `tests/python/test_opensees_response_plan.py`

**Interfaces:**
- Consumes:
  - `validate_engineering_model_spec(model_spec)`
  - `evaluate_engineering_model_readiness(model_spec)`
  - `validate_engineering_analysis_spec(analysis_spec)`
- Produces:
  - `resolve_opensees_response_access(channel: dict[str, Any], *, element_type: str | None = None) -> dict[str, Any]`
  - `derive_response_unit(channel: dict[str, Any], model_units: dict[str, str]) -> str`
  - `evaluate_engineering_analysis_readiness(model_spec: dict[str, Any], analysis_spec: dict[str, Any]) -> dict[str, Any]`
- `resolve_opensees_response_access` returns access/selector/reference-frame only; trusted units are added only by Analysis Readiness through `derive_response_unit`.

- [ ] **Step 1: Write RED readiness tests around one bound portal-frame helper**

In `tests/python/test_analysis_readiness.py`, define deterministic helpers that bind AnalysisSpec to the actual fixture fingerprint instead of hard-coding stale hashes:

```python
def bound_analysis_spec(model_spec: dict[str, Any]) -> dict[str, Any]:
    validation = validate_engineering_model_spec(model_spec)
    assert validation["status"] == "VALID"
    return {
        "schemaVersion": "1.0",
        "kind": "engineering_analysis_spec",
        "modelSpecFingerprint": validation["modelSpecFingerprint"],
        "analysisType": "LINEAR_STATIC",
        "units": {"force": model_spec["units"]["force"]},
        "loadCases": [
            {
                "loadCaseId": "LC1",
                "nodalLoads": [{"nodeId": 3, "FX": 0.0, "FY": -10000.0, "MZ": 0.0}],
            }
        ],
        "resultRequests": [
            {
                "requestId": "R_DISP",
                "loadCaseId": "LC1",
                "quantity": "DISPLACEMENT",
                "target": {"type": "NODE", "id": 3},
                "component": "Y",
            },
            {
                "requestId": "R_RY",
                "loadCaseId": "LC1",
                "quantity": "REACTION_FORCE",
                "target": {"type": "NODE", "id": 1},
                "component": "Y",
            },
            {
                "requestId": "R_MZ",
                "loadCaseId": "LC1",
                "quantity": "REACTION_MOMENT",
                "target": {"type": "NODE", "id": 1},
                "component": "Z",
            },
            {
                "requestId": "R_ELE_MZ",
                "loadCaseId": "LC1",
                "quantity": "GENERALIZED_FORCE",
                "target": {"type": "ELEMENT", "id": 2},
                "component": "MZ",
                "location": "END_J",
            },
        ],
    }
```

Add assertions for a valid pair:

```python
report = evaluate_engineering_analysis_readiness(model_spec, analysis_spec)
assert report["schema"] == "FEMAGENT_ANALYSIS_READINESS_V1"
assert report["status"] == "READY"
assert report["profile"] == "OPENSEES_FRAME_2D_LINEAR_STATIC_V1"
assert report["modelSpecFingerprint"] == analysis_spec["modelSpecFingerprint"]
assert isinstance(report["analysisSpecFingerprint"], str)
assert report["checks"]["responseMapping"]["status"] == "PASS"
assert {item["requestId"] for item in report["checks"]["responseMapping"]["channels"]} == {
    "R_DISP", "R_RY", "R_MZ", "R_ELE_MZ"
}
```

Run:

```bash
python -m pytest tests/python/test_analysis_readiness.py -q
```

Expected RED: readiness module/function missing.

- [ ] **Step 2: Expand RED cases for every admission boundary before implementation**

Add exact cases asserting issue codes and `NOT_READY` / `INVALID_SPEC`:

```text
invalid ModelSpec -> INVALID_SPEC
invalid AnalysisSpec -> INVALID_SPEC
ModelSpec Model Readiness NOT_READY -> ANALYSIS_READINESS_MODEL_NOT_READY
modelSpecFingerprint mismatch -> ANALYSIS_READINESS_MODEL_FINGERPRINT_MISMATCH
AnalysisSpec force unit != ModelSpec force unit -> ANALYSIS_READINESS_FORCE_UNIT_MISMATCH
load node absent -> ANALYSIS_READINESS_LOAD_NODE_NOT_FOUND
NODE result target absent -> ANALYSIS_READINESS_RESULT_NODE_NOT_FOUND
ELEMENT result target absent -> ANALYSIS_READINESS_RESULT_ELEMENT_NOT_FOUND
REACTION_FORCE X on node without UX restraint -> ANALYSIS_READINESS_REACTION_DOF_UNRESTRAINED
REACTION_FORCE Y on node without UY restraint -> same code
REACTION_MOMENT Z on node without RZ restraint -> same code
```

Also lock the PR25/PR26 boundary:

```python
intrinsic = validate_engineering_analysis_spec(spec_with_node_999999)
assert intrinsic["status"] == "VALID"
combined = evaluate_engineering_analysis_readiness(model_spec, spec_with_node_999999)
assert combined["status"] == "NOT_READY"
assert "ANALYSIS_READINESS_LOAD_NODE_NOT_FOUND" in issue_codes(combined)
```

For `INVALID_SPEC`, assert dependent joint checks use `status == "SKIPPED"` and no trusted response mappings are emitted.

- [ ] **Step 3: Implement the shared response-access resolver**

Create `fem_core/opensees_response_mapping.py` with fixed V1 access mappings:

```python
_NODE_DOF = {"X": 1, "Y": 2, "Z": 3}
_ELASTIC_BEAM_2D_LOCAL_FORCE = {
    ("N", "END_I"): 0,
    ("VY", "END_I"): 1,
    ("MZ", "END_I"): 2,
    ("N", "END_J"): 3,
    ("VY", "END_J"): 4,
    ("MZ", "END_J"): 5,
}


def resolve_opensees_response_access(
    channel: dict[str, Any], *, element_type: str | None = None
) -> dict[str, Any]:
    quantity = channel.get("quantity")
    component = channel.get("component")
    if quantity == "DISPLACEMENT" and channel.get("target", {}).get("type") == "NODE":
        return {"access": "NODE_DISP", "dof": _NODE_DOF[str(component)], "referenceFrame": "GLOBAL"}
    if quantity in {"REACTION_FORCE", "REACTION_MOMENT"} and channel.get("target", {}).get("type") == "NODE":
        return {"access": "NODE_REACTION", "dof": _NODE_DOF[str(component)], "referenceFrame": "GLOBAL"}
    if quantity == "GENERALIZED_FORCE" and element_type == "ElasticBeam2d":
        index = _ELASTIC_BEAM_2D_LOCAL_FORCE.get((str(component), str(channel.get("location"))))
        if index is not None:
            return {
                "access": "ELEMENT_LOCAL_FORCE",
                "response": "localForce",
                "index": index,
                "vectorLength": 6,
                "referenceFrame": "ELEMENT_LOCAL",
            }
    raise FemCoreError("STRUCTURAL_RESPONSE_MAPPING_UNAVAILABLE", ...)
```

Implement deterministic unit derivation separately:

```python
def derive_response_unit(channel: dict[str, Any], model_units: dict[str, str]) -> str:
    force = model_units["force"]
    length = model_units["length"]
    quantity = channel["quantity"]
    component = channel["component"]
    if quantity == "DISPLACEMENT":
        return length
    if quantity == "REACTION_FORCE":
        return force
    if quantity == "REACTION_MOMENT":
        return f"{force}*{length}"
    if quantity == "GENERALIZED_FORCE" and component in {"N", "VY"}:
        return force
    if quantity == "GENERALIZED_FORCE" and component == "MZ":
        return f"{force}*{length}"
    raise FemCoreError("STRUCTURAL_RESPONSE_MAPPING_UNAVAILABLE", ...)
```

Modify `fem_core/opensees_response_plan.py` so arbitrary response plans reuse `resolve_opensees_response_access` but continue returning `unit: None`; do not let arbitrary plans call `derive_response_unit`.

- [ ] **Step 4: Implement Analysis Readiness with compact validation and deterministic checks**

Create `fem_core/analysis_spec/readiness.py` with constants:

```python
READINESS_SCHEMA = "FEMAGENT_ANALYSIS_READINESS_V1"
READINESS_PROFILE = "OPENSEES_FRAME_2D_LINEAR_STATIC_V1"
```

Implementation order must be deterministic:

```text
1. validate ModelSpec and AnalysisSpec intrinsically.
2. INVALID_SPEC -> compact validation reports + all joint checks SKIPPED.
3. evaluate Model Readiness; propagate non-ready as ANALYSIS_READINESS_MODEL_NOT_READY.
4. compare AnalysisSpec.modelSpecFingerprint with current ModelSpec fingerprint.
5. compare force units exactly; no conversion.
6. validate every nodal-load node ID against ModelSpec nodes.
7. validate every result target against ModelSpec node/element IDs.
8. validate reaction requested DOF against normalized ModelSpec constraints.
9. resolve every result request with the shared OpenSees resolver and trusted ModelSpec-derived unit.
10. return READY only when no ERROR issues exist.
```

For normalized ModelSpec V1 `ELASTIC_FRAME_2D`, pass `element_type="ElasticBeam2d"` to the proven element response resolver because the shared PR23 compiler deterministically emits `elasticBeamColumn` for this profile.

Each successful resolved mapping preserves `requestId`, `quantity`, `target`, `component`, optional `location`, then adds `access`, DOF or index/response/vectorLength as applicable, `referenceFrame`, and trusted `unit`.

Export `evaluate_engineering_analysis_readiness` from `fem_core/analysis_spec/__init__.py`.

- [ ] **Step 5: Run focused readiness and existing response-plan regressions**

```bash
python -m pytest tests/python/test_analysis_readiness.py tests/python/test_opensees_response_plan.py -q
python -m ruff check fem_core/opensees_response_mapping.py fem_core/analysis_spec/readiness.py fem_core/opensees_response_plan.py tests/python/test_analysis_readiness.py tests/python/test_opensees_response_plan.py
```

Expected: PASS; arbitrary response plan unit behavior remains `None`.

- [ ] **Step 6: Commit readiness and shared mapping**

```bash
git add fem_core/opensees_response_mapping.py fem_core/analysis_spec/readiness.py fem_core/analysis_spec/__init__.py fem_core/opensees_response_plan.py tests/python/test_analysis_readiness.py tests/python/test_opensees_response_plan.py
git commit -m "feat: add OpenSees Analysis Readiness and response mappings"
```

---

### Task 3: Deterministic Standalone OpenSees Analysis Renderer

**Files:**
- Create: `fem_core/analysis_spec/opensees_renderer.py`
- Modify: `fem_core/analysis_spec/__init__.py`
- Create: `tests/python/test_opensees_analysis_renderer.py`

**Interfaces:**
- Consumes:
  - `evaluate_engineering_analysis_readiness(model_spec, analysis_spec)`
  - `validate_engineering_model_spec(model_spec)`
  - `validate_engineering_analysis_spec(analysis_spec)`
  - `build_opensees_frame_2d_model_source(normalized_model_spec)`
- Produces: `render_opensees_linear_static_analysis(workspace: Path, model_spec: dict[str, Any], analysis_spec: dict[str, Any]) -> dict[str, Any]` with schema `FEMAGENT_OPENSEES_ANALYSIS_RENDER_V1` and `BLOCKED | RENDERED`.

- [ ] **Step 1: Write renderer RED tests for the exact four-file bundle**

Use the bound portal-frame helper and assert:

```python
report = render_opensees_linear_static_analysis(tmp_path, model_spec, analysis_spec)
assert report["schema"] == "FEMAGENT_OPENSEES_ANALYSIS_RENDER_V1"
assert report["status"] == "RENDERED"
assert report["renderer"] == {
    "name": "OPENSEES_FRAME_2D_LINEAR_STATIC_V1",
    "version": "1.0",
}
for key in ("analysisPath", "responsePlanPath", "readinessPath", "manifestPath"):
    assert (tmp_path / report["artifacts"][key]).is_file()
```

Read `analysis.py` and assert exact controlled analysis tokens:

```text
ops.timeSeries("Linear", 1)
ops.pattern("Plain", 1, 1)
ops.load(3, 0.0, -10000.0, 0.0)
ops.constraints("Plain")
ops.numberer("Plain")
ops.system("BandGeneral")
ops.algorithm("Linear")
ops.integrator("LoadControl", 1.0)
ops.analysis("Static")
ops.analyze(1)
```

Assert there is exactly one `ops.analyze(` occurrence and forbidden result/execution tokens are absent:

```text
nodeDisp
nodeReaction
eleResponse
subprocess
structural_response.json
```

Run:

```bash
python -m pytest tests/python/test_opensees_analysis_renderer.py -q
```

Expected RED: renderer module/function missing.

- [ ] **Step 2: Add RED tests for response-plan identity, manifest semantics, blocking, and determinism**

Assert generated `response_plan.json` uses:

```json
{
  "schemaVersion": "1.0",
  "kind": "structural_response_plan",
  "channels": [
    {
      "channelId": "R_DISP",
      "quantity": "DISPLACEMENT",
      "target": {"type": "NODE", "id": 3},
      "component": "Y"
    }
  ]
}
```

with all requests sorted by `requestId`; no `unit`, `dof`, `index`, `access`, or recorder command fields are allowed.

Assert `analysis_manifest.json` contains:

```text
schema = FEMAGENT_OPENSEES_ANALYSIS_RENDER_V1
status = RENDERED
renderer name/version
normalizedModelSpec
normalizedAnalysisSpec
modelSpecFingerprint
analysisSpecFingerprint
readinessProfile
units
loadCaseId
responseMappings
artifact paths + SHA256
analysisRenderFingerprint
```

Add cases:

```text
NOT_READY pair -> BLOCKED, reason ANALYSIS_NOT_READY, no generated-analysis directory published
same semantic ModelSpec/AnalysisSpec with reorderings -> identical analysis.py SHA, response_plan SHA, readiness SHA, analysisRenderFingerprint
repeat render -> analysisRenderId may differ, deterministic content hashes/fingerprint remain equal
write failure after fresh directory creation -> directory removed + OPENSEES_ANALYSIS_RENDER_WRITE_FAILED
```

- [ ] **Step 3: Implement minimal deterministic renderer**

Create `fem_core/analysis_spec/opensees_renderer.py` with:

```python
RENDER_SCHEMA = "FEMAGENT_OPENSEES_ANALYSIS_RENDER_V1"
RENDERER_NAME = "OPENSEES_FRAME_2D_LINEAR_STATIC_V1"
RENDERER_VERSION = "1.0"
SUPPORTED_READINESS_PROFILE = "OPENSEES_FRAME_2D_LINEAR_STATIC_V1"


def build_opensees_linear_static_analysis_source(
    normalized_model_spec: dict[str, Any],
    normalized_analysis_spec: dict[str, Any],
) -> str:
    ...


def build_structural_response_plan(normalized_analysis_spec: dict[str, Any]) -> dict[str, Any]:
    ...


def render_opensees_linear_static_analysis(
    workspace: Path,
    model_spec: dict[str, Any],
    analysis_spec: dict[str, Any],
) -> dict[str, Any]:
    ...
```

Source construction must call the shared PR23 compiler, append one `Linear` time series and one `Plain` pattern, emit sorted normalized loads as `ops.load(nodeId, FX, FY, MZ)`, then fixed V1 static controls and exactly one analyze call with explicit nonzero-code failure.

Build all JSON/source bytes in memory first. Create only `.femagent/generated-analyses/analysis_render_<16hex>/`. Write:

```text
analysis.py
response_plan.json
analysis_readiness.json
analysis_manifest.json
```

The manifest embeds normalized ModelSpec and normalized AnalysisSpec plus trusted readiness response mappings. Compute `analysisRenderFingerprint` from canonical JSON of renderer name/version, ModelSpec fingerprint, AnalysisSpec fingerprint, and SHA256 of analysis source, response plan, and readiness artifact; exclude random render ID and manifest path.

Export `render_opensees_linear_static_analysis` from `fem_core/analysis_spec/__init__.py`.

- [ ] **Step 4: Run renderer tests and full pre-solver Python regression**

```bash
python -m pytest tests/python/test_opensees_analysis_renderer.py tests/python/test_opensees_model_renderer.py tests/python/test_analysis_readiness.py -q
python -m ruff check fem_core/analysis_spec/opensees_renderer.py tests/python/test_opensees_analysis_renderer.py
```

Expected: PASS.

- [ ] **Step 5: Commit renderer**

```bash
git add fem_core/analysis_spec/opensees_renderer.py fem_core/analysis_spec/__init__.py tests/python/test_opensees_analysis_renderer.py
git commit -m "feat: render standalone OpenSees linear-static analyses"
```

---

### Task 4: Python Bridge, TypeScript Contracts, and One High-Level Analysis Tool

**Files:**
- Modify: `fem_core/bridge.py`
- Create: `tests/python/test_analysis_render_bridge.py`
- Modify: `packages/fem-tools/src/analysisSpecTypes.ts`
- Modify: `packages/fem-tools/src/pythonBridge.ts`
- Modify: `packages/fem-tools/src/index.ts`
- Create: `tests/ts/analysis-readiness.test.ts`
- Modify: `.pi/extensions/analysis-spec-tools.ts`
- Modify: `apps/agent/src/main.ts`
- Create: `tests/ts/analysis-prepare-tool-registration.test.ts`

**Interfaces:**
- Produces bridge commands:
  - `analysis.readiness` payload `{ modelSpec, analysisSpec }`
  - `analysis.renderOpenSees` payload `{ modelSpec, analysisSpec }`
- Produces TS wrappers:
  - `runFemAnalysisReadiness(cwd, modelSpec, analysisSpec, signal?)`
  - `runFemAnalysisRenderOpenSees(cwd, modelSpec, analysisSpec, signal?)`
- Produces one Agent tool: `fem_analysis_prepare_opensees` with `mode: "CHECK" | "RENDER"`.

- [ ] **Step 1: Write Python bridge RED tests**

In `tests/python/test_analysis_render_bridge.py`, use bridge envelopes and assert:

```python
ready = handle_request(request("analysis.readiness", model_spec, analysis_spec), workspace=tmp_path)
assert ready["ok"] is True
assert ready["result"]["status"] == "READY"

rendered = handle_request(request("analysis.renderOpenSees", model_spec, analysis_spec), workspace=tmp_path)
assert rendered["ok"] is True
assert rendered["result"]["status"] == "RENDERED"
```

Also assert engineering `NOT_READY` / `BLOCKED` remain `ok=True`, while non-object `modelSpec` or `analysisSpec` returns bridge `INVALID_ARGUMENT`.

Run:

```bash
python -m pytest tests/python/test_analysis_render_bridge.py -q
```

Expected RED: `UNKNOWN_COMMAND`.

- [ ] **Step 2: Add bridge dispatch only; no engineering logic**

In `fem_core/bridge.py` import the two AnalysisSpec capabilities and add:

```python
elif command == "analysis.readiness":
    result = evaluate_engineering_analysis_readiness(
        _required_object(payload, "modelSpec"),
        _required_object(payload, "analysisSpec"),
    )
elif command == "analysis.renderOpenSees":
    result = render_opensees_linear_static_analysis(
        workspace,
        _required_object(payload, "modelSpec"),
        _required_object(payload, "analysisSpec"),
    )
```

Run the focused bridge tests and Ruff.

- [ ] **Step 3: Write TypeScript RED tests for exact command names and result typing**

In `tests/ts/analysis-readiness.test.ts`, call both wrappers with the existing fixture model plus a bound AnalysisSpec fixture/helper and assert:

```ts
assert.equal(readiness.schema, "FEMAGENT_ANALYSIS_READINESS_V1");
assert.equal(readiness.status, "READY");
assert.equal(rendered.schema, "FEMAGENT_OPENSEES_ANALYSIS_RENDER_V1");
assert.equal(rendered.status, "RENDERED");
```

Before implementation, `pnpm test:ts` must fail because the new exports do not exist.

- [ ] **Step 4: Add TS mirror types and thin bridge wrappers**

Extend `packages/fem-tools/src/analysisSpecTypes.ts` with discriminated access mappings:

```ts
export type FemAnalysisReadinessStatus = "INVALID_SPEC" | "NOT_READY" | "READY";
export type FemOpenSeesAnalysisRenderStatus = "BLOCKED" | "RENDERED";

export type FemAnalysisResponseMapping =
  | {
      requestId: string;
      quantity: "DISPLACEMENT";
      target: { type: "NODE"; id: number };
      component: "X" | "Y";
      access: "NODE_DISP";
      dof: 1 | 2;
      referenceFrame: "GLOBAL";
      unit: string;
    }
  | {
      requestId: string;
      quantity: "REACTION_FORCE" | "REACTION_MOMENT";
      target: { type: "NODE"; id: number };
      component: "X" | "Y" | "Z";
      access: "NODE_REACTION";
      dof: 1 | 2 | 3;
      referenceFrame: "GLOBAL";
      unit: string;
    }
  | {
      requestId: string;
      quantity: "GENERALIZED_FORCE";
      target: { type: "ELEMENT"; id: number };
      component: "N" | "VY" | "MZ";
      location: "END_I" | "END_J";
      access: "ELEMENT_LOCAL_FORCE";
      response: "localForce";
      index: 0 | 1 | 2 | 3 | 4 | 5;
      vectorLength: 6;
      referenceFrame: "ELEMENT_LOCAL";
      unit: string;
    };
```

Add `FemAnalysisReadiness`, `FemOpenSeesAnalysisRenderArtifacts`, and `FemOpenSeesAnalysisRenderResult` matching Python fields exactly.

In `pythonBridge.ts`, add thin wrappers using `runFemCoreRequest` and exact commands; do not derive any mapping or unit in TS. Export all new symbols from `index.ts`.

- [ ] **Step 5: Write Agent registration RED tests before changing the extension**

`tests/ts/analysis-prepare-tool-registration.test.ts` must inspect `.pi/extensions/analysis-spec-tools.ts` and `apps/agent/src/main.ts` and assert:

```text
fem_analysis_prepare_opensees is registered exactly once
mode includes CHECK and RENDER
CHECK calls runFemAnalysisReadiness
RENDER calls runFemAnalysisRenderOpenSees
extension does not import/call runFemSolverRun
extension does not expose outputPath
prompt text states READY/RENDERED do not mean solver execution
app allow-list contains fem_analysis_prepare_opensees
no separate fem_analysis_readiness or fem_analysis_render_opensees public tools are added
```

Run `pnpm test:ts`; expected RED only on the new registration expectations.

- [ ] **Step 6: Implement one high-level CHECK/RENDER tool**

Modify `.pi/extensions/analysis-spec-tools.ts` to reuse the existing strict ModelSpec and AnalysisSpec TypeBox schemas and register:

```ts
name: "fem_analysis_prepare_opensees"
parameters: Type.Object({
  mode: Type.Union([Type.Literal("CHECK"), Type.Literal("RENDER")]),
  modelSpec: modelSpecSchema,
  analysisSpec: analysisSpecSchema,
}, { additionalProperties: false })
```

Execution:

```ts
const report = params.mode === "CHECK"
  ? await runFemAnalysisReadiness(ctx.cwd, params.modelSpec, params.analysisSpec, signal)
  : await runFemAnalysisRenderOpenSees(ctx.cwd, params.modelSpec, params.analysisSpec, signal);
return toolResult(report);
```

Guidance must state: CHECK is read-only; RENDER writes only controlled generated-analysis artifacts; neither runs OpenSees; do not mutate engineering facts to force READY; solver preflight and permission-gated solver run remain separate.

Add the tool name to `apps/agent/src/main.ts`; keep the temporary `fem_analysis_spec_validate` tool intact.

- [ ] **Step 7: Run bridge/TS/registration regression and commit**

```bash
python -m pytest tests/python/test_analysis_render_bridge.py -q
pnpm typecheck
pnpm test:ts
python -m ruff check fem_core/bridge.py tests/python/test_analysis_render_bridge.py
```

Expected: PASS.

```bash
git add fem_core/bridge.py tests/python/test_analysis_render_bridge.py packages/fem-tools/src/analysisSpecTypes.ts packages/fem-tools/src/pythonBridge.ts packages/fem-tools/src/index.ts tests/ts/analysis-readiness.test.ts .pi/extensions/analysis-spec-tools.ts apps/agent/src/main.ts tests/ts/analysis-prepare-tool-registration.test.ts
git commit -m "feat: expose high-level OpenSees analysis preparation"
```

---

### Task 5: Semantic Generated-Analysis Manifest Verification in Solver Preflight

**Files:**
- Create: `fem_core/solvers/opensees_generated_analysis.py`
- Modify: `fem_core/bridge.py`
- Modify: `fem_core/solvers/opensees_python.py`
- Modify: `.pi/extensions/fem-tools.ts`
- Create: `tests/python/test_generated_opensees_analysis.py`
- Modify: `tests/ts/analysis-prepare-tool-registration.test.ts`

**Interfaces:**
- Produces:
  - `verify_generated_analysis_bundle(workspace: Path, *, model_path: str, response_plan_path: str, manifest_path: str) -> dict[str, Any]`
  - returned verified object contains parsed manifest, recomputed readiness, regenerated expected artifact hashes, and private `responseContext` channels.
- OpenSees solver options expand from `{ responsePlanPath? }` to `{ responsePlanPath?, analysisManifestPath? }`.
- `analysisManifestPath` is valid only together with a PR26 generated `.py` model and matching `responsePlanPath`; arbitrary scripts remain on the old path.

- [ ] **Step 1: Write RED semantic-verification tests using a freshly rendered bundle**

In `tests/python/test_generated_opensees_analysis.py` render the golden pair, then call:

```python
verified = verify_generated_analysis_bundle(
    tmp_path,
    model_path=report["artifacts"]["analysisPath"],
    response_plan_path=report["artifacts"]["responsePlanPath"],
    manifest_path=report["artifacts"]["manifestPath"],
)
assert verified["analysisRenderFingerprint"] == report["analysisRenderFingerprint"]
assert verified["readiness"]["status"] == "READY"
assert {channel["channelId"] for channel in verified["responseContext"]["channels"]} == {
    "R_DISP", "R_RY", "R_MZ", "R_ELE_MZ"
}
```

Run the focused test; expected RED because verifier module is missing.

- [ ] **Step 2: Add RED tamper/mixing cases before verifier implementation**

Independently mutate and assert exact fail-closed `FemCoreError` codes:

```text
invalid manifest schema/missing embedded specs -> GENERATED_ANALYSIS_MANIFEST_INVALID
modelPath differs from manifest analysisPath -> GENERATED_ANALYSIS_PATH_MISMATCH
responsePlanPath differs from manifest responsePlanPath -> GENERATED_ANALYSIS_PATH_MISMATCH
modify analysis.py only -> GENERATED_ANALYSIS_ARTIFACT_MISMATCH
modify response_plan.json only -> GENERATED_ANALYSIS_ARTIFACT_MISMATCH
modify readiness file only -> GENERATED_ANALYSIS_ARTIFACT_MISMATCH
change embedded normalized ModelSpec without matching current fingerprint -> GENERATED_ANALYSIS_FINGERPRINT_MISMATCH
change embedded normalized AnalysisSpec without matching current fingerprint -> GENERATED_ANALYSIS_FINGERPRINT_MISMATCH
change manifest analysisRenderFingerprint -> GENERATED_ANALYSIS_FINGERPRINT_MISMATCH
```

Also test the stronger semantic case: mutate `analysis.py`, update its declared SHA and analysisRenderFingerprint to be internally hash-consistent, and assert verification still fails because regenerated expected source from embedded normalized specs does not match the artifact.

- [ ] **Step 3: Implement semantic verifier with reconstruction, not manifest trust**

Create `fem_core/solvers/opensees_generated_analysis.py`.

Validation sequence:

```text
1. resolve all paths with existing workspace path helpers.
2. parse manifest UTF-8 JSON and require exact PR26 schema/renderer identity plus embedded normalizedModelSpec/normalizedAnalysisSpec.
3. require supplied model_path and response_plan_path to equal manifest workspace-relative paths exactly.
4. revalidate embedded ModelSpec and AnalysisSpec through authoritative validators.
5. require recomputed fingerprints to equal manifest fingerprints.
6. rerun Analysis Readiness from the embedded normalized specs and require READY plus exact readiness profile.
7. regenerate expected analysis source with build_opensees_linear_static_analysis_source().
8. regenerate expected response plan with build_structural_response_plan().
9. canonical-serialize recomputed readiness exactly as renderer does.
10. compare actual file bytes/SHA256 to regenerated expected bytes and manifest hashes.
11. recompute analysisRenderFingerprint with the same renderer helper and compare.
12. build a private responseContext from the recomputed readiness resolved mappings, never from user response-plan unit fields.
```

Return only verified deterministic data needed by adapter/worker; do not execute the solver or publish public artifacts.

- [ ] **Step 4: Extend OpenSees solverOptions contract and bridge allow-list**

In `fem_core/bridge.py`, OpenSees `_solver_call_arguments` must accept exactly:

```python
{"responsePlanPath", "analysisManifestPath"}
```

and continue rejecting all other solver options.

In `.pi/extensions/fem-tools.ts`, add optional:

```ts
analysisManifestPath: Type.Optional(Type.String({
  description: "Workspace-relative PR26 generated-analysis manifest; used only to verify a generated OpenSees analysis bundle before execution.",
}))
```

Guidance must require the manifest path and response-plan path returned by the same PR26 render and forbid inventing/mixing them.

- [ ] **Step 5: Integrate verifier into `OpenSeesBundleAdapter.preflight`**

In `fem_core/solvers/opensees_python.py`, parse both options without weakening arbitrary-script behavior:

```text
no analysisManifestPath -> existing arbitrary Python response-plan path behavior remains unchanged
analysisManifestPath provided -> responsePlanPath must also be provided; loadPath must be omitted for PR26 generated static script
```

For generated analyses, call `verify_generated_analysis_bundle(...)` before build inspection and add preflight checks:

```text
GENERATED_ANALYSIS_MANIFEST = PASSED
GENERATED_ANALYSIS_SEMANTICS = PASSED
STRUCTURAL_RESPONSE_MAPPING = PASSED
```

Include in preflight model/provenance summary:

```text
analysisRenderFingerprint
modelSpecFingerprint
analysisSpecFingerprint
analysisManifestSha256
```

Do not write the private response context during preflight; verification may construct it in memory only.

- [ ] **Step 6: Run verifier/preflight tests and commit**

```bash
python -m pytest tests/python/test_generated_opensees_analysis.py tests/python/test_opensees_structural_response.py -q
pnpm typecheck
pnpm test:ts
python -m ruff check fem_core/solvers/opensees_generated_analysis.py fem_core/solvers/opensees_python.py fem_core/bridge.py tests/python/test_generated_opensees_analysis.py
```

Expected: PASS.

```bash
git add fem_core/solvers/opensees_generated_analysis.py fem_core/bridge.py fem_core/solvers/opensees_python.py .pi/extensions/fem-tools.ts tests/python/test_generated_opensees_analysis.py tests/ts/analysis-prepare-tool-registration.test.ts
git commit -m "feat: verify generated OpenSees analysis bundles before execution"
```

---

### Task 6: Verified Worker Response Context and Real OpenSees Mapping Proof

**Files:**
- Modify: `fem_core/solvers/opensees_python.py`
- Modify: `fem_core/solvers/opensees_worker.py`
- Modify: `tests/python/test_opensees_structural_response.py`
- Modify: `tests/python/test_generated_opensees_analysis.py`

**Interfaces:**
- Generated-analysis `run()` stages a private JSON response context under the run directory and passes `--response-context <path>` to `opensees_worker --mode script-run`.
- Worker response context schema is internal: `schemaVersion: "1.0"`, `kind: "opensees_response_execution_context"`, non-empty `channels` with already verified `access`, target, selector, unit, and reference frame.
- Arbitrary/user Python models without `analysisManifestPath` keep the existing `--response-plan` path and continue recording `unit: null`.

- [ ] **Step 1: Add a real pinned-OpenSeesPy RED/characterization test covering all PR25 V1 mapping classes**

Extend `tests/python/test_opensees_structural_response.py` with a simple cantilever generated through ModelSpec+AnalysisSpec:

```text
node 1 = fixed at (0,0)
node 2 = free at (L,0)
one ELASTIC_FRAME_2D element 1->2
vertical FY = -P at node 2
requests:
- node 2 displacement Y
- node 1 reaction force Y
- node 1 reaction moment Z
- element 1 N END_I
- element 1 VY END_I
- element 1 MZ END_I
```

Use explicit values such as `L = 2.0 m`, `P = 1000.0 N`, `E = 2.0e11 N/m²`, `I = 8.0e-6 m⁴`, and compare within explicit tolerances:

```python
assert reaction_y == pytest.approx(P, rel=1e-9, abs=1e-7)
assert abs(reaction_mz) == pytest.approx(P * L, rel=1e-9, abs=1e-7)
assert abs(element_shear_i) == pytest.approx(P, rel=1e-9, abs=1e-7)
assert abs(element_mz_i) == pytest.approx(P * L, rel=1e-9, abs=1e-7)
assert displacement_y < 0.0
```

Skip only when `get_solver_adapter("opensees").status()["available"]` is false. Before Task 6 implementation, generated node channels should fail because the current worker supports element-only response-plan sampling.

- [ ] **Step 2: Add RED tests for trusted vs untrusted unit provenance**

Generated manifest/context run must output:

```text
DISPLACEMENT unit = m
REACTION_FORCE unit = N
REACTION_MOMENT unit = N*m
GENERALIZED_FORCE N/VY unit = N
GENERALIZED_FORCE MZ unit = N*m
```

An existing arbitrary OpenSees Python script with a user response plan must still emit `unit is None`; no ModelSpec-derived trusted unit may leak into that path.

- [ ] **Step 3: Stage a private verified response context during generated `run()`**

In `OpenSeesBundleAdapter.run`, when `analysisManifestPath` is provided:

```text
1. rerun generated-bundle verification just before execution; do not trust prior preflight result.
2. stage the model bundle exactly as existing code does.
3. write run_dir/response_context.verified.json from verifier["responseContext"].
4. pass --response-context to worker instead of relying on response-plan semantic interpretation.
5. still stage/copy the normalized response plan for run provenance and manifest hashes.
```

Include the response-context file only as private run implementation detail; it is not an Agent output contract.

- [ ] **Step 4: Extend worker argument parsing and sampling by verified access kind**

In `fem_core/solvers/opensees_worker.py`, add strict `_read_response_context(path)` and extend `run_python_model` with optional `response_context_path`.

After a successful wrapped `ops.analyze(...)`:

```python
if any(channel["access"] == "NODE_REACTION" for channel in channels):
    ops.reactions()

for channel in channels:
    if channel["access"] == "NODE_DISP":
        value = float(ops.nodeDisp(int(channel["targetId"]), int(channel["dof"])))
    elif channel["access"] == "NODE_REACTION":
        value = float(ops.nodeReaction(int(channel["targetId"]), int(channel["dof"])))
    elif channel["access"] == "ELEMENT_LOCAL_FORCE":
        vector = ops.eleResponse(int(channel["targetId"]), channel["response"])
        # require exact vectorLength and read verified index
    else:
        raise FemCoreError("STRUCTURAL_RESPONSE_MAPPING_UNAVAILABLE", ...)
```

All values and abscissa must be finite. Write the existing canonical `structural_response_series` fields using unit/referenceFrame from verified context. One static analyze call produces one sample.

For the old arbitrary response-plan path, retain runtime domain validation and mapping through the shared untrusted resolver; emitted units remain `None`.

- [ ] **Step 5: Extend run manifest provenance only for generated analyses**

Add:

```json
"generatedAnalysis": {
  "analysisRenderFingerprint": "...",
  "modelSpecFingerprint": "...",
  "analysisSpecFingerprint": "...",
  "analysisManifestSha256": "..."
}
```

For arbitrary Python scripts, `generatedAnalysis` is absent or `null`; do not imply generated-spec provenance.

- [ ] **Step 6: Run real OpenSees mapping proof and worker regressions**

```bash
python -m pytest tests/python/test_opensees_structural_response.py tests/python/test_generated_opensees_analysis.py -q
python -m ruff check fem_core/solvers/opensees_python.py fem_core/solvers/opensees_worker.py tests/python/test_opensees_structural_response.py tests/python/test_generated_opensees_analysis.py
```

Expected: PASS with the pinned OpenSeesPy runtime in CI; node mappings are considered proven only after this green run.

- [ ] **Step 7: Commit worker/provenance support**

```bash
git add fem_core/solvers/opensees_python.py fem_core/solvers/opensees_worker.py tests/python/test_opensees_structural_response.py tests/python/test_generated_opensees_analysis.py
git commit -m "feat: record verified generated-analysis responses"
```

---

### Task 7: Full PR26 Golden Path, Determinism, Tamper, and Result Intelligence

**Files:**
- Create: `tests/python/test_pr26_golden_path.py`
- Modify: `tests/python/test_generated_opensees_analysis.py`
- Modify only if a proven compatibility defect exists: `fem_core/result_intelligence.py`

**Interfaces:**
- Consumes all PR26 public/internal capabilities plus existing `get_solver_adapter("opensees")`, `inspect_result`, and `query_result`.
- Produces integration proof that one rendered/verified solve exposes all PR25 V1 response classes through canonical recorded results without alternate execution or truth paths.

- [ ] **Step 1: Write the end-to-end golden test before any Result Intelligence compatibility fix**

`tests/python/test_pr26_golden_path.py` must execute:

```python
model_validation = validate_engineering_model_spec(model_spec)
analysis_validation = validate_engineering_analysis_spec(analysis_spec)
readiness = evaluate_engineering_analysis_readiness(model_spec, analysis_spec)
rendered = render_opensees_linear_static_analysis(tmp_path, model_spec, analysis_spec)

adapter = get_solver_adapter("opensees")
preflight = adapter.preflight(
    tmp_path,
    model_path=rendered["artifacts"]["analysisPath"],
    load_path=None,
    solver_options={
        "responsePlanPath": rendered["artifacts"]["responsePlanPath"],
        "analysisManifestPath": rendered["artifacts"]["manifestPath"],
    },
)
assert preflight["status"] == "READY"

run = adapter.run(
    tmp_path,
    model_path=rendered["artifacts"]["analysisPath"],
    load_path=None,
    solver_options={
        "responsePlanPath": rendered["artifacts"]["responsePlanPath"],
        "analysisManifestPath": rendered["artifacts"]["manifestPath"],
    },
)
assert run["status"] == "COMPLETED"
```

Then use `inspect_result(tmp_path, run["runId"])` / existing run reference semantics and assert the structural response artifact is VALID and queryable.

- [ ] **Step 2: Query all supported response classes from the same solve**

The same run must prove recorded availability for:

```text
NODE DISPLACEMENT X/Y as requested
NODE REACTION_FORCE X/Y as requested
NODE REACTION_MOMENT Z
ELEMENT GENERALIZED_FORCE N/VY/MZ at END_I/END_J as requested
```

Use the exact canonical Result Intelligence query form currently supported. If Result Intelligence already reads mixed `structural_response_series`, no production code change is allowed. If a test proves it rejects one PR25 V1 canonical quantity despite a valid artifact, make the smallest compatibility extension in `fem_core/result_intelligence.py` and add a focused regression in the same task.

- [ ] **Step 3: Add end-to-end determinism proof**

Create semantically identical reordered ModelSpec and AnalysisSpec copies and assert:

```text
modelSpecFingerprint equal
analysisSpecFingerprint equal
analysis.py SHA equal
response_plan SHA equal
analysis_readiness SHA equal
analysisRenderFingerprint equal
```

Random render IDs/directories may differ.

- [ ] **Step 4: Add pre-worker tamper assertions at the real adapter boundary**

Render once, then independently tamper with:

```text
analysis.py
response_plan.json
analysis_readiness.json
manifest path fields
manifest hashes/fingerprint
embedded normalized ModelSpec/AnalysisSpec
```

Call `adapter.preflight(...)` and assert it fails closed before worker execution. Verify no new `.femagent/runs/run_*` directory appears for failed preflight cases.

- [ ] **Step 5: Run the complete PR26 focused suite**

```bash
python -m pytest \
  tests/python/test_analysis_readiness.py \
  tests/python/test_opensees_analysis_renderer.py \
  tests/python/test_analysis_render_bridge.py \
  tests/python/test_generated_opensees_analysis.py \
  tests/python/test_opensees_response_plan.py \
  tests/python/test_opensees_structural_response.py \
  tests/python/test_pr26_golden_path.py -q
```

Expected: PASS.

- [ ] **Step 6: Commit integration proof**

```bash
git add tests/python/test_pr26_golden_path.py tests/python/test_generated_opensees_analysis.py fem_core/result_intelligence.py
git commit -m "test: prove PR26 OpenSees analysis golden path"
```

If `fem_core/result_intelligence.py` was not changed, omit it from `git add`; do not create a no-op edit merely to match this command.

---

### Task 8: Full Verification, Scope Audit, and Review-Ready Gate

**Files:**
- No new production scope by default.
- Corrections are limited to PR26-touched files listed in the File Map and tests proving the correction.

**Interfaces:**
- Produces evidence that the implementation matches the approved PR26 spec and is safe to mark review-ready.

- [ ] **Step 1: Run focused PR26 Python tests from the latest HEAD**

```bash
python -m pytest \
  tests/python/test_analysis_readiness.py \
  tests/python/test_opensees_analysis_renderer.py \
  tests/python/test_analysis_render_bridge.py \
  tests/python/test_generated_opensees_analysis.py \
  tests/python/test_opensees_response_plan.py \
  tests/python/test_opensees_structural_response.py \
  tests/python/test_pr26_golden_path.py -q
```

Expected: PASS.

- [ ] **Step 2: Run full repository verification**

```bash
python -m pytest tests/python -q
python -m ruff check fem_core tests/python
pnpm typecheck
pnpm test:ts
pnpm fem:health
```

Expected: all PASS. CI must also execute its existing OpenSees availability smoke against the latest PR26 HEAD.

- [ ] **Step 3: Run the explicit PR26 scope audit**

Inspect `git diff main...HEAD` and verify all statements below are true:

```text
no ANSYS renderer/analysis behavior added
no PR27 natural-language AnalysisSpec completion added
no new AnalysisSpec V1 fields
no distributed/gravity/thermal/load-combination support
no modal/transient/nonlinear/spectrum solver path
no caller-selected solver algorithm/integrator/step/tolerance controls
no unit conversion in readiness or renderer
no duplicate ModelSpec→OpenSees model compiler
no result extraction inside generated analysis.py
no alternate solver subprocess/run path outside SolverAdapter
no permission-gate broadening beyond existing fem_solver_run
no trusted unit accepted from response_plan.json
no worker-side trusted engineering reinterpretation for generated analyses
no permanent separate fem_analysis_readiness / fem_analysis_render_opensees Agent tools
```

Also confirm the temporary `fem_analysis_spec_validate` tool still exists and `fem_analysis_prepare_opensees` is the only new LLM-visible Analysis preparation tool.

- [ ] **Step 4: Check diff hygiene and exact branch scope**

```bash
git diff --check main...HEAD
git diff --stat main...HEAD
git status --short
```

Expected: no whitespace errors, only intended PR26 files, clean worktree after commits.

- [ ] **Step 5: Apply only evidence-driven corrections and rerun the relevant RED→GREEN cycle**

If verification exposes a defect, first add or identify a failing focused test, run it to confirm RED, make the smallest correction in the affected PR26 file, rerun focused tests, then rerun the full commands from Step 2. Do not add unrelated refactors during this gate.

- [ ] **Step 6: Commit any final corrections explicitly**

Use one of these exact commit messages according to the defect class:

```bash
git commit -m "fix: preserve PR26 analysis readiness invariants"
git commit -m "fix: preserve generated OpenSees analysis integrity"
git commit -m "fix: preserve PR26 response provenance"
```

Stage only files changed by the corresponding correction before committing.

## Completion Gate

PR26 may be called implementation-complete only when:

- Analysis Readiness deterministically returns `INVALID_SPEC | NOT_READY | READY` with all approved joint checks.
- Every PR25 V1 result request has a real pinned-OpenSeesPy proven mapping.
- Reaction requests on unrestrained DOFs are `NOT_READY`.
- Model and Analysis force units must match exactly; no hidden conversion occurs.
- PR23 and PR26 share one ModelSpec→OpenSees compiler and PR23 output remains regression-stable.
- READY pairs render the exact four-file standalone generated-analysis bundle.
- Generated `analysis.py` never extracts results and never executes a subprocess.
- Generated bundle verification reconstructs engineering semantics from embedded normalized specs instead of trusting mutable manifest hashes alone.
- Arbitrary OpenSees response plans retain untrusted `unit: null`; only verified PR26 generated analyses promote ModelSpec-derived trusted units.
- Solver preflight/run reverify generated bundle identity and semantics; tampered bundles fail before worker execution.
- The isolated worker records mixed NODE displacement/reaction and ELEMENT generalized-force channels into canonical `structural_response_series` from one solve.
- Existing SolverAdapter and permission-gated `fem_solver_run` remain the only real execution route.
- Only one new high-level Agent preparation tool is added: `fem_analysis_prepare_opensees` with CHECK/RENDER.
- Focused PR26 tests, full Python suite, Ruff, TypeScript typecheck/tests, health smoke, and OpenSees CI smoke pass from the latest HEAD.
- `main` remains unmodified by implementation work until the user explicitly authorizes merge.
