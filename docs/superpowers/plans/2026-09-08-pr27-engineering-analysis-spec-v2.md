# PR27 — EngineeringAnalysisSpec V2 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a versioned solver-neutral `EngineeringAnalysisSpec V2` that intrinsically validates and fingerprints `LINEAR_STATIC`, `MODAL`, and linear-direct-integration `TRANSIENT` analysis intent while preserving every proven V1 static behavior and keeping all V2 profiles non-executable in PR27.

**Architecture:** Keep `validate_engineering_analysis_spec(spec)` as the single Python validation entry point and refactor its implementation into a schema-version router with isolated V1 and V2 validators. V2 uses one shared envelope plus analysis-type-discriminated definitions. Static, modal, and transient rules stay in separate modules. Transient semantic identity includes artifact SHA-256 but excludes artifact locator path. TypeScript mirrors this as a discriminated V1/V2 union. Existing PR26 readiness/render remain V1-only and reject V2 fail-closed.

**Tech Stack:** Python >=3.13, pytest >=8.4,<9, Ruff >=0.12,<1, Node >=22, TypeScript 5.9, pnpm, TypeBox, existing `femagent.bridge/v1` transport.

**Spec:** `docs/superpowers/specs/2026-09-08-pr27-engineering-analysis-spec-v2-design.md`

## Global Constraints

- V2 supports exactly `LINEAR_STATIC`, `MODAL`, and `TRANSIENT`.
- `TRANSIENT` means linear structural direct-integration time-history analysis only.
- Transient excitation supports only `NODAL_TIME_HISTORY` force and `UNIFORM_BASE_EXCITATION` acceleration.
- Transient damping supports only explicit `NONE` or explicit `RAYLEIGH`; no damping default exists.
- PR27 performs intrinsic AnalysisSpec validation only; it does not read ModelSpec targets, load artifact bytes, solver state, or result artifacts.
- Every V2 profile, including V2 `LINEAR_STATIC`, stops at `VALID` in PR27.
- Existing V1 normalized representation, validation semantics, canonicalization, fingerprints, PR26 readiness/render/generated-analysis verification, and PR26 golden path remain unchanged.
- V1 is never silently migrated during validation, readiness, rendering, or execution.
- Semantically equivalent V1 and V2 static specs intentionally have different fingerprints.
- No unit inference/conversion, target inference, load summation, sign correction, automatic repair, Semantic Role inference, or solver-control inference.
- Modal scalar quantities are `EIGENVALUE`, `NATURAL_FREQUENCY`, `PERIOD`; `MODE_SHAPE` requires NODE target, mode, and X/Y/RZ component.
- Base-excitation transient acceleration must be `RELATIVE_ACCELERATION` or `ABSOLUTE_ACCELERATION`; bare `ACCELERATION` is invalid for `UNIFORM_BASE_EXCITATION`.
- Transient normalized specs retain `loadArtifact.path`; transient fingerprint projection removes only that path and retains `loadArtifact.sha256`.
- Migration is pure/read-only, accepts only valid V1 `LINEAR_STATIC`, and is not registered as a permanent LLM-visible tool in PR27.
- PR27 adds no V2 readiness/renderer/worker/result extraction, OpenSees modal/transient execution, ANSYS V2 renderer, natural-language completion, repair, nonlinear analysis, or optimization.
- Standard verification: `pnpm typecheck`, `pnpm test:ts`, `python -m pytest`, `python -m ruff check .`, `pnpm fem:health`.

---

## File Map

### Create
- `fem_core/analysis_spec/common.py` — V2-safe primitive validators and canonical SHA helper.
- `fem_core/analysis_spec/v1.py` — preserved PR25 V1 implementation.
- `fem_core/analysis_spec/v2/__init__.py`
- `fem_core/analysis_spec/v2/validator.py`
- `fem_core/analysis_spec/v2/static.py`
- `fem_core/analysis_spec/v2/modal.py`
- `fem_core/analysis_spec/v2/transient.py`
- `fem_core/analysis_spec/v2/normalization.py`
- `fem_core/analysis_spec/v2/migration.py`
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
- `fem_core/analysis_spec/validator.py`
- `fem_core/analysis_spec/__init__.py`
- `fem_core/analysis_spec/readiness.py`
- `fem_core/bridge.py`
- `tests/python/test_analysis_spec.py`
- `tests/python/test_analysis_spec_fingerprint.py`
- `tests/python/test_analysis_spec_bridge.py`
- `tests/python/test_analysis_readiness.py`
- `tests/python/test_analysis_render_bridge.py`
- `packages/fem-tools/src/analysisSpecTypes.ts`
- `packages/fem-tools/src/pythonBridge.ts`
- `packages/fem-tools/src/index.ts`
- `.pi/extensions/analysis-spec-tools.ts`
- `tests/ts/analysis-spec.test.ts`
- `tests/ts/analysis-spec-v2.test.ts`
- `tests/ts/analysis-spec-tool-registration.test.ts`
- `tests/ts/analysis-prepare-tool-registration.test.ts`
- `tests/ts/analysis-readiness.test.ts`

