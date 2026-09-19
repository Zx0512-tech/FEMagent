# PR28 — V2 Analysis Readiness + OpenSees Renderers Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make EngineeringAnalysisSpec V2 `LINEAR_STATIC`, `MODAL`, and both `TRANSIENT` excitation profiles executable through one controlled OpenSees readiness → render → verify → isolated-worker → canonical-result pipeline while preserving the PR26 V1 static path.

**Architecture:** Keep one public preparation capability and route internally through exact OpenSees execution profiles. V2 readiness owns model/artifact/solver-mapping truth; profile compilers produce deterministic analysis source and response contracts; a shared publisher/verifier preserves provenance and fingerprints; the existing OpenSees bundle adapter remains the sole solver execution gate.

**Tech Stack:** Python 3.13, OpenSeesPy, TypeScript, TypeBox, pnpm, pytest, Ruff, GitHub Actions.

**Spec:** `docs/superpowers/specs/2026-09-10-pr28-v2-readiness-opensees-renderers-design.md`

## Global Constraints

- Stacked base is PR27 HEAD `c25422b6467257d7b270aae6f19b4f476afa0174`; do not merge PR28 before PR27 lands and PR28 is rebased/retargeted cleanly.
- Preserve `OPENSEES_FRAME_2D_LINEAR_STATIC_V1`, `FEMAGENT_ANALYSIS_READINESS_V1`, `FEMAGENT_OPENSEES_ANALYSIS_RENDER_V1`, and `FEMAGENT_GENERATED_ANALYSIS_VERIFICATION_V1` behavior and fingerprints.
- V2 readiness schema is exactly `FEMAGENT_ANALYSIS_READINESS_V2`.
- V2 render schema is exactly `FEMAGENT_OPENSEES_ANALYSIS_RENDER_V2`.
- V2 verification schema is exactly `FEMAGENT_GENERATED_ANALYSIS_VERIFICATION_V2`.
- V2 renderer version is exactly `2.0`.
- V2 profiles are exactly `OPENSEES_FRAME_2D_LINEAR_STATIC_V2`, `OPENSEES_FRAME_2D_MODAL_V2`, `OPENSEES_FRAME_2D_TRANSIENT_NODAL_FORCE_V2`, and `OPENSEES_FRAME_2D_TRANSIENT_UNIFORM_BASE_V2`.
- `VALID` never implies `READY`, `RENDERED`, `VERIFIED`, or `COMPLETED`.
- `ABSOLUTE_ACCELERATION` under `UNIFORM_BASE_EXCITATION` remains `NOT_READY` with `ANALYSIS_READINESS_ABSOLUTE_ACCELERATION_MAPPING_UNPROVEN`.
- Controlled transient artifacts begin at zero seconds, use a uniform time step, and end at AnalysisSpec `duration` after deterministic unit conversion.
- `NODAL_TIME_HISTORY` and `UNIFORM_BASE_EXCITATION` both execute in PR28.
- `NODAL_TIME_HISTORY` requires `analysisSpec.units.force == modelSpec.units.force`; canonical artifact N values are converted to that shared force unit.
- Transient integration is fixed to `Plain` constraints, `Plain` numberer, `BandGeneral` system, `Linear` algorithm, and `Newmark(0.5, 0.25)` integrator.
- `RAYLEIGH` maps exactly to `ops.rayleigh(alphaM, betaK, 0.0, 0.0)`; no damping-ratio inference or default damping.
- Modal renderer emits exactly one `ops.eigen(modeCount)` call; the real numerical solve occurs only in `modal-run`, never in build inspection.
- Modal worker results come from real `ops.eigen(...)` and `ops.nodeEigenvector(...)`; renderers never compute numerical modal results.
- Transient structural response samples are recorded only after each successful `ops.analyze(1, dt)` call. No synthetic `t=0` result sample is inserted. For duration `T` and step `dt`, the series has `T/dt` samples with abscissa `dt, 2dt, ..., T` when the ratio is integral.
- Generated-analysis verification is mandatory before solver execution.
- Keep existing Agent tool names; do not add profile-specific LLM-visible tools.
- OpenSees generated-bundle solver options remain exactly `{responsePlanPath, analysisManifestPath}`; execution mode is derived from verified bundle context, never user-selected.
- Do not modify ANSYS execution, natural-language Analysis Completion, Controlled Repair, nonlinear analysis, optimization, or Semantic Role inference in PR28.
- Standard final verification: `pnpm typecheck`, `pnpm test:ts`, `python -m pytest`, `python -m ruff check fem_core tests/python examples/ansys/golden_path`, OpenSees/ANSYS smoke checks, and `pnpm fem:health`.

## File Structure

New focused modules:

- `fem_core/analysis_spec/opensees_profiles/__init__.py` — profile constants and public profile-selection exports.
- `fem_core/analysis_spec/opensees_profiles/registry.py` — exact validated AnalysisSpec → OpenSees profile routing.
- `fem_core/analysis_spec/opensees_profiles/common.py` — shared V2 readiness target/reaction/mapping/unit helpers.
- `fem_core/analysis_spec/opensees_profiles/static_v2.py` — V2 static readiness and compilation adapters.
- `fem_core/analysis_spec/opensees_profiles/modal_v2.py` — modal readiness, modal response plan, and source builder.
- `fem_core/analysis_spec/opensees_profiles/transient_v2.py` — transient readiness, artifact evidence, conversions, and source builders.
- `fem_core/analysis_spec/transient_artifact.py` — strict one-channel `FEMAGENT_LOAD_CSV_V1` reader for PR28 readiness.
- `fem_core/analysis_spec/opensees_renderer_v2.py` — shared V2 generated-analysis publisher and render fingerprinting.
- `fem_core/modal_results.py` — canonical `modal_result_set` construction/validation/query helpers.

Existing modules modified only where their current responsibility already applies:

