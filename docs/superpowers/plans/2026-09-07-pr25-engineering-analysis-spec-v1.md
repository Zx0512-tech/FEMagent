# PR25 Engineering Analysis Specification V1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a deterministic, solver-neutral `EngineeringAnalysisSpec V1` contract for explicit 2D-frame linear-static analysis intent, including strict validation, canonical normalization, stable fingerprinting, bridge transport, and a temporary SAFE validation tool.

**Architecture:** Python `fem_core.analysis_spec` is the sole engineering authority. It validates AnalysisSpec-local facts only, never checks whether referenced model nodes/elements exist, never executes a solver, and never renders solver code. TypeScript mirrors the transport contract and exposes a thin bridge helper. A fine-grained Pi validation tool is allowed in PR25 for development/integration, but it is explicitly temporary under the long-term tool-surface convergence principle.

**Tech Stack:** Python 3.13, `hashlib`, `json`, `math`, `re`, pytest, Ruff, TypeScript 5.9, TypeBox, Node test runner, existing FEMagent Python bridge and Pi extension runtime.

**Spec:** `docs/superpowers/specs/2026-09-07-pr25-engineering-analysis-spec-v1-design.md`

## Global Constraints

- V1 `schemaVersion` is exactly `1.0` and `kind` is exactly `engineering_analysis_spec`.
- `modelSpecFingerprint` is mandatory and must match `^[0-9a-f]{64}$`.
- V1 `analysisType` is exactly `LINEAR_STATIC`.
- V1 force unit is exactly `N | kN`; no unit inference or conversion.
- V1 contains exactly one explicit load case.
- V1 load source is inline nodal loads only; every nodal load explicitly contains `nodeId`, `FX`, `FY`, and `MZ`.
- Each nodal-load record must contain at least one non-zero component; duplicate target nodes in one load case are invalid and are never summed.
- V1 result requests are limited to: node `DISPLACEMENT X|Y`, node `REACTION_FORCE X|Y`, node `REACTION_MOMENT Z`, and element `GENERALIZED_FORCE N|VY|MZ @ END_I|END_J`.
- PR25 validates AnalysisSpec-local referential integrity only. It must not check whether node/element IDs exist in a ModelSpec or whether the model is READY; those checks belong to PR26 Analysis Readiness.
- PR25 does not call `normalize_structural_query()` because that function uppercases/coerces inputs and supports a broader vocabulary. PR25 uses the same canonical result literals but enforces its own strict, narrower whitelist without coercion.
- Normalization sorts `loadCases` by `loadCaseId`, `nodalLoads` by `nodeId`, and `resultRequests` by `requestId`; it does not change values, signs, units, targets, or missing fields.
- `analysisSpecFingerprint` uses the same canonical JSON serialization strategy as ModelSpec: `sort_keys=True`, `separators=(",", ":")`, `ensure_ascii=False`, `allow_nan=False`, then SHA-256.
- Invalid specs return `normalizedSpec=null` and `analysisSpecFingerprint=null`.
- Python is the only engineering validator. TypeScript/TypeBox is transport/schema admission only and must not become an independent engineering decision path.
- `analysisSpec.validate` is SAFE/read-only: no file writes, no output path, no renderer, no permission gate, no solver preflight, no solver run.
- Internal capability growth does not imply permanent LLM-visible tool growth. `fem_analysis_spec_validate` is a PR25 integration surface, not a permanent architecture commitment.
- No merge to `main` without explicit user permission.

---

## File Structure

Create:

- `fem_core/analysis_spec/__init__.py` — public Python export only.
- `fem_core/analysis_spec/validator.py` — strict V1 validation, canonical normalization, fingerprinting.
- `tests/fixtures/analysis_spec/simple-linear-static.json` — stable valid AnalysisSpec fixture.
- `tests/python/test_analysis_spec.py` — schema, load, result-request, boundary tests.
- `tests/python/test_analysis_spec_fingerprint.py` — deterministic identity tests.
- `tests/python/test_analysis_spec_bridge.py` — bridge routing and transport/domain-boundary tests.
- `packages/fem-tools/src/analysisSpecTypes.ts` — TypeScript transport types.
- `tests/ts/analysis-spec.test.ts` — real TypeScript→Python bridge tests.
- `.pi/extensions/analysis-spec-tools.ts` — temporary SAFE/read-only Agent validation tool.
- `tests/ts/analysis-spec-tool-registration.test.ts` — registration and safety/tool-surface tests.