---

### Task 1: Freeze V1 Behind a Version Router

**Files:**
- Create: `fem_core/analysis_spec/v1.py`
- Create: `fem_core/analysis_spec/common.py`
- Modify: `fem_core/analysis_spec/validator.py`
- Test: `tests/python/test_analysis_spec.py`
- Test: `tests/python/test_analysis_spec_fingerprint.py`

**Interfaces:**
- Public: `validate_engineering_analysis_spec(spec: dict[str, Any]) -> dict[str, Any]`.
- Internal: `validate_engineering_analysis_spec_v1(spec: Any) -> dict[str, Any]`.
- V2 helpers in `common.py`: `_issue()`, `validate_exact_keys()`, `is_positive_int()`, `is_finite_number()`, `validate_id_token()`, `validate_positive_target_id()`, `canonical_sha256()`.

- [ ] **Step 1: Write the failing V1-module parity test**

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

Expected: import failure for `fem_core.analysis_spec.v1`.

- [ ] **Step 3: Move the current V1 implementation without semantic edits**

Move the existing validator body and private V1 helpers into `v1.py` and expose:

```python
def validate_engineering_analysis_spec_v1(spec: Any) -> dict[str, Any]:
    # body copied from the current validate_engineering_analysis_spec implementation
    ...
```

When implementing, replace the comment/body marker above with the current production body verbatim. Do not change issue ordering, sort keys, numeric values, canonical JSON settings, or report fields.

Create `common.py` with concrete V2 helpers:

```python
import hashlib
import json
import math
import re
from typing import Any

ID_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_-]{0,63}$")
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


def issue(code: str, path: str, message: str) -> dict[str, str]:
    return {"severity": "ERROR", "code": code, "path": path, "message": message}


def is_positive_int(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value > 0


def is_finite_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(float(value))


def canonical_sha256(value: Any) -> str:
    raw = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()
```

`validate_exact_keys`, `validate_id_token`, and `validate_positive_target_id` must append the existing `ANALYSIS_SPEC_*` issue family and return booleans/validated values rather than raising.

- [ ] **Step 4: Make `validator.py` a version router**

```python
from typing import Any

from fem_core.analysis_spec.v1 import validate_engineering_analysis_spec_v1


def validate_engineering_analysis_spec(spec: Any) -> dict[str, Any]:
    if isinstance(spec, dict) and spec.get("schemaVersion") == "2.0":
        from fem_core.analysis_spec.v2 import validate_engineering_analysis_spec_v2
        return validate_engineering_analysis_spec_v2(spec)
    return validate_engineering_analysis_spec_v1(spec)
```

Unknown/missing schema versions continue through the proven V1 fail-closed schema error path until they explicitly equal `2.0`.

- [ ] **Step 5: Run V1 regression**

```bash
python -m pytest tests/python/test_analysis_spec.py tests/python/test_analysis_spec_fingerprint.py -q
python -m ruff check fem_core/analysis_spec/validator.py fem_core/analysis_spec/v1.py fem_core/analysis_spec/common.py
```

- [ ] **Step 6: Commit**

```bash
git add fem_core/analysis_spec/validator.py fem_core/analysis_spec/v1.py fem_core/analysis_spec/common.py tests/python/test_analysis_spec.py tests/python/test_analysis_spec_fingerprint.py
git commit -m "refactor: preserve AnalysisSpec V1 behind version router"
```

---

### Task 2: V2 Shared Envelope + LINEAR_STATIC

**Files:**
- Create: `fem_core/analysis_spec/v2/__init__.py`
- Create: `fem_core/analysis_spec/v2/validator.py`
- Create: `fem_core/analysis_spec/v2/static.py`
- Create: `fem_core/analysis_spec/v2/normalization.py`
- Create: `tests/fixtures/analysis_spec/simple-linear-static-v2.json`
- Create: `tests/python/test_analysis_spec_v2_static.py`

**Interfaces:**
- `validate_engineering_analysis_spec_v2(spec: dict[str, Any]) -> dict[str, Any]`.
- `normalize_analysis_spec_v2(spec: dict[str, Any]) -> dict[str, Any]`.
- `fingerprint_analysis_spec_v2(normalized_spec: dict[str, Any]) -> str`.