- `fem_core/analysis_spec/readiness.py` — preserve V1 path and dispatch supported V2 profiles.
- `fem_core/analysis_spec/opensees_renderer.py` — expose reusable V1 static compiler primitives without changing V1 output.
- `fem_core/analysis_spec/__init__.py` — export one version-aware OpenSees render entry point while preserving legacy export.
- `fem_core/opensees_response_mapping.py` — add proven transient node velocity/acceleration mappings and units.
- `fem_core/solvers/opensees_generated_analysis.py` — V1/V2 verification router and trusted V2 contexts.
- `fem_core/solvers/opensees_worker.py` — build-only eigen interception, transient sampling access, modal execution mode.
- `fem_core/solvers/opensees_python.py` — verified V2 bundle admission and execution-mode routing.
- `fem_core/result_intelligence.py` — canonical modal result inspection/query and transient structural-response semantics.
- `fem_core/bridge.py` — pass workspace to readiness and use version-aware renderer.
- `packages/fem-tools/src/analysisSpecTypes.ts` — V1/V2 readiness/render unions and response mappings.
- `packages/fem-tools/src/pythonBridge.ts` — widen existing readiness/render functions to `FemEngineeringAnalysisSpecInput`.
- `.pi/extensions/analysis-spec-tools.ts` — widen only `fem_analysis_prepare_opensees`; update guidance from “future V2 readiness” to current PR28 behavior.

---

### Task 1: Profile Registry and Version-Aware Readiness Dispatch

**Files:**
- Create: `fem_core/analysis_spec/opensees_profiles/__init__.py`
- Create: `fem_core/analysis_spec/opensees_profiles/registry.py`
- Modify: `fem_core/analysis_spec/readiness.py`
- Create: `tests/python/test_analysis_profile_registry.py`
- Test: `tests/python/test_analysis_readiness.py`

**Interfaces:**
- Produces: `select_opensees_analysis_profile(normalized_analysis_spec: dict[str, Any]) -> str`.
- Produces: `evaluate_engineering_analysis_readiness(model_spec: dict[str, Any], analysis_spec: dict[str, Any], *, workspace: Path | None = None) -> dict[str, Any]`.
- Preserves V1 calls without `workspace` and exact V1 report/profile identity.

- [ ] **Step 1: Write failing routing tests using explicit validated specs**

In `tests/python/test_analysis_profile_registry.py`, define a minimal valid bound ModelSpec helper and explicit AnalysisSpec dictionaries in the test file. Load the existing PR27 fixtures for V2 shapes and replace `modelSpecFingerprint` with the validated model fingerprint. For transient fixtures, only routing is tested; artifact bytes are not read by registry selection.

```python
@pytest.mark.parametrize(
    ("fixture_name", "profile"),
    [
        ("simple-linear-static-v2.json", "OPENSEES_FRAME_2D_LINEAR_STATIC_V2"),
        ("simple-modal-v2.json", "OPENSEES_FRAME_2D_MODAL_V2"),
        ("simple-transient-nodal-v2.json", "OPENSEES_FRAME_2D_TRANSIENT_NODAL_FORCE_V2"),
        ("simple-transient-base-v2.json", "OPENSEES_FRAME_2D_TRANSIENT_UNIFORM_BASE_V2"),
    ],
)
def test_selects_exact_v2_profile(fixture_name: str, profile: str) -> None:
    spec = json.loads((FIXTURE_DIR / fixture_name).read_text(encoding="utf-8"))
    validation = validate_engineering_analysis_spec(spec)
    assert validation["status"] == "VALID"
    assert select_opensees_analysis_profile(validation["normalizedSpec"]) == profile
```

Add one explicit V1 static dictionary and assert `OPENSEES_FRAME_2D_LINEAR_STATIC_V1`.

- [ ] **Step 2: Run RED**

Run: `python -m pytest tests/python/test_analysis_profile_registry.py tests/python/test_analysis_readiness.py -q`

Expected: new registry import/selection tests fail; existing V1 readiness assertions remain green.

- [ ] **Step 3: Implement exact registry and a V2 dispatch shell**

```python
def select_opensees_analysis_profile(spec: dict[str, Any]) -> str:
    version = spec["schemaVersion"]
    analysis_type = spec["analysisType"]
    if version == "1.0" and analysis_type == "LINEAR_STATIC":
        return OPENSEES_STATIC_V1
    if version == "2.0" and analysis_type == "LINEAR_STATIC":
        return OPENSEES_STATIC_V2
    if version == "2.0" and analysis_type == "MODAL":
        return OPENSEES_MODAL_V2
    if version == "2.0" and analysis_type == "TRANSIENT":
        excitation = spec["definition"]["excitation"]["type"]
        if excitation == "NODAL_TIME_HISTORY":
            return OPENSEES_TRANSIENT_NODAL_V2
        if excitation == "UNIFORM_BASE_EXCITATION":
            return OPENSEES_TRANSIENT_BASE_V2
    raise FemCoreError("ANALYSIS_READINESS_UNSUPPORTED_PROFILE", "Unsupported OpenSees analysis profile")
```

For Task 1, validated V2 profiles return `NOT_READY` with selected profile and profile-specific checks `SKIPPED`; do not mark any V2 profile READY yet.

- [ ] **Step 4: Run GREEN and V1 regression**

Run: `python -m pytest tests/python/test_analysis_profile_registry.py tests/python/test_analysis_readiness.py tests/python/test_pr26_golden_path.py -q`

Expected: PASS; PR26 V1 path retains schema/profile identity and golden behavior.

- [ ] **Step 5: Commit**

```bash
git add fem_core/analysis_spec/opensees_profiles fem_core/analysis_spec/readiness.py tests/python/test_analysis_profile_registry.py tests/python/test_analysis_readiness.py
git commit -m "feat: add OpenSees V2 analysis profile registry"
```

### Task 2: Shared Readiness Primitives and V2 Linear Static Readiness

**Files:**
- Create: `fem_core/analysis_spec/opensees_profiles/common.py`
- Create: `fem_core/analysis_spec/opensees_profiles/static_v2.py`
- Modify: `fem_core/analysis_spec/readiness.py`
- Create: `tests/python/test_analysis_readiness_v2_static.py`
- Modify: `tests/python/test_analysis_readiness.py`