Modify:

- `fem_core/bridge.py` — import validator and dispatch `analysisSpec.validate`.
- `packages/fem-tools/src/pythonBridge.ts` — add `runFemAnalysisSpecValidate()`.
- `packages/fem-tools/src/index.ts` — export AnalysisSpec types/helper.
- `apps/agent/src/main.ts` — load and allow the temporary PR25 AnalysisSpec validation tool.

Do not modify solver adapters, OpenSees renderer code, ANSYS renderer code, Result Intelligence, Structural Response normalization, permission-gate code, or ModelSpec validation/readiness behavior.

---

### Task 1: Python EngineeringAnalysisSpec V1 Validator

**Files:**
- Create: `fem_core/analysis_spec/__init__.py`
- Create: `fem_core/analysis_spec/validator.py`
- Create: `tests/fixtures/analysis_spec/simple-linear-static.json`
- Create: `tests/python/test_analysis_spec.py`

**Interfaces:**
- Consumes: `spec: dict[str, Any]`.
- Produces: `validate_engineering_analysis_spec(spec: dict[str, Any]) -> dict[str, Any]`.
- Result schema: `FEMAGENT_ANALYSIS_SPEC_VALIDATION_V1`.
- Result status: `VALID | INVALID`.

- [ ] **Step 1: Add the valid fixture and RED happy-path test**

Create `tests/fixtures/analysis_spec/simple-linear-static.json`:

```json
{
  "schemaVersion": "1.0",
  "kind": "engineering_analysis_spec",
  "modelSpecFingerprint": "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef",
  "analysisType": "LINEAR_STATIC",
  "units": {"force": "kN"},
  "loadCases": [
    {
      "loadCaseId": "LC1",
      "nodalLoads": [
        {"nodeId": 2, "FX": 0, "FY": -10, "MZ": 0}
      ]
    }
  ],
  "resultRequests": [
    {
      "requestId": "R1",
      "loadCaseId": "LC1",
      "quantity": "DISPLACEMENT",
      "target": {"type": "NODE", "id": 2},
      "component": "Y"
    }
  ]
}
```

Start `tests/python/test_analysis_spec.py` with helpers patterned after `test_model_spec.py`:

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


def test_valid_linear_static_spec_returns_normalized_spec_and_fingerprint() -> None:
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

Expected: import/collection failure because `fem_core.analysis_spec` does not exist.

- [ ] **Step 3: Add RED schema/model-binding/unit tests**

Add cases proving:

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
```

Also cover uppercase 64-character fingerprint rejection and unknown nested fields in `units`, load case, nodal load, result request, and target.

- [ ] **Step 4: Add RED load-case/nodal-load tests**

Cover exact-one-load-case behavior, invalid IDs, duplicate node targets, zero load, non-finite values, bool-as-number, and missing explicit components:

```python
spec = load_spec(); spec["loadCases"] = []
assert_invalid(validate_engineering_analysis_spec(spec), "ANALYSIS_SPEC_INVALID_LOAD_CASE_COUNT")

spec = load_spec(); spec["loadCases"].append(copy.deepcopy(spec["loadCases"][0]))
assert_invalid(validate_engineering_analysis_spec(spec), "ANALYSIS_SPEC_INVALID_LOAD_CASE_COUNT")

spec = load_spec(); spec["loadCases"][0]["nodalLoads"][0] = {"nodeId": 2, "FX": 0, "FY": 0, "MZ": 0}
assert_invalid(validate_engineering_analysis_spec(spec), "ANALYSIS_SPEC_ZERO_NODAL_LOAD")

