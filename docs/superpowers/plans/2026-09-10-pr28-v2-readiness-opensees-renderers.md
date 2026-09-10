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
- Controlled transient artifacts must begin at zero seconds, use a uniform time step, and end at AnalysisSpec `duration` after deterministic unit conversion.
- `NODAL_TIME_HISTORY` and `UNIFORM_BASE_EXCITATION` both execute in PR28.
- Transient integration is fixed to `Plain` constraints, `Plain` numberer, `BandGeneral` system, `Linear` algorithm, `Newmark(0.5, 0.25)` integrator.
- `RAYLEIGH` maps exactly to `ops.rayleigh(alphaM, betaK, 0.0, 0.0)`; no damping-ratio inference or default damping.
- Modal worker results come from real `ops.eigen(...)` and `ops.nodeEigenvector(...)`; renderers never compute numerical modal results.
- Generated-analysis verification is mandatory before solver execution.
- Keep the existing Agent tool names; do not add profile-specific LLM-visible tools.
- Do not modify ANSYS execution, natural-language Analysis Completion, Controlled Repair, nonlinear analysis, optimization, or Semantic Role inference in PR28.
- Standard final verification: `pnpm typecheck`, `pnpm test:ts`, `python -m pytest`, `python -m ruff check fem_core tests/python examples/ansys/golden_path`, OpenSees/ANSYS smoke checks, and `pnpm fem:health`.

## File Structure

New focused modules:

- `fem_core/analysis_spec/opensees_profiles/__init__.py` — profile constants and public profile-selection exports.
- `fem_core/analysis_spec/opensees_profiles/registry.py` — exact V1/V2 AnalysisSpec → OpenSees profile routing.
- `fem_core/analysis_spec/opensees_profiles/common.py` — shared V2 readiness target/reaction/mapping/unit helpers.
- `fem_core/analysis_spec/opensees_profiles/static_v2.py` — V2 static readiness and compilation adapters.
- `fem_core/analysis_spec/opensees_profiles/modal_v2.py` — modal readiness, modal response plan, and source builder.
- `fem_core/analysis_spec/opensees_profiles/transient_v2.py` — transient readiness, artifact evidence, conversions, and source builders.
- `fem_core/analysis_spec/transient_artifact.py` — strict one-channel `FEMAGENT_LOAD_CSV_V1` parser for PR28 readiness.
- `fem_core/analysis_spec/opensees_renderer_v2.py` — shared V2 generated-analysis publisher and render fingerprinting.
- `fem_core/modal_results.py` — canonical `modal_result_set` validation/query helpers.

Existing modules modified only where their current responsibility already applies:

- `fem_core/analysis_spec/readiness.py` — preserve V1 path and dispatch supported V2 profiles.
- `fem_core/analysis_spec/opensees_renderer.py` — expose reusable V1 static compiler primitives without changing V1 output.
- `fem_core/analysis_spec/__init__.py` — export one version-aware OpenSees render entry point while preserving legacy export.
- `fem_core/opensees_response_mapping.py` — add proven transient node velocity/acceleration mappings and units.
- `fem_core/solvers/opensees_generated_analysis.py` — V1/V2 verification router.
- `fem_core/solvers/opensees_worker.py` — transient sampling access and modal execution mode.
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
- Test: `tests/python/test_analysis_profile_registry.py`
- Test: `tests/python/test_analysis_readiness.py`

**Interfaces:**
- Produces: `select_opensees_analysis_profile(normalized_analysis_spec: dict[str, Any]) -> str`.
- Produces: `evaluate_engineering_analysis_readiness(model_spec, analysis_spec, *, workspace: Path | None = None) -> dict[str, Any]`.
- Preserves: V1 calls without `workspace` and V1 report identity.

- [ ] **Step 1: Write failing routing tests**

```python
@pytest.mark.parametrize(
    ("analysis", "profile"),
    [
        (_v1_static(), "OPENSEES_FRAME_2D_LINEAR_STATIC_V1"),
        (_v2_static(), "OPENSEES_FRAME_2D_LINEAR_STATIC_V2"),
        (_v2_modal(), "OPENSEES_FRAME_2D_MODAL_V2"),
        (_v2_nodal_transient(), "OPENSEES_FRAME_2D_TRANSIENT_NODAL_FORCE_V2"),
        (_v2_base_transient(), "OPENSEES_FRAME_2D_TRANSIENT_UNIFORM_BASE_V2"),
    ],
)
def test_selects_exact_opensees_profile(analysis, profile):
    validation = validate_engineering_analysis_spec(analysis)
    assert validation["status"] == "VALID"
    assert select_opensees_analysis_profile(validation["normalizedSpec"]) == profile
```

