# Cross-Solver Validation V1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a deterministic, read-only evidence-first cross-solver validation layer that compares the `absolutePeak` summary value from two independently verified role-backed FEM result records when their engineering semantics and result metadata are exactly compatible.

**Architecture:** Add a focused `fem_core.cross_solver` package. The package has a pure validation/comparison layer over two PR13 role-backed Engineering Evidence reports and a thin orchestration API that calls the existing PR13/PR12 production evidence path for each side. The bridge, TypeScript client, and Pi SAFE tool expose the same read-only operation without adding solver execution, unit conversion, semantic inference, tolerance judgments, or SERIES alignment.

**Tech Stack:** Python 3.13, TypeScript, Pi extension tooling, existing FEMagent Semantic Roles / Result Intelligence / Engineering Evidence Center, pytest, Node test runner, Ruff, GitHub Actions.

**Spec:** `docs/superpowers/specs/2026-09-05-cross-solver-validation-v1-design.md`

## Global Constraints

- Both solver/model sides must be independently resolved through the explicit PR13 Semantic Role Manifest path.
- Both numerical responses must be projected through PR12 role-backed Engineering Evidence; PR14 does not accept caller-provided values, hashes, units, semantic metadata, or node IDs.
- V1 supports `operation == "SUMMARY"` only and compares `metric.summary.absolutePeak` only.
- Different solver-native NODE IDs and different Model Bundle fingerprints across sides are allowed.
- Exact semantic identity requires matching `semanticRole.roleId` and `semanticRole.roleType`.
- Exact result compatibility requires matching normalized `quantity`, `component`, and `operation`.
- Both result units must be non-null strings and match exactly; PR14 performs no unit inference or conversion.
- Both reference frames must be non-empty strings and match exactly; PR14 performs no frame transformation.
- Unknown or incompatible metadata returns `NOT_COMPARABLE` with deterministic limitation codes; integrity/staleness/tampering errors continue to fail closed.
- Numerical comparison is `absoluteDifference = abs(L - R)` and symmetric `relativeDifference = absoluteDifference / max(abs(L), abs(R))`, with `0.0` when both values are zero.
- PR14 never treats either solver as ground truth, never ranks solvers, never embeds a tolerance, and never emits an engineering PASS/FAIL judgment.
- PR14 does not perform SERIES resampling, interpolation, alignment, phase matching, or abscissa comparison.
- PR14 does not execute OpenSees or ANSYS.

---

### Task 1: Pure Cross-Solver Comparison Core

**Files:**
- Create: `fem_core/cross_solver/__init__.py`
- Create: `fem_core/cross_solver/models.py`
- Create: `fem_core/cross_solver/validation.py`
- Test: `tests/python/test_cross_solver_validation.py`

**Interfaces:**
- Consumes two dictionaries shaped like the output of `project_role_evidence()`.
- Produces `compare_role_evidence_reports(*, project_id: str, left_report: dict[str, Any], right_report: dict[str, Any], query: dict[str, Any]) -> dict[str, Any]`.
- The function is pure with respect to filesystem/solver/result readers: it only validates/extracts the supplied evidence reports.

- [ ] **Step 1: Write RED tests for a compatible comparison**

Create helper evidence reports that each contain exactly one `VERIFIED` evidence record, the same role ID/type, same query metadata, same unit/reference frame, different NODE IDs, and distinct peaks:

```python
result = compare_role_evidence_reports(
    project_id="bridge-demo",
    left_report=_report(node_id=17, peak=0.031),
    right_report=_report(node_id=1024, peak=0.030),
    query={"quantity": "DISPLACEMENT", "component": "X", "operation": "SUMMARY"},
)

assert result["status"] == "COMPARABLE"
assert result["sides"]["left"]["entity"] == {"type": "NODE", "id": 17}
assert result["sides"]["right"]["entity"] == {"type": "NODE", "id": 1024}
assert result["comparison"]["absoluteDifference"] == pytest.approx(0.001)
assert result["comparison"]["relativeDifference"] == pytest.approx(0.001 / 0.031)
assert result["limitations"] == []
```

