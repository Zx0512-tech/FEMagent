# PR27 — EngineeringAnalysisSpec V2 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a versioned solver-neutral `EngineeringAnalysisSpec V2` that intrinsically validates and fingerprints `LINEAR_STATIC`, `MODAL`, and linear-direct-integration `TRANSIENT` analysis intent while preserving every proven V1 static behavior and keeping all V2 profiles non-executable in PR27.

**Architecture:** Keep `validate_engineering_analysis_spec(spec)` as the single Python entry point and refactor its implementation into a schema-version router with isolated V1 and V2 validators. V2 uses one shared envelope plus analysis-type-discriminated definitions; static, modal, and transient profile logic remain separate, and transient fingerprinting projects artifact identity by SHA-256 while excluding locator path. TypeScript mirrors the Python contract as a V1/V2 discriminated union. Existing PR26 readiness/render remain V1-only and reject V2 fail-closed.

**Tech Stack:** Python >=3.13, pytest >=8.4,<9, Ruff >=0.12,<1, Node >=22, TypeScript 5.9, pnpm, TypeBox, existing `femagent.bridge/v1` transport.

**Spec:** `docs/superpowers/specs/2026-09-08-pr27-engineering-analysis-spec-v2-design.md`

## Global Constraints

- V2 supports exactly `LINEAR_STATIC`, `MODAL`, and `TRANSIENT`.
- `TRANSIENT` means linear structural direct-integration time-history analysis only.
- V2 transient excitation supports only `NODAL_TIME_HISTORY` force and `UNIFORM_BASE_EXCITATION` acceleration.
- V2 transient damping supports only explicit `NONE` or explicit `RAYLEIGH`; no implicit damping ratio or 5% default.
- PR27 performs intrinsic AnalysisSpec validation only; it does not read ModelSpec targets, load artifact bytes, solver state, or result artifacts.
- PR27 adds no V2 readiness, renderer, worker, result extraction, solver execution, ANSYS rendering, natural-language completion, repair, nonlinear analysis, or optimization.
- All V2 profiles, including V2 `LINEAR_STATIC`, stop at `VALID` in PR27.
- Existing V1 validation semantics, normalized representation, canonicalization, fingerprints, PR26 readiness/render/generated-analysis verification, and PR26 golden path remain unchanged.
- V1 is never silently migrated during validation or execution.
- V2 static and semantically equivalent V1 static intentionally have different fingerprints.
- Result requests remain exact whitelist contracts; no arbitrary solver commands or recorder syntax enter AnalysisSpec.
- No unit inference, target inference, load summation, sign correction, automatic repair, or unit conversion.
- Modal scalar requests are `EIGENVALUE`, `NATURAL_FREQUENCY`, `PERIOD`; mode shape is NODE `MODE_SHAPE` with X/Y/RZ and explicit mode index.
- Transient base-excitation acceleration requests must distinguish `RELATIVE_ACCELERATION` from `ABSOLUTE_ACCELERATION`; bare `ACCELERATION` is invalid for `UNIFORM_BASE_EXCITATION`.
- Transient normalized specs retain `loadArtifact.path`, but semantic fingerprint payload removes `path` and retains `sha256`.
- Migration is pure/read-only and accepts only valid V1 `LINEAR_STATIC`.
- Migration does not become a new permanent LLM-visible tool in PR27.
- Standard verification remains: `pnpm typecheck`, `pnpm test:ts`, `python -m pytest`, Ruff, `pnpm fem:health`.

---

## File Map

### Create
- `fem_core/analysis_spec/common.py` — shared intrinsic validation primitives and canonical hash helpers used by V2 without changing V1 semantics.
- `fem_core/analysis_spec/v1.py` — preserved PR25 validator/normalizer/fingerprint implementation.
- `fem_core/analysis_spec/v2/__init__.py` — V2 exports.
- `fem_core/analysis_spec/v2/validator.py` — V2 envelope/discriminator router.
- `fem_core/analysis_spec/v2/static.py` — V2 static intrinsic validation and normalized profile data.
- `fem_core/analysis_spec/v2/modal.py` — V2 modal intrinsic validation.
- `fem_core/analysis_spec/v2/transient.py` — V2 transient intrinsic validation.
- `fem_core/analysis_spec/v2/normalization.py` — canonical V2 normalized spec and fingerprint projection.
- `fem_core/analysis_spec/v2/migration.py` — pure V1→V2 static migration.
- `tests/fixtures/analysis_spec/simple-linear-static-v2.json`
- `tests/fixtures/analysis_spec/simple-modal-v2.json`
- `tests/fixtures/analysis_spec/simple-transient-nodal-v2.json`
- `tests/fixtures/analysis_spec/simple-transient-base-v2.json`
- `tests/python/test_analysis_spec_v2_static.py`
- `tests/python/test_analysis_spec_v2_modal.py`
- `tests/python/test_analysis_spec_v2_transient.py`
- `tests/python/test_analysis_spec_migration.py`
- `tests/ts/analysis-spec-v2.test.ts`