**Interfaces:**
- Produces: `evaluate_static_v2_readiness(*, model_validation: dict[str, Any], analysis_validation: dict[str, Any], normalized_model: dict[str, Any], normalized_analysis: dict[str, Any]) -> dict[str, Any]`.
- Shared helpers accept explicit normalized specs; no undefined context object or second truth store is introduced.
- Consumes V2 static loads from `normalized_analysis["definition"]["loadCases"]` directly; never calls V1 migration.

- [ ] **Step 1: Write V2 Static RED tests**

```python
def test_v2_static_is_ready_without_v1_identity_conversion() -> None:
    report = evaluate_engineering_analysis_readiness(model, v2_static)
    assert report["schema"] == "FEMAGENT_ANALYSIS_READINESS_V2"
    assert report["status"] == "READY"
    assert report["profile"] == "OPENSEES_FRAME_2D_LINEAR_STATIC_V2"
    assert report["analysisSpecFingerprint"] == validate_engineering_analysis_spec(v2_static)["analysisSpecFingerprint"]
```

Add cases for missing load node, missing result node/element, unrestrained reaction, model fingerprint mismatch, and force-unit mismatch. Assert existing stable issue families where semantics are identical. Replace the PR27-era `test_valid_v2_is_not_admitted_to_pr26_v1_readiness` only after observing its expected stale failure once V2 Static admission is implemented; retain explicit tests proving V1 still reports V1 schema/profile.

- [ ] **Step 2: Run RED**

Run: `python -m pytest tests/python/test_analysis_readiness_v2_static.py -q`

Expected: V2 Static remains `NOT_READY` from Task 1 shell.

- [ ] **Step 3: Extract shared deterministic checks and implement Static V2 readiness**

Move reusable target/reaction/mapping calculations into `common.py` without changing V1 report content. Build the V2 response from the same engineering facts but under `FEMAGENT_ANALYSIS_READINESS_V2` and `OPENSEES_FRAME_2D_LINEAR_STATIC_V2`.

- [ ] **Step 4: Run GREEN plus V1 readiness regression**

Run: `python -m pytest tests/python/test_analysis_readiness_v2_static.py tests/python/test_analysis_readiness.py tests/python/test_pr26_golden_path.py -q`

Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add fem_core/analysis_spec/opensees_profiles/common.py fem_core/analysis_spec/opensees_profiles/static_v2.py fem_core/analysis_spec/readiness.py tests/python/test_analysis_readiness_v2_static.py tests/python/test_analysis_readiness.py
git commit -m "feat: add V2 linear static OpenSees readiness"
```

### Task 3: V2 Modal Readiness and Proven Modal Response Mapping

**Files:**
- Create: `fem_core/analysis_spec/opensees_profiles/modal_v2.py`
- Modify: `fem_core/analysis_spec/readiness.py`
- Create: `tests/python/test_analysis_readiness_v2_modal.py`

**Interfaces:**
- Produces: `positive_free_translational_mass_dofs(model_spec: dict[str, Any]) -> list[tuple[int, str]]`.
- Produces: `evaluate_modal_v2_readiness(*, model_validation: dict[str, Any], analysis_validation: dict[str, Any], normalized_model: dict[str, Any], normalized_analysis: dict[str, Any]) -> dict[str, Any]`.
- Modal response mapping records `mode`, `quantity`, optional NODE target/component, DOF for MODE_SHAPE, and unit semantics: eigenvalue `1/<time>2`, frequency `Hz`, period `<time>`, mode shape `1` with `normalization="OPENSEES_NATIVE"` deferred until solver result.

- [ ] **Step 1: Write modal RED tests**

```python
assert ready["profile"] == "OPENSEES_FRAME_2D_MODAL_V2"
assert ready["checks"]["modalMass"]["positiveFreeTranslationalDofCount"] == 2
assert "ANALYSIS_READINESS_MODAL_MASS_REQUIRED" in issue_codes(no_mass)
assert "ANALYSIS_READINESS_MODAL_FREE_MASS_DOF_REQUIRED" in issue_codes(all_mass_restrained)
assert "ANALYSIS_READINESS_MODAL_MODE_COUNT_EXCEEDS_DOF_BOUND" in issue_codes(too_many_modes)
assert "ANALYSIS_READINESS_RESULT_NODE_NOT_FOUND" in issue_codes(missing_mode_shape_node)
```

Assert X/Y/RZ MODE_SHAPE requests map to OpenSees DOF 1/2/3. Scalar EIGENVALUE/NATURAL_FREQUENCY/PERIOD mappings contain no target.

- [ ] **Step 2: Run RED**

Run: `python -m pytest tests/python/test_analysis_readiness_v2_modal.py -q`

Expected: modal profile is not READY because profile-specific readiness is absent.

- [ ] **Step 3: Implement conservative modal readiness**

Count a translational DOF only when `mUX > 0` or `mUY > 0` and the corresponding `UX`/`UY` is not constrained. Do not inspect assembled matrices or claim numerical rank, repeated-mode behavior, or eigensolver convergence.

- [ ] **Step 4: Run GREEN**

Run: `python -m pytest tests/python/test_analysis_readiness_v2_modal.py tests/python/test_analysis_spec_v2_modal.py -q`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add fem_core/analysis_spec/opensees_profiles/modal_v2.py fem_core/analysis_spec/readiness.py tests/python/test_analysis_readiness_v2_modal.py
git commit -m "feat: add V2 modal OpenSees readiness"
```

### Task 4: Canonical Transient Artifact Reader and Deterministic Unit Conversion

**Files:**
- Create: `fem_core/analysis_spec/transient_artifact.py`
- Create: `tests/python/test_transient_analysis_artifact.py`
- Create: `tests/fixtures/analysis_spec/transient-nodal-force.csv`
- Create: `tests/fixtures/analysis_spec/transient-uniform-base.csv`

**Interfaces:**
- Produces: `read_transient_load_artifact(workspace: Path, ref: dict[str, str]) -> dict[str, Any]`.
- Produces: `force_n_to_model_factor(force_unit: str) -> float`.
- Produces: `seconds_to_model_time_factor(time_unit: str) -> float`.
- Produces: `acceleration_m_s2_to_model_factor(length_unit: str, time_unit: str) -> tuple[float, str]`.
- Reader returns metadata including `timeStartS`; zero-origin policy is enforced by Task 5 readiness so it can emit the required readiness issue code.

