# PR22 Engineering Model Readiness Validator Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a deterministic, solver-neutral engineering-readiness gate for PR21-valid 2D elastic frame ModelSpecs so obvious rigid-body and connectivity defects are caught before renderer authoring.

**Architecture:** Python `fem_core.model_spec` remains the sole engineering authority. PR22 always invokes PR21 validation first, then evaluates deterministic graph components, exact planar rigid-body restraint rank with `Decimal`, and repeated node-pair connectivity. TypeScript and Pi only transport the request/result; they do not duplicate engineering logic.

**Tech Stack:** Python 3.13, `decimal.Decimal`, existing `fem_core` bridge, TypeScript 5.9, TypeBox/Pi extensions, Node test runner, pytest, Ruff.

**Spec:** `docs/superpowers/specs/2026-09-07-pr22-engineering-model-readiness-validator-design.md`

## Global Constraints

- PR22 depends on PR21 `validate_engineering_model_spec()` and must always call it internally.
- V1 applies only to PR21 `2D` `FRAME` `ELASTIC_FRAME_2D` `EULER_BERNOULLI` specs.
- No solver execution, solver preflight, renderer output, model-file writes, stiffness-matrix assembly, eigenvalue analysis, hidden numerical tolerance, unit inference/conversion, semantic-role inference, RAG, or automatic repair.
- Readiness status is exactly `READY | NOT_READY | INVALID_SPEC`.
- Individual check status is exactly `PASS | WARN | FAIL | SKIPPED`.
- Readiness profile is exactly `FRAME_2D_ELASTIC_READINESS_V1`.
- PR21 `modelSpecFingerprint` is copied unchanged and never recalculated by PR22.
- Rigid-body rank uses exact `Decimal` arithmetic and exact-zero Gaussian elimination; do not call `numpy.linalg.matrix_rank`.
- Disconnected components and repeated node-pair connectivity are warnings, not automatic blockers.
- Every graph component, including isolated nodes, is evaluated independently for planar rigid-body restraint rank 3.
- Python is the only readiness engineering authority; TypeScript/Pi must not reimplement graph/rank logic.

---

### Task 1: Python readiness core

**Files:**
- Create: `fem_core/model_spec/readiness.py`
- Modify: `fem_core/model_spec/__init__.py`
- Test: `tests/python/test_model_spec_readiness.py`

**Interfaces:**
- Consumes: `validate_engineering_model_spec(spec: dict[str, Any]) -> dict[str, Any]` from PR21.
- Produces: `evaluate_engineering_model_readiness(spec: dict[str, Any]) -> dict[str, Any]`.

- [ ] **Step 1: Write the failing Python tests**

Cover these exact behaviors in `tests/python/test_model_spec_readiness.py`:

```python
from copy import deepcopy
import json
from pathlib import Path

from fem_core.model_spec import evaluate_engineering_model_readiness, validate_engineering_model_spec

FIXTURE = Path("tests/fixtures/model_spec/simple-portal-frame.json")


def load_spec():
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


def test_portal_frame_is_ready_and_preserves_pr21_fingerprint():
    spec = load_spec()
    validation = validate_engineering_model_spec(spec)
    result = evaluate_engineering_model_readiness(spec)
    assert result["status"] == "READY"
    assert result["profile"] == "FRAME_2D_ELASTIC_READINESS_V1"
    assert result["checks"]["connectivity"]["componentCount"] == 1
    assert result["checks"]["rigidBodyRestraint"]["components"][0]["constraintRank"] == 3
    assert result["checks"]["rigidBodyRestraint"]["components"][0]["deficiency"] == 0
    assert result["modelSpecFingerprint"] == validation["modelSpecFingerprint"]


def test_free_frame_is_not_ready_with_rank_zero():
    spec = load_spec()
    spec["constraints"] = []
    result = evaluate_engineering_model_readiness(spec)
    assert result["status"] == "NOT_READY"
    assert result["checks"]["rigidBodyRestraint"]["components"][0]["constraintRank"] == 0
    assert result["checks"]["rigidBodyRestraint"]["components"][0]["deficiency"] == 3
    assert any(i["code"] == "MODEL_READINESS_RIGID_BODY_RESTRAINT_INSUFFICIENT" for i in result["issues"])


def test_simple_support_geometry_has_rank_three():
    spec = load_spec()
    spec["constraints"] = [
        {"nodeId": 1, "dofs": ["UX", "UY"]},
        {"nodeId": 2, "dofs": ["UY"]},
    ]
    result = evaluate_engineering_model_readiness(spec)
    assert result["checks"]["rigidBodyRestraint"]["components"][0]["constraintRank"] == 3


def test_disconnected_fully_restrained_components_are_ready_with_warning():
    spec = load_spec()
    # Build two independent 2-node components and restrain each independently.
    spec["nodes"] = [
        {"id": 1, "x": 0.0, "y": 0.0}, {"id": 2, "x": 1.0, "y": 0.0},
        {"id": 3, "x": 10.0, "y": 0.0}, {"id": 4, "x": 11.0, "y": 0.0},
    ]
    spec["elements"] = [
        {**spec["elements"][0], "id": 1, "nodeI": 1, "nodeJ": 2},
        {**spec["elements"][0], "id": 2, "nodeI": 3, "nodeJ": 4},
    ]
    spec["constraints"] = [
        {"nodeId": 1, "dofs": ["UX", "UY"]}, {"nodeId": 2, "dofs": ["UY"]},
        {"nodeId": 3, "dofs": ["UX", "UY"]}, {"nodeId": 4, "dofs": ["UY"]},
    ]
    result = evaluate_engineering_model_readiness(spec)
    assert result["status"] == "READY"
    assert result["checks"]["connectivity"]["componentCount"] == 2
    assert any(i["code"] == "MODEL_READINESS_DISCONNECTED_COMPONENTS" for i in result["issues"])


def test_isolated_unconstrained_node_blocks_readiness():
    spec = load_spec()
    spec["nodes"].append({"id": 99, "x": 99.0, "y": 99.0})
    result = evaluate_engineering_model_readiness(spec)
    assert result["status"] == "NOT_READY"
    isolated = next(c for c in result["checks"]["rigidBodyRestraint"]["components"] if c["nodeIds"] == [99])
    assert isolated["constraintRank"] == 0


def test_parallel_connectivity_warns_without_blocking_ready_model():
    spec = load_spec()
    duplicate = deepcopy(spec["elements"][0])
    duplicate["id"] = 99
    spec["elements"].append(duplicate)
    result = evaluate_engineering_model_readiness(spec)
    assert result["status"] == "READY"
    assert result["checks"]["parallelConnectivity"]["status"] == "WARN"
    assert any(i["code"] == "MODEL_READINESS_PARALLEL_CONNECTIVITY" for i in result["issues"])


def test_invalid_pr21_spec_skips_readiness():
    spec = load_spec()
    del spec["units"]
    result = evaluate_engineering_model_readiness(spec)
    assert result["status"] == "INVALID_SPEC"
    assert result["modelSpecFingerprint"] is None
    assert result["checks"]["connectivity"]["status"] == "SKIPPED"
    assert result["checks"]["rigidBodyRestraint"]["status"] == "SKIPPED"
    assert result["checks"]["parallelConnectivity"]["status"] == "SKIPPED"
```

Also add a determinism test that reorders nodes/elements/constraints and asserts the readiness result is semantically identical apart from no fields that encode source order.

- [ ] **Step 2: Run the focused tests and verify RED**

Run:

```bash
python -m pytest tests/python/test_model_spec_readiness.py -q
```

Expected: collection/import failure because `evaluate_engineering_model_readiness` does not exist.

- [ ] **Step 3: Implement deterministic readiness core**

Create `fem_core/model_spec/readiness.py` with these focused helpers:

```python
READINESS_SCHEMA = "FEMAGENT_MODEL_SPEC_READINESS_V1"
READINESS_PROFILE = "FRAME_2D_ELASTIC_READINESS_V1"


def evaluate_engineering_model_readiness(spec: dict[str, Any]) -> dict[str, Any]:
    validation = validate_engineering_model_spec(spec)
    if validation["status"] == "INVALID":
        return _invalid_spec_result(validation)
    normalized = validation["normalizedSpec"]
    components = _connected_components(normalized)
    rigid = _rigid_body_check(normalized, components)
    parallel = _parallel_connectivity(normalized)
    issues = _ordered_issues(components, rigid, parallel)
    return {
        "schema": READINESS_SCHEMA,
        "status": "NOT_READY" if any(i["severity"] == "ERROR" for i in issues) else "READY",
        "profile": READINESS_PROFILE,
        "modelSpecFingerprint": validation["modelSpecFingerprint"],
        "validation": {
            "schema": validation["schema"],
            "status": validation["status"],
            "issues": validation["issues"],
        },
        "checks": {
            "connectivity": _connectivity_check(components),
            "rigidBodyRestraint": rigid,
            "parallelConnectivity": parallel,
        },
        "issues": issues,
    }
```

Implement exact Decimal rank with rows:

```python
UX -> [Decimal(1), Decimal(0), -y]
UY -> [Decimal(0), Decimal(1),  x]
RZ -> [Decimal(0), Decimal(0), Decimal(1)]
```

Convert coordinates with `Decimal(str(value))` and use deterministic Gaussian elimination with exact `== Decimal(0)` pivot checks. Return per-component `nodeIds`, `elementIds`, `constraintRank`, and `deficiency = 3 - rank`.

- [ ] **Step 4: Export the Python API**

Update `fem_core/model_spec/__init__.py` to export both PR21 validation and PR22 readiness:

```python
from .readiness import evaluate_engineering_model_readiness
from .validator import validate_engineering_model_spec

__all__ = ["evaluate_engineering_model_readiness", "validate_engineering_model_spec"]
```

- [ ] **Step 5: Run focused + regression tests**

Run:

```bash
python -m pytest tests/python/test_model_spec.py tests/python/test_model_spec_fingerprint.py tests/python/test_model_spec_readiness.py -q
python -m ruff check fem_core/model_spec tests/python/test_model_spec_readiness.py
```

Expected: PASS.

- [ ] **Step 6: Commit Task 1**

```bash
git add fem_core/model_spec tests/python/test_model_spec_readiness.py
git commit -m "feat: add engineering model readiness core"
```

---

### Task 2: Python bridge command

**Files:**
- Modify: `fem_core/bridge.py`
- Test: `tests/python/test_model_spec_readiness_bridge.py`

**Interfaces:**
- Consumes: `evaluate_engineering_model_readiness(spec)`.
- Produces: bridge command `modelSpec.readiness`.

- [ ] **Step 1: Write failing bridge tests**

```python
from fem_core.bridge import dispatch_request


def test_model_spec_readiness_bridge_returns_typed_result(portal_frame_spec):
    response = dispatch_request({
        "protocolVersion": "1.0",
        "command": "modelSpec.readiness",
        "cwd": ".",
        "payload": {"spec": portal_frame_spec},
    })
    assert response["ok"] is True
    assert response["result"]["schema"] == "FEMAGENT_MODEL_SPEC_READINESS_V1"


def test_invalid_spec_is_result_not_transport_error(portal_frame_spec):
    del portal_frame_spec["units"]
    response = dispatch_request({
        "protocolVersion": "1.0",
        "command": "modelSpec.readiness",
        "cwd": ".",
        "payload": {"spec": portal_frame_spec},
    })
    assert response["ok"] is True
    assert response["result"]["status"] == "INVALID_SPEC"
```

Also test `payload.spec` non-object follows the existing `INVALID_ARGUMENT` bridge path.

- [ ] **Step 2: Run bridge test and verify RED**

```bash
python -m pytest tests/python/test_model_spec_readiness_bridge.py -q
```

Expected: `UNKNOWN_COMMAND` for `modelSpec.readiness`.

- [ ] **Step 3: Register bridge command**

Import `evaluate_engineering_model_readiness` and add the smallest dispatch branch following the existing `modelSpec.validate` pattern. Do not duplicate validation/readiness logic inside the bridge.

- [ ] **Step 4: Run bridge + full Python tests**

```bash
python -m pytest tests/python/test_model_spec_readiness_bridge.py tests/python/test_model_spec_bridge.py -q
python -m pytest -q
```