- [ ] **Step 1: Add exact V2 static fixture**

```json
{"schemaVersion":"2.0","kind":"engineering_analysis_spec","modelSpecFingerprint":"0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef","analysisType":"LINEAR_STATIC","units":{"force":"kN"},"definition":{"loadCases":[{"loadCaseId":"LC1","nodalLoads":[{"nodeId":2,"FX":0,"FY":-10,"MZ":0}]}]},"resultRequests":[{"requestId":"R1","loadCaseId":"LC1","quantity":"DISPLACEMENT","target":{"type":"NODE","id":2},"component":"Y"}]}
```

- [ ] **Step 2: Write executable RED tests**

```python
def test_v2_static_validates() -> None:
    result = validate_engineering_analysis_spec(load_v2_static())
    assert result["schema"] == "FEMAGENT_ANALYSIS_SPEC_VALIDATION_V1"
    assert result["status"] == "VALID"
    assert result["normalizedSpec"]["schemaVersion"] == "2.0"
    assert re.fullmatch(r"[0-9a-f]{64}", result["analysisSpecFingerprint"])


def test_v2_static_rejects_duplicate_load_target() -> None:
    spec = load_v2_static()
    spec["definition"]["loadCases"][0]["nodalLoads"].append(
        {"nodeId": 2, "FX": 1, "FY": 0, "MZ": 0}
    )
    result = validate_engineering_analysis_spec(spec)
    assert result["status"] == "INVALID"
    assert "ANALYSIS_SPEC_DUPLICATE_NODAL_LOAD_TARGET" in codes(result)
```

Add equivalent executable tests for unknown fields, bad discriminator, unsupported force unit, zero/multiple load cases, empty nodal loads, zero load, missing FX/FY/MZ, unsupported request, missing load-case reference, duplicate request ID, positive target IDs, and non-finite values.

Add a two-load/two-request fixture mutation, reverse `nodalLoads` and `resultRequests`, and assert identical normalized spec and fingerprint.

- [ ] **Step 3: Run RED**

```bash
python -m pytest tests/python/test_analysis_spec_v2_static.py -q
```

Expected: missing V2 module or V2 currently rejected.

- [ ] **Step 4: Implement V2 envelope/static validation and normalization**

Exact V2 top-level keys:

```python
V2_KEYS = {"schemaVersion", "kind", "modelSpecFingerprint", "analysisType", "units", "definition", "resultRequests"}
```

Static exact rules mirror V1 except load cases live at `definition.loadCases`. `resultRequests` must be a non-empty array. Normalize static load cases by `loadCaseId`, nodal loads by `nodeId`, and result requests by `requestId`.

- [ ] **Step 5: Run GREEN**

```bash
python -m pytest tests/python/test_analysis_spec_v2_static.py tests/python/test_analysis_spec.py tests/python/test_analysis_spec_fingerprint.py -q
python -m ruff check fem_core/analysis_spec/v2 tests/python/test_analysis_spec_v2_static.py
```

- [ ] **Step 6: Commit**

```bash
git add fem_core/analysis_spec/v2 tests/fixtures/analysis_spec/simple-linear-static-v2.json tests/python/test_analysis_spec_v2_static.py
git commit -m "feat: add AnalysisSpec V2 linear-static profile"
```

---

### Task 3: MODAL V2

**Files:**
- Create: `fem_core/analysis_spec/v2/modal.py`
- Create: `tests/fixtures/analysis_spec/simple-modal-v2.json`
- Create: `tests/python/test_analysis_spec_v2_modal.py`
- Modify: `fem_core/analysis_spec/v2/validator.py`
- Modify: `fem_core/analysis_spec/v2/normalization.py`

**Interfaces:**
- Units exact `{}`.
- Definition exact `{"modeCount": positive integer}`.
- Scalar requests: `EIGENVALUE|NATURAL_FREQUENCY|PERIOD` with only `requestId`, `quantity`, `mode`.
- Mode shape: `MODE_SHAPE` + NODE target + X/Y/RZ + mode.

- [ ] **Step 1: Add modal fixture**

```json
{"schemaVersion":"2.0","kind":"engineering_analysis_spec","modelSpecFingerprint":"0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef","analysisType":"MODAL","units":{},"definition":{"modeCount":3},"resultRequests":[{"requestId":"FREQ1","quantity":"NATURAL_FREQUENCY","mode":1},{"requestId":"MODE1Y","quantity":"MODE_SHAPE","mode":1,"target":{"type":"NODE","id":3},"component":"Y"}]}
```

- [ ] **Step 2: Write executable RED modal tests**

