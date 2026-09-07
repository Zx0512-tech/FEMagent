# PR26 — Analysis Readiness + OpenSees Analysis Renderer Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Bind `EngineeringModelSpec` and `EngineeringAnalysisSpec` through deterministic OpenSees V1 Analysis Readiness, render a standalone linear-static OpenSees analysis bundle, verify it semantically before execution, and record every PR25 V1 result request through the existing isolated worker and Result Intelligence path.

**Architecture:** Python `fem_core` remains the engineering truth path. PR23 and PR26 share one pure ModelSpec→OpenSees source compiler; PR26 adds joint readiness, resolved response mappings, a four-file generated-analysis bundle, semantic manifest verification, and a private worker response context. TypeScript/Pi remain transport and tool surfaces only. Solver execution remains exclusively behind existing `fem_solver_preflight` and permission-gated `fem_solver_run`.

**Tech Stack:** Python >=3.13, pytest >=8.4,<9, Ruff >=0.12,<1, pinned OpenSeesPy through the existing `[opensees]` extra, Node >=22, TypeScript, pnpm, TypeBox, `femagent.bridge/v1`, current OpenSees Python adapter/worker, current `structural_response_series` Result Intelligence.

**Spec:** `docs/superpowers/specs/2026-09-07-pr26-analysis-readiness-opensees-renderer-design.md`

## Global Constraints

- V1 supports ModelSpec `2D / FRAME / CARTESIAN_XY / ELASTIC_FRAME_2D / EULER_BERNOULLI` and AnalysisSpec `LINEAR_STATIC` with exactly one explicit load case.
- Analysis Readiness statuses are `INVALID_SPEC | NOT_READY | READY`; renderer statuses are `BLOCKED | RENDERED`.
- `READY` requires intrinsic validity, Model Readiness, exact model fingerprint binding, exact force-unit equality, existing load/result targets, valid reaction restraint semantics, and proven OpenSees mappings for every result request.
- No unit conversion, load summation, target inference, sign correction, repair, Semantic Role inference, or solver-control inference.
- Reaction execution requires a restrained requested DOF: X→UX, Y→UY, Z moment→RZ.
- Moment units use machine-readable `force*length`, for example `N*m`, `kN*m`, `N*mm`, `kN*mm`.
- Arbitrary OpenSees Python bundles keep response `unit: null`; only verified PR26 generated analyses may promote ModelSpec-derived units.
- PR23 and PR26 share one deterministic ModelSpec→OpenSees source compiler and PR23 rendered bytes/hashes remain unchanged.
- Generated `analysis.py` contains model construction, explicit nodal loads, fixed static controls, and exactly one `ops.analyze(1)`; it contains no result extraction and no subprocess execution.
- Fixed static controls are `Plain` constraints, `Plain` numberer, `BandGeneral` system, `Linear` algorithm, `LoadControl(1.0)`, `Static`, one `analyze(1)`.
- Generated artifacts live only below `.femagent/generated-analyses/analysis_render_<16 hex>/`; callers cannot choose an output path.
- `response_plan.json` carries response identity only; it never carries trusted units, DOF/index, recorder commands, or arbitrary solver arguments.
- Generated-analysis preflight/run revalidate embedded normalized ModelSpec/AnalysisSpec, recompute fingerprints/readiness, regenerate expected source/plan, and compare artifacts before worker execution.
- Legacy arbitrary response-plan execution remains on its existing element-only runtime-domain path; PR26 NODE channels enter the worker only through verified generated-analysis response context.
- SolverAdapter remains the sole execution path. `fem_analysis_prepare_opensees(mode=RENDER)` may write controlled artifacts but never runs OpenSees and never broadens the current execution permission gate.
- PR26 keeps `kind = structural_response_series`; static pseudo-time/load state is solver-native abscissa, not seconds.
- PR26 excludes ANSYS rendering, PR27 natural-language completion, multiple load cases, distributed/gravity/thermal loads, modal/transient/spectrum/nonlinear analysis, customizable solver controls, repair, optimization, and new AnalysisSpec V1 fields.

---

## File Map

