# PR25 Engineering Analysis Specification V1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a deterministic, solver-neutral `EngineeringAnalysisSpec V1` for explicit 2D-frame linear-static analysis intent, with strict validation, canonical normalization, stable fingerprinting, bridge transport, and a temporary SAFE validation tool.

**Architecture:** Python `fem_core.analysis_spec` is the sole engineering authority. PR25 validates AnalysisSpec-local facts only; it never resolves ModelSpec node/element existence, never decides readiness, never renders analysis code, and never executes a solver. TypeScript mirrors the transport contract. The PR25 fine-grained Agent validation tool is explicitly temporary under the long-term Modeling / Analysis / Result tool-surface convergence principle.

**Tech Stack:** Python 3.13, pytest, Ruff, `hashlib`, `json`, `math`, `re`, TypeScript 5.9, TypeBox, Node test runner, FEMagent Python bridge, Pi extensions.

**Spec:** `docs/superpowers/specs/2026-09-07-pr25-engineering-analysis-spec-v1-design.md`

## Global Constraints

- `schemaVersion="1.0"`; `kind="engineering_analysis_spec"`.
- `modelSpecFingerprint` matches `^[0-9a-f]{64}$` exactly.
- `analysisType="LINEAR_STATIC"` only.
- Force unit is `N | kN`; no inference or conversion.
- Exactly one load case; inline explicit nodal loads only.
- Every nodal load contains `nodeId`, `FX`, `FY`, `MZ`; at least one component is nonzero.
- Duplicate nodal targets are invalid and are never summed.
- Result whitelist is exactly: `NODE DISPLACEMENT X|Y`, `NODE REACTION_FORCE X|Y`, `NODE REACTION_MOMENT Z`, `ELEMENT GENERALIZED_FORCE N|VY|MZ @ END_I|END_J`.
- Validation checks AnalysisSpec-local integrity only. Model target existence, ModelSpec fingerprint matching, model readiness, unit relationship, and renderer admission belong to PR26.
- Do not call `normalize_structural_query()` from PR25 validation: it uppercases/coerces and accepts a broader vocabulary. Reuse the same result literals, but enforce the approved narrower whitelist without coercion.
- Normalization sorts `loadCases` by `loadCaseId`, `nodalLoads` by `nodeId`, and `resultRequests` by `requestId`; it never changes engineering values.
- Fingerprinting uses canonical JSON with `sort_keys=True`, `separators=(",", ":")`, `ensure_ascii=False`, `allow_nan=False`, followed by SHA-256.
- Invalid specs have `normalizedSpec=null` and `analysisSpecFingerprint=null`.
- Python is authoritative. TypeScript/TypeBox performs transport admission only.
- `analysisSpec.validate` is SAFE/read-only: no file writes, output path, renderer, permission gate, preflight, or solver run.
- Internal capability growth does not imply permanent LLM-visible tool growth. `fem_analysis_spec_validate` is a PR25 integration surface, not a permanent architecture commitment.
- Never merge without explicit user permission.

---

## File Map

Create:
- `fem_core/analysis_spec/__init__.py`
- `fem_core/analysis_spec/validator.py`
- `tests/fixtures/analysis_spec/simple-linear-static.json`
- `tests/python/test_analysis_spec.py`
- `tests/python/test_analysis_spec_fingerprint.py`
- `tests/python/test_analysis_spec_bridge.py`
- `packages/fem-tools/src/analysisSpecTypes.ts`
- `tests/ts/analysis-spec.test.ts`
- `.pi/extensions/analysis-spec-tools.ts`
- `tests/ts/analysis-spec-tool-registration.test.ts`

Modify:
- `fem_core/bridge.py`
- `packages/fem-tools/src/pythonBridge.ts`
- `packages/fem-tools/src/index.ts`
- `apps/agent/src/main.ts`

Do not modify solver adapters, ModelSpec validator/readiness/renderer behavior, Structural Response normalization, Result Intelligence, permission-gate logic, or ANSYS/OpenSees execution code.