- [ ] **Step 1: Write artifact-reader RED tests**

Assert exact `FEMAGENT_LOAD_CSV_V1` column order; reject missing file, path escape, malformed UTF-8/CSV, multiple channels, nonuniform or non-increasing time, malformed numeric values, and SHA mismatch. A structurally valid nonzero-start file is parsed and reports its nonzero `timeStartS`, leaving policy rejection to readiness.

Use exact conversion anchors:

```python
assert force_n_to_model_factor("N") == 1.0
assert force_n_to_model_factor("kN") == 0.001
assert seconds_to_model_time_factor("s") == 1.0
assert seconds_to_model_time_factor("ms") == 1000.0
assert acceleration_m_s2_to_model_factor("mm", "ms") == (0.001, "mm/ms2")
```

- [ ] **Step 2: Run RED**

Run: `python -m pytest tests/python/test_transient_analysis_artifact.py -q`

Expected: module/import failure.

- [ ] **Step 3: Implement strict one-channel reader**

Read long-form rows, require one invariant `channel_id`, keep numeric values in canonical artifact units, verify declared SHA, and return:

```python
{
    "timesS": [...], "values": [...], "dtS": 0.01,
    "timeStartS": 0.0, "timeEndS": 1.0,
    "channelId": "...", "applicationType": "...",
    "targetType": "...", "targetId": "...",
    "component": "X", "quantity": "FORCE", "unit": "N",
    "path": "...", "sha256": "..."
}
```

Conversion formula for acceleration is `value_target = value_m_s2 * (1 / meters_per_length_unit) * seconds_per_time_unit**2`, with `meters_per_length_unit={m:1,cm:0.01,mm:0.001}` and `seconds_per_time_unit={s:1,ms:0.001}`.

- [ ] **Step 4: Run GREEN**

Run: `python -m pytest tests/python/test_transient_analysis_artifact.py -q`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add fem_core/analysis_spec/transient_artifact.py tests/python/test_transient_analysis_artifact.py tests/fixtures/analysis_spec/transient-nodal-force.csv tests/fixtures/analysis_spec/transient-uniform-base.csv
git commit -m "feat: add verified transient load artifact reader"
```

### Task 5: V2 Transient Readiness for Both Excitations

**Files:**
- Create: `fem_core/analysis_spec/opensees_profiles/transient_v2.py`
- Modify: `fem_core/analysis_spec/readiness.py`
- Modify: `fem_core/opensees_response_mapping.py`
- Create: `tests/python/test_analysis_readiness_v2_transient.py`

**Interfaces:**
- Produces: `evaluate_transient_v2_readiness(..., workspace: Path | None) -> dict[str, Any]` for both transient profiles.
- Extends response access with `NODE_VEL` and `NODE_ACCEL`.
- Exact response units: `VELOCITY -> <length>/<time>`; `ACCELERATION` and `RELATIVE_ACCELERATION -> <length>/<time>2` such as `m/s2` or `mm/ms2`.
- Nodal-force displacement/velocity/acceleration use `referenceFrame="GLOBAL"`.
- Uniform-base displacement/velocity/relative acceleration use `referenceFrame="RELATIVE"`; reactions remain GLOBAL and generalized forces ELEMENT_LOCAL.
- Records conversion evidence as `{quantity, sourceUnit, targetUnit, factor}`.

- [ ] **Step 1: Write transient RED tests**

Cover both READY profiles and fail-closed cases:

```python
assert nodal["profile"] == "OPENSEES_FRAME_2D_TRANSIENT_NODAL_FORCE_V2"
assert base["profile"] == "OPENSEES_FRAME_2D_TRANSIENT_UNIFORM_BASE_V2"
assert "ANALYSIS_READINESS_LOAD_ARTIFACT_HASH_MISMATCH" in issue_codes(hash_mismatch)
assert "ANALYSIS_READINESS_LOAD_CHANNEL_MISMATCH" in issue_codes(channel_mismatch)
assert "ANALYSIS_READINESS_TIME_ORIGIN_MISMATCH" in issue_codes(nonzero_start)
assert "ANALYSIS_READINESS_TIME_STEP_MISMATCH" in issue_codes(dt_mismatch)
assert "ANALYSIS_READINESS_DURATION_MISMATCH" in issue_codes(duration_mismatch)
assert "ANALYSIS_READINESS_ABSOLUTE_ACCELERATION_MAPPING_UNPROVEN" in issue_codes(absolute_accel)
assert "ANALYSIS_READINESS_FORCE_UNIT_MISMATCH" in issue_codes(nodal_force_unit_mismatch)
```

A valid transient with `workspace=None` returns `NOT_READY` and `ANALYSIS_READINESS_WORKSPACE_REQUIRED`. V1 Static, V2 Static, and V2 Modal remain callable without workspace.

- [ ] **Step 2: Run RED**

Run: `python -m pytest tests/python/test_analysis_readiness_v2_transient.py -q`

Expected: transient profiles are not READY.

- [ ] **Step 3: Implement readiness using Task 4 artifact evidence**

Map artifact reader failures to stable readiness codes. Require exact excitation semantics:

```text
NODAL_TIME_HISTORY: NODAL_FORCE / FORCE / NODE / nodeId / X|Y
UNIFORM_BASE_EXCITATION: UNIFORM_EXCITATION / ACCELERATION / X|Y
```

Require nodal transient AnalysisSpec force unit to equal ModelSpec force unit, then record N→that-unit conversion. Convert AnalysisSpec `timeStep` and `duration` from ModelSpec time units to seconds for artifact comparison. Require start time zero within deterministic tolerance. Reject `ABSOLUTE_ACCELERATION` before renderer admission.

- [ ] **Step 4: Run GREEN plus mapping/V1 regressions**

Run: `python -m pytest tests/python/test_analysis_readiness_v2_transient.py tests/python/test_opensees_structural_response.py tests/python/test_analysis_readiness.py -q`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add fem_core/analysis_spec/opensees_profiles/transient_v2.py fem_core/analysis_spec/readiness.py fem_core/opensees_response_mapping.py tests/python/test_analysis_readiness_v2_transient.py
git commit -m "feat: add V2 transient OpenSees readiness"
```