### Create
- `fem_core/model_spec/opensees_source.py` — shared pure ModelSpec→OpenSees construction compiler.
- `fem_core/opensees_response_mapping.py` — proven solver access mapping and trusted-unit derivation helpers.
- `fem_core/analysis_spec/readiness.py` — joint ModelSpec+AnalysisSpec readiness.
- `fem_core/analysis_spec/opensees_renderer.py` — four-file standalone analysis renderer.
- `fem_core/solvers/opensees_generated_analysis.py` — generated-analysis semantic verifier and private response-context builder.
- `tests/python/test_analysis_readiness.py`
- `tests/python/test_opensees_analysis_renderer.py`
- `tests/python/test_analysis_render_bridge.py`
- `tests/python/test_generated_opensees_analysis.py`
- `tests/python/test_pr26_golden_path.py`
- `tests/ts/analysis-readiness.test.ts`
- `tests/ts/analysis-prepare-tool-registration.test.ts`

### Modify
- `fem_core/model_spec/opensees_renderer.py`
- `fem_core/analysis_spec/__init__.py`
- `fem_core/opensees_response_plan.py`
- `fem_core/bridge.py`
- `fem_core/solvers/opensees_python.py`
- `fem_core/solvers/opensees_worker.py`
- `tests/python/test_opensees_model_renderer.py`
- `tests/python/test_opensees_response_plan.py`
- `tests/python/test_opensees_structural_response.py`
- `packages/fem-tools/src/analysisSpecTypes.ts`
- `packages/fem-tools/src/pythonBridge.ts`
- `packages/fem-tools/src/index.ts`
- `.pi/extensions/analysis-spec-tools.ts`
- `.pi/extensions/fem-tools.ts`
- `apps/agent/src/main.ts`

---

### Task 1: Shared PR23 Model Compiler

**Files:**
- Create: `fem_core/model_spec/opensees_source.py`
- Modify: `fem_core/model_spec/opensees_renderer.py`
- Test: `tests/python/test_opensees_model_renderer.py`

**Interfaces:**
- Produces `build_opensees_frame_2d_model_source(spec: dict[str, Any]) -> str`.
- Produces `format_opensees_number(value: Any) -> str`.
- PR23 `render_opensees_frame_2d()` public result remains byte-for-byte compatible.

- [ ] **Step 1: Write the failing shared-compiler regression test**

```python
from fem_core.model_spec.opensees_source import build_opensees_frame_2d_model_source
from fem_core.model_spec.validator import validate_engineering_model_spec


def test_shared_model_source_matches_pr23_rendered_model(tmp_path: Path) -> None:
    spec = load_model_fixture("simple-portal-frame.json")
    validation = validate_engineering_model_spec(spec)
    assert validation["status"] == "VALID"
    expected = build_opensees_frame_2d_model_source(validation["normalizedSpec"])
    report = render_opensees_frame_2d(tmp_path, spec)
    actual = (tmp_path / report["artifacts"]["modelPath"]).read_text(encoding="utf-8")
    assert actual == expected
```

- [ ] **Step 2: Run RED**

```bash
python -m pytest tests/python/test_opensees_model_renderer.py::test_shared_model_source_matches_pr23_rendered_model -q
```

Expected: import failure for `fem_core.model_spec.opensees_source`.

- [ ] **Step 3: Extract the current PR23 source logic without behavior changes**

Create `opensees_source.py` with:

```python
GEOM_TRANSF_TAG = 1


def format_opensees_number(value: Any) -> str:
    number = float(value)
    return "0.0" if number == 0.0 else repr(number)


def build_opensees_frame_2d_model_source(spec: dict[str, Any]) -> str:
    lines = [
        "import openseespy.opensees as ops",
        "",
        "ops.wipe()",
        'ops.model("basic", "-ndm", 2, "-ndf", 3)',
        "",
    ]
    # Move the existing node, constraint, mass, geomTransf, material/section lookup,
    # and elasticBeamColumn emission blocks here unchanged in ordering and literals.
    # Preserve the existing OPENSEES_RENDER_INTERNAL_INVARIANT error for lost refs.
    return "\n".join(lines) + "\n"
```

Implementation requirement: copy the current production blocks exactly from `fem_core/model_spec/opensees_renderer.py`; do not redesign them. Then replace PR23 private source generation with this helper.

- [ ] **Step 4: Run GREEN and PR23 regression**

```bash
python -m pytest tests/python/test_opensees_model_renderer.py -q
python -m ruff check fem_core/model_spec/opensees_source.py fem_core/model_spec/opensees_renderer.py tests/python/test_opensees_model_renderer.py
```

- [ ] **Step 5: Commit**