---

### Task 1: Python EngineeringAnalysisSpec Validator

**Files:**
- Create: `fem_core/analysis_spec/__init__.py`
- Create: `fem_core/analysis_spec/validator.py`
- Create: `tests/fixtures/analysis_spec/simple-linear-static.json`
- Create: `tests/python/test_analysis_spec.py`

**Interfaces:**
- Consumes: `dict[str, Any]`.
- Produces: `validate_engineering_analysis_spec(spec: dict[str, Any]) -> dict[str, Any]`.
- Report schema: `FEMAGENT_ANALYSIS_SPEC_VALIDATION_V1`.

- [ ] **Step 1: Create the valid fixture and RED happy-path test**

Fixture:

```json
{
  "schemaVersion": "1.0",
  "kind": "engineering_analysis_spec",
  "modelSpecFingerprint": "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef",
  "analysisType": "LINEAR_STATIC",
  "units": {"force": "kN"},
  "loadCases": [{
    "loadCaseId": "LC1",
    "nodalLoads": [{"nodeId": 2, "FX": 0, "FY": -10, "MZ": 0}]
  }],
  "resultRequests": [{
    "requestId": "R1",
    "loadCaseId": "LC1",
    "quantity": "DISPLACEMENT",
    "target": {"type": "NODE", "id": 2},
    "component": "Y"
  }]
}
```

Test skeleton:

```python
from __future__ import annotations

import copy
import json
import math
import re
from pathlib import Path

from fem_core.analysis_spec import validate_engineering_analysis_spec

FIXTURE = Path("tests/fixtures/analysis_spec/simple-linear-static.json")


def load_spec() -> dict:
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


def codes(result: dict) -> set[str]:
    return {issue["code"] for issue in result["issues"]}


def assert_invalid(result: dict, code: str) -> None:
    assert result["schema"] == "FEMAGENT_ANALYSIS_SPEC_VALIDATION_V1"
    assert result["status"] == "INVALID"
    assert code in codes(result)
    assert result["normalizedSpec"] is None
    assert result["analysisSpecFingerprint"] is None


def test_valid_spec_returns_normalized_spec_and_fingerprint() -> None:
    result = validate_engineering_analysis_spec(load_spec())
    assert result["status"] == "VALID"
    assert result["issues"] == []
    assert result["normalizedSpec"] is not None
    assert re.fullmatch(r"[0-9a-f]{64}", result["analysisSpecFingerprint"])
```

- [ ] **Step 2: Run RED**

```bash
python -m pytest tests/python/test_analysis_spec.py -v
```

Expected: import failure because `fem_core.analysis_spec` does not exist.

- [ ] **Step 3: Add RED schema, binding, unit, and load tests**

Cover these exact outcomes:

```python
spec = load_spec(); spec["schemaVersion"] = "2.0"
assert_invalid(validate_engineering_analysis_spec(spec), "ANALYSIS_SPEC_INVALID_SCHEMA")

spec = load_spec(); spec["unexpected"] = True
assert_invalid(validate_engineering_analysis_spec(spec), "ANALYSIS_SPEC_UNKNOWN_FIELD")

spec = load_spec(); spec["modelSpecFingerprint"] = "ABC"
assert_invalid(validate_engineering_analysis_spec(spec), "ANALYSIS_SPEC_INVALID_MODEL_FINGERPRINT")

spec = load_spec(); spec["analysisType"] = "MODAL"
assert_invalid(validate_engineering_analysis_spec(spec), "ANALYSIS_SPEC_UNSUPPORTED_ANALYSIS_TYPE")

spec = load_spec(); spec["units"]["force"] = "lbf"
assert_invalid(validate_engineering_analysis_spec(spec), "ANALYSIS_SPEC_UNSUPPORTED_UNIT")

spec = load_spec(); spec["loadCases"] = []
assert_invalid(validate_engineering_analysis_spec(spec), "ANALYSIS_SPEC_INVALID_LOAD_CASE_COUNT")

spec = load_spec(); spec["loadCases"][0]["nodalLoads"][0] = {"nodeId": 2, "FX": 0, "FY": 0, "MZ": 0}
assert_invalid(validate_engineering_analysis_spec(spec), "ANALYSIS_SPEC_ZERO_NODAL_LOAD")
```