spec = load_spec(); spec["loadCases"][0]["nodalLoads"].append(
    {"nodeId": 2, "FX": 1, "FY": 0, "MZ": 0}
)
assert_invalid(validate_engineering_analysis_spec(spec), "ANALYSIS_SPEC_DUPLICATE_NODAL_LOAD_TARGET")
```

- [ ] **Step 5: Add RED result-request whitelist tests**

Test all accepted forms:

```text
NODE DISPLACEMENT X/Y
NODE REACTION_FORCE X/Y
NODE REACTION_MOMENT Z
ELEMENT GENERALIZED_FORCE N/VY/MZ with END_I/END_J
```

Test rejected forms:

```text
DISPLACEMENT Z
REACTION_MOMENT X
GENERALIZED_FORCE with SECTION
GENERALIZED_FORCE without location
NODE response with location
STRESS
VELOCITY
ACCELERATION
DAMPER_RESPONSE
```

Also prove duplicate `requestId` gives `ANALYSIS_SPEC_DUPLICATE_ID` and a result request referencing another load case gives `ANALYSIS_SPEC_RESULT_LOAD_CASE_NOT_FOUND`.

- [ ] **Step 6: Add the deliberate PR25/PR26 boundary test**

Use IDs that cannot exist in the fixture ModelSpec context:

```python
def test_analysis_spec_does_not_validate_model_target_existence() -> None:
    spec = load_spec()
    spec["loadCases"][0]["nodalLoads"][0]["nodeId"] = 999999
    spec["resultRequests"][0]["target"]["id"] = 999999
    result = validate_engineering_analysis_spec(spec)
    assert result["status"] == "VALID"
```

This test must remain even after PR26 exists; it protects the intrinsic-validation boundary.

- [ ] **Step 7: Implement the minimal deterministic validator**

In `validator.py`, define the approved constants and helpers:

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

Implement ModelSpec-style helpers:

```python
def _issue(issues, severity, code, path, message): ...
def _is_positive_int(value): ...
def _is_finite_number(value): ...
def _validate_exact_keys(value, expected, path, issues): ...
def _validate_id_token(value, path, issues): ...
def _validate_target_id(value, path, issues): ...
def _validate_number(value, path, issues): ...
```

Result-request validation must compare exact submitted strings. Do not uppercase them and do not call `normalize_structural_query()`.

- [ ] **Step 8: Implement canonical normalization and fingerprint in the same authoritative module**

```python
def _normalize_spec(spec: dict[str, Any]) -> dict[str, Any]:
    return {
        "schemaVersion": spec["schemaVersion"],
        "kind": spec["kind"],
        "modelSpecFingerprint": spec["modelSpecFingerprint"],
        "analysisType": spec["analysisType"],
        "units": {"force": spec["units"]["force"]},
        "loadCases": sorted(
            (
                {
                    "loadCaseId": case["loadCaseId"],
                    "nodalLoads": sorted(
                        (dict(load) for load in case["nodalLoads"]),
                        key=lambda load: load["nodeId"],
                    ),
                }
                for case in spec["loadCases"]
            ),
            key=lambda case: case["loadCaseId"],
        ),
        "resultRequests": sorted(
            (dict(request) for request in spec["resultRequests"]),
            key=lambda request: request["requestId"],
        ),
    }
```

When copying `target`, construct `{"type": ..., "id": ...}` explicitly so normalized output is a fresh canonical structure. Include `location` only for requests that supplied/require it.

Fingerprint:

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

- [ ] **Step 9: Export the public Python API**

`fem_core/analysis_spec/__init__.py`:

```python
from fem_core.analysis_spec.validator import validate_engineering_analysis_spec

__all__ = ["validate_engineering_analysis_spec"]
```

- [ ] **Step 10: Run focused GREEN + lint**

```bash
python -m pytest tests/python/test_analysis_spec.py -v
python -m ruff check fem_core/analysis_spec tests/python/test_analysis_spec.py
```

Expected: PASS.

- [ ] **Step 11: Commit Task 1**

```bash
git add fem_core/analysis_spec tests/fixtures/analysis_spec tests/python/test_analysis_spec.py
git commit -m "feat: add EngineeringAnalysisSpec V1 validator"
```

---

### Task 2: Canonical Fingerprint Regression Contract

**Files:**
- Create: `tests/python/test_analysis_spec_fingerprint.py`
- Modify only if tests reveal a defect: `fem_core/analysis_spec/validator.py`

**Interfaces:**
- Consumes: `validate_engineering_analysis_spec()` from Task 1.
- Produces: regression guarantees for AnalysisSpec identity.

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
    assert result["analysisSpecFingerprint"] is not None
    return result["analysisSpecFingerprint"]
```

Add a second nodal load and a second result request, then assert reversing each collection does not change the fingerprint. Assert changing `FY`, a target ID, result component, and `modelSpecFingerprint` each changes the fingerprint.