Also keep `test_bound_valid_specs_are_ready_with_proven_response_mappings` asserting the exact V1 schema/profile.

- [ ] **Step 2: Run RED**

Run: `python -m pytest tests/python/test_analysis_profile_registry.py tests/python/test_analysis_readiness.py -q`

Expected: new tests fail because registry/profile selection does not exist; existing V1 assertions remain green.

- [ ] **Step 3: Implement exact registry and readiness dispatch shell**

Use exact discriminator routing:

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

For Task 1, V2 dispatch may return `NOT_READY` with profile-specific checks `SKIPPED`; do not mark any V2 profile READY until its task lands.

- [ ] **Step 4: Run GREEN and V1 regression**

Run: `python -m pytest tests/python/test_analysis_profile_registry.py tests/python/test_analysis_readiness.py tests/python/test_pr26_golden_path.py -q`

Expected: PASS; PR26 V1 golden path remains unchanged.

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
- Test: `tests/python/test_analysis_readiness_v2_static.py`

**Interfaces:**
- Produces: `evaluate_static_v2_readiness(context: ReadinessContext) -> dict[str, Any]`.
- Produces shared helpers for model binding, target existence, reaction restraint, and structural response mapping.
- Consumes V2 static loads from `normalizedAnalysisSpec["definition"]["loadCases"]` directly; never calls V1 migration.

- [ ] **Step 1: Write V2 Static RED tests**

```python
def test_v2_static_is_ready_without_v1_identity_conversion():
    report = evaluate_engineering_analysis_readiness(model, v2_static)
    assert report["schema"] == "FEMAGENT_ANALYSIS_READINESS_V2"
    assert report["status"] == "READY"
    assert report["profile"] == "OPENSEES_FRAME_2D_LINEAR_STATIC_V2"
    assert report["analysisSpecFingerprint"] == validate_engineering_analysis_spec(v2_static)["analysisSpecFingerprint"]
```

Add cases for missing load node, missing result node/element, unrestrained reaction, model fingerprint mismatch, and force-unit mismatch. Assert the same stable PR26 issue families where semantics are identical.

- [ ] **Step 2: Run RED**

Run: `python -m pytest tests/python/test_analysis_readiness_v2_static.py -q`

Expected: V2 remains NOT_READY from the Task 1 shell.

- [ ] **Step 3: Extract shared deterministic checks and implement Static V2 readiness**

Keep the V1 report construction unchanged. Shared helpers receive normalized objects and return check dictionaries/issues; V2 assembles them under `FEMAGENT_ANALYSIS_READINESS_V2` and `OPENSEES_FRAME_2D_LINEAR_STATIC_V2`.

- [ ] **Step 4: Run GREEN plus V1 readiness regression**