### Modify
- `fem_core/analysis_spec/validator.py` — become schema-version router only.
- `fem_core/analysis_spec/__init__.py` — export migration API without changing existing exports.
- `fem_core/analysis_spec/readiness.py` — explicit V1-only admission guard so valid V2 never reaches PR26 field assumptions.
- `fem_core/bridge.py` — add `analysisSpec.migrateV1ToV2`.
- `tests/python/test_analysis_spec.py` — retain V1 regressions and adjust only assertions that intentionally test V2 rejection by the V1 validator internals.
- `tests/python/test_analysis_spec_fingerprint.py` — preserve V1 fingerprint regressions.
- `tests/python/test_analysis_spec_bridge.py` — validation bridge accepts V2 and migration bridge is pure.
- `tests/python/test_analysis_readiness.py` — V2 valid spec returns V1-profile `NOT_READY`, never crashes or becomes READY.
- `tests/python/test_analysis_render_bridge.py` — V2 render attempt remains a normal blocked domain result with no artifacts.
- `packages/fem-tools/src/analysisSpecTypes.ts` — V1/V2 discriminated type system while keeping PR26 readiness/render types V1-specific.
- `packages/fem-tools/src/pythonBridge.ts` — add typed migration transport; narrow V1-only readiness/render inputs.
- `packages/fem-tools/src/index.ts` — export new V2/migration types and transport.
- `.pi/extensions/analysis-spec-tools.ts` — validation schema becomes V1|V2 union; OpenSees prepare schema remains V1-only.
- `tests/ts/analysis-spec.test.ts` — retain V1 bridge regression.
- `tests/ts/analysis-spec-tool-registration.test.ts` — validation guidance covers V2 intrinsic-only semantics.
- `tests/ts/analysis-prepare-tool-registration.test.ts` — prove prepare remains V1-only.
- `tests/ts/analysis-readiness.test.ts` — keep V1 execution typing and runtime path unchanged.

---

### Task 1: Freeze V1 Behind a Version Router

**Files:**
- Create: `fem_core/analysis_spec/v1.py`
- Create: `fem_core/analysis_spec/common.py`
- Modify: `fem_core/analysis_spec/validator.py`
- Test: `tests/python/test_analysis_spec.py`
- Test: `tests/python/test_analysis_spec_fingerprint.py`

**Interfaces:**
- Public stays `validate_engineering_analysis_spec(spec: dict[str, Any]) -> dict[str, Any]`.
- New internal `validate_engineering_analysis_spec_v1(spec: dict[str, Any]) -> dict[str, Any]` owns the exact current PR25 behavior.
- V1 report stays `FEMAGENT_ANALYSIS_SPEC_VALIDATION_V1` with the same fields.

- [ ] **Step 1: Write a failing direct V1-module regression test**

Append to `tests/python/test_analysis_spec.py`:

```python
def test_public_router_matches_explicit_v1_validator() -> None:
    from fem_core.analysis_spec.v1 import validate_engineering_analysis_spec_v1

    spec = load_spec()
    assert validate_engineering_analysis_spec(spec) == validate_engineering_analysis_spec_v1(spec)
```

- [ ] **Step 2: Run RED**

```bash
python -m pytest tests/python/test_analysis_spec.py::test_public_router_matches_explicit_v1_validator -q
```

Expected: import failure because `fem_core.analysis_spec.v1` does not exist.

- [ ] **Step 3: Move current V1 implementation intact and make `validator.py` a router**

`validator.py` should reduce to version dispatch equivalent to:

```python
from fem_core.analysis_spec.v1 import validate_engineering_analysis_spec_v1


def validate_engineering_analysis_spec(spec: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(spec, dict):
        return validate_engineering_analysis_spec_v1(spec)
    version = spec.get("schemaVersion")
    if version == "1.0":
        return validate_engineering_analysis_spec_v1(spec)
    if version == "2.0":
        from fem_core.analysis_spec.v2 import validate_engineering_analysis_spec_v2
        return validate_engineering_analysis_spec_v2(spec)
    return validate_engineering_analysis_spec_v1(spec)
```

Implementation requirement: preserve the old V1 functions, issue codes, normalized ordering, and `_fingerprint()` behavior exactly in `v1.py`. Shared `common.py` may contain new helpers for V2, but V1 must not be rewritten to use helpers if doing so changes bytes, numeric handling, ordering, or issue ordering.

- [ ] **Step 4: Run V1 regression suite**

```bash
python -m pytest tests/python/test_analysis_spec.py tests/python/test_analysis_spec_fingerprint.py -q
python -m ruff check fem_core/analysis_spec/validator.py fem_core/analysis_spec/v1.py fem_core/analysis_spec/common.py tests/python/test_analysis_spec.py tests/python/test_analysis_spec_fingerprint.py
```

Expected: all existing V1 tests pass unchanged plus the new router parity test.