- [ ] **Step 2: Run focused test**

```bash
python -m pytest tests/python/test_analysis_spec_fingerprint.py -v
```

Expected: PASS if Task 1 normalization is correct; if RED, change only canonicalization/fingerprint behavior required by the approved spec.

- [ ] **Step 3: Run combined core tests**

```bash
python -m pytest tests/python/test_analysis_spec.py tests/python/test_analysis_spec_fingerprint.py -q
python -m ruff check fem_core/analysis_spec tests/python/test_analysis_spec.py tests/python/test_analysis_spec_fingerprint.py
```

- [ ] **Step 4: Commit Task 2**

```bash
git add fem_core/analysis_spec/validator.py tests/python/test_analysis_spec_fingerprint.py
git commit -m "test: lock AnalysisSpec fingerprint semantics"
```

---

### Task 3: Python Bridge Command

**Files:**
- Modify: `fem_core/bridge.py`
- Create: `tests/python/test_analysis_spec_bridge.py`

**Interfaces:**
- Consumes: `validate_engineering_analysis_spec(spec)`.
- Produces bridge command: `analysisSpec.validate`.
- Payload: `{"spec": {...}}`.

- [ ] **Step 1: Write RED bridge tests**

Follow the current `test_model_spec_bridge.py` envelope exactly:

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

Assert:

```text
valid AnalysisSpec -> response.ok == True, result.status == VALID
invalid engineering content -> response.ok == True, result.status == INVALID
non-object payload.spec -> response.ok == False, error.code == INVALID_ARGUMENT
```

- [ ] **Step 2: Run RED**

```bash
python -m pytest tests/python/test_analysis_spec_bridge.py -v
```

Expected: `UNKNOWN_COMMAND` for `analysisSpec.validate`.

- [ ] **Step 3: Add minimal bridge routing**

In `fem_core/bridge.py`:

```python
from fem_core.analysis_spec import validate_engineering_analysis_spec
```

and beside other spec commands:

```python
elif command == "analysisSpec.validate":
    result = validate_engineering_analysis_spec(_required_object(payload, "spec"))
```

Do not add workspace I/O, solver calls, permission handling, or ModelSpec lookup.

- [ ] **Step 4: Run bridge + Python regression suite**

```bash
python -m pytest tests/python/test_analysis_spec_bridge.py tests/python/test_model_spec_bridge.py -q
python -m pytest tests/python -q
python -m ruff check fem_core tests/python
```

Expected: PASS.

- [ ] **Step 5: Commit Task 3**

```bash
git add fem_core/bridge.py tests/python/test_analysis_spec_bridge.py
git commit -m "feat: expose AnalysisSpec validation bridge command"
```

---

### Task 4: TypeScript Contract and Bridge Transport

**Files:**
- Create: `packages/fem-tools/src/analysisSpecTypes.ts`
- Modify: `packages/fem-tools/src/pythonBridge.ts`
- Modify: `packages/fem-tools/src/index.ts`
- Create: `tests/ts/analysis-spec.test.ts`

**Interfaces:**
- Consumes: Python bridge command `analysisSpec.validate`.
- Produces: `FemEngineeringAnalysisSpecInput`, `FemAnalysisSpecValidation`, and `runFemAnalysisSpecValidate(cwd, spec, signal?)`.

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

test("AnalysisSpec validation crosses the strict TypeScript/Python bridge", async () => {
  const result = await runFemAnalysisSpecValidate(process.cwd(), await loadSpec());
  assert.equal(result.schema, "FEMAGENT_ANALYSIS_SPEC_VALIDATION_V1");
  assert.equal(result.status, "VALID");
  assert.match(result.analysisSpecFingerprint ?? "", /^[0-9a-f]{64}$/);
});
```

Add an invalid engineering-content case and assert it returns typed `INVALID` rather than throwing a `FemCoreError`.

- [ ] **Step 2: Run RED**

```bash
pnpm typecheck
pnpm test:ts
```

Expected: missing AnalysisSpec exports/helper.

- [ ] **Step 3: Add exact TypeScript transport types**

In `analysisSpecTypes.ts`, define:

```ts
export type FemAnalysisSpecForceUnit = "N" | "kN";
export type FemAnalysisSpecStatus = "VALID" | "INVALID";
export type FemAnalysisSpecIssueSeverity = "ERROR" | "WARNING";