### Task 6: Shared V2 Renderer Publisher and V2 Static Renderer

**Files:**
- Create: `fem_core/analysis_spec/opensees_renderer_v2.py`
- Modify: `fem_core/analysis_spec/opensees_renderer.py`
- Modify: `fem_core/analysis_spec/opensees_profiles/static_v2.py`
- Modify: `fem_core/analysis_spec/__init__.py`
- Create: `tests/python/test_analysis_renderer_v2_static.py`

**Interfaces:**
- Produces: `render_opensees_analysis(workspace: Path, model_spec: dict[str, Any], analysis_spec: dict[str, Any]) -> dict[str, Any]`.
- Preserves: `render_opensees_linear_static_analysis(...)` legacy V1 behavior and hashes.
- V2 bundle schema: `FEMAGENT_OPENSEES_ANALYSIS_RENDER_V2`; renderer version `2.0`.

- [ ] **Step 1: Write V2 Static renderer RED tests**

Assert V2 Static becomes RENDERED, keeps V2 analysis fingerprint/profile, source equals deterministic recompilation, same semantic inputs yield same source/plan/readiness hashes and render fingerprint, render IDs may differ, and NOT_READY yields BLOCKED with no generated-analysis writes.

- [ ] **Step 2: Run RED**

Run: `python -m pytest tests/python/test_analysis_renderer_v2_static.py -q`

Expected: version-aware renderer/V2 publisher absent.

- [ ] **Step 3: Extract static compiler primitive and implement V2 publisher**

The shared primitive accepts normalized load cases but does not create any V1 AnalysisSpec. V1 and V2 retain separate report/fingerprint identities. V2 render fingerprint includes renderer identity, ModelSpec fingerprint, AnalysisSpec fingerprint, analysis source SHA, response plan SHA, readiness SHA, and external artifact provenance/conversions when present.

- [ ] **Step 4: Run GREEN and V1 golden regression**

Run: `python -m pytest tests/python/test_analysis_renderer_v2_static.py tests/python/test_pr26_golden_path.py -q`

Expected: PASS with unchanged V1 assertions.

- [ ] **Step 5: Commit**

```bash
git add fem_core/analysis_spec/opensees_renderer_v2.py fem_core/analysis_spec/opensees_renderer.py fem_core/analysis_spec/opensees_profiles/static_v2.py fem_core/analysis_spec/__init__.py tests/python/test_analysis_renderer_v2_static.py
git commit -m "feat: render V2 linear static OpenSees bundles"
```

### Task 7: Modal Renderer, Modal Response Plan, and V2 Bundle Verification

**Files:**
- Modify: `fem_core/analysis_spec/opensees_profiles/modal_v2.py`
- Modify: `fem_core/analysis_spec/opensees_renderer_v2.py`
- Modify: `fem_core/solvers/opensees_generated_analysis.py`
- Create: `tests/python/test_analysis_renderer_v2_modal.py`
- Create: `tests/python/test_generated_analysis_v2_verification.py`

**Interfaces:**
- Modal response plan: `{"schemaVersion":"1.0","kind":"modal_response_plan","modeCount":N,"requests":[...]}`.
- V2 verifier returns schema `FEMAGENT_GENERATED_ANALYSIS_VERIFICATION_V2`, `executionMode="MODAL"`, and trusted context:

```json
{
  "schemaVersion": "1.0",
  "kind": "verified_modal_response_context",
  "modeCount": 3,
  "modelTimeUnit": "s",
  "requests": []
}
```

- Modal generated source contains exactly `_femagent_eigenvalues = ops.eigen(modeCount)` and performs no frequency/period/mode-shape postprocessing.

- [ ] **Step 1: Write Modal render/verifier RED tests**

Assert source contains exactly one `ops.eigen(` call with requested modeCount; plan preserves request IDs/modes/targets; verifier revalidates embedded specs/profile/source/plan/readiness hashes; tampering source/plan/readiness/manifest fails verification.

- [ ] **Step 2: Run RED**

Run: `python -m pytest tests/python/test_analysis_renderer_v2_modal.py tests/python/test_generated_analysis_v2_verification.py -q`

Expected: Modal render or V2 verification unsupported.

- [ ] **Step 3: Implement Modal compilation and V1/V2 verifier routing**

Verifier dispatches by manifest schema and renderer identity, deterministically regenerates artifacts, and emits only trusted response contexts. Keep V1 verifier behavior exact. Modal verified context carries normalized requests and model time unit; it never carries caller-supplied execution commands.

- [ ] **Step 4: Run GREEN plus V1 tamper regression**