```bash
git add fem_core/model_spec/opensees_source.py fem_core/model_spec/opensees_renderer.py tests/python/test_opensees_model_renderer.py
git commit -m "refactor: share deterministic OpenSees model source compiler"
```

---

### Task 2: Response Mapping + Analysis Readiness

**Files:**
- Create: `fem_core/opensees_response_mapping.py`
- Create: `fem_core/analysis_spec/readiness.py`
- Modify: `fem_core/analysis_spec/__init__.py`
- Modify: `fem_core/opensees_response_plan.py`
- Test: `tests/python/test_analysis_readiness.py`
- Test: `tests/python/test_opensees_response_plan.py`

**Interfaces:**
- Produces `resolve_opensees_response_access(channel, *, element_type=None)`.
- Produces `derive_response_unit(channel, model_units)`.
- Produces `evaluate_engineering_analysis_readiness(model_spec, analysis_spec)`.

- [ ] **Step 1: Write RED readiness tests with a bound AnalysisSpec helper**

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
        "loadCases": [{
            "loadCaseId": "LC1",
            "nodalLoads": [{"nodeId": 3, "FX": 0.0, "FY": -10000.0, "MZ": 0.0}],
        }],
        "resultRequests": [
            {"requestId": "R_DISP", "loadCaseId": "LC1", "quantity": "DISPLACEMENT", "target": {"type": "NODE", "id": 3}, "component": "Y"},
            {"requestId": "R_RY", "loadCaseId": "LC1", "quantity": "REACTION_FORCE", "target": {"type": "NODE", "id": 1}, "component": "Y"},
            {"requestId": "R_MZ", "loadCaseId": "LC1", "quantity": "REACTION_MOMENT", "target": {"type": "NODE", "id": 1}, "component": "Z"},
            {"requestId": "R_ELE_MZ", "loadCaseId": "LC1", "quantity": "GENERALIZED_FORCE", "target": {"type": "ELEMENT", "id": 2}, "component": "MZ", "location": "END_J"},
        ],
    }