```python
def test_modal_mode_index_must_be_within_requested_count() -> None:
    spec = load_modal()
    spec["resultRequests"][0]["mode"] = 4
    result = validate_engineering_analysis_spec(spec)
    assert result["status"] == "INVALID"
    assert "ANALYSIS_SPEC_MODE_EXCEEDS_REQUESTED_COUNT" in codes(result)


def test_modal_scalar_request_rejects_target() -> None:
    spec = load_modal()
    spec["resultRequests"][0]["target"] = {"type": "NODE", "id": 3}
    result = validate_engineering_analysis_spec(spec)
    assert result["status"] == "INVALID"
    assert "ANALYSIS_SPEC_UNKNOWN_FIELD" in codes(result)


def test_mode_shape_accepts_rz() -> None:
    spec = load_modal()
    spec["resultRequests"][1]["component"] = "RZ"
    assert validate_engineering_analysis_spec(spec)["status"] == "VALID"
```

Also test `modeCount=0`, `mode=0`, scalar extra `component/location/loadCaseId`, mode-shape missing NODE target, ELEMENT target, bad component Z, duplicate requestId, non-empty requests, and deterministic request ordering.

- [ ] **Step 3: Run RED**

```bash
python -m pytest tests/python/test_analysis_spec_v2_modal.py -q
```

- [ ] **Step 4: Implement modal validation/normalization**

Do not read ModelSpec mass, target existence, solver support, or mode availability beyond the intrinsic `mode <= modeCount` contract.

- [ ] **Step 5: Run GREEN and commit**

```bash
python -m pytest tests/python/test_analysis_spec_v2_modal.py tests/python/test_analysis_spec_v2_static.py -q
python -m ruff check fem_core/analysis_spec/v2/modal.py tests/python/test_analysis_spec_v2_modal.py
git add fem_core/analysis_spec/v2 tests/fixtures/analysis_spec/simple-modal-v2.json tests/python/test_analysis_spec_v2_modal.py
git commit -m "feat: add AnalysisSpec V2 modal profile"
```

---

### Task 4: TRANSIENT V2 + Artifact Fingerprint Projection

**Files:**
- Create: `fem_core/analysis_spec/v2/transient.py`
- Create: `tests/fixtures/analysis_spec/simple-transient-nodal-v2.json`
- Create: `tests/fixtures/analysis_spec/simple-transient-base-v2.json`
- Create: `tests/python/test_analysis_spec_v2_transient.py`
- Modify: `fem_core/analysis_spec/v2/validator.py`
- Modify: `fem_core/analysis_spec/v2/normalization.py`

**Interfaces:**
- Nodal excitation units exact `{force: N|kN}`; base excitation units exact `{}`.
- `timeStep`/`duration` positive finite.
- Damping exact union `NONE | RAYLEIGH(alphaM,betaK)`.
- Artifact reference exact `{path, sha256}`; path must be non-empty workspace-relative locator with no absolute root and no `..` segment.

- [ ] **Step 1: Add both complete fixtures**

Nodal fixture:

```json
{"schemaVersion":"2.0","kind":"engineering_analysis_spec","modelSpecFingerprint":"0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef","analysisType":"TRANSIENT","units":{"force":"N"},"definition":{"time":{"timeStep":0.01,"duration":1.0},"damping":{"type":"NONE"},"excitation":{"type":"NODAL_TIME_HISTORY","nodeId":3,"component":"Y","quantity":"FORCE","loadArtifact":{"path":"loads/force.csv","sha256":"aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"}}},"resultRequests":[{"requestId":"A3Y","quantity":"ACCELERATION","target":{"type":"NODE","id":3},"component":"Y"}]}
```

Base fixture:

```json
{"schemaVersion":"2.0","kind":"engineering_analysis_spec","modelSpecFingerprint":"0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef","analysisType":"TRANSIENT","units":{},"definition":{"time":{"timeStep":0.01,"duration":1.0},"damping":{"type":"RAYLEIGH","alphaM":0.0,"betaK":0.002},"excitation":{"type":"UNIFORM_BASE_EXCITATION","component":"X","quantity":"ACCELERATION","loadArtifact":{"path":"loads/eq.csv","sha256":"aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"}}},"resultRequests":[{"requestId":"A3X","quantity":"ABSOLUTE_ACCELERATION","target":{"type":"NODE","id":3},"component":"X"}]}
```

- [ ] **Step 2: Write executable RED transient tests**