Run: `python -m pytest tests/python/test_analysis_renderer_v2_modal.py tests/python/test_generated_analysis_v2_verification.py tests/python/test_pr26_golden_path.py -q`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add fem_core/analysis_spec/opensees_profiles/modal_v2.py fem_core/analysis_spec/opensees_renderer_v2.py fem_core/solvers/opensees_generated_analysis.py tests/python/test_analysis_renderer_v2_modal.py tests/python/test_generated_analysis_v2_verification.py
git commit -m "feat: render and verify V2 modal OpenSees bundles"
```

### Task 8: Transient Renderers and V2 External-Artifact Verification

**Files:**
- Modify: `fem_core/analysis_spec/opensees_profiles/transient_v2.py`
- Modify: `fem_core/analysis_spec/opensees_renderer_v2.py`
- Modify: `fem_core/solvers/opensees_generated_analysis.py`
- Create: `tests/python/test_analysis_renderer_v2_transient.py`

**Interfaces:**
- Both transient profiles emit `structural_response_plan`.
- V2 verifier re-hashes external artifact at admission time and rejects changes after render.
- V2 verifier returns `executionMode="SCRIPT"` and a trusted context with exact shape:

```json
{
  "schemaVersion": "2.0",
  "kind": "verified_structural_response_context",
  "analysisType": "TRANSIENT",
  "abscissaSemantic": "TIME",
  "abscissaUnit": "s",
  "channels": []
}
```

For V2 Static the same V2 context kind uses `analysisType="LINEAR_STATIC"`, `abscissaSemantic="SOLVER_NATIVE_RESULT_ABSCISSA"`, and `abscissaUnit=null`. V1 keeps its existing schemaVersion 1.0 verified context unchanged.

- [ ] **Step 1: Write transient renderer RED tests**

Assert exact fixed transient configuration. Nodal force source must use one Path timeSeries, one Plain pattern, and a unit load vector in the selected DOF so Path values are the converted force history. Uniform base source must use one Path timeSeries and one UniformExcitation pattern. Assert NONE emits no `ops.rayleigh`; RAYLEIGH emits exactly `ops.rayleigh(alphaM, betaK, 0.0, 0.0)`.

Assert `analysisSteps = duration / dt` is an integer validated by readiness and source executes exactly that many `ops.analyze(1, dt)` increments. Add relocation identity test:

```python
assert spec_a_fp == spec_b_fp
assert rendered_a["analysisRenderFingerprint"] != rendered_b["analysisRenderFingerprint"]
```

Add post-render external artifact tamper test expecting verifier failure.

- [ ] **Step 2: Run RED**

Run: `python -m pytest tests/python/test_analysis_renderer_v2_transient.py -q`

Expected: transient V2 rendering absent.

- [ ] **Step 3: Implement both transient source builders and verifier evidence**

Use ModelSpec-native `dt`. For NODAL_TIME_HISTORY, Path values are canonical N values multiplied by the recorded N→ModelSpec force factor, then `ops.load(node, 1.0, 0.0, 0.0)` or the Y equivalent. For Uniform Base, Path values are canonical m/s2 values multiplied by the recorded acceleration factor and `ops.pattern("UniformExcitation", ..., dof, "-accel", timeSeriesTag)` is emitted. Manifest records original external artifact path+SHA and conversions; verifier re-reads/re-hashes the external artifact before execution.

- [ ] **Step 4: Run GREEN**

Run: `python -m pytest tests/python/test_analysis_renderer_v2_transient.py tests/python/test_analysis_readiness_v2_transient.py tests/python/test_generated_analysis_v2_verification.py -q`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add fem_core/analysis_spec/opensees_profiles/transient_v2.py fem_core/analysis_spec/opensees_renderer_v2.py fem_core/solvers/opensees_generated_analysis.py tests/python/test_analysis_renderer_v2_transient.py
git commit -m "feat: render and verify V2 transient OpenSees bundles"
```

### Task 9: Worker Safety and Execution — Build-Only Eigen Interception, Modal Run, Transient Sampling

**Files:**
- Modify: `fem_core/solvers/opensees_worker.py`
- Modify: `fem_core/solvers/opensees_python.py`
- Create: `fem_core/modal_results.py`
- Create: `tests/python/test_opensees_worker_v2.py`

**Interfaces:**
- Build inspection intercepts both `ops.analyze` and `ops.eigen`, reports `interceptedAnalyzeCalls` and `interceptedEigenCalls`, restores both functions, and never performs numerical analysis/eigensolution.
- Adds worker CLI mode `modal-run`.
- Extends script-run sampling with `NODE_VEL` and `NODE_ACCEL`.
- Produces `modal_results.json` with `schemaVersion="1.0"`, `kind="modal_result_set"`.
- Modal mode-shape unit is `1` and normalization is exactly `OPENSEES_NATIVE`.

- [ ] **Step 1: Write worker RED tests**

Fake-ops accessor tests:

```python
assert _sample_response_channel(ops, channel=vel, mapping={"access":"NODE_VEL","dof":2}) == expected_vel
assert _sample_response_channel(ops, channel=acc, mapping={"access":"NODE_ACCEL","dof":1}) == expected_acc
```

Build-inspect test uses a tiny generated modal source and asserts real `ops.eigen` is not allowed to run while `interceptedEigenCalls == 1`.

Modal canonicalization uses real captured eigenvalues and exact formulas:

```python
omega_native = math.sqrt(lam)
period = 2 * math.pi / omega_native
frequency_hz = omega_native / (2 * math.pi * seconds_per_model_time_unit)
```

Reject nonpositive or nonfinite eigenvalues.

- [ ] **Step 2: Run RED**

Run: `python -m pytest tests/python/test_opensees_worker_v2.py -q`

Expected: eigen interception, new accessors, and modal-run are absent.

- [ ] **Step 3: Implement build-only eigen interception and one-solve modal-run**

In build inspection, wrap `ops.eigen` with a blocker that increments `interceptedEigenCalls` and returns placeholder values without invoking the original. In `modal-run`, replace `ops.eigen` with a capture wrapper that invokes the original exactly once when the generated script calls it, stores the returned eigenvalue vector, and returns it to the script. After `runpy.run_path` and before `ops.wipe`, use the captured values plus `ops.nodeEigenvector(node, mode, dof)` to build requested canonical modal results. Restore original functions in `finally`.

- [ ] **Step 4: Lock post-step transient sampling semantics**

Add a script-run test with duration `0.03` and dt `0.01` asserting exactly three samples with abscissa `[0.01, 0.02, 0.03]`; no synthetic zero-time sample is present. V2 verified structural response context supplies `abscissaSemantic="TIME"` and `abscissaUnit=<ModelSpec time unit>` to `_write_structural_response`. Keep V1 context output unchanged.

- [ ] **Step 5: Run GREEN**