Run: `python -m pytest tests/python/test_analysis_readiness_v2_static.py tests/python/test_analysis_readiness.py tests/python/test_pr26_golden_path.py -q`

Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add fem_core/analysis_spec/opensees_profiles/common.py fem_core/analysis_spec/opensees_profiles/static_v2.py fem_core/analysis_spec/readiness.py tests/python/test_analysis_readiness_v2_static.py
git commit -m "feat: add V2 linear static OpenSees readiness"
```

### Task 3: V2 Modal Readiness and Proven Modal Response Mapping

**Files:**
- Create: `fem_core/analysis_spec/opensees_profiles/modal_v2.py`
- Modify: `fem_core/analysis_spec/readiness.py`
- Test: `tests/python/test_analysis_readiness_v2_modal.py`

**Interfaces:**
- Produces: `positive_free_translational_mass_dofs(model_spec) -> list[tuple[int, str]]`.
- Produces modal response mappings with mode, quantity, target/component when applicable, OpenSees DOF for MODE_SHAPE, and canonical unit semantics.

- [ ] **Step 1: Write modal RED tests**

Cover these exact outcomes:

```python
assert ready["profile"] == "OPENSEES_FRAME_2D_MODAL_V2"
assert ready["checks"]["modalMass"]["positiveFreeTranslationalDofCount"] == 2
assert "ANALYSIS_READINESS_MODAL_MASS_REQUIRED" in issue_codes(no_mass)
assert "ANALYSIS_READINESS_MODAL_FREE_MASS_DOF_REQUIRED" in issue_codes(all_mass_restrained)
assert "ANALYSIS_READINESS_MODAL_MODE_COUNT_EXCEEDS_DOF_BOUND" in issue_codes(too_many_modes)
assert "ANALYSIS_READINESS_RESULT_NODE_NOT_FOUND" in issue_codes(missing_mode_shape_node)
```

Assert X/Y/RZ maps to OpenSees DOF 1/2/3. Scalar `EIGENVALUE`, `NATURAL_FREQUENCY`, and `PERIOD` mappings contain no target.

- [ ] **Step 2: Run RED**

Run: `python -m pytest tests/python/test_analysis_readiness_v2_modal.py -q`

Expected: modal profile is not READY because profile-specific readiness is absent.

- [ ] **Step 3: Implement conservative modal readiness**

Count a DOF only when `mUX > 0` or `mUY > 0` and the corresponding `UX`/`UY` is not constrained. Do not inspect assembled matrices or claim numerical rank. Keep MODE_SHAPE normalization unresolved in readiness metadata.

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
- Create fixtures: `tests/fixtures/analysis_spec/transient-nodal-force.csv`, `tests/fixtures/analysis_spec/transient-uniform-base.csv`

**Interfaces:**
- Produces: `read_transient_load_artifact(workspace: Path, ref: dict[str, str]) -> dict[str, Any]`.
- Produces: `force_n_to_model_factor(force_unit: str) -> float`.
- Produces: `seconds_to_model_time_factor(time_unit: str) -> float`.
- Produces: `acceleration_m_s2_to_model_factor(length_unit: str, time_unit: str) -> tuple[float, str]`.

- [ ] **Step 1: Write artifact-reader RED tests**

Assert accepted canonical columns exactly match `FEMAGENT_LOAD_CSV_V1`; reject missing files, path escape, malformed UTF-8/CSV, multiple channels, nonuniform time, nonzero time origin, malformed numeric values, and SHA mismatch.

Use conversion anchors:

```python
assert force_n_to_model_factor("N") == 1.0
assert force_n_to_model_factor("kN") == 0.001
assert seconds_to_model_time_factor("s") == 1.0
assert seconds_to_model_time_factor("ms") == 1000.0
assert acceleration_m_s2_to_model_factor("mm", "ms") == (0.001, "mm/ms2")
```

- [ ] **Step 2: Run RED**

Run: `python -m pytest tests/python/test_transient_analysis_artifact.py -q`

Expected: import/module failure.

- [ ] **Step 3: Implement strict reader without reusing the SDOF-only parser**

Read all long-form rows, require a single invariant `channel_id`, preserve canonical values in SI, return `timesS`, `values`, `dtS`, `timeStartS`, `timeEndS`, `applicationType`, `targetType`, `targetId`, `component`, `quantity`, `unit`, `path`, and actual `sha256`.

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
- Test: `tests/python/test_analysis_readiness_v2_transient.py`

**Interfaces:**
- Produces both transient readiness profiles.
- Extends response access with `NODE_VEL` and `NODE_ACCEL`; base-relative acceleration uses `NODE_ACCEL` with `referenceFrame="RELATIVE"`.
- Records deterministic conversion evidence as `{quantity, sourceUnit, targetUnit, factor}`.

- [ ] **Step 1: Write transient RED tests**

Cover both READY paths and fail-closed cases:

```python
assert nodal["profile"] == "OPENSEES_FRAME_2D_TRANSIENT_NODAL_FORCE_V2"
assert base["profile"] == "OPENSEES_FRAME_2D_TRANSIENT_UNIFORM_BASE_V2"
assert "ANALYSIS_READINESS_LOAD_ARTIFACT_HASH_MISMATCH" in issue_codes(hash_mismatch)
assert "ANALYSIS_READINESS_LOAD_CHANNEL_MISMATCH" in issue_codes(channel_mismatch)
assert "ANALYSIS_READINESS_TIME_ORIGIN_MISMATCH" in issue_codes(nonzero_start)
assert "ANALYSIS_READINESS_TIME_STEP_MISMATCH" in issue_codes(dt_mismatch)
assert "ANALYSIS_READINESS_DURATION_MISMATCH" in issue_codes(duration_mismatch)
assert "ANALYSIS_READINESS_ABSOLUTE_ACCELERATION_MAPPING_UNPROVEN" in issue_codes(absolute_accel)
```

Also assert `workspace=None` for a valid transient returns `NOT_READY` with `ANALYSIS_READINESS_WORKSPACE_REQUIRED`, while V1/static/modal remain callable without workspace.

- [ ] **Step 2: Run RED**

Run: `python -m pytest tests/python/test_analysis_readiness_v2_transient.py -q`

Expected: transient profiles are not READY.

- [ ] **Step 3: Implement readiness using Task 4 artifact evidence**

Match exact excitation semantics: `NODAL_FORCE/FORCE/NODE/<id>/<X|Y>` or `UNIFORM_EXCITATION/ACCELERATION/<X|Y>`. Compare artifact `dtS` and end time to AnalysisSpec values converted from ModelSpec time units. Do not rewrite the AnalysisSpec artifact path or SHA.

- [ ] **Step 4: Run GREEN plus response-mapping regression**

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
- Test: `tests/python/test_analysis_renderer_v2_static.py`

**Interfaces:**
- Produces: `render_opensees_analysis(workspace: Path, model_spec: dict[str, Any], analysis_spec: dict[str, Any]) -> dict[str, Any]` as version-aware public renderer.
- Preserves: `render_opensees_linear_static_analysis(...)` legacy V1 behavior.
- Produces V2 bundle schema `FEMAGENT_OPENSEES_ANALYSIS_RENDER_V2` and renderer version `2.0`.

- [ ] **Step 1: Write V2 Static renderer RED tests**

Assert V2 Static RENDERED, V2 identity retained, source equals deterministic recompilation, same semantic inputs yield same artifact hashes/render fingerprint, different render IDs are allowed, and NOT_READY yields `BLOCKED` with zero generated-analysis writes.

- [ ] **Step 2: Run RED**

Run: `python -m pytest tests/python/test_analysis_renderer_v2_static.py -q`

Expected: version-aware renderer/V2 publisher absent.

- [ ] **Step 3: Extract static command primitive and implement V2 publisher**

Use one shared primitive accepting a normalized load-case list, but keep V1 and V2 manifests/fingerprints separate. The V2 render fingerprint payload contains renderer identity, model/analysis fingerprints, readiness SHA, source SHA, response-plan SHA, and any external artifact provenance/conversion record when present.

- [ ] **Step 4: Run GREEN and V1 golden regression**

Run: `python -m pytest tests/python/test_analysis_renderer_v2_static.py tests/python/test_pr26_golden_path.py -q`

Expected: PASS with unchanged V1 assertions.

- [ ] **Step 5: Commit**

```bash
git add fem_core/analysis_spec/opensees_renderer_v2.py fem_core/analysis_spec/opensees_renderer.py fem_core/analysis_spec/opensees_profiles/static_v2.py fem_core/analysis_spec/__init__.py tests/python/test_analysis_renderer_v2_static.py
git commit -m "feat: render V2 linear static OpenSees bundles"
```

### Task 7: Modal Renderer, Modal Response Plan, and Deterministic V2 Bundle Verification

**Files:**
- Modify: `fem_core/analysis_spec/opensees_profiles/modal_v2.py`
- Modify: `fem_core/analysis_spec/opensees_renderer_v2.py`
- Modify: `fem_core/solvers/opensees_generated_analysis.py`
- Test: `tests/python/test_analysis_renderer_v2_modal.py`
- Test: `tests/python/test_generated_analysis_v2_verification.py`

**Interfaces:**
- Modal response plan identity: `{"schemaVersion":"1.0","kind":"modal_response_plan",...}`.
- V2 verifier returns `FEMAGENT_GENERATED_ANALYSIS_VERIFICATION_V2` and a verified execution contract indicating `executionMode="MODAL"`.

- [ ] **Step 1: Write Modal render/verifier RED tests**

Assert generated source contains exactly one real eigen call for `modeCount`, plan preserves requested modes/targets, verifier revalidates embedded specs/profile/source/plan/readiness hashes, and tampering with source/plan/readiness/manifest fails before solver run directories are created.

- [ ] **Step 2: Run RED**

Run: `python -m pytest tests/python/test_analysis_renderer_v2_modal.py tests/python/test_generated_analysis_v2_verification.py -q`

Expected: Modal render or V2 verification unsupported.

- [ ] **Step 3: Implement Modal compilation and V1/V2 verifier routing**

Generated source builds the model and invokes OpenSees eigenanalysis; it does not calculate frequency/period itself. Verifier dispatches by manifest schema and renderer identity, regenerates deterministic artifacts, and returns a trusted modal response plan.

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
- Test: `tests/python/test_analysis_renderer_v2_transient.py`

**Interfaces:**
- Both profiles emit `structural_response_plan`.
- V2 verifier re-hashes the external artifact at admission time and rejects changes after render.
- Verified execution contract reports `executionMode="SCRIPT"` and trusted structural response context.

- [ ] **Step 1: Write transient renderer RED tests**

Assert exact fixed analysis configuration, Nodal Path+Plain load construction, UniformExcitation construction, NONE/RAYLEIGH behavior, converted values, exact number of `ops.analyze(1, dt)` increments, and deterministic output.

Add relocation identity test:

```python
assert spec_a_fp == spec_b_fp              # same artifact SHA, different path
assert rendered_a["analysisRenderFingerprint"] != rendered_b["analysisRenderFingerprint"]
```

Add post-render external artifact tampering test expecting verification failure.

- [ ] **Step 2: Run RED**

Run: `python -m pytest tests/python/test_analysis_renderer_v2_transient.py -q`

Expected: transient V2 rendering absent.

- [ ] **Step 3: Implement both transient source builders and verifier evidence**

Use converted ModelSpec-time `dt`; write deterministic Path values into generated source; record original artifact path/SHA and conversion evidence in manifest. Do not reconstruct absolute acceleration.

- [ ] **Step 4: Run GREEN**

Run: `python -m pytest tests/python/test_analysis_renderer_v2_transient.py tests/python/test_analysis_readiness_v2_transient.py tests/python/test_generated_analysis_v2_verification.py -q`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add fem_core/analysis_spec/opensees_profiles/transient_v2.py fem_core/analysis_spec/opensees_renderer_v2.py fem_core/solvers/opensees_generated_analysis.py tests/python/test_analysis_renderer_v2_transient.py
git commit -m "feat: render and verify V2 transient OpenSees bundles"
```