```python
def test_base_excitation_rejects_bare_acceleration() -> None:
    spec = load_base()
    spec["resultRequests"][0]["quantity"] = "ACCELERATION"
    result = validate_engineering_analysis_spec(spec)
    assert result["status"] == "INVALID"
    assert "ANALYSIS_SPEC_UNSUPPORTED_TRANSIENT_RESPONSE" in codes(result)


def test_transient_artifact_path_is_not_semantic_identity() -> None:
    first = load_base()
    second = deepcopy(first)
    second["definition"]["excitation"]["loadArtifact"]["path"] = "copies/eq.csv"
    assert fingerprint(first) == fingerprint(second)


def test_transient_artifact_sha_is_semantic_identity() -> None:
    first = load_base()
    second = deepcopy(first)
    second["definition"]["excitation"]["loadArtifact"]["sha256"] = "b" * 64
    assert fingerprint(first) != fingerprint(second)
```

Also add exact tests for non-positive/non-finite time values; `NONE` extra fields; negative/non-finite Rayleigh coefficients; bad SHA; empty/absolute/parent-traversal paths; bad excitation discriminator/component/quantity; nodal excitation with `{}` units; base excitation with force units; `RELATIVE_ACCELERATION`/`ABSOLUTE_ACCELERATION`; nodal `ACCELERATION`; common displacement/velocity/reaction/generalized-force requests; duplicate requestId; deterministic request ordering.

- [ ] **Step 3: Run RED**

```bash
python -m pytest tests/python/test_analysis_spec_v2_transient.py -q
```

- [ ] **Step 4: Implement transient validation and separate fingerprint projection**

Normalization retains path. Fingerprint projection deep-copies normalized transient input and executes:

```python
artifact = payload["definition"]["excitation"]["loadArtifact"]
del artifact["path"]
```

Then hash with `canonical_sha256(payload)`.

- [ ] **Step 5: Run GREEN and commit**

```bash
python -m pytest tests/python/test_analysis_spec_v2_transient.py tests/python/test_analysis_spec_v2_modal.py tests/python/test_analysis_spec_v2_static.py -q
python -m ruff check fem_core/analysis_spec/v2/transient.py fem_core/analysis_spec/v2/normalization.py tests/python/test_analysis_spec_v2_transient.py
git add fem_core/analysis_spec/v2 tests/fixtures/analysis_spec/simple-transient-nodal-v2.json tests/fixtures/analysis_spec/simple-transient-base-v2.json tests/python/test_analysis_spec_v2_transient.py
git commit -m "feat: add AnalysisSpec V2 transient profile"
```

---

### Task 5: Deterministic V1→V2 Migration + Bridge

**Files:**
- Create: `fem_core/analysis_spec/v2/migration.py`
- Create: `tests/python/test_analysis_spec_migration.py`
- Modify: `fem_core/analysis_spec/__init__.py`
- Modify: `fem_core/bridge.py`
- Modify: `tests/python/test_analysis_spec_bridge.py`

**Interfaces:**
- `migrate_engineering_analysis_spec_v1_to_v2(spec: dict[str, Any]) -> dict[str, Any]`.
- Bridge command `analysisSpec.migrateV1ToV2` payload `{spec}`.

- [ ] **Step 1: Write RED migration tests**

```python
def test_valid_v1_static_migrates_deterministically() -> None:
    source = load_v1()
    first = migrate_engineering_analysis_spec_v1_to_v2(source)
    second = migrate_engineering_analysis_spec_v1_to_v2(source)
    assert first == second
    assert first["status"] == "MIGRATED"
    assert first["candidateSpec"]["schemaVersion"] == "2.0"
    assert first["candidateSpec"]["definition"]["loadCases"] == source["loadCases"]
    assert first["source"]["analysisSpecFingerprint"] != first["target"]["analysisSpecFingerprint"]


def test_v2_source_is_not_migrated_again() -> None:
    report = migrate_engineering_analysis_spec_v1_to_v2(load_v2_static())
    assert report["status"] == "UNSUPPORTED_SOURCE"
```

Also test invalid V1 -> `INVALID_SOURCE`, semantic result requests preserved, and target candidate validates as V2.

- [ ] **Step 2: Run RED**

```bash
python -m pytest tests/python/test_analysis_spec_migration.py -q
```

- [ ] **Step 3: Implement pure migration**

Migration source shape is copied as:

```python
candidate = {
    "schemaVersion": "2.0",
    "kind": "engineering_analysis_spec",
    "modelSpecFingerprint": normalized_v1["modelSpecFingerprint"],
    "analysisType": "LINEAR_STATIC",
    "units": copy.deepcopy(normalized_v1["units"]),
    "definition": {"loadCases": copy.deepcopy(normalized_v1["loadCases"])},
    "resultRequests": copy.deepcopy(normalized_v1["resultRequests"]),
}
```

Validate the candidate through `validate_engineering_analysis_spec`; return normalized V2 candidate and both fingerprints. No workspace parameter or filesystem APIs.