- [ ] **Step 5: Commit**

```bash
git add fem_core/analysis_spec/validator.py fem_core/analysis_spec/v1.py fem_core/analysis_spec/common.py tests/python/test_analysis_spec.py tests/python/test_analysis_spec_fingerprint.py
git commit -m "refactor: preserve AnalysisSpec V1 behind version router"
```

---

### Task 2: V2 Shared Envelope + LINEAR_STATIC Profile

**Files:**
- Create: `fem_core/analysis_spec/v2/__init__.py`
- Create: `fem_core/analysis_spec/v2/validator.py`
- Create: `fem_core/analysis_spec/v2/static.py`
- Create: `fem_core/analysis_spec/v2/normalization.py`
- Create: `tests/fixtures/analysis_spec/simple-linear-static-v2.json`
- Create: `tests/python/test_analysis_spec_v2_static.py`
- Modify: `fem_core/analysis_spec/validator.py`

**Interfaces:**
- Produces `validate_engineering_analysis_spec_v2(spec) -> validation report`.
- Produces `normalize_analysis_spec_v2(spec) -> dict[str, Any]` only after profile validation succeeds.
- Produces `fingerprint_analysis_spec_v2(normalized_spec) -> str`.

- [ ] **Step 1: Add the exact V2 static fixture**

```json
{
  "schemaVersion": "2.0",
  "kind": "engineering_analysis_spec",
  "modelSpecFingerprint": "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef",
  "analysisType": "LINEAR_STATIC",
  "units": {"force": "kN"},
  "definition": {
    "loadCases": [{
      "loadCaseId": "LC1",
      "nodalLoads": [{"nodeId": 2, "FX": 0, "FY": -10, "MZ": 0}]
    }]
  },
  "resultRequests": [{
    "requestId": "R1",
    "loadCaseId": "LC1",
    "quantity": "DISPLACEMENT",
    "target": {"type": "NODE", "id": 2},
    "component": "Y"
  }]
}
```

- [ ] **Step 2: Write RED tests for envelope, static rules, and deterministic normalization**

In `test_analysis_spec_v2_static.py`, assert:

```python
def test_v2_static_validates_and_normalizes() -> None:
    result = validate_engineering_analysis_spec(load_v2_static())
    assert result["schema"] == "FEMAGENT_ANALYSIS_SPEC_VALIDATION_V1"
    assert result["status"] == "VALID"
    assert result["normalizedSpec"]["schemaVersion"] == "2.0"
    assert result["normalizedSpec"]["definition"]["loadCases"][0]["loadCaseId"] == "LC1"
    assert re.fullmatch(r"[0-9a-f]{64}", result["analysisSpecFingerprint"])
```

Also add exact failures for unknown top-level field, wrong discriminator, bad force unit, zero/multiple load cases, empty loads, duplicate node target, zero load, missing FX/FY/MZ, unsupported static result request, missing loadCaseId reference, and duplicate requestId.

Add ordering test by adding node 5 + request R2, reversing both arrays, and asserting identical normalized spec and fingerprint.

- [ ] **Step 3: Run RED**

```bash
python -m pytest tests/python/test_analysis_spec_v2_static.py -q
```

Expected: V2 currently returns `ANALYSIS_SPEC_INVALID_SCHEMA` or missing V2 import/module.

- [ ] **Step 4: Implement V2 envelope router and static validator**

V2 exact top-level keys:

```python
V2_TOP_LEVEL_KEYS = {
    "schemaVersion", "kind", "modelSpecFingerprint",
    "analysisType", "units", "definition", "resultRequests",
}
```

`v2/validator.py` validates the shared envelope, then dispatches by `analysisType`. `static.py` preserves the existing V1 static engineering rules but reads `definition.loadCases`. `normalization.py` sorts static load cases by `loadCaseId`, nodal loads by `nodeId`, requests by `requestId`, and computes SHA-256 over canonical JSON with `sort_keys=True`, compact separators, UTF-8, and `allow_nan=False`.

- [ ] **Step 5: Run GREEN**

```bash
python -m pytest tests/python/test_analysis_spec_v2_static.py tests/python/test_analysis_spec.py tests/python/test_analysis_spec_fingerprint.py -q
python -m ruff check fem_core/analysis_spec/v2 tests/python/test_analysis_spec_v2_static.py
```

- [ ] **Step 6: Commit**

```bash
git add fem_core/analysis_spec/validator.py fem_core/analysis_spec/v2 tests/fixtures/analysis_spec/simple-linear-static-v2.json tests/python/test_analysis_spec_v2_static.py
git commit -m "feat: add AnalysisSpec V2 linear-static profile"
```

---

### Task 3: MODAL V2 Profile

**Files:**
- Create: `fem_core/analysis_spec/v2/modal.py`
- Create: `tests/fixtures/analysis_spec/simple-modal-v2.json`
- Create: `tests/python/test_analysis_spec_v2_modal.py`
- Modify: `fem_core/analysis_spec/v2/validator.py`
- Modify: `fem_core/analysis_spec/v2/normalization.py`