Also test: uppercase 64-char model fingerprint, nested unknown fields, invalid ID tokens, bool IDs, non-finite loads, bool-as-number, missing `FX/FY/MZ`, empty `nodalLoads`, and duplicate node targets (`ANALYSIS_SPEC_DUPLICATE_NODAL_LOAD_TARGET`).

- [ ] **Step 4: Add RED result-request tests**

Accepted cases must cover all four V1 families. Rejected cases must cover `DISPLACEMENT/Z`, `REACTION_MOMENT/X`, generalized force missing location, `SECTION`, node response with location, `STRESS`, `VELOCITY`, `ACCELERATION`, and `DAMPER_RESPONSE`. Duplicate `requestId` must produce `ANALYSIS_SPEC_DUPLICATE_ID`; an unknown internal `loadCaseId` must produce `ANALYSIS_SPEC_RESULT_LOAD_CASE_NOT_FOUND`.

- [ ] **Step 5: Add the PR25/PR26 boundary test**

```python
def test_validator_does_not_check_model_target_existence() -> None:
    spec = load_spec()
    spec["loadCases"][0]["nodalLoads"][0]["nodeId"] = 999999
    spec["resultRequests"][0]["target"]["id"] = 999999
    result = validate_engineering_analysis_spec(spec)
    assert result["status"] == "VALID"
```

- [ ] **Step 6: Implement strict validation helpers and V1 rules**

Use ModelSpec-style helpers and exact keys:

```python
VALIDATION_SCHEMA = "FEMAGENT_ANALYSIS_SPEC_VALIDATION_V1"
_ID_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_-]{0,63}$")
_MODEL_FINGERPRINT_RE = re.compile(r"^[0-9a-f]{64}$")
_ALLOWED_FORCE_UNITS = {"N", "kN"}
_TOP_LEVEL_KEYS = {
    "schemaVersion", "kind", "modelSpecFingerprint", "analysisType",
    "units", "loadCases", "resultRequests",
}
```

Implement `_issue`, `_is_positive_int`, `_is_finite_number`, `_validate_exact_keys`, `_validate_id_token`, `_validate_target_id`, and `_validate_number` with the same fail-closed style as ModelSpec. Compare result-request literals exactly; never uppercase input.

- [ ] **Step 7: Implement canonical normalization and fingerprint**

Normalization must construct fresh objects and sort only semantically unordered collections. Fingerprint exactly:

```python
def _fingerprint(normalized: dict[str, Any]) -> str:
    canonical = json.dumps(
        normalized,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()
```

- [ ] **Step 8: Export the Python API**

```python
from fem_core.analysis_spec.validator import validate_engineering_analysis_spec

__all__ = ["validate_engineering_analysis_spec"]
```

- [ ] **Step 9: Run GREEN and commit**

```bash
python -m pytest tests/python/test_analysis_spec.py -v
python -m ruff check fem_core/analysis_spec tests/python/test_analysis_spec.py
git add fem_core/analysis_spec tests/fixtures/analysis_spec tests/python/test_analysis_spec.py
git commit -m "feat: add EngineeringAnalysisSpec V1 validator"
```

---

### Task 2: Fingerprint Regression Contract

**Files:**
- Create: `tests/python/test_analysis_spec_fingerprint.py`
- Modify if required by RED tests: `fem_core/analysis_spec/validator.py`

**Interfaces:** Uses `validate_engineering_analysis_spec()` and locks canonical identity behavior.

- [ ] **Step 1: Write fingerprint tests**