- [ ] **Step 4: Add bridge command/test**

Import migration in `bridge.py` and add:

```python
elif command == "analysisSpec.migrateV1ToV2":
    result = migrate_engineering_analysis_spec_v1_to_v2(_required_object(payload, "spec"))
```

Bridge test asserts `ok is True`, `status == "MIGRATED"`, and `list(tmp_path.iterdir()) == []`.

- [ ] **Step 5: Run GREEN and commit**

```bash
python -m pytest tests/python/test_analysis_spec_migration.py tests/python/test_analysis_spec_bridge.py -q
python -m ruff check fem_core/analysis_spec/v2/migration.py fem_core/analysis_spec/__init__.py fem_core/bridge.py
git add fem_core/analysis_spec/v2/migration.py fem_core/analysis_spec/__init__.py fem_core/bridge.py tests/python/test_analysis_spec_migration.py tests/python/test_analysis_spec_bridge.py
git commit -m "feat: add deterministic AnalysisSpec V1 to V2 migration"
```

---

### Task 6: Keep PR26 Readiness/Renderer V1-Only

**Files:**
- Modify: `fem_core/analysis_spec/readiness.py`
- Modify: `tests/python/test_analysis_readiness.py`
- Modify: `tests/python/test_analysis_render_bridge.py`
- Test: `tests/python/test_pr26_golden_path.py`

**Interfaces:**
- Existing readiness profile stays `OPENSEES_FRAME_2D_LINEAR_STATIC_V1`.
- Valid V2 returns `NOT_READY` with `ANALYSIS_READINESS_UNSUPPORTED_ANALYSIS_SPEC_VERSION`; all execution-dependent checks are `SKIPPED`.

- [ ] **Step 1: Write RED readiness test**

```python
def test_valid_v2_is_not_admitted_to_pr26_v1_readiness() -> None:
    model = _model_spec()
    v2 = migrate_engineering_analysis_spec_v1_to_v2(_bound_analysis_spec(model))["candidateSpec"]
    assert validate_engineering_analysis_spec(v2)["status"] == "VALID"
    report = evaluate_engineering_analysis_readiness(model, v2)
    assert report["status"] == "NOT_READY"
    assert "ANALYSIS_READINESS_UNSUPPORTED_ANALYSIS_SPEC_VERSION" in _issue_codes(report)
    assert all(check["status"] == "SKIPPED" for check in report["checks"].values())
```

- [ ] **Step 2: Run RED**

```bash
python -m pytest tests/python/test_analysis_readiness.py::test_valid_v2_is_not_admitted_to_pr26_v1_readiness -q
```

- [ ] **Step 3: Add the explicit version guard before V1 field access**

After intrinsic validations and normalized/fingerprint invariant checks:

```python
if normalized_analysis.get("schemaVersion") != "1.0":
    return {
        "schema": READINESS_SCHEMA,
        "status": "NOT_READY",
        "profile": READINESS_PROFILE,
        "modelSpecFingerprint": model_fingerprint,
        "analysisSpecFingerprint": analysis_fingerprint,
        "validation": {
            "modelSpec": _compact_validation(model_validation),
            "analysisSpec": _compact_validation(analysis_validation),
        },
        "checks": _skipped_checks(),
        "issues": [
            _issue(
                "ANALYSIS_READINESS_UNSUPPORTED_ANALYSIS_SPEC_VERSION",
                "analysisSpec.schemaVersion",
                "The PR26 OpenSees readiness profile accepts only AnalysisSpec schemaVersion 1.0",
            )
        ],
    }
```

- [ ] **Step 4: Add render fail-closed test**

Use a valid migrated V2 spec with `analysis.renderOpenSees`; assert bridge `ok=True`, result `status="BLOCKED"`, readiness status `NOT_READY`, issue code above, `artifacts is None`, and no generated-analysis directory exists.

- [ ] **Step 5: Run V1/V2 admission regressions and commit**