Run: `python -m pytest tests/python/test_opensees_worker_v2.py tests/python/test_opensees_structural_response.py -q`

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add fem_core/solvers/opensees_worker.py fem_core/solvers/opensees_python.py fem_core/modal_results.py tests/python/test_opensees_worker_v2.py
git commit -m "feat: execute V2 modal and transient OpenSees responses"
```

### Task 10: Solver Adapter Admission and Canonical Run Manifests

**Files:**
- Modify: `fem_core/solvers/opensees_python.py`
- Modify: `fem_core/solvers/opensees_generated_analysis.py`
- Create: `tests/python/test_generated_opensees_analysis_v2.py`

**Interfaces:**
- Existing solver options remain exactly `{responsePlanPath, analysisManifestPath}`.
- Verified V2 bundle selects worker execution mode from verifier output; caller cannot request mode manually.
- Run manifest remains `schemaVersion="1.0"`, `kind="solver_run"`, and records generated-analysis verification identity plus `structuralResponse/structuralResponseSha256` or `modalResults/modalResultsSha256`.

- [ ] **Step 1: Write solver-admission RED tests**

Assert preflight accepts verified V2 Static/Modal/both Transient bundles; build-domain identity still matches embedded ModelSpec; `loadPath` remains forbidden for generated bundles; Modal preflight reports intercepted eigen without numerical solve; tampered V2 bundles fail before `.femagent/runs/run_*` creation.

- [ ] **Step 2: Run RED**

Run: `python -m pytest tests/python/test_generated_opensees_analysis_v2.py -q`

Expected: V2 verifier output is not yet fully routed by adapter.

- [ ] **Step 3: Implement verified execution-mode routing**

Keep `_solver_options` as the sole generated-bundle admission. Route verified `executionMode="MODAL"` to worker `modal-run`; route verified `executionMode="SCRIPT"` to controlled script-run. Stage only verifier-produced trusted context; do not stage raw unverified execution instructions. Record output path+SHA in run manifest.

- [ ] **Step 4: Run GREEN plus PR26 admission regression**

Run: `python -m pytest tests/python/test_generated_opensees_analysis_v2.py tests/python/test_generated_opensees_analysis.py tests/python/test_pr26_golden_path.py -q`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add fem_core/solvers/opensees_python.py fem_core/solvers/opensees_generated_analysis.py tests/python/test_generated_opensees_analysis_v2.py
git commit -m "feat: admit verified V2 generated analyses to OpenSees"
```

### Task 11: Result Intelligence for Modal and V2 Transient Outputs

**Files:**
- Modify: `fem_core/result_intelligence.py`
- Modify: `fem_core/modal_results.py`
- Create: `tests/python/test_result_intelligence_modal.py`
- Create: `tests/python/test_result_intelligence_v2_transient.py`

**Interfaces:**
- `inspect_result` advertises only requested Modal capabilities from verified `modal_results.json`.
- `query_result` accepts Modal `VALUE` queries by `quantity+mode`; MODE_SHAPE additionally requires NODE target/component.
- Transient structural response uses TIME abscissa in ModelSpec time unit and preserves each verified channel reference frame.

- [ ] **Step 1: Write Result Intelligence RED tests**

Modal:

```python
freq = query_result(workspace, run_id, {"quantity":"NATURAL_FREQUENCY", "mode":1, "operation":"VALUE"})
assert freq["unit"] == "Hz"
shape = query_result(workspace, run_id, {
    "quantity":"MODE_SHAPE", "mode":1,
    "target":{"type":"NODE","id":2}, "component":"Y", "operation":"VALUE"
})
assert shape["unit"] == "1"
assert shape["normalization"] == "OPENSEES_NATIVE"
```

Transient SERIES/SUMMARY tests assert TIME abscissa, exact model-time unit, response unit strings, and reference frames. Uniform Base displacement/velocity/relative acceleration are RELATIVE. No ABSOLUTE_ACCELERATION capability is advertised.

- [ ] **Step 2: Run RED**

Run: `python -m pytest tests/python/test_result_intelligence_modal.py tests/python/test_result_intelligence_v2_transient.py -q`

Expected: modal artifact unsupported and/or transient mappings absent.

- [ ] **Step 3: Implement modal reader/query and transient semantic mapping**

Add `modalResults/modalResultsSha256` to artifact verification pairs. Keep legacy SDOF response.csv behavior unchanged. Do not reinterpret MODE_SHAPE as displacement or reconstruct absolute acceleration.

- [ ] **Step 4: Run GREEN plus existing Result Intelligence regression**

Run: `python -m pytest tests/python/test_result_intelligence_modal.py tests/python/test_result_intelligence_v2_transient.py tests/python/test_result_intelligence.py tests/python/test_pr26_golden_path.py -q`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add fem_core/result_intelligence.py fem_core/modal_results.py tests/python/test_result_intelligence_modal.py tests/python/test_result_intelligence_v2_transient.py
git commit -m "feat: query modal and V2 transient OpenSees results"
```

### Task 12: Bridge, TypeScript, Agent Surface, Four Real Golden Paths, and Final Verification

**Files:**
- Modify: `fem_core/bridge.py`
- Modify: `packages/fem-tools/src/analysisSpecTypes.ts`
- Modify: `packages/fem-tools/src/pythonBridge.ts`
- Modify: `.pi/extensions/analysis-spec-tools.ts`
- Modify: `tests/ts/analysis-readiness.test.ts`
- Modify: `tests/ts/analysis-prepare-tool-registration.test.ts`
- Modify: `tests/ts/generated-analysis-solver-admission.test.ts`
- Create: `tests/python/test_pr28_golden_paths.py`
- Modify: `tests/python/test_analysis_render_bridge.py`

**Interfaces:**
- `runFemAnalysisReadiness(..., analysisSpec: FemEngineeringAnalysisSpecInput)`.
- `runFemAnalysisRenderOpenSees(..., analysisSpec: FemEngineeringAnalysisSpecInput)`.
- `FemAnalysisReadiness` becomes a V1/V2 discriminated union.
- `FemOpenSeesAnalysisRenderResult` becomes a V1/V2 discriminated union.
- Existing Agent tool name remains exactly `fem_analysis_prepare_opensees`.

- [ ] **Step 1: Write TypeScript/bridge RED tests**

Assert preparation tool schema accepts V1 Static plus V2 Static/Modal/both Transient shapes, CHECK remains read-only, RENDER uses workspace-aware readiness/render, and no `fem_modal_prepare`, `fem_transient_prepare`, `fem_analysis_execute_v2`, or migration Agent tool is registered.

Run: `pnpm typecheck && pnpm test:ts`

Expected before implementation: typecheck/tests fail because prepare transport remains V1-only.

- [ ] **Step 2: Widen transport and the existing preparation tool only**

Python bridge:

```python
elif command == "analysis.readiness":
    result = evaluate_engineering_analysis_readiness(model_spec, analysis_spec, workspace=workspace)