```python
from __future__ import annotations

import copy
import json
from pathlib import Path

from fem_core.analysis_spec import validate_engineering_analysis_spec

FIXTURE = Path("tests/fixtures/analysis_spec/simple-linear-static.json")


def load_spec() -> dict:
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


def fingerprint(spec: dict) -> str:
    result = validate_engineering_analysis_spec(spec)
    assert result["status"] == "VALID"
    value = result["analysisSpecFingerprint"]
    assert isinstance(value, str)
    return value
```

Add a second nodal load and result request, reverse their order, and assert fingerprint equality. Assert fingerprint changes for changed `FY`, changed target ID, changed result component, and changed `modelSpecFingerprint`.

- [ ] **Step 2: Run focused tests, fix only canonicalization defects, then commit**

```bash
python -m pytest tests/python/test_analysis_spec_fingerprint.py -v
python -m pytest tests/python/test_analysis_spec.py tests/python/test_analysis_spec_fingerprint.py -q
python -m ruff check fem_core/analysis_spec tests/python/test_analysis_spec_fingerprint.py
git add fem_core/analysis_spec/validator.py tests/python/test_analysis_spec_fingerprint.py
git commit -m "test: lock AnalysisSpec fingerprint semantics"
```

---

### Task 3: Python Bridge Command

**Files:**
- Modify: `fem_core/bridge.py`
- Create: `tests/python/test_analysis_spec_bridge.py`

**Interfaces:** Produces bridge command `analysisSpec.validate` with payload `{"spec": object}`.

- [ ] **Step 1: Write RED bridge tests**

```python
from fem_core.bridge import handle_request
from fem_core.protocol import BRIDGE_PROTOCOL


def request(spec: object) -> dict:
    return {
        "protocol": BRIDGE_PROTOCOL,
        "requestId": "req-analysis-spec",
        "command": "analysisSpec.validate",
        "payload": {"spec": spec},
    }
```

Assert: valid content returns `ok=True/status=VALID`; invalid engineering content returns `ok=True/status=INVALID`; non-object `spec` returns `ok=False/error.code=INVALID_ARGUMENT`.

- [ ] **Step 2: Run RED**

```bash
python -m pytest tests/python/test_analysis_spec_bridge.py -v
```

Expected: `UNKNOWN_COMMAND`.

- [ ] **Step 3: Add the minimal dispatch**

```python
from fem_core.analysis_spec import validate_engineering_analysis_spec
```

```python
elif command == "analysisSpec.validate":
    result = validate_engineering_analysis_spec(_required_object(payload, "spec"))
```

- [ ] **Step 4: Run regression and commit**

```bash
python -m pytest tests/python/test_analysis_spec_bridge.py tests/python/test_model_spec_bridge.py -q
python -m pytest tests/python -q
python -m ruff check fem_core tests/python
git add fem_core/bridge.py tests/python/test_analysis_spec_bridge.py
git commit -m "feat: expose AnalysisSpec validation bridge command"
```

---

### Task 4: TypeScript Types and Transport

**Files:**
- Create: `packages/fem-tools/src/analysisSpecTypes.ts`
- Modify: `packages/fem-tools/src/pythonBridge.ts`
- Modify: `packages/fem-tools/src/index.ts`
- Create: `tests/ts/analysis-spec.test.ts`

**Interfaces:** Produces `FemEngineeringAnalysisSpecInput`, `FemAnalysisSpecValidation`, and `runFemAnalysisSpecValidate()`.

- [ ] **Step 1: Write RED TypeScript bridge test**

```ts
import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";
import {
  runFemAnalysisSpecValidate,
  type FemEngineeringAnalysisSpecInput,
} from "@femagent/fem-tools";

async function loadSpec(): Promise<FemEngineeringAnalysisSpecInput> {
  return JSON.parse(
    await readFile("tests/fixtures/analysis_spec/simple-linear-static.json", "utf8"),
  ) as FemEngineeringAnalysisSpecInput;
}

test("AnalysisSpec validation crosses the TypeScript/Python bridge", async () => {
  const result = await runFemAnalysisSpecValidate(process.cwd(), await loadSpec());
  assert.equal(result.schema, "FEMAGENT_ANALYSIS_SPEC_VALIDATION_V1");
  assert.equal(result.status, "VALID");
  assert.match(result.analysisSpecFingerprint ?? "", /^[0-9a-f]{64}$/);
});
```