Add a zero/zero case requiring `relativeDifference == 0.0`.

- [ ] **Step 2: Write RED tests for deterministic limitations**

Cover one limitation per test and assert `comparison is None`:

```text
CROSS_SOLVER_SIDE_NOT_VERIFIED
CROSS_SOLVER_ROLE_MISMATCH
CROSS_SOLVER_QUERY_MISMATCH
CROSS_SOLVER_UNIT_UNKNOWN
CROSS_SOLVER_UNIT_MISMATCH
CROSS_SOLVER_REFERENCE_FRAME_MISMATCH
CROSS_SOLVER_METRIC_UNAVAILABLE
```

For role mismatch, keep NODE IDs irrelevant. For unit unknown, set one metric unit to `None`. For reference-frame mismatch, use `RELATIVE` vs `SOLVER_NATIVE`. For metric unavailable, remove `summary.absolutePeak` or set it to a non-finite value.

- [ ] **Step 3: Commit tests only and verify RED on GitHub Actions**

Expected failure: import/collection error because `fem_core.cross_solver` does not exist. Existing TypeScript tests should remain green before Python reaches the new failure.

- [ ] **Step 4: Implement status and limitation constants**

`models.py` defines:

```python
COMPARABLE = "COMPARABLE"
NOT_COMPARABLE = "NOT_COMPARABLE"

CROSS_SOLVER_SIDE_NOT_VERIFIED = "CROSS_SOLVER_SIDE_NOT_VERIFIED"
CROSS_SOLVER_ROLE_MISMATCH = "CROSS_SOLVER_ROLE_MISMATCH"
CROSS_SOLVER_QUERY_MISMATCH = "CROSS_SOLVER_QUERY_MISMATCH"
CROSS_SOLVER_UNIT_UNKNOWN = "CROSS_SOLVER_UNIT_UNKNOWN"
CROSS_SOLVER_UNIT_MISMATCH = "CROSS_SOLVER_UNIT_MISMATCH"
CROSS_SOLVER_REFERENCE_FRAME_MISMATCH = "CROSS_SOLVER_REFERENCE_FRAME_MISMATCH"
CROSS_SOLVER_METRIC_UNAVAILABLE = "CROSS_SOLVER_METRIC_UNAVAILABLE"
CROSS_SOLVER_OPERATION_NOT_SUPPORTED = "CROSS_SOLVER_OPERATION_NOT_SUPPORTED"
```

- [ ] **Step 5: Implement pure extraction and comparison**

`validation.py` must extract exactly one `VERIFIED` evidence record per side and build a compact side projection containing solver, run ID, model fingerprint, entity, unit, reference frame, and absolute peak. Compatibility checks run in this order:

```text
side VERIFIED availability
role ID/type
quantity/component/operation
known unit
unit equality
reference-frame equality
finite absolutePeak
```

Return only the first deterministic limitation in V1 so callers get stable output independent of dictionary ordering.

- [ ] **Step 6: Verify GREEN**

Run focused Python tests, then full Python suite and Ruff. Expected: all Task 1 tests pass without modifying PR12/PR13 behavior.

- [ ] **Step 7: Commit Task 1 GREEN**

Commit the new package and focused tests.

---

### Task 2: Evidence-First Cross-Solver Orchestration API

**Files:**
- Create: `fem_core/cross_solver/api.py`
- Modify: `fem_core/cross_solver/__init__.py`
- Test: `tests/python/test_cross_solver_api.py`

**Interfaces:**
- Consumes `project_role_evidence()` from `fem_core.semantic_roles.evidence`.
- Produces:

```python
def validate_cross_solver(
    workspace: Path,
    *,
    project_id: str,
    left: dict[str, str],
    right: dict[str, str],
    query: dict[str, Any],
) -> dict[str, Any]:
    ...
```