```

Assert valid pair → `READY`, profile `OPENSEES_FRAME_2D_LINEAR_STATIC_V1`, exact fingerprints, and responseMapping PASS.

- [ ] **Step 2: Add RED cases for every joint boundary**

Assert these exact outcomes:

```text
invalid ModelSpec -> INVALID_SPEC
invalid AnalysisSpec -> INVALID_SPEC
Model Readiness NOT_READY -> ANALYSIS_READINESS_MODEL_NOT_READY
fingerprint mismatch -> ANALYSIS_READINESS_MODEL_FINGERPRINT_MISMATCH
force unit mismatch -> ANALYSIS_READINESS_FORCE_UNIT_MISMATCH
missing load node -> ANALYSIS_READINESS_LOAD_NODE_NOT_FOUND
missing node result target -> ANALYSIS_READINESS_RESULT_NODE_NOT_FOUND
missing element result target -> ANALYSIS_READINESS_RESULT_ELEMENT_NOT_FOUND
reaction on unrestrained DOF -> ANALYSIS_READINESS_REACTION_DOF_UNRESTRAINED
```

Also assert a PR25-intrinsically-VALID target ID `999999` becomes PR26 `NOT_READY`.

- [ ] **Step 3: Run RED**

```bash
python -m pytest tests/python/test_analysis_readiness.py -q
```

Expected: missing readiness module/function.

- [ ] **Step 4: Implement shared response access mapping**

Use exact mappings:

```python
NODE_DOF = {"X": 1, "Y": 2, "Z": 3}
ELASTIC_BEAM_2D_LOCAL_FORCE = {
    ("N", "END_I"): 0,
    ("VY", "END_I"): 1,
    ("MZ", "END_I"): 2,
    ("N", "END_J"): 3,
    ("VY", "END_J"): 4,
    ("MZ", "END_J"): 5,
}
```

Resolver behavior:

```text
NODE DISPLACEMENT -> access NODE_DISP + dof + GLOBAL
NODE REACTION_FORCE/REACTION_MOMENT -> access NODE_REACTION + dof + GLOBAL
ELEMENT GENERALIZED_FORCE on ElasticBeam2d -> access ELEMENT_LOCAL_FORCE + response localForce + index + vectorLength 6 + ELEMENT_LOCAL
unsupported mapping -> FemCoreError STRUCTURAL_RESPONSE_MAPPING_UNAVAILABLE
```

Unit derivation:

```text
DISPLACEMENT -> model length
REACTION_FORCE -> model force
REACTION_MOMENT -> force*length
GENERALIZED_FORCE N/VY -> force
GENERALIZED_FORCE MZ -> force*length
```

Modify `opensees_response_plan.py` to reuse only the element access resolver for the legacy arbitrary response-plan path. Preserve its existing element-only domain restriction and `unit: null` behavior.

- [ ] **Step 5: Implement Analysis Readiness**

Order checks deterministically:

```text
1 intrinsic ModelSpec validation
2 intrinsic AnalysisSpec validation
3 Model Readiness
4 exact model fingerprint binding
5 exact force-unit equality
6 nodal load target existence
7 result target existence
8 reaction restraint DOF semantics
9 response access resolution and trusted unit derivation
```

`INVALID_SPEC` returns compact validations and SKIPPED dependent checks. `NOT_READY` and `READY` remain normal domain results. For V1 `ELASTIC_FRAME_2D`, pass runtime element type `ElasticBeam2d` to the proven resolver.

- [ ] **Step 6: Run GREEN**

```bash
python -m pytest tests/python/test_analysis_readiness.py tests/python/test_opensees_response_plan.py -q
python -m ruff check fem_core/opensees_response_mapping.py fem_core/analysis_spec/readiness.py fem_core/opensees_response_plan.py tests/python/test_analysis_readiness.py tests/python/test_opensees_response_plan.py
```

- [ ] **Step 7: Commit**

```bash
git add fem_core/opensees_response_mapping.py fem_core/analysis_spec/readiness.py fem_core/analysis_spec/__init__.py fem_core/opensees_response_plan.py tests/python/test_analysis_readiness.py tests/python/test_opensees_response_plan.py
git commit -m "feat: add OpenSees Analysis Readiness and response mappings"
```

---

### Task 3: Standalone OpenSees Analysis Renderer

**Files:**
- Create: `fem_core/analysis_spec/opensees_renderer.py`
- Modify: `fem_core/analysis_spec/__init__.py`
- Test: `tests/python/test_opensees_analysis_renderer.py`

**Interfaces:**
- Produces `build_opensees_linear_static_analysis_source(normalized_model_spec, normalized_analysis_spec)`.
- Produces `build_structural_response_plan(normalized_analysis_spec)`.
- Produces `render_opensees_linear_static_analysis(workspace, model_spec, analysis_spec)`.

- [ ] **Step 1: Write RED four-file bundle tests**

Assert successful render creates:

```text
analysis.py
response_plan.json
analysis_readiness.json
analysis_manifest.json
```

Assert `analysis.py` contains:

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

Assert exactly one `ops.analyze(` and absence of `nodeDisp`, `nodeReaction`, `eleResponse`, `subprocess`, and result-file writing.

- [ ] **Step 2: Add RED manifest/plan/determinism/blocking tests**

`response_plan.json` must contain only `channelId`, `quantity`, `target`, `component`, optional `location`, sorted by requestId. It must not contain unit/access/dof/index/recorder metadata.

Manifest must contain normalizedModelSpec, normalizedAnalysisSpec, both fingerprints, readiness profile, units, loadCaseId, trusted responseMappings, artifact paths/hashes, renderer identity, and analysisRenderFingerprint.

Also assert:

```text
NOT_READY -> BLOCKED with ANALYSIS_NOT_READY and no partial directory
semantic reordering -> identical source/plan/readiness hashes and analysisRenderFingerprint
repeat render -> different renderId allowed, same deterministic content identity
write failure -> cleanup + OPENSEES_ANALYSIS_RENDER_WRITE_FAILED
```

- [ ] **Step 3: Run RED**

```bash
python -m pytest tests/python/test_opensees_analysis_renderer.py -q
```

- [ ] **Step 4: Implement renderer**

Renderer constants:

```python
RENDER_SCHEMA = "FEMAGENT_OPENSEES_ANALYSIS_RENDER_V1"
RENDERER_NAME = "OPENSEES_FRAME_2D_LINEAR_STATIC_V1"
RENDERER_VERSION = "1.0"
SUPPORTED_READINESS_PROFILE = "OPENSEES_FRAME_2D_LINEAR_STATIC_V1"
```

Implementation sequence:

```text
rerun readiness
BLOCKED unless READY
revalidate both specs and require fingerprints agree with readiness
build model source through shared PR23 compiler
append sorted explicit loads and fixed V1 static controls
build strict response plan from normalized resultRequests
serialize exact readiness report
compute source/plan/readiness SHA256
compute analysisRenderFingerprint from canonical identity fields
create fresh controlled directory
write four files; cleanup on failed publication
```

- [ ] **Step 5: Run GREEN**

```bash
python -m pytest tests/python/test_opensees_analysis_renderer.py tests/python/test_opensees_model_renderer.py tests/python/test_analysis_readiness.py -q
python -m ruff check fem_core/analysis_spec/opensees_renderer.py tests/python/test_opensees_analysis_renderer.py
```

- [ ] **Step 6: Commit**

```bash
git add fem_core/analysis_spec/opensees_renderer.py fem_core/analysis_spec/__init__.py tests/python/test_opensees_analysis_renderer.py
git commit -m "feat: render standalone OpenSees linear-static analyses"
```

---

### Task 4: Bridge, TypeScript Contract, High-Level Analysis Tool

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
- Bridge commands: `analysis.readiness`, `analysis.renderOpenSees`.
- TS wrappers: `runFemAnalysisReadiness`, `runFemAnalysisRenderOpenSees`.
- Agent tool: `fem_analysis_prepare_opensees` with `mode: CHECK | RENDER`.

- [ ] **Step 1: Write bridge RED tests**

Assert READY/RENDERED, NOT_READY/BLOCKED as `ok=true`, and non-object modelSpec/analysisSpec as `INVALID_ARGUMENT`.

- [ ] **Step 2: Run RED**

```bash
python -m pytest tests/python/test_analysis_render_bridge.py -q
```

Expected: `UNKNOWN_COMMAND`.

- [ ] **Step 3: Add bridge dispatch only**

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

- [ ] **Step 4: Write TypeScript RED tests and types**

Add discriminated mapping types for NODE_DISP, NODE_REACTION, ELEMENT_LOCAL_FORCE plus readiness/render results. Add thin wrappers using exact bridge command strings. Export through `index.ts`. TypeScript must not calculate any engineering fact.

Run before implementation:

```bash
pnpm test:ts
```

Expected: missing new exports.

- [ ] **Step 5: Write Agent registration RED test**

Assert one tool `fem_analysis_prepare_opensees`, CHECK→readiness wrapper, RENDER→render wrapper, no `runFemSolverRun`, no `outputPath`, no separate public `fem_analysis_readiness`/`fem_analysis_render_opensees`, and Agent allow-list registration.

- [ ] **Step 6: Implement one high-level Analysis tool**

Use strict existing ModelSpec/AnalysisSpec TypeBox schemas and:

```ts
const report = params.mode === "CHECK"
  ? await runFemAnalysisReadiness(ctx.cwd, params.modelSpec, params.analysisSpec, signal)
  : await runFemAnalysisRenderOpenSees(ctx.cwd, params.modelSpec, params.analysisSpec, signal);
return toolResult(report);
```

Guidance must state CHECK is read-only; RENDER writes only controlled artifacts; neither runs a solver; READY/RENDERED are not execution success; engineering facts must not be mutated to force readiness.

- [ ] **Step 7: Run GREEN and commit**

```bash
python -m pytest tests/python/test_analysis_render_bridge.py -q
pnpm typecheck
pnpm test:ts
python -m ruff check fem_core/bridge.py tests/python/test_analysis_render_bridge.py

git add fem_core/bridge.py tests/python/test_analysis_render_bridge.py packages/fem-tools/src/analysisSpecTypes.ts packages/fem-tools/src/pythonBridge.ts packages/fem-tools/src/index.ts tests/ts/analysis-readiness.test.ts .pi/extensions/analysis-spec-tools.ts apps/agent/src/main.ts tests/ts/analysis-prepare-tool-registration.test.ts
git commit -m "feat: expose high-level OpenSees analysis preparation"
```

---

### Task 5: Generated-Analysis Semantic Verification in Solver Preflight

**Files:**
- Create: `fem_core/solvers/opensees_generated_analysis.py`
- Modify: `fem_core/bridge.py`
- Modify: `fem_core/solvers/opensees_python.py`
- Modify: `.pi/extensions/fem-tools.ts`
- Test: `tests/python/test_generated_opensees_analysis.py`

**Interfaces:**
- Produces `verify_generated_analysis_bundle(workspace, *, model_path, response_plan_path, manifest_path)`.
- OpenSees solverOptions become `{ responsePlanPath?, analysisManifestPath? }` only.

- [ ] **Step 1: Write RED verifier test from a fresh rendered bundle**

Assert verifier returns matching analysisRenderFingerprint, READY readiness, and private responseContext channel IDs matching the rendered requests.

- [ ] **Step 2: Add RED tamper/mixing cases**

Exact error classes:

```text
bad manifest schema or missing embedded specs -> GENERATED_ANALYSIS_MANIFEST_INVALID
supplied model/plan paths differ from manifest -> GENERATED_ANALYSIS_PATH_MISMATCH
changed analysis.py/response_plan/readiness bytes -> GENERATED_ANALYSIS_ARTIFACT_MISMATCH
changed embedded spec/fingerprint or render fingerprint -> GENERATED_ANALYSIS_FINGERPRINT_MISMATCH
```

Also mutate `analysis.py`, update manifest hash/fingerprint to be internally self-consistent, and assert failure because regenerated expected source from embedded normalized specs does not match actual source.

- [ ] **Step 3: Run RED**

```bash
python -m pytest tests/python/test_generated_opensees_analysis.py -q
```

- [ ] **Step 4: Implement semantic verifier**

Verification order:

```text
resolve workspace paths
parse exact PR26 manifest schema/renderer identity
require supplied paths equal manifest paths
revalidate embedded normalized ModelSpec/AnalysisSpec
recompute and compare both fingerprints
rerun Analysis Readiness and require READY/profile
regenerate expected analysis source
regenerate expected response plan
serialize recomputed readiness with renderer serialization contract
compare expected bytes/hashes with actual artifacts and manifest hashes
recompute analysisRenderFingerprint
construct private responseContext from recomputed readiness mappings
```

Never read trusted unit/access fields from `response_plan.json`.

- [ ] **Step 5: Extend solverOptions without weakening legacy path**

`bridge.py` OpenSees allow-list becomes exactly:

```python
{"responsePlanPath", "analysisManifestPath"}
```

`.pi/extensions/fem-tools.ts` adds optional `analysisManifestPath` and guidance requiring it to come from the same PR26 render as responsePlanPath.

- [ ] **Step 6: Integrate verifier into preflight**

Rules:

```text
no analysisManifestPath -> existing arbitrary Python behavior unchanged and element-only response-plan domain validation remains active
analysisManifestPath -> responsePlanPath required, loadPath omitted, semantic verifier required before build/run admission
```

For generated path, do not call the legacy element-only response-plan domain validator on mixed NODE/ELEMENT requests. After build inspection, require realized node/element tags to match embedded normalized ModelSpec IDs exactly. Add generated provenance checks and fingerprints to preflight report.

- [ ] **Step 7: Run GREEN and commit**

```bash
python -m pytest tests/python/test_generated_opensees_analysis.py tests/python/test_opensees_structural_response.py -q
pnpm typecheck
pnpm test:ts
python -m ruff check fem_core/solvers/opensees_generated_analysis.py fem_core/solvers/opensees_python.py fem_core/bridge.py tests/python/test_generated_opensees_analysis.py

git add fem_core/solvers/opensees_generated_analysis.py fem_core/bridge.py fem_core/solvers/opensees_python.py .pi/extensions/fem-tools.ts tests/python/test_generated_opensees_analysis.py
git commit -m "feat: verify generated OpenSees analysis bundles before execution"
```

---

### Task 6: Verified Worker Response Context + Real Mapping Proof

**Files:**
- Modify: `fem_core/solvers/opensees_python.py`
- Modify: `fem_core/solvers/opensees_worker.py`
- Modify: `tests/python/test_opensees_structural_response.py`
- Modify: `tests/python/test_generated_opensees_analysis.py`

**Interfaces:**
- Generated run stages private `response_context.verified.json` and passes `--response-context`.
- Arbitrary run retains legacy `--response-plan` and untrusted units.

- [ ] **Step 1: Write a real pinned-OpenSeesPy cantilever test**

Use `L=2.0 m`, `P=1000.0 N`, one fixed node, one free node, one elastic frame element, vertical tip load. Request tip displacement Y, support reaction Y, support reaction moment Z, element N/VY/MZ at END_I.

Assertions:

```python
assert reaction_y == pytest.approx(P, rel=1e-9, abs=1e-7)
assert abs(reaction_mz) == pytest.approx(P * L, rel=1e-9, abs=1e-7)
assert abs(element_shear_i) == pytest.approx(P, rel=1e-9, abs=1e-7)
assert abs(element_mz_i) == pytest.approx(P * L, rel=1e-9, abs=1e-7)
assert displacement_y < 0.0
```

Skip only when OpenSees optional dependency is genuinely unavailable.

- [ ] **Step 2: Add trusted/untrusted unit RED tests**

Generated bundle must emit `m`, `N`, `N*m` as appropriate. Arbitrary user Python + legacy response plan must still emit `unit is None`.

- [ ] **Step 3: Run RED**

```bash
python -m pytest tests/python/test_opensees_structural_response.py tests/python/test_generated_opensees_analysis.py -q
```

Expected: generated NODE response execution unsupported by current worker.

- [ ] **Step 4: Stage verified context during generated run**

Just before execution, rerun generated-bundle verification. Write `run_dir/response_context.verified.json` from verifier responseContext and pass `--response-context` to worker. Still stage normalized response plan for provenance.

- [ ] **Step 5: Extend worker sampling**

After successful analyze:

```python
if any(channel["access"] == "NODE_REACTION" for channel in channels):
    ops.reactions()
```

Per channel:

```text
NODE_DISP -> ops.nodeDisp(targetId, dof)
NODE_REACTION -> ops.nodeReaction(targetId, dof)
ELEMENT_LOCAL_FORCE -> ops.eleResponse(targetId, response), exact vectorLength check, verified index
```

Require finite abscissa/value. Emit existing `structural_response_series` with unit/referenceFrame from verified context. Legacy arbitrary response plan continues its element-only validation and emits `unit: null`.

- [ ] **Step 6: Add generatedAnalysis provenance to run manifest**

Generated runs include:

```json
{
  "analysisRenderFingerprint": "<verified fingerprint>",
  "modelSpecFingerprint": "<verified fingerprint>",
  "analysisSpecFingerprint": "<verified fingerprint>",
  "analysisManifestSha256": "<verified sha256>"
}
```

Arbitrary Python runs do not claim this provenance.

- [ ] **Step 7: Run GREEN and commit**

```bash
python -m pytest tests/python/test_opensees_structural_response.py tests/python/test_generated_opensees_analysis.py -q
python -m ruff check fem_core/solvers/opensees_python.py fem_core/solvers/opensees_worker.py tests/python/test_opensees_structural_response.py tests/python/test_generated_opensees_analysis.py

git add fem_core/solvers/opensees_python.py fem_core/solvers/opensees_worker.py tests/python/test_opensees_structural_response.py tests/python/test_generated_opensees_analysis.py
git commit -m "feat: record verified generated-analysis responses"
```

---

### Task 7: Full PR26 Golden Path + Tamper + Result Intelligence

**Files:**
- Create: `tests/python/test_pr26_golden_path.py`
- Modify: `tests/python/test_generated_opensees_analysis.py`
- Modify only if a failing canonical-query test proves necessary: `fem_core/result_intelligence.py`

**Interfaces:**
- Proves ModelSpec VALID → AnalysisSpec VALID → Analysis READY → RENDERED → solver preflight READY → worker COMPLETED → structural_response → Result Intelligence.

- [ ] **Step 1: Write full golden-path test**

Call authoritative validators/readiness/renderer, then:

```python
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
```

Run with the same paths/options and assert `COMPLETED`.

- [ ] **Step 2: Query mixed response classes from the same solve**

The same run must expose requested NODE displacement, NODE reaction force, NODE reaction moment, and ELEMENT N/VY/MZ through canonical Result Intelligence. Do not modify Result Intelligence unless the test proves a valid `structural_response_series` quantity is rejected; if so, add one focused failing query test before the smallest compatibility fix.

- [ ] **Step 3: Add determinism assertions**

Semantic collection reordering must preserve modelSpecFingerprint, analysisSpecFingerprint, analysis source SHA, response plan SHA, readiness SHA, and analysisRenderFingerprint. Render IDs may differ.

- [ ] **Step 4: Add real adapter tamper assertions**

Tamper analysis source, response plan, readiness artifact, manifest paths, manifest hashes/fingerprint, and embedded normalized specs separately. `adapter.preflight()` must fail before creating any new run directory.

- [ ] **Step 5: Run GREEN**

```bash
python -m pytest tests/python/test_analysis_readiness.py tests/python/test_opensees_analysis_renderer.py tests/python/test_analysis_render_bridge.py tests/python/test_generated_opensees_analysis.py tests/python/test_opensees_response_plan.py tests/python/test_opensees_structural_response.py tests/python/test_pr26_golden_path.py -q
```

- [ ] **Step 6: Commit**

```bash
git add tests/python/test_pr26_golden_path.py tests/python/test_generated_opensees_analysis.py
git commit -m "test: prove PR26 OpenSees analysis golden path"
```

If Result Intelligence required a proven compatibility fix, stage its source and focused test in this same commit.

---

### Task 8: Full Verification + Scope Audit

**Files:**
- No new production files by default.
- Any correction must stay within the PR26 File Map and be driven by a failing test.

- [ ] **Step 1: Run focused PR26 suite from latest HEAD**

```bash
python -m pytest tests/python/test_analysis_readiness.py tests/python/test_opensees_analysis_renderer.py tests/python/test_analysis_render_bridge.py tests/python/test_generated_opensees_analysis.py tests/python/test_opensees_response_plan.py tests/python/test_opensees_structural_response.py tests/python/test_pr26_golden_path.py -q
```

- [ ] **Step 2: Run full repository verification**

```bash
python -m pytest tests/python -q
python -m ruff check fem_core tests/python
pnpm typecheck
pnpm test:ts
pnpm fem:health
```

CI must also pass its existing real OpenSees availability smoke on the latest PR26 HEAD.

- [ ] **Step 3: Scope audit `main...HEAD`**

Verify all are true:

```text
no ANSYS renderer/analysis behavior
no PR27 natural-language completion
no new AnalysisSpec V1 fields
no distributed/gravity/thermal/load-combination support
no modal/transient/nonlinear/spectrum path
no caller-selected solver controls
no unit conversion
no duplicate ModelSpec→OpenSees compiler
no result extraction inside generated analysis.py
no alternate solver execution path
no permission-gate broadening
no trusted unit from response_plan.json
legacy arbitrary response-plan path remains element-only
no worker-side trusted engineering reinterpretation for generated analyses
no separate public fem_analysis_readiness/fem_analysis_render_opensees tools
```

Confirm temporary `fem_analysis_spec_validate` remains and only one new LLM-visible Analysis preparation tool exists.

- [ ] **Step 4: Diff hygiene**

```bash
git diff --check main...HEAD
git diff --stat main...HEAD
git status --short
```

- [ ] **Step 5: Correct only verified defects**

For any defect: add or identify a focused failing test, confirm RED, make the smallest correction, confirm GREEN, then rerun Step 2.

- [ ] **Step 6: Commit final correction only when needed**

Use the exact matching message:

```text
fix: preserve PR26 analysis readiness invariants
fix: preserve generated OpenSees analysis integrity
fix: preserve PR26 response provenance
```

## Completion Gate

PR26 is implementation-complete only when:

- Analysis Readiness enforces the approved joint checks and statuses.
- Every PR25 V1 result request has a real pinned-OpenSeesPy proven mapping.
- Unrestrained reaction requests are NOT_READY.
- Force units match exactly and no hidden conversion occurs.
- PR23/PR26 share one model compiler with PR23 regression stability.
- READY pairs render the exact four-file standalone bundle.
- Generated source never extracts results or runs a subprocess.
- Verification reconstructs semantics from embedded normalized specs instead of trusting mutable manifest hashes alone.
- Arbitrary OpenSees plans keep `unit: null`; only verified generated analyses get trusted ModelSpec-derived units.
- Generated preflight/run reverify semantic identity; tampering fails before worker execution.
- Worker records mixed NODE and ELEMENT channels from one solve into canonical `structural_response_series`.
- SolverAdapter and permission-gated `fem_solver_run` remain the only real execution route.
- Only one new high-level Agent tool is added: `fem_analysis_prepare_opensees` CHECK/RENDER.
- Focused tests, full Python suite, Ruff, TS typecheck/tests, health smoke, and OpenSees CI smoke all pass at latest HEAD.
- `main` remains unmodified until the user explicitly authorizes merge.