export interface FemAnalysisSpecNodalLoad {
  nodeId: number;
  FX: number;
  FY: number;
  MZ: number;
}

export interface FemAnalysisSpecLoadCase {
  loadCaseId: string;
  nodalLoads: FemAnalysisSpecNodalLoad[];
}
```

Define the result-request union with exact V1 variants, including `location` only on `GENERALIZED_FORCE`. Define:

```ts
export interface FemEngineeringAnalysisSpecInput {
  schemaVersion: "1.0";
  kind: "engineering_analysis_spec";
  modelSpecFingerprint: string;
  analysisType: "LINEAR_STATIC";
  units: { force: FemAnalysisSpecForceUnit };
  loadCases: FemAnalysisSpecLoadCase[];
  resultRequests: FemAnalysisSpecResultRequest[];
}

export interface FemAnalysisSpecValidation {
  schema: "FEMAGENT_ANALYSIS_SPEC_VALIDATION_V1";
  status: FemAnalysisSpecStatus;
  issues: FemAnalysisSpecIssue[];
  normalizedSpec: FemEngineeringAnalysisSpecInput | null;
  analysisSpecFingerprint: string | null;
}
```

- [ ] **Step 4: Add thin Python bridge wrapper**

In `pythonBridge.ts` import the new types and add:

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

- [ ] **Step 5: Export the public TS surface**

Update `packages/fem-tools/src/index.ts` to export all AnalysisSpec types and `runFemAnalysisSpecValidate`.

- [ ] **Step 6: Run GREEN**

```bash
pnpm typecheck
pnpm test:ts
```

Expected: PASS.

- [ ] **Step 7: Commit Task 4**

```bash
git add packages/fem-tools/src tests/ts/analysis-spec.test.ts
git commit -m "feat: add AnalysisSpec TypeScript bridge contract"
```

---

### Task 5: Temporary SAFE AnalysisSpec Agent Validation Tool

**Files:**
- Create: `.pi/extensions/analysis-spec-tools.ts`
- Modify: `apps/agent/src/main.ts`
- Create: `tests/ts/analysis-spec-tool-registration.test.ts`

**Interfaces:**
- Consumes: `runFemAnalysisSpecValidate()`.
- Produces temporary Pi tool: `fem_analysis_spec_validate`.
- Safety classification: SAFE/read-only.

- [ ] **Step 1: Write RED registration/safety tests**

```ts
import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import path from "node:path";
import test from "node:test";

const TOOL_NAME = "fem_analysis_spec_validate";