Add an invalid engineering-content case that returns typed `INVALID` without throwing.

- [ ] **Step 2: Run RED**

```bash
pnpm typecheck
pnpm test:ts
```

- [ ] **Step 3: Add exact transport types**

Define force unit/status/issues, nodal load, load case, the four exact result-request variants, `FemEngineeringAnalysisSpecInput`, and:

```ts
export interface FemAnalysisSpecValidation {
  schema: "FEMAGENT_ANALYSIS_SPEC_VALIDATION_V1";
  status: "VALID" | "INVALID";
  issues: FemAnalysisSpecIssue[];
  normalizedSpec: FemEngineeringAnalysisSpecInput | null;
  analysisSpecFingerprint: string | null;
}
```

- [ ] **Step 4: Add the thin bridge wrapper**

```ts
export async function runFemAnalysisSpecValidate(
  cwd: string,
  spec: FemEngineeringAnalysisSpecInput,
  signal?: AbortSignal,
): Promise<FemAnalysisSpecValidation> {
  return await runFemCoreRequest<FemAnalysisSpecValidation>(
    cwd,
    "analysisSpec.validate",
    { spec },
    { signal },
  );
}
```

Export types/helper from `index.ts`.

- [ ] **Step 5: Run GREEN and commit**

```bash
pnpm typecheck
pnpm test:ts
git add packages/fem-tools/src/analysisSpecTypes.ts packages/fem-tools/src/pythonBridge.ts packages/fem-tools/src/index.ts tests/ts/analysis-spec.test.ts
git commit -m "feat: add AnalysisSpec TypeScript bridge contract"
```

---

### Task 5: Temporary SAFE Agent Validation Tool

**Files:**
- Create: `.pi/extensions/analysis-spec-tools.ts`
- Modify: `apps/agent/src/main.ts`
- Create: `tests/ts/analysis-spec-tool-registration.test.ts`

**Interfaces:** Produces temporary `fem_analysis_spec_validate`; consumes `runFemAnalysisSpecValidate()` only.

- [ ] **Step 1: Write RED registration/safety tests**

```ts
import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import path from "node:path";
import test from "node:test";

const TOOL_NAME = "fem_analysis_spec_validate";

test("AnalysisSpec validator is SAFE and explicitly temporary", async () => {
  const extension = await readFile(path.resolve(".pi/extensions/analysis-spec-tools.ts"), "utf8");
  assert.match(extension, /name:\s*["']fem_analysis_spec_validate["']/);
  assert.match(extension, /runFemAnalysisSpecValidate/);
  assert.match(extension, /SAFE|read-only/i);
  assert.match(extension, /temporary|tool surface|high-level/i);
  assert.doesNotMatch(extension, /runFemSolverRun/);
  assert.doesNotMatch(extension, /runFemModelSpecRenderOpenSees/);
  assert.doesNotMatch(extension, /outputPath/);
});

test("agent loads and allows AnalysisSpec validation", async () => {
  const agent = await readFile(path.resolve("apps/agent/src/main.ts"), "utf8");
  assert.match(agent, /\.pi\/extensions\/analysis-spec-tools\.ts/);
  assert.ok(agent.includes(`"${TOOL_NAME}"`));
});
```

- [ ] **Step 2: Run RED**

```bash
pnpm test:ts
```

- [ ] **Step 3: Implement the exact TypeBox transport schema and tool**

Use `{ additionalProperties: false }` at every object level and a union for the four result-request forms. Register only `fem_analysis_spec_validate`, calling `runFemAnalysisSpecValidate`.