elif command == "analysis.renderOpenSees":
    result = render_opensees_analysis(workspace, model_spec, analysis_spec)
```

TypeScript readiness/render report unions discriminate by V1/V2 schema/profile. Add response mappings for NODE_VEL/NODE_ACCEL and modal mappings without weakening existing V1 fields. Update prompt guidance so V2 READY/RENDERED is supported in PR28 but real execution still requires generic solver preflight/run and verified generated-bundle admission.

- [ ] **Step 3: Run TS/bridge GREEN**

Run: `pnpm typecheck && pnpm test:ts && python -m pytest tests/python/test_analysis_render_bridge.py -q`

Expected: PASS.

- [ ] **Step 4: Write and run four real OpenSees golden cases**

`tests/python/test_pr28_golden_paths.py` executes renderer → adapter preflight → adapter run → Result Intelligence for:

```text
V2 LINEAR_STATIC
V2 MODAL
V2 TRANSIENT NODAL_TIME_HISTORY
V2 TRANSIENT UNIFORM_BASE_EXCITATION
```

Use small deterministic models and short histories. Modal asserts finite positive eigenvalue/frequency/period and `period_in_seconds * frequencyHz ≈ 1`; for ModelSpec `time="ms"`, convert period to seconds before the product. Transient cases assert `analysisSteps = duration/dt`, sample count equals analysisSteps, first abscissa equals `dt`, final abscissa equals `duration`, no zero-time sample is synthesized, all values are finite, and only requested capabilities are advertised. Avoid fragile exact transient amplitudes unless an analytic solution is explicitly encoded.

Run: `python -m pytest tests/python/test_pr28_golden_paths.py -q`

Expected: PASS with OpenSeesPy installed. Optional-dependency skip is acceptable only when `adapter.status()["available"]` is false; CI must exercise installed OpenSeesPy.

- [ ] **Step 5: Run full fresh PR28 verification**

Run exactly:

```bash
pnpm typecheck
pnpm test:ts
python -m pytest
python -m ruff check fem_core tests/python examples/ansys/golden_path
python -c "from fem_core.solvers import get_solver_adapter; print(get_solver_adapter('opensees').status())"
python -c "from fem_core.ansys_result_reader import read_binary; print(read_binary)"
pnpm fem:health
```

Expected: zero typecheck/test/lint failures; solver smoke imports succeed; health reports `status=ok`.

- [ ] **Step 6: Perform final scope audit**

Compare PR27 HEAD `c25422b6467257d7b270aae6f19b4f476afa0174` to PR28 HEAD. Changed production files must be limited to OpenSees AnalysisSpec readiness/render/verifier/worker/result paths, bridge/TypeScript contracts, and preparation-tool widening. Confirm no ANSYS production file, natural-language completion file, repair subsystem, optimization subsystem, or new Agent tool registration was added.

- [ ] **Step 7: Commit final integration changes**

```bash
git add fem_core/bridge.py packages/fem-tools/src/analysisSpecTypes.ts packages/fem-tools/src/pythonBridge.ts .pi/extensions/analysis-spec-tools.ts tests/ts/analysis-readiness.test.ts tests/ts/analysis-prepare-tool-registration.test.ts tests/ts/generated-analysis-solver-admission.test.ts tests/python/test_pr28_golden_paths.py tests/python/test_analysis_render_bridge.py
git commit -m "feat: complete PR28 V2 OpenSees analysis execution"
```

## Completion Criteria

PR28 is complete only when all criteria below are demonstrated by tests and fresh final CI:

1. PR26 V1 Static validation/readiness/render/verification/execution/result path remains green with exact V1 protocol/profile identities.
2. V2 Static becomes READY when its bound model/targets/units are executable and renders under `OPENSEES_FRAME_2D_LINEAR_STATIC_V2` without V1 migration.
3. V2 Modal checks mass/free-DOF/target prerequisites, renders deterministically, build inspection intercepts eigensolution, `modal-run` performs exactly one real OpenSees eigensolve, and canonical modal results come from solver values.
4. V2 Nodal Transient verifies force artifact identity/semantics/time and AnalysisSpec↔ModelSpec force-unit agreement, renders deterministic Path+Plain loading, executes, and produces requested structural-response series.
5. V2 Uniform Base Transient verifies acceleration artifact identity/semantics/time, renders deterministic UniformExcitation loading, executes, and produces requested structural-response series.
6. `ABSOLUTE_ACCELERATION` remains valid intrinsically but is NOT_READY for the base-excitation OpenSees profile.
7. External transient artifact mutation after render is caught by generated-analysis verification before solver execution.
8. V2 bundle source/plan/readiness/manifest tampering is caught before solver execution.
9. Same transient artifact SHA at different paths keeps AnalysisSpec fingerprint identity but changes concrete render identity/provenance.
10. Modal MODE_SHAPE is unit `1`, carries `normalization="OPENSEES_NATIVE"`, and is never represented as displacement.
11. Transient result series contains only post-successful-step samples: first abscissa `dt`, last abscissa `duration`, sample count `duration/dt`; no synthetic `t=0` result is inserted.
12. Uniform-base displacement, velocity, and relative acceleration are explicitly labeled `referenceFrame="RELATIVE"`; nodal-force dynamic responses are GLOBAL.
13. Existing `fem_analysis_prepare_opensees` accepts V1/V2 supported AnalysisSpecs; no profile-specific preparation tool is added.
14. Generic `fem_solver_preflight` / `fem_solver_run` remain the only real solver execution path and accept no new user-selectable execution-mode option.
15. No ANSYS V2 renderer, natural-language Analysis Completion, Controlled Repair, nonlinear analysis, or optimization implementation enters PR28.
16. Full typecheck, TypeScript tests, Python tests, Ruff, solver smoke checks, and health check are fresh and green on final PR28 HEAD.