test("AnalysisSpec validation is a dedicated SAFE temporary Pi tool", async () => {
  const extension = await readFile(
    path.resolve(".pi/extensions/analysis-spec-tools.ts"),
    "utf8",
  );
  assert.match(extension, /name:\s*["']fem_analysis_spec_validate["']/);
  assert.match(extension, /runFemAnalysisSpecValidate/);
  assert.match(extension, /SAFE|read-only/i);
  assert.match(extension, /temporary|tool surface|high-level/i);
  assert.doesNotMatch(extension, /runFemSolverRun/);
  assert.doesNotMatch(extension, /runFemModelSpecRenderOpenSees/);
  assert.doesNotMatch(extension, /outputPath/);
});

test("agent loads and allows the temporary AnalysisSpec validation tool", async () => {
  const agent = await readFile(path.resolve("apps/agent/src/main.ts"), "utf8");
  assert.match(agent, /\.pi\/extensions\/analysis-spec-tools\.ts/);
  assert.ok(agent.includes(`"${TOOL_NAME}"`));
});
```

- [ ] **Step 2: Run RED**

```bash
pnpm test:ts
```

Expected: missing extension/tool registration.

- [ ] **Step 3: Implement exact TypeBox transport schema**

Create `.pi/extensions/analysis-spec-tools.ts` with exact V1 top-level and nested object schemas using `{ additionalProperties: false }`. Use a union for the four allowed result-request shapes. This schema is transport admission only; the tool must still call Python for authoritative validation.

Register:

```ts
pi.registerTool({
  name: "fem_analysis_spec_validate",
  label: "Validate FEM Analysis Specification",
  description:
    "Validate a V1 linear-static EngineeringAnalysisSpec through the authoritative Python FEM core. SAFE and read-only. This fine-grained PR25 tool is a temporary integration surface; long-term Agent tools should converge into higher-level Analysis capabilities.",
  parameters: Type.Object({ spec: analysisSpecSchema }, { additionalProperties: false }),
  async execute(_toolCallId, params, signal, _onUpdate, ctx) {
    const report = await runFemAnalysisSpecValidate(
      ctx.cwd,
      params.spec as FemEngineeringAnalysisSpecInput,
      signal,
    );
    return toolResult(report);
  },
});
```

Prompt guidelines must state:

```text
VALID means intrinsic AnalysisSpec validity only.
Do not infer units, node IDs, element IDs, load directions, zero components, or result targets.
Do not claim node/element existence or analysis readiness from this tool.
Do not run/render a solver.
PR26 performs ModelSpec+AnalysisSpec readiness.
This fine-grained tool is not a permanent tool-surface commitment.
```

- [ ] **Step 4: Add extension to Agent loader/allow-list**

In `apps/agent/src/main.ts`, append `analysis-spec-tools.ts` after `model-spec-tools.ts` and add `fem_analysis_spec_validate` after the ModelSpec authoring tools. Do not add solver/render functionality to this extension.

- [ ] **Step 5: Run GREEN**

```bash
pnpm typecheck
pnpm test:ts
```

Expected: PASS.

- [ ] **Step 6: Commit Task 5**

```bash
git add .pi/extensions/analysis-spec-tools.ts apps/agent/src/main.ts tests/ts/analysis-spec-tool-registration.test.ts
git commit -m "feat: register temporary AnalysisSpec validation tool"
```

---

### Task 6: Full PR25 Verification and Scope Audit

**Files:**
- No planned production-file additions.
- Modify only defects revealed by the verification commands below.

**Interfaces:**
- Produces evidence that PR25 is complete without crossing into PR26/solver responsibilities.

- [ ] **Step 1: Run focused Python PR25 tests**

```bash
python -m pytest \
  tests/python/test_analysis_spec.py \
  tests/python/test_analysis_spec_fingerprint.py \
  tests/python/test_analysis_spec_bridge.py -v
```

Expected: PASS.

- [ ] **Step 2: Run complete Python regression and lint**

```bash
python -m pytest tests/python -q
python -m ruff check fem_core tests/python
```

Expected: PASS.

- [ ] **Step 3: Run TypeScript typecheck and complete TS suite**

```bash
pnpm typecheck
pnpm test:ts
```

Expected: PASS.

- [ ] **Step 4: Run the repository health contract**

```bash
pnpm fem:health
```

Expected: existing FEM core health behavior remains healthy; this does not imply any solver analysis succeeded.

- [ ] **Step 5: Perform explicit scope grep/audit**

Inspect the PR25 diff and verify:

```text
no OpenSees analysis renderer added
no ANSYS renderer added
no solver.run/preflight calls added to AnalysisSpec code/tool
no file-write/outputPath path added
no ModelSpec node/element lookup inside validate_engineering_analysis_spec
no unit conversion
no automatic load summation
no call to normalize_structural_query
no natural-language completion
```

Also verify `fem_analysis_spec_validate` wording includes the temporary/high-level-tool-surface convergence constraint.

- [ ] **Step 6: Compare branch to main**

```bash
git diff --check main...HEAD
git diff --stat main...HEAD
```

Expected: only PR25 design/plan plus the files listed in this implementation plan.

- [ ] **Step 7: Commit verification-only fixes if any**

If and only if verification required code/test corrections:

```bash
git add <only corrected PR25 files>
git commit -m "fix: close PR25 verification gaps"
```

Otherwise do not create an empty commit.

---

## Completion Gate

PR25 is ready for review only when:

```text
EngineeringAnalysisSpec validator = deterministic and solver-neutral
analysisSpec.validate bridge = working
TypeScript contract = typed and thin
fem_analysis_spec_validate = SAFE/read-only and explicitly temporary
fingerprint = stable and order-insensitive for normalized collections
PR25 intrinsic validation != PR26 readiness
all Python tests = PASS
Ruff = PASS
TypeScript typecheck = PASS
all TS tests = PASS
fem:health = PASS
main = unmodified
branch = not merged
```

Do not open or merge a PR until normal verification/review workflow has completed, and never merge without explicit user permission.