The tool description/guidelines must explicitly say: `VALID` means intrinsic AnalysisSpec validity only; no unit/target/load inference; no ModelSpec target-existence or readiness claim; no render/solver execution; PR26 owns Analysis Readiness; this fine-grained tool is temporary and future Agent surfaces should converge into high-level Analysis capability.

- [ ] **Step 4: Load/allow the tool without changing solver permissions**

Add `.pi/extensions/analysis-spec-tools.ts` to `additionalExtensionPaths` after `model-spec-tools.ts`, and add `fem_analysis_spec_validate` to the Agent tool list. Do not add permission-gate behavior to this SAFE tool.

- [ ] **Step 5: Run GREEN and commit**

```bash
pnpm typecheck
pnpm test:ts
git add .pi/extensions/analysis-spec-tools.ts apps/agent/src/main.ts tests/ts/analysis-spec-tool-registration.test.ts
git commit -m "feat: register temporary AnalysisSpec validation tool"
```

---

### Task 6: PR25 Verification and Scope Audit

**Files:** No planned new files. Corrections are restricted to PR25 files listed in the File Map.

**Interfaces:** Produces verification evidence; no new capability.

- [ ] **Step 1: Focused PR25 tests**

```bash
python -m pytest tests/python/test_analysis_spec.py tests/python/test_analysis_spec_fingerprint.py tests/python/test_analysis_spec_bridge.py -v
```

- [ ] **Step 2: Full Python regression/lint**

```bash
python -m pytest tests/python -q
python -m ruff check fem_core tests/python
```

- [ ] **Step 3: Full TypeScript verification**

```bash
pnpm typecheck
pnpm test:ts
```

- [ ] **Step 4: Runtime health check**

```bash
pnpm fem:health
```

This confirms the existing FEM core health contract only; it is not solver-success evidence.

- [ ] **Step 5: Scope audit**

Inspect the branch diff and confirm all are false:

```text
OpenSees analysis renderer added
ANSYS analysis renderer added
solver.run or solver.preflight called by AnalysisSpec validator/tool
file-write or outputPath behavior added
ModelSpec node/element lookup inside validate_engineering_analysis_spec
unit conversion added
automatic load summation added
normalize_structural_query called by AnalysisSpec validator
natural-language analysis completion added
```

Confirm the temporary/high-level tool-surface convergence wording remains present.

- [ ] **Step 6: Diff hygiene**

```bash
git diff --check main...HEAD
git diff --stat main...HEAD
```

Expected: PR25 design/plan plus only the File Map implementation paths.

- [ ] **Step 7: If verification exposes a defect, correct only the affected PR25 path and rerun its failing command before the full suite**

Allowed correction paths are exactly:

```text
fem_core/analysis_spec/__init__.py
fem_core/analysis_spec/validator.py
fem_core/bridge.py
packages/fem-tools/src/analysisSpecTypes.ts
packages/fem-tools/src/pythonBridge.ts
packages/fem-tools/src/index.ts
.pi/extensions/analysis-spec-tools.ts
apps/agent/src/main.ts
tests/fixtures/analysis_spec/simple-linear-static.json
tests/python/test_analysis_spec.py
tests/python/test_analysis_spec_fingerprint.py
tests/python/test_analysis_spec_bridge.py
tests/ts/analysis-spec.test.ts
tests/ts/analysis-spec-tool-registration.test.ts
```

After a correction, stage the exact changed path(s) by their literal names and commit:

```bash
git commit -m "fix: close PR25 verification gaps"
```

Do not create an empty commit.

---

## Completion Gate

PR25 is ready for review only when all are true:

```text
EngineeringAnalysisSpec validator = deterministic and solver-neutral
analysisSpec.validate bridge = working
TypeScript contract = typed and thin
fem_analysis_spec_validate = SAFE/read-only and explicitly temporary
fingerprint = stable and canonical
PR25 intrinsic validation != PR26 readiness
Python tests = PASS
Ruff = PASS
TypeScript typecheck = PASS
TypeScript tests = PASS
fem:health = PASS
main = unmodified
branch = not merged
```

Do not merge without explicit user permission.