**Interfaces:**
- `analysisType="MODAL"` exact units `{}` and definition `{"modeCount": positive int}`.
- Modal requests are scalar modal results or one NODE mode-shape request.

- [ ] **Step 1: Add modal fixture**

```json
{
  "schemaVersion": "2.0",
  "kind": "engineering_analysis_spec",
  "modelSpecFingerprint": "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef",
  "analysisType": "MODAL",
  "units": {},
  "definition": {"modeCount": 3},
  "resultRequests": [
    {"requestId": "FREQ1", "quantity": "NATURAL_FREQUENCY", "mode": 1},
    {"requestId": "MODE1Y", "quantity": "MODE_SHAPE", "mode": 1, "target": {"type": "NODE", "id": 3}, "component": "Y"}
  ]
}
```

- [ ] **Step 2: Write RED modal tests**

Cover:

```python
assert valid["status"] == "VALID"
assert invalid_mode_count has ANALYSIS_SPEC_INVALID_MODE_COUNT
assert mode_zero has ANALYSIS_SPEC_INVALID_MODE_INDEX
assert mode_above_count has ANALYSIS_SPEC_MODE_EXCEEDS_REQUESTED_COUNT
assert scalar_with_target has ANALYSIS_SPEC_UNSUPPORTED_RESULT_REQUEST
assert mode_shape_without_target has ANALYSIS_SPEC_UNSUPPORTED_RESULT_REQUEST
assert mode_shape_component_Z has ANALYSIS_SPEC_UNSUPPORTED_RESULT_REQUEST
assert mode_shape_component_RZ is VALID
```

Also prove `EIGENVALUE`, `NATURAL_FREQUENCY`, and `PERIOD` reject `target`, `component`, `location`, and `loadCaseId`, and prove request reorder gives identical fingerprint.

- [ ] **Step 3: Run RED**

```bash
python -m pytest tests/python/test_analysis_spec_v2_modal.py -q
```

Expected: unsupported analysis type `MODAL`.

- [ ] **Step 4: Implement modal validator and normalization**

The validator must not read a ModelSpec to check mass, DOF existence, or target existence. It checks only exact shape, positive mode count/index, mode upper bound, request IDs, and modal whitelist.

- [ ] **Step 5: Run GREEN**

```bash
python -m pytest tests/python/test_analysis_spec_v2_modal.py tests/python/test_analysis_spec_v2_static.py -q
python -m ruff check fem_core/analysis_spec/v2/modal.py fem_core/analysis_spec/v2/validator.py fem_core/analysis_spec/v2/normalization.py tests/python/test_analysis_spec_v2_modal.py
```

- [ ] **Step 6: Commit**

```bash
git add fem_core/analysis_spec/v2 tests/fixtures/analysis_spec/simple-modal-v2.json tests/python/test_analysis_spec_v2_modal.py
git commit -m "feat: add AnalysisSpec V2 modal profile"
```

---

### Task 4: TRANSIENT V2 Profile + Artifact Identity Projection

**Files:**
- Create: `fem_core/analysis_spec/v2/transient.py`
- Create: `tests/fixtures/analysis_spec/simple-transient-nodal-v2.json`
- Create: `tests/fixtures/analysis_spec/simple-transient-base-v2.json`
- Create: `tests/python/test_analysis_spec_v2_transient.py`
- Modify: `fem_core/analysis_spec/v2/validator.py`
- Modify: `fem_core/analysis_spec/v2/normalization.py`

**Interfaces:**
- `NODAL_TIME_HISTORY`: units exactly `{force: N|kN}`, nodeId positive, component X/Y, quantity FORCE.
- `UNIFORM_BASE_EXCITATION`: units exactly `{}`, component X/Y, quantity ACCELERATION.
- `loadArtifact` transport has `path` + lowercase 64-hex `sha256`; fingerprint projection drops only `path`.

- [ ] **Step 1: Add both transient fixtures**

Nodal fixture core:

```json
{
  "analysisType": "TRANSIENT",
  "units": {"force": "N"},
  "definition": {
    "time": {"timeStep": 0.01, "duration": 1.0},
    "damping": {"type": "NONE"},
    "excitation": {
      "type": "NODAL_TIME_HISTORY",
      "nodeId": 3,
      "component": "Y",
      "quantity": "FORCE",
      "loadArtifact": {"path": "loads/force.csv", "sha256": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"}
    }
  },
  "resultRequests": [{"requestId": "A3Y", "quantity": "ACCELERATION", "target": {"type": "NODE", "id": 3}, "component": "Y"}]
}
```

Base fixture uses units `{}`, `UNIFORM_BASE_EXCITATION`, and an `ABSOLUTE_ACCELERATION` request.

- [ ] **Step 2: Write RED transient intrinsic tests**

Cover exact issue families:

```text
timeStep <= 0 -> ANALYSIS_SPEC_INVALID_TIME_STEP
duration <= 0 -> ANALYSIS_SPEC_INVALID_DURATION
NONE with extra field -> ANALYSIS_SPEC_INVALID_DAMPING
negative/nonfinite alphaM or betaK -> ANALYSIS_SPEC_INVALID_DAMPING
bad loadArtifact path/SHA -> ANALYSIS_SPEC_INVALID_LOAD_ARTIFACT
wrong excitation fields/type/quantity/component -> ANALYSIS_SPEC_INVALID_EXCITATION
nodal excitation with units {} -> INVALID
base excitation with units.force -> INVALID
base excitation + bare ACCELERATION request -> ANALYSIS_SPEC_UNSUPPORTED_TRANSIENT_RESPONSE
base excitation + RELATIVE_ACCELERATION -> VALID
base excitation + ABSOLUTE_ACCELERATION -> VALID
nodal excitation + ACCELERATION -> VALID
```

Also prove shared transient `DISPLACEMENT`, `VELOCITY`, `REACTION_FORCE`, `REACTION_MOMENT`, and ELEMENT `GENERALIZED_FORCE` whitelist shapes.

- [ ] **Step 3: Write the fingerprint projection RED test**

```python
def test_transient_path_does_not_change_semantic_fingerprint() -> None:
    first = load_base_transient()
    second = deepcopy(first)
    second["definition"]["excitation"]["loadArtifact"]["path"] = "copied/eq.csv"
    assert fingerprint(first) == fingerprint(second)


def test_transient_sha_changes_semantic_fingerprint() -> None:
    first = load_base_transient()
    second = deepcopy(first)
    second["definition"]["excitation"]["loadArtifact"]["sha256"] = "b" * 64
    assert fingerprint(first) != fingerprint(second)
```

- [ ] **Step 4: Run RED**

```bash
python -m pytest tests/python/test_analysis_spec_v2_transient.py -q
```

- [ ] **Step 5: Implement transient validation and fingerprint projection**

`normalize_analysis_spec_v2()` must retain the original normalized `loadArtifact.path`. A separate fingerprint payload builder deep-copies the normalized V2 spec and removes exactly:

```python
payload["definition"]["excitation"]["loadArtifact"].pop("path")
```

only for `analysisType == "TRANSIENT"`.

- [ ] **Step 6: Run GREEN**

```bash
python -m pytest tests/python/test_analysis_spec_v2_transient.py tests/python/test_analysis_spec_v2_static.py tests/python/test_analysis_spec_v2_modal.py -q
python -m ruff check fem_core/analysis_spec/v2/transient.py fem_core/analysis_spec/v2/normalization.py tests/python/test_analysis_spec_v2_transient.py
```

- [ ] **Step 7: Commit**

```bash
git add fem_core/analysis_spec/v2 tests/fixtures/analysis_spec/simple-transient-nodal-v2.json tests/fixtures/analysis_spec/simple-transient-base-v2.json tests/python/test_analysis_spec_v2_transient.py
git commit -m "feat: add AnalysisSpec V2 transient profile"
```

---

### Task 5: Deterministic V1→V2 Migration + Bridge Command

**Files:**
- Create: `fem_core/analysis_spec/v2/migration.py`
- Create: `tests/python/test_analysis_spec_migration.py`
- Modify: `fem_core/analysis_spec/__init__.py`
- Modify: `fem_core/bridge.py`
- Modify: `tests/python/test_analysis_spec_bridge.py`

**Interfaces:**
- Produces `migrate_engineering_analysis_spec_v1_to_v2(spec: dict[str, Any]) -> dict[str, Any]`.
- Bridge command: `analysisSpec.migrateV1ToV2` with payload `{spec}`.

- [ ] **Step 1: Write RED migration tests**

```python
def test_valid_v1_static_migrates_to_valid_v2_static() -> None:
    report = migrate_engineering_analysis_spec_v1_to_v2(load_v1())
    assert report["schema"] == "FEMAGENT_ANALYSIS_SPEC_MIGRATION_V1_TO_V2"
    assert report["status"] == "MIGRATED"
    candidate = report["candidateSpec"]
    assert candidate["schemaVersion"] == "2.0"
    assert "loadCases" not in candidate
    assert candidate["definition"]["loadCases"] == load_v1()["loadCases"]
    assert report["source"]["analysisSpecFingerprint"] != report["target"]["analysisSpecFingerprint"]
```

Add invalid V1 -> `INVALID_SOURCE`; V2 input -> `UNSUPPORTED_SOURCE`; repeated migration of the same V1 -> identical candidate and target fingerprint.

- [ ] **Step 2: Run RED**

```bash
python -m pytest tests/python/test_analysis_spec_migration.py -q
```

- [ ] **Step 3: Implement pure migration**