Expected: PASS.

- [ ] **Step 5: Commit Task 2**

```bash
git add fem_core/bridge.py tests/python/test_model_spec_readiness_bridge.py
git commit -m "feat: expose model readiness bridge command"
```

---

### Task 3: TypeScript readiness contract and transport

**Files:**
- Modify: `packages/fem-tools/src/modelSpecTypes.ts`
- Modify: `packages/fem-tools/src/pythonBridge.ts`
- Modify: `packages/fem-tools/src/index.ts`
- Test: `tests/ts/model-spec-readiness.test.ts`

**Interfaces:**
- Consumes: bridge command `modelSpec.readiness`.
- Produces: `FemModelSpecReadiness` result types and `runFemModelSpecReadiness(cwd, spec)`.

- [ ] **Step 1: Write failing TypeScript test**

```ts
import test from "node:test";
import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import {
  runFemModelSpecReadiness,
  type FemEngineeringModelSpecInput,
} from "@femagent/fem-tools";


test("ModelSpec readiness crosses the strict TypeScript/Python bridge", async () => {
  const spec = JSON.parse(await readFile("tests/fixtures/model_spec/simple-portal-frame.json", "utf8")) as FemEngineeringModelSpecInput;
  const result = await runFemModelSpecReadiness(process.cwd(), spec);
  assert.equal(result.schema, "FEMAGENT_MODEL_SPEC_READINESS_V1");
  assert.equal(result.status, "READY");
  assert.equal(result.checks.rigidBodyRestraint.components[0]?.constraintRank, 3);
});
```

Add an invalid-spec case expecting `INVALID_SPEC` without a thrown bridge/domain error.

- [ ] **Step 2: Run TypeScript typecheck/test and verify RED**

```bash
pnpm typecheck
pnpm test:ts
```

Expected: missing exported member/type/helper errors.

- [ ] **Step 3: Add TypeScript result types**

Extend `modelSpecTypes.ts` with exact unions/interfaces:

```ts
export type FemModelSpecReadinessStatus = "READY" | "NOT_READY" | "INVALID_SPEC";
export type FemModelSpecReadinessCheckStatus = "PASS" | "WARN" | "FAIL" | "SKIPPED";

export interface FemModelSpecReadiness {
  schema: "FEMAGENT_MODEL_SPEC_READINESS_V1";
  status: FemModelSpecReadinessStatus;
  profile: "FRAME_2D_ELASTIC_READINESS_V1";
  modelSpecFingerprint: string | null;
  validation: Pick<FemModelSpecValidation, "schema" | "status" | "issues">;
  checks: {
    connectivity: {
      status: FemModelSpecReadinessCheckStatus;
      componentCount: number;
      components: Array<{ index: number; nodeIds: number[]; elementIds: number[] }>;
    };
    rigidBodyRestraint: {
      status: FemModelSpecReadinessCheckStatus;
      requiredRankPerComponent: 3;
      components: Array<{ index: number; nodeIds: number[]; elementIds: number[]; constraintRank: number; deficiency: number }>;
    };
    parallelConnectivity: {
      status: FemModelSpecReadinessCheckStatus;
      groups: Array<{ nodeIds: [number, number]; elementIds: number[] }>;
    };
  };
  issues: FemModelSpecIssue[];
}
```

- [ ] **Step 4: Add bridge helper/export**

Add `runFemModelSpecReadiness(cwd, spec)` beside `runFemModelSpecValidate()` and export it through `packages/fem-tools/src/index.ts`. It must only call the Python bridge; no graph/rank calculation in TS.

- [ ] **Step 5: Run TS + cross-language tests**

```bash
pnpm typecheck
pnpm test:ts
```

Expected: PASS.

- [ ] **Step 6: Commit Task 3**

```bash
git add packages/fem-tools/src tests/ts/model-spec-readiness.test.ts
git commit -m "feat: add ModelSpec readiness TypeScript bridge"
```

---

### Task 4: SAFE Pi tool and Agent registration