Required side keys: `modelPath`, `manifestPath`, `roleId`, `runRef`.
Required query keys: `quantity`, `component`, `operation`.

- [ ] **Step 1: Write RED API tests with two recorded OpenSees fixtures**

Build two separate OpenSees model/manifest/run fixture groups with different NODE IDs but the same explicit `roleId`/`roleType`, each recorded through the existing standard response CSV schema. Assert `validate_cross_solver()` returns `COMPARABLE` and correct peaks/deltas.

This fixture proves the architecture allows different solver-native identities even though CI can exercise the comparable path without a licensed ANSYS runtime.

- [ ] **Step 2: Add RED tests for unsupported operation before side projection**

Call with `operation="SERIES"` and intentionally invalid/nonexistent side paths. Assert the function returns:

```python
{
    "status": "NOT_COMPARABLE",
    "comparison": None,
    "limitations": [{"code": "CROSS_SOLVER_OPERATION_NOT_SUPPORTED", ...}],
}
```

This proves V1 does not perform unnecessary model/result access for an unsupported comparison mode.

- [ ] **Step 3: Add RED tests that PR13/PR12 hard errors propagate**

At minimum:

- stale semantic manifest -> `SEMANTIC_ROLE_MODEL_MISMATCH`;
- recorded run fingerprint mismatch -> `SEMANTIC_ROLE_RUN_MODEL_MISMATCH`;
- tampered response artifact -> `RESULT_ARTIFACT_HASH_MISMATCH`.

Do not convert these into `NOT_COMPARABLE`.

- [ ] **Step 4: Commit API tests only and verify RED**

Expected failure: `validate_cross_solver` is absent.

- [ ] **Step 5: Implement strict request validation and orchestration**

`api.py` must:

```text
validate project/query/side shape
-> if operation != SUMMARY, return NOT_COMPARABLE immediately
-> call project_role_evidence(left)
-> call project_role_evidence(right)
-> pass both reports to compare_role_evidence_reports()
```

Generate deterministic internal evidence IDs such as:

```text
{project_id}:cross-solver:left
{project_id}:cross-solver:right
```

The API must not accept caller-provided evidence values/hashes/units.

- [ ] **Step 6: Verify GREEN and regression gate**

Run focused API tests, full Python tests, and Ruff.

- [ ] **Step 7: Commit Task 2 GREEN**

Commit the orchestration API and tests.

---

### Task 3: Python Bridge, TypeScript Client, and Pi SAFE Tool

**Files:**
- Modify: `fem_core/bridge.py`
- Create: `packages/fem-tools/src/validationTypes.ts`
- Modify: `packages/fem-tools/src/pythonBridge.ts`
- Modify: `packages/fem-tools/src/index.ts`
- Create: `.pi/extensions/validation-tools.ts`
- Create: `tests/ts/cross-solver-validation.test.ts`

**Interfaces:**
- Python bridge command: `validation.crossSolver`.
- TypeScript client: `runFemCrossSolverValidation()`.
- Pi tool: `fem_cross_solver_validate`.

- [ ] **Step 1: Write TypeScript RED bridge test**

Import `runFemCrossSolverValidation` from `@femagent/fem-tools`, build two temporary comparable recorded OpenSees role-backed fixtures, call the client, and assert:

```ts
assert.equal(report.status, "COMPARABLE");
assert.equal(report.comparison?.metric, "absolutePeak");
assert.equal(report.sides.left.entity.id, 2);
assert.equal(report.sides.right.entity.id, 3);
```

Add a `SERIES` request test requiring `NOT_COMPARABLE` without solver execution.

- [ ] **Step 2: Commit TS tests only and verify clean RED**

Expected TypeScript failure: `runFemCrossSolverValidation` is not exported. If the test itself has an unrelated typing problem, fix the test and re-establish a clean missing-client RED before production code.

- [ ] **Step 3: Add Python bridge command**

In `fem_core/bridge.py`, parse required objects and call:

```python
validate_cross_solver(
    workspace,
    project_id=_required_text(payload, "projectId"),
    left=_required_object(payload, "left"),
    right=_required_object(payload, "right"),
    query=_required_object(payload, "query"),
)
```

The bridge contains no comparison logic.

- [ ] **Step 4: Add TypeScript contract**

`validationTypes.ts` defines explicit side request, query request, limitation, side projection, comparison, and report interfaces. `pythonBridge.ts` adds `runFemCrossSolverValidation()`, and `index.ts` exports the types/client.

- [ ] **Step 5: Add isolated Pi SAFE extension**

Create `.pi/extensions/validation-tools.ts` and register `fem_cross_solver_validate` with explicit left/right model/manifest/role/run inputs plus quantity/component/operation.

Prompt guidance must state:

```text
- semantic roles come only from explicit manifests;
- never rewrite role mappings;
- never execute either solver;
- never infer or convert result units;
- never treat either side as ground truth;
- do not declare engineering PASS/FAIL without a future explicit tolerance policy;
- NOT_COMPARABLE is a limitation, not evidence that one solver is wrong;
- preserve Result Intelligence / Evidence / Semantic hard errors.
```

- [ ] **Step 6: Verify GREEN repository gate**

Run through CI:

```text
pnpm typecheck
pnpm test:ts
python -m pytest
python -m ruff check fem_core tests/python examples/ansys/golden_path
OpenSees adapter availability smoke
ANSYS result-reader import smoke
pnpm fem:health
```

- [ ] **Step 7: Commit Task 3 GREEN**

Commit bridge, TypeScript contract/client, Pi tool, and tests.

---

### Task 4: Architecture/Verification Documentation and PR14 Closeout

**Files:**
- Create: `docs/architecture/cross-solver-validation.md`
- Create: `docs/verification/pr14-cross-solver-validation.md`
- Update PR #14 metadata only after exact-final-head verification.

**Interfaces:**
- Documents the evidence-first trust model, strict compatibility contract, limitation/error separation, numerical formula, ANSYS unit boundary, and V1 non-goals.

- [ ] **Step 1: Synchronize with current `main`**

Compare `main...feat/pr14-cross-solver-validation-v1`. If `behind_by > 0`, safely synchronize before final verification. Re-review the diff after synchronization.

- [ ] **Step 2: Write architecture documentation**

Document:

```text
Semantic Role A/B
-> independent role-backed VERIFIED evidence
-> strict metadata compatibility
-> COMPARABLE / NOT_COMPARABLE
-> deterministic absolutePeak delta only
```

Explicitly state that a current OpenSees `m` result versus ANSYS `unit=null` must return `CROSS_SOLVER_UNIT_UNKNOWN`, not a numerical comparison.

- [ ] **Step 3: Write verification record**

Record all actual RED/GREEN CI run numbers and exact test counts. Distinguish:

- fixture-backed comparable path;
- production artifact-integrity reuse;
- no licensed ANSYS numerical cross-solver comparison in hosted CI unless one was actually executed;
- current third-party VTK/NumPy warnings separately from failures.

- [ ] **Step 4: Final diff review**

Confirm the PR contains none of the following:

```text
solver execution
unit conversion/inference
reference-frame transformation
SERIES alignment/resampling
hidden tolerances
PASS/FAIL engineering judgments
solver ranking/ground-truth selection
semantic role inference or manifest writes
new result parsers
optimization/UI/PDF scope
```

- [ ] **Step 5: Run exact-final-head CI**

Require the full repository gate on the documentation head. Fetch the workflow by exact branch head SHA and inspect job logs for exact TypeScript/Python counts.

- [ ] **Step 6: Check PR state**

Require:

```text
behind_by = 0
mergeable = true
no unresolved review blocker
exact-final-head CI = success
```

- [ ] **Step 7: Update PR body and mark Draft -> Ready for review**

The PR description must name the exact final head and CI run. Do not merge PR14 without explicit user instruction.