### Task 9: Worker Execution — Modal Mode and Transient Sampling

**Files:**
- Modify: `fem_core/solvers/opensees_worker.py`
- Create: `fem_core/modal_results.py`
- Test: `tests/python/test_opensees_worker_v2.py`

**Interfaces:**
- Adds worker CLI mode `modal-run`.
- Extends script-run sampling with `NODE_VEL` and `NODE_ACCEL`.
- Produces `modal_results.json` with `schemaVersion="1.0"`, `kind="modal_result_set"`.

- [ ] **Step 1: Write worker RED tests with a fake ops boundary where possible**

For transient sampling assert:

```python
assert _sample_response_channel(ops, channel=vel, mapping={"access":"NODE_VEL","dof":2}) == expected_vel
assert _sample_response_channel(ops, channel=acc, mapping={"access":"NODE_ACCEL","dof":1}) == expected_acc
```

For modal canonicalization assert positive eigenvalues produce:

```python
omega = math.sqrt(lam)
expected_period = 2 * math.pi / omega
expected_hz = omega / (2 * math.pi * seconds_per_model_time_unit)
```

and nonpositive/nonfinite solver eigenvalues fail closed.

- [ ] **Step 2: Run RED**

Run: `python -m pytest tests/python/test_opensees_worker_v2.py -q`