**Files:**
- Modify: `.pi/extensions/model-spec-tools.ts`
- Modify: `apps/agent/src/main.ts`
- Test: `tests/ts/model-spec-tool-registration.test.ts`

**Interfaces:**
- Consumes: `runFemModelSpecReadiness(cwd, spec)`.
- Produces: public SAFE/read-only tool `fem_model_spec_readiness`.

- [ ] **Step 1: Extend registration tests first**

Require the extension source to contain registration for `fem_model_spec_readiness`, require Agent loading/allow-list exposure, and assert the extension does not reference `runFemSolverRun`.

- [ ] **Step 2: Run registration test and verify RED**

```bash
pnpm test:ts
```

Expected: only new readiness registration assertions fail.

- [ ] **Step 3: Register SAFE tool**

In `.pi/extensions/model-spec-tools.ts`, add a second tool using the existing ModelSpec TypeBox parameter shape:

```text
name: fem_model_spec_readiness
risk: SAFE/read-only
execute: runFemModelSpecReadiness(ctx.cwd, params.spec)
```

Agent guidance must explicitly say validation and readiness are distinct and that readiness does not render or solve.

- [ ] **Step 4: Add Agent allow-list entry**

Update `apps/agent/src/main.ts` so the already-loaded model-spec extension exposes `fem_model_spec_readiness` alongside `fem_model_spec_validate`.

- [ ] **Step 5: Run TS suite**

```bash
pnpm typecheck
pnpm test:ts
```

Expected: PASS.

- [ ] **Step 6: Commit Task 4**

```bash
git add .pi/extensions/model-spec-tools.ts apps/agent/src/main.ts tests/ts/model-spec-tool-registration.test.ts
git commit -m "feat: expose SAFE model readiness tool"
```

---

### Task 5: Architecture, verification, and exact-head closeout

**Files:**
- Create: `docs/architecture/engineering-model-readiness.md`
- Create: `docs/verification/pr22-engineering-model-readiness.md`
- Modify: PR #18 body only after final exact-head verification.

**Interfaces:**
- Consumes: completed PR22 implementation and CI evidence.
- Produces: durable architecture/verification record and review-ready PR.

- [ ] **Step 1: Run full pre-documentation verification**

```bash
pnpm typecheck
pnpm test:ts
python -m pytest
python -m ruff check fem_core tests/python examples/ansys/golden_path
python -c "from fem_core.solvers import get_solver_adapter; s=get_solver_adapter('opensees').status(); assert s['available'], s"
python -c "from ansys.mapdl import reader; assert callable(reader.read_binary)"
pnpm fem:health
```

Expected: all PASS. Record exact test counts from output; do not guess them.

- [ ] **Step 2: Write architecture document**

Document:

```text
PR21 VALID spec
  -> PR22 connected components
  -> exact per-component rigid-body rank
  -> READY / NOT_READY
  -> future PR23 renderer
```

State explicitly that disconnected components/parallel connectivity are warnings, readiness is solver-neutral, and no stiffness/eigenvalue/heuristic/solver path exists.

- [ ] **Step 3: Write verification record**

Record each RED→GREEN cycle with exact commit SHA/CI run, final test counts, warnings, acceptance-criteria audit, and the final exact-head rule.

- [ ] **Step 4: Commit documentation**

```bash
git add docs/architecture/engineering-model-readiness.md docs/verification/pr22-engineering-model-readiness.md
git commit -m "docs: document PR22 readiness architecture and verification"
```

- [ ] **Step 5: Run/observe exact-final-head CI**

The authoritative completion evidence is the GitHub Actions run attached to the final documentation head. Confirm all gates are success before changing PR status.

- [ ] **Step 6: Review PR diff against stacked base**

Confirm PR22 changes only readiness core/bridge/TS/Pi/tests/docs and does not modify solver adapters, Result Intelligence, Load Intelligence, Semantic Roles, Engineering Evidence, Cross-Solver Validation, or knowledge provider code.

- [ ] **Step 7: Update PR #18 metadata and mark Ready for Review**

PR body must record final head SHA, exact CI run ID/number, exact TypeScript/Python counts, explicit non-goals, and stacked-base note. Mark Draft → Ready only after exact-head CI succeeds.