Migration must call authoritative V1 validation first, create a new V2 dict by copying semantic fields, call authoritative public V2 validation, and return normalized valid V2 candidate plus source/target fingerprints. It must not accept a workspace parameter or call filesystem APIs.

- [ ] **Step 4: Add bridge RED/GREEN test**

In `test_analysis_spec_bridge.py`, send:

```python
{
    "protocol": BRIDGE_PROTOCOL,
    "requestId": "req-analysis-migrate",
    "command": "analysisSpec.migrateV1ToV2",
    "payload": {"spec": load_spec()},
}
```

Assert `ok is True`, `status == "MIGRATED"`, and `tmp_path` remains empty.

- [ ] **Step 5: Run GREEN**

```bash
python -m pytest tests/python/test_analysis_spec_migration.py tests/python/test_analysis_spec_bridge.py -q
python -m ruff check fem_core/analysis_spec/v2/migration.py fem_core/analysis_spec/__init__.py fem_core/bridge.py tests/python/test_analysis_spec_migration.py tests/python/test_analysis_spec_bridge.py
```

- [ ] **Step 6: Commit**

```bash
git add fem_core/analysis_spec/v2/migration.py fem_core/analysis_spec/__init__.py fem_core/bridge.py tests/python/test_analysis_spec_migration.py tests/python/test_analysis_spec_bridge.py
git commit -m "feat: add deterministic AnalysisSpec V1 to V2 migration"
```

---

### Task 6: Fail-Closed PR26 V1 Readiness/Renderer Admission

**Files:**
- Modify: `fem_core/analysis_spec/readiness.py`
- Modify: `tests/python/test_analysis_readiness.py`
- Modify: `tests/python/test_analysis_render_bridge.py`
- Test: `tests/python/test_pr26_golden_path.py`

**Interfaces:**
- Existing profile remains `OPENSEES_FRAME_2D_LINEAR_STATIC_V1`.
- Valid V2 input is intrinsically valid but unsupported by this concrete readiness profile.
- Add readiness issue `ANALYSIS_READINESS_UNSUPPORTED_ANALYSIS_SPEC_VERSION` and return `NOT_READY` with dependent checks `SKIPPED`.

- [ ] **Step 1: Write RED readiness test for a valid V2 static spec**

```python
def test_valid_v2_spec_is_not_admitted_to_pr26_v1_readiness() -> None:
    model = _model_spec()
    v1 = _bound_analysis_spec(model)
    migrated = migrate_engineering_analysis_spec_v1_to_v2(v1)
    v2 = migrated["candidateSpec"]
    assert validate_engineering_analysis_spec(v2)["status"] == "VALID"

    report = evaluate_engineering_analysis_readiness(model, v2)
    assert report["status"] == "NOT_READY"
    assert "ANALYSIS_READINESS_UNSUPPORTED_ANALYSIS_SPEC_VERSION" in _issue_codes(report)
    assert all(check["status"] == "SKIPPED" for check in report["checks"].values())
```

- [ ] **Step 2: Run RED**

```bash
python -m pytest tests/python/test_analysis_readiness.py::test_valid_v2_spec_is_not_admitted_to_pr26_v1_readiness -q
```

Expected before guard: KeyError/internal failure or incorrect use of V1 fields.

- [ ] **Step 3: Add explicit V1-profile gate after intrinsic validation**

After both specs validate and before any access to `normalized_analysis["loadCases"]`, require:

```python
if normalized_analysis.get("schemaVersion") != "1.0":
    return {
        "schema": READINESS_SCHEMA,
        "status": "NOT_READY",
        "profile": READINESS_PROFILE,
        "modelSpecFingerprint": model_fingerprint,
        "analysisSpecFingerprint": analysis_fingerprint,
        "validation": {...},
        "checks": _skipped_checks(),
        "issues": [_issue(
            "ANALYSIS_READINESS_UNSUPPORTED_ANALYSIS_SPEC_VERSION",
            "analysisSpec.schemaVersion",
            "The PR26 OpenSees readiness profile accepts only AnalysisSpec schemaVersion 1.0",
        )],
    }
```

- [ ] **Step 4: Prove render is blocked and writes nothing**

Add bridge test using valid migrated V2 and assert `analysis.renderOpenSees` returns `ok=True`, result `status="BLOCKED"`, readiness `NOT_READY`, and no `.femagent/generated-analyses` directory is created.

- [ ] **Step 5: Run V1 golden regression + new V2 block tests**

```bash
python -m pytest tests/python/test_analysis_readiness.py tests/python/test_analysis_render_bridge.py tests/python/test_pr26_golden_path.py -q
python -m ruff check fem_core/analysis_spec/readiness.py tests/python/test_analysis_readiness.py tests/python/test_analysis_render_bridge.py
```

- [ ] **Step 6: Commit**

```bash
git add fem_core/analysis_spec/readiness.py tests/python/test_analysis_readiness.py tests/python/test_analysis_render_bridge.py
git commit -m "fix: keep PR26 OpenSees analysis admission V1-only"
```

---