Expected: unsupported worker modes/accessors.

- [ ] **Step 3: Implement worker accessors and modal execution**

`modal-run` loads only a verified modal response contract, runs the generated script in isolation, reads real OpenSees eigenvalues/nodeEigenvector values, and writes requested results plus package/engine identity. Mode-shape channels carry `normalization="OPENSEES_NATIVE"` and are never labeled displacement.

- [ ] **Step 4: Run GREEN**

Run: `python -m pytest tests/python/test_opensees_worker_v2.py tests/python/test_opensees_structural_response.py -q`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add fem_core/solvers/opensees_worker.py fem_core/modal_results.py tests/python/test_opensees_worker_v2.py
git commit -m "feat: execute V2 modal and transient OpenSees responses"
```

### Task 10: Solver Adapter Admission and Canonical Run Manifests

**Files:**
- Modify: `fem_core/solvers/opensees_python.py`
- Modify: `fem_core/solvers/opensees_generated_analysis.py`
- Test: `tests/python/test_generated_opensees_analysis_v2.py`

**Interfaces:**
- Existing `solverOptions={responsePlanPath, analysisManifestPath}` remains unchanged.
- Verified V2 bundle selects worker execution mode from verifier output; caller cannot request mode manually.
- Run manifest remains `schemaVersion="1.0"`, `kind="solver_run"`, and records generated-analysis verification identity plus `structuralResponse` or `modalResults` output hashes.

- [ ] **Step 1: Write solver-admission RED tests**

Assert preflight accepts verified V2 static/modal/transient bundles, build-domain identity still matches ModelSpec, `loadPath` remains forbidden for generated bundles, and tampered V2 bundles fail before `.femagent/runs/run_*` creation.

- [ ] **Step 2: Run RED**

Run: `python -m pytest tests/python/test_generated_opensees_analysis_v2.py -q`

Expected: V2 verifier output is not yet routed by adapter.

- [ ] **Step 3: Implement verified execution-mode routing**

Keep `_solver_options` as the sole generated-bundle admission. Route verified `MODAL` to worker `modal-run`; route V1/V2 Static and Transient to controlled script-run. Record output path+SHA in the run manifest.

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
- Test: `tests/python/test_result_intelligence_modal.py`
- Test: `tests/python/test_result_intelligence_v2_transient.py`

**Interfaces:**
- `inspect_result` advertises requested Modal capabilities from `modal_results.json`.
- `query_result` accepts Modal queries using quantity+mode and optional NODE target/component for MODE_SHAPE.
- Transient structural response uses TIME abscissa in ModelSpec time unit and exposes `VELOCITY`, nodal `ACCELERATION` or `RELATIVE_ACCELERATION`, reactions, and generalized forces from verified channels.

- [ ] **Step 1: Write Result Intelligence RED tests**

Modal examples:

```python
query = {"quantity":"NATURAL_FREQUENCY", "mode":1, "operation":"VALUE"}
assert result["unit"] == "Hz"
shape = {"quantity":"MODE_SHAPE", "mode":1, "target":{"type":"NODE","id":2}, "component":"Y", "operation":"VALUE"}
assert query_result(workspace, run_id, shape)["normalization"] == "OPENSEES_NATIVE"
```

Transient examples assert `SERIES`/`SUMMARY` preserve TIME abscissa, units, and reference frames; no `ABSOLUTE_ACCELERATION` capability is advertised.

- [ ] **Step 2: Run RED**

Run: `python -m pytest tests/python/test_result_intelligence_modal.py tests/python/test_result_intelligence_v2_transient.py -q`

Expected: modal artifact unsupported and/or transient accessors absent.

- [ ] **Step 3: Implement modal reader/query and transient semantic mapping**

Add `modalResults/modalResultsSha256` to artifact verification pairs. Do not reinterpret MODE_SHAPE as displacement. Keep legacy SDOF response.csv behavior intact.

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

Assert the preparation tool schema accepts V1 Static plus V2 Static/Modal/both Transient shapes, CHECK remains read-only, RENDER passes the workspace-aware readiness/render path, and no `fem_modal_prepare`, `fem_transient_prepare`, or new migration tool is registered.

Run: `pnpm typecheck && pnpm test:ts`

Expected before implementation: typecheck/tests fail because prepare transport remains V1-only.

- [ ] **Step 2: Widen transport and the existing tool only**

In Python bridge:

```python
elif command == "analysis.readiness":
    result = evaluate_engineering_analysis_readiness(model_spec, analysis_spec, workspace=workspace)