```bash
python -m pytest tests/python/test_analysis_readiness.py tests/python/test_analysis_render_bridge.py tests/python/test_pr26_golden_path.py -q
python -m ruff check fem_core/analysis_spec/readiness.py tests/python/test_analysis_readiness.py tests/python/test_analysis_render_bridge.py
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
- Preserve old `FemAnalysisResultRequest` as the V1 static request alias used by PR26 mappings.
- New V2 request unions use distinct names: `FemAnalysisV2StaticResultRequest`, `FemAnalysisModalResultRequest`, `FemAnalysisTransientResultRequest`.
- `runFemAnalysisReadiness` and `runFemAnalysisRenderOpenSees` accept `FemEngineeringAnalysisSpecV1Input` only.
- `FemOpenSeesAnalysisRenderedResult.input.normalizedAnalysisSpec` is `FemEngineeringAnalysisSpecV1Input`.

- [ ] **Step 1: Write RED typed V2 fixture construction**

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

Add typed V2 static, nodal transient, and base transient objects and pass each to `runFemAnalysisSpecValidate`.

- [ ] **Step 2: Run RED**

```bash
pnpm typecheck
pnpm exec tsx --test tests/ts/analysis-spec-v2.test.ts
```

Expected: missing V2 types/transport.

- [ ] **Step 3: Implement exact TypeScript unions**

Define:

```ts
export type FemAnalysisTypeV2 = "LINEAR_STATIC" | "MODAL" | "TRANSIENT";
export type FemEngineeringAnalysisSpecV2Input =
  | FemEngineeringLinearStaticAnalysisSpecV2Input
  | FemEngineeringModalAnalysisSpecV2Input
  | FemEngineeringTransientAnalysisSpecV2Input;
export type FemEngineeringAnalysisSpecInput =
  | FemEngineeringAnalysisSpecV1Input
  | FemEngineeringAnalysisSpecV2Input;