### Task 7: TypeScript V1/V2 Contracts + Migration Transport

**Files:**
- Modify: `packages/fem-tools/src/analysisSpecTypes.ts`
- Modify: `packages/fem-tools/src/pythonBridge.ts`
- Modify: `packages/fem-tools/src/index.ts`
- Create: `tests/ts/analysis-spec-v2.test.ts`
- Modify: `tests/ts/analysis-spec.test.ts`
- Modify: `tests/ts/analysis-readiness.test.ts`

**Interfaces:**
- `FemEngineeringAnalysisSpecInput = FemEngineeringAnalysisSpecV1Input | FemEngineeringAnalysisSpecV2Input`.
- `FemEngineeringAnalysisSpecV2Input` discriminates Static/Modal/Transient.
- `runFemAnalysisSpecMigrateV1ToV2(cwd, spec, signal?)` returns typed migration report.
- `runFemAnalysisReadiness` and `runFemAnalysisRenderOpenSees` accept `FemEngineeringAnalysisSpecV1Input`, not the broad V1|V2 union.

- [ ] **Step 1: Write RED TypeScript compile/bridge coverage**

In `analysis-spec-v2.test.ts`, construct typed values:

```ts
const modal: FemEngineeringModalAnalysisSpecV2Input = {
  schemaVersion: "2.0",
  kind: "engineering_analysis_spec",
  modelSpecFingerprint: "0".repeat(64),
  analysisType: "MODAL",
  units: {},
  definition: { modeCount: 3 },
  resultRequests: [{ requestId: "FREQ1", quantity: "NATURAL_FREQUENCY", mode: 1 }],
};
```

Also construct V2 static and both transient excitation variants and call `runFemAnalysisSpecValidate` for each. Assert all return VALID.

- [ ] **Step 2: Run RED typecheck/test**

```bash
pnpm typecheck
pnpm exec tsx --test tests/ts/analysis-spec-v2.test.ts
```

Expected: missing V2 types and migration transport.

- [ ] **Step 3: Implement discriminated types**

Keep all current V1 request interfaces available for PR26. Introduce V2-specific request unions rather than weakening V1 fields such as mandatory `loadCaseId`. Define exact modal/transient request types, damping union, excitation union, load artifact reference, and migration report.

Narrow PR26 execution interfaces so code cannot accidentally pass a V2 modal/transient spec to current readiness/render at compile time.

- [ ] **Step 4: Add migration bridge test**

Use `runFemAnalysisSpecMigrateV1ToV2(process.cwd(), v1Spec)` and assert target candidate is V2 static and target fingerprint is 64 lowercase hex.

- [ ] **Step 5: Run GREEN**

```bash
pnpm typecheck
pnpm exec tsx --test tests/ts/analysis-spec.test.ts tests/ts/analysis-spec-v2.test.ts tests/ts/analysis-readiness.test.ts
```

- [ ] **Step 6: Commit**

```bash
git add packages/fem-tools/src/analysisSpecTypes.ts packages/fem-tools/src/pythonBridge.ts packages/fem-tools/src/index.ts tests/ts/analysis-spec.test.ts tests/ts/analysis-spec-v2.test.ts tests/ts/analysis-readiness.test.ts
git commit -m "feat: add typed AnalysisSpec V2 transport"
```

---

### Task 8: Pi Validation Tool Union Without Expanding Execution Surface

**Files:**
- Modify: `.pi/extensions/analysis-spec-tools.ts`
- Modify: `tests/ts/analysis-spec-tool-registration.test.ts`
- Modify: `tests/ts/analysis-prepare-tool-registration.test.ts`

**Interfaces:**
- `fem_analysis_spec_validate` accepts V1 static plus all three V2 profiles.
- `fem_analysis_prepare_opensees` remains exactly V1 static.
- No new migration LLM-visible tool is registered.

- [ ] **Step 1: Write RED tool-registration assertions**

Extend `analysis-spec-tool-registration.test.ts`:

```ts
assert.match(extension, /Type\.Literal\("2\.0"\)/);
assert.match(extension, /Type\.Literal\("MODAL"\)/);
assert.match(extension, /Type\.Literal\("TRANSIENT"\)/);
assert.match(extension, /VALID.*V2.*intrinsic/is);
assert.match(extension, /does not.*READY|not.*READY/is);
assert.doesNotMatch(extension, /name:\s*"fem_analysis_spec_migrate/);
```

Extend prepare-tool test to prove its `analysisSpec` schema remains V1-only and guidance still says V1 linear static.

- [ ] **Step 2: Run RED**

```bash
pnpm exec tsx --test tests/ts/analysis-spec-tool-registration.test.ts tests/ts/analysis-prepare-tool-registration.test.ts
```

- [ ] **Step 3: Split TypeBox schemas by version/profile**

Use named schemas:

```ts
const analysisSpecV1Schema = Type.Object(...);
const analysisSpecV2StaticSchema = Type.Object(...);
const analysisSpecV2ModalSchema = Type.Object(...);
const analysisSpecV2TransientSchema = Type.Object(...);
const analysisSpecValidationSchema = Type.Union([
  analysisSpecV1Schema,
  analysisSpecV2StaticSchema,
  analysisSpecV2ModalSchema,
  analysisSpecV2TransientSchema,
]);
```

Bind only `analysisSpecValidationSchema` to `fem_analysis_spec_validate`. Bind `analysisSpecV1Schema` to `fem_analysis_prepare_opensees`.

Update validation guidance to say V2 VALID is intrinsic-only and does not establish target existence, modal mass, artifact integrity/time alignment, solver mapping, READY, RENDERED, or execution success.

- [ ] **Step 4: Run GREEN**

```bash
pnpm typecheck
pnpm exec tsx --test tests/ts/analysis-spec-tool-registration.test.ts tests/ts/analysis-prepare-tool-registration.test.ts
```

- [ ] **Step 5: Commit**

```bash
git add .pi/extensions/analysis-spec-tools.ts tests/ts/analysis-spec-tool-registration.test.ts tests/ts/analysis-prepare-tool-registration.test.ts
git commit -m "feat: expose AnalysisSpec V2 intrinsic validation"
```

---

### Task 9: Full PR27 Verification + Scope Audit

**Files:**
- Review all PR27 changed files.
- No production change unless verification exposes a defect covered by this spec.

**Interfaces:**
- Final state: V1 static remains executable exactly as before; V2 Static/Modal/Transient validate only.

- [ ] **Step 1: Run focused Python AnalysisSpec suite**

```bash
python -m pytest \
  tests/python/test_analysis_spec.py \
  tests/python/test_analysis_spec_fingerprint.py \
  tests/python/test_analysis_spec_v2_static.py \
  tests/python/test_analysis_spec_v2_modal.py \
  tests/python/test_analysis_spec_v2_transient.py \
  tests/python/test_analysis_spec_migration.py \
  tests/python/test_analysis_spec_bridge.py \
  tests/python/test_analysis_readiness.py \
  tests/python/test_analysis_render_bridge.py \
  tests/python/test_pr26_golden_path.py -q
```

Expected: all pass.

- [ ] **Step 2: Run focused TypeScript suite**

```bash
pnpm typecheck
pnpm exec tsx --test \
  tests/ts/analysis-spec.test.ts \
  tests/ts/analysis-spec-v2.test.ts \
  tests/ts/analysis-readiness.test.ts \
  tests/ts/analysis-spec-tool-registration.test.ts \
  tests/ts/analysis-prepare-tool-registration.test.ts
```

Expected: all pass.

- [ ] **Step 3: Run full repository verification**

```bash
pnpm typecheck
pnpm test:ts
python -m pytest
python -m ruff check .
pnpm fem:health
```

Expected: all commands succeed; existing ANSYS-result deprecation warnings may remain warnings only.

- [ ] **Step 4: Audit V1 regression and V2 scope boundaries**

Verify by diff and tests:

```text
V1 fixture normalized output/fingerprint semantics unchanged
PR26 readiness profile remains OPENSEES_FRAME_2D_LINEAR_STATIC_V1
PR26 renderer/generated-analysis verifier accepts only V1 semantics
V2 static/modal/transient never report READY or RENDERED
no OpenSees modal/transient renderer or worker implementation added
no ANSYS renderer change
no Result Intelligence/modal-result implementation
no natural-language Analysis Requirement Completion
no Controlled Repair
no nonlinear/profile expansion
no new solver permission or arbitrary command path
no migration Pi tool registration
```

- [ ] **Step 5: Review fingerprint invariants explicitly**

Confirm tests prove:

```text
V1 reorder -> same V1 fingerprint
V1 engineering fact change -> different V1 fingerprint
V2 static reorder -> same V2 fingerprint
V2 modal reorder -> same V2 fingerprint
V2 transient same SHA + different path -> same V2 fingerprint
V2 transient different SHA -> different V2 fingerprint
V1 static fingerprint != migrated V2 static fingerprint
```

- [ ] **Step 6: Commit final verification-only fixes if needed**

If verification required a spec-scoped fix, commit only those changed files with a message describing the verified defect. If no fix is needed, do not create an empty commit.

---

## Execution Order and Review Gates

Execute Tasks 1→9 in order. Each task gets its own RED→GREEN cycle and review before the next task because later tasks depend on exact contracts from earlier tasks:

```text
Task 1 V1 preservation/router
  ↓
Task 2 V2 static/shared envelope
  ↓
Task 3 modal
  ↓
Task 4 transient/fingerprint projection
  ↓
Task 5 migration/bridge
  ↓
Task 6 PR26 V1-only admission guard
  ↓
Task 7 TypeScript contracts/transport
  ↓
Task 8 Pi validation surface
  ↓
Task 9 full verification/scope audit
```

Do not merge PR27 without explicit user approval.