elif command == "analysis.renderOpenSees":
    result = render_opensees_analysis(workspace, model_spec, analysis_spec)
```

Update prompt guidance so V2 READY/RENDERED is supported in PR28 but execution still requires generic solver preflight/run and verified bundle admission.

- [ ] **Step 3: Run TS/bridge GREEN**

Run: `pnpm typecheck && pnpm test:ts && python -m pytest tests/python/test_analysis_render_bridge.py -q`

Expected: PASS.

- [ ] **Step 4: Write and run four real OpenSees golden cases**

`tests/python/test_pr28_golden_paths.py` must execute through renderer → adapter preflight → adapter run → Result Intelligence for:

```text
V2 LINEAR_STATIC
V2 MODAL
V2 TRANSIENT NODAL_TIME_HISTORY
V2 TRANSIENT UNIFORM_BASE_EXCITATION
```

Use small deterministic models and short histories. Modal must assert finite positive eigenvalue/frequency/period and internally consistent `period * frequencyHz ≈ 1` after time-unit conversion. Transient cases must assert expected sample count/time axis, finite channel values, and requested capabilities. Do not assert fragile exact dynamic amplitudes unless an analytic solution is explicitly encoded in the test.

Run: `python -m pytest tests/python/test_pr28_golden_paths.py -q`

Expected: PASS with OpenSeesPy installed; optional-dependency skip is acceptable only in environments where `adapter.status()["available"]` is false. CI must exercise the installed OpenSees path.

- [ ] **Step 5: Run the full fresh PR28 verification suite**

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

Expected: zero test/lint/typecheck failures; OpenSees and ANSYS smoke imports succeed; `fem:health` reports `status=ok`.

- [ ] **Step 6: Perform final scope audit**

Compare PR27 HEAD `c25422b6467257d7b270aae6f19b4f476afa0174` to PR28 HEAD and verify changed files are limited to PR28 design/plan, OpenSees AnalysisSpec readiness/render/verifier/worker/result paths, TypeScript contracts, Pi preparation-tool widening, fixtures, and tests. Confirm no ANSYS production file, natural-language completion file, repair subsystem, optimization subsystem, or new Agent tool registration was added.

- [ ] **Step 7: Commit final integration changes**

```bash
git add fem_core/bridge.py packages/fem-tools/src/analysisSpecTypes.ts packages/fem-tools/src/pythonBridge.ts .pi/extensions/analysis-spec-tools.ts tests/ts/analysis-readiness.test.ts tests/ts/analysis-prepare-tool-registration.test.ts tests/ts/generated-analysis-solver-admission.test.ts tests/python/test_pr28_golden_paths.py tests/python/test_analysis_render_bridge.py
git commit -m "feat: complete PR28 V2 OpenSees analysis execution"
```

## Completion Criteria

PR28 is complete only when all of the following are demonstrated by tests and final CI:

1. PR26 V1 static validation/readiness/render/verification/execution/result path remains green and retains V1 protocol/profile identities.
2. V2 Static is READY when its bound model/targets/units are executable and renders under `OPENSEES_FRAME_2D_LINEAR_STATIC_V2` without V1 migration.
3. V2 Modal checks mass/free-DOF/target prerequisites, renders deterministically, runs real OpenSees eigenanalysis, and produces canonical modal results.
4. V2 Nodal Transient verifies canonical force artifact identity/semantics/time, renders deterministic Path+Plain loading, executes, and produces requested structural-response series.
5. V2 Uniform Base Transient verifies canonical acceleration artifact identity/semantics/time, renders deterministic UniformExcitation loading, executes, and produces requested structural-response series.
6. `ABSOLUTE_ACCELERATION` remains valid intrinsically but is NOT_READY for the base-excitation OpenSees profile.
7. External transient artifact mutation after render is caught by generated-analysis verification before solver execution.
8. V2 bundle source/plan/readiness/manifest tampering is caught before solver execution.
9. Same transient artifact SHA at different paths keeps AnalysisSpec fingerprint identity but changes concrete render identity/provenance.
10. Modal MODE_SHAPE is recorded as OpenSees-native normalization-dependent output, not physical displacement.
11. The existing `fem_analysis_prepare_opensees` tool accepts V1/V2 supported AnalysisSpecs; no profile-specific preparation tool is added.
12. Generic `fem_solver_preflight` / `fem_solver_run` remain the only real solver execution path.
13. No ANSYS V2 renderer, natural-language Analysis Completion, Controlled Repair, nonlinear analysis, or optimization implementation enters PR28.
14. Full typecheck, TypeScript tests, Python tests, Ruff, solver smoke checks, and health check are fresh and green on the final PR28 HEAD.