```

Keep current V1 interfaces structurally unchanged under `FemEngineeringAnalysisSpecV1Input`. Add exact V2 static/modal/transient definitions and request unions. `FemAnalysisSpecValidation.normalizedSpec` becomes `FemEngineeringAnalysisSpecInput | null` without changing the report shape.

Add migration type:

```ts
export interface FemAnalysisSpecMigrationV1ToV2 {
  schema: "FEMAGENT_ANALYSIS_SPEC_MIGRATION_V1_TO_V2";
  status: "MIGRATED" | "INVALID_SOURCE" | "UNSUPPORTED_SOURCE";
  source?: { schemaVersion: "1.0"; analysisSpecFingerprint: string };
  target?: { schemaVersion: "2.0"; analysisSpecFingerprint: string };
  candidateSpec: FemEngineeringLinearStaticAnalysisSpecV2Input | null;
}
```

- [ ] **Step 4: Add migration transport**

```ts
export async function runFemAnalysisSpecMigrateV1ToV2(
  cwd: string,
  spec: FemEngineeringAnalysisSpecV1Input,
  signal?: AbortSignal,
): Promise<FemAnalysisSpecMigrationV1ToV2> {
  return await runFemCoreRequest<FemAnalysisSpecMigrationV1ToV2>(
    cwd,
    "analysisSpec.migrateV1ToV2",
    { spec },
    { signal },
  );
}
```

Export new types/function from `index.ts`.

- [ ] **Step 5: Run GREEN and commit**

```bash
pnpm typecheck
pnpm exec tsx --test tests/ts/analysis-spec.test.ts tests/ts/analysis-spec-v2.test.ts tests/ts/analysis-readiness.test.ts
git add packages/fem-tools/src/analysisSpecTypes.ts packages/fem-tools/src/pythonBridge.ts packages/fem-tools/src/index.ts tests/ts/analysis-spec.test.ts tests/ts/analysis-spec-v2.test.ts tests/ts/analysis-readiness.test.ts
git commit -m "feat: add typed AnalysisSpec V2 transport"
```

---

### Task 8: Pi Validation Union Without Expanding Execution Surface

**Files:**
- Modify: `.pi/extensions/analysis-spec-tools.ts`
- Modify: `tests/ts/analysis-spec-tool-registration.test.ts`
- Modify: `tests/ts/analysis-prepare-tool-registration.test.ts`

**Interfaces:**
- `fem_analysis_spec_validate` accepts V1 static plus all three V2 profiles.
- `fem_analysis_prepare_opensees` remains exactly V1 static.
- No migration Pi tool is registered.

- [ ] **Step 1: Write RED registration/guidance assertions**

```ts
assert.match(extension, /Type\.Literal\("2\.0"\)/);
assert.match(extension, /Type\.Literal\("MODAL"\)/);
assert.match(extension, /Type\.Literal\("TRANSIENT"\)/);
assert.match(extension, /VALID.*V2.*intrinsic/is);
assert.match(extension, /V2.*not.*READY|V2.*does not.*READY/is);
assert.doesNotMatch(extension, /name:\s*"fem_analysis_spec_migrate/);
```

Prepare-tool test must still find V1-only wording and must not find a V2 union bound to the `analysisSpec` field of `fem_analysis_prepare_opensees`.

- [ ] **Step 2: Run RED**

```bash
pnpm exec tsx --test tests/ts/analysis-spec-tool-registration.test.ts tests/ts/analysis-prepare-tool-registration.test.ts
```

- [ ] **Step 3: Build explicit TypeBox schemas**

Create named schemas `analysisSpecV1Schema`, `analysisSpecV2StaticSchema`, `analysisSpecV2ModalSchema`, `analysisSpecV2TransientNodalSchema`, and `analysisSpecV2TransientBaseSchema`. Build:

```ts
const analysisSpecValidationSchema = Type.Union([
  analysisSpecV1Schema,
  analysisSpecV2StaticSchema,
  analysisSpecV2ModalSchema,
  analysisSpecV2TransientNodalSchema,
  analysisSpecV2TransientBaseSchema,
]);
```

Bind this union only to `fem_analysis_spec_validate`. Keep `analysisSpecV1Schema` bound to `fem_analysis_prepare_opensees`.

Update guidance to state V2 VALID proves only intrinsic solver-neutral validity and does not establish target existence, modal mass, artifact integrity/time alignment, solver response mapping, READY, RENDERED, or execution success.

- [ ] **Step 4: Run GREEN and commit**

```bash
pnpm typecheck
pnpm exec tsx --test tests/ts/analysis-spec-tool-registration.test.ts tests/ts/analysis-prepare-tool-registration.test.ts
git add .pi/extensions/analysis-spec-tools.ts tests/ts/analysis-spec-tool-registration.test.ts tests/ts/analysis-prepare-tool-registration.test.ts
git commit -m "feat: expose AnalysisSpec V2 intrinsic validation"
```

---

### Task 9: Full PR27 Verification + Scope Audit

**Files:** Review every PR27 changed file; change production code only when a failing verification identifies a defect inside this approved spec.

**Interfaces:** Final state is V1 static executable as before; V2 Static/Modal/Transient intrinsically validatable only.

- [ ] **Step 1: Run focused Python suite**

```bash
python -m pytest tests/python/test_analysis_spec.py tests/python/test_analysis_spec_fingerprint.py tests/python/test_analysis_spec_v2_static.py tests/python/test_analysis_spec_v2_modal.py tests/python/test_analysis_spec_v2_transient.py tests/python/test_analysis_spec_migration.py tests/python/test_analysis_spec_bridge.py tests/python/test_analysis_readiness.py tests/python/test_analysis_render_bridge.py tests/python/test_pr26_golden_path.py -q
```

- [ ] **Step 2: Run focused TypeScript suite**

```bash
pnpm typecheck
pnpm exec tsx --test tests/ts/analysis-spec.test.ts tests/ts/analysis-spec-v2.test.ts tests/ts/analysis-readiness.test.ts tests/ts/analysis-spec-tool-registration.test.ts tests/ts/analysis-prepare-tool-registration.test.ts
```

- [ ] **Step 3: Run full repository verification**

```bash
pnpm typecheck
pnpm test:ts
python -m pytest
python -m ruff check .
pnpm fem:health
```

- [ ] **Step 4: Audit exact scope invariants**

Confirm the diff/tests prove all of these:

```text
V1 normalized/fingerprint semantics unchanged
PR26 profile remains OPENSEES_FRAME_2D_LINEAR_STATIC_V1
PR26 V1 golden path remains green
V2 static/modal/transient never report READY or RENDERED
no OpenSees modal/transient renderer or worker added
no ANSYS renderer change
no modal/transient Result Intelligence artifact added
no natural-language Analysis Requirement Completion
no Controlled Repair
no nonlinear or extra analysis family
no solver permission expansion or arbitrary command path
no migration LLM-visible tool
```

- [ ] **Step 5: Audit fingerprint invariants**

Confirm tests explicitly prove:

```text
V1 reorder => same V1 fingerprint
V1 engineering-fact change => different V1 fingerprint
V2 static reorder => same V2 fingerprint
V2 modal reorder => same V2 fingerprint
V2 transient same SHA + different path => same V2 fingerprint
V2 transient different SHA => different V2 fingerprint
V1 static fingerprint != migrated V2 static fingerprint
```

- [ ] **Step 6: Commit only a verification-discovered spec-scoped fix**

If all verification commands pass without code changes, do not create a commit. If one fails, fix only the defect demonstrated by that failing check, rerun the failing focused test plus the full verification set, then commit the exact changed files with a descriptive message.

---

## Execution Order and Review Gates

Execute Tasks 1→9 in order, with a fresh RED→GREEN cycle and review at each task boundary:

```text
1 V1 preservation/router
2 V2 shared envelope + static
3 modal
4 transient + artifact identity
5 migration + bridge
6 PR26 V1-only admission guard
7 TypeScript contracts + transport
8 Pi validation surface
9 full verification + scope audit
```

Do not merge PR27 without explicit user approval.