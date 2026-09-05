# Engineering Semantic Roles V1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a deterministic, read-only semantic-role layer that resolves explicit user/project engineering-role declarations to solver-native NODE identities bound to exact Model Bundle fingerprints, then composes those roles into Result Intelligence and Engineering Evidence.

**Architecture:** Add a focused `fem_core.semantic_roles` package that validates a workspace-local JSON manifest, binds it to production Model Intelligence, and resolves one declared NODE role without any heuristic inference. Extend Result Intelligence only to expose recorded model bundle identity, then add a role-aware Evidence composition API and matching Python bridge, TypeScript client/types, and Pi SAFE tools.

**Tech Stack:** Python 3.13, TypeScript, Pi extension tooling, existing FEMagent Model Intelligence / Result Intelligence / Evidence Center, pytest, Node test runner, Ruff, GitHub Actions.

**Spec:** `docs/superpowers/specs/2026-09-05-engineering-semantic-roles-v1-design.md`

## Global Constraints

- Semantic truth comes only from an explicit workspace-local Semantic Role Manifest; PR13 does not infer roles from component names, variable names, coordinates, constraints, topology, or result values.
- Manifest schema is `schemaVersion == "1.0"`, `kind == "engineering_semantic_roles"`, one 64-character `model.bundleFingerprint`, and a non-empty `roles` array.
- V1 `roleType` vocabulary is exactly `TOWER_BASE`, `GIRDER_END`, `BEARING`, `DAMPER_ATTACHMENT`, `MIDSPAN`, `SUPPORT`.
- V1 entity type is exactly `NODE` with a positive integer ID.
- `roleId` matches `^[A-Z][A-Z0-9_]{0,63}$` and is unique within one manifest.
- Semantic statuses are independent of PR12 evidence statuses.
- Current-model fingerprint mismatch fails closed with `SEMANTIC_ROLE_MODEL_MISMATCH`.
- Unknown role fails with `SEMANTIC_ROLE_NOT_FOUND`.
- If complete static node enumeration is available and the declared node is absent, fail with `SEMANTIC_ROLE_ENTITY_NOT_FOUND`.
- If topology cannot be statically enumerated, an explicit mapping may still resolve but reports `entityValidation: NOT_STATICALLY_ENUMERABLE`.
- Role-based evidence must prove the recorded run model bundle fingerprint equals the semantic model bundle fingerprint; otherwise fail with `SEMANTIC_ROLE_RUN_MODEL_MISMATCH`.
- Semantic operations are read-only. PR13 does not expose manifest create/update tools and never invokes a solver.
- Result units remain exactly those returned by Result Intelligence; no ANSYS unit inference is added.
- V1 excludes ELEMENT roles, heuristic candidates, UI, HTTP server, PDF generation, optimization, and cross-solver comparison/ranking.

---

### Task 1: Semantic Manifest Core and Deterministic Resolver

**Files:**
- Create: `fem_core/semantic_roles/__init__.py`
- Create: `fem_core/semantic_roles/models.py`
- Create: `fem_core/semantic_roles/manifest.py`
- Create: `fem_core/semantic_roles/resolver.py`
- Create: `fem_core/semantic_roles/api.py`
- Modify: `fem_core/model_inspection.py`
- Test: `tests/python/test_semantic_roles.py`

**Interfaces:**
- Consumes: `inspect_model(workspace: Path, raw_path: str) -> dict[str, Any]`.
- Produces: `load_semantic_manifest(workspace: Path, manifest_path: str) -> dict[str, Any]`.
- Produces: `inspect_semantic_roles(workspace: Path, *, model_path: str, manifest_path: str) -> dict[str, Any]`.
- Produces: `resolve_semantic_role(workspace: Path, *, model_path: str, manifest_path: str, role_id: str) -> dict[str, Any]`.
- Extends ANSYS Model Intelligence `manifest.topology` with `nodeTags` only when complete explicit numeric-node enumeration is already proven.

- [ ] **Step 1: Write failing manifest-validation and resolution tests**

Add focused tests covering:

```python
from fem_core.errors import FemCoreError
from fem_core.semantic_roles import inspect_semantic_roles, resolve_semantic_role


def test_ansys_explicit_role_resolves_to_statically_confirmed_node(tmp_path: Path) -> None:
    model = tmp_path / "model.inp"
    model.write_text("/PREP7\nN,1,0,0,0\nN,2,1,0,0\nET,1,LINK180\nE,1,2\n", encoding="utf-8")
    model_report = inspect_model(tmp_path, "model.inp")
    fingerprint = model_report["bundle"]["bundleFingerprint"]
    _write_manifest(tmp_path, fingerprint=fingerprint, node_id=1)

    result = resolve_semantic_role(
        tmp_path,
        model_path="model.inp",
        manifest_path="semantic-roles.json",
        role_id="TOWER_BASE_LEFT",
    )

    assert result["status"] == "RESOLVED"
    assert result["entity"] == {"type": "NODE", "id": 1}
    assert result["entityValidation"] == "STATICALLY_CONFIRMED"


def test_stale_manifest_fails_closed(tmp_path: Path) -> None:
    ...
    with pytest.raises(FemCoreError) as exc_info:
        resolve_semantic_role(...)
    assert exc_info.value.code == "SEMANTIC_ROLE_MODEL_MISMATCH"


def test_missing_explicit_node_fails_when_topology_is_complete(tmp_path: Path) -> None:
    ...
    assert exc_info.value.code == "SEMANTIC_ROLE_ENTITY_NOT_FOUND"


def test_dynamic_opensees_role_remains_explicit_but_not_statically_enumerable(tmp_path: Path) -> None:
    ...
    assert result["status"] == "RESOLVED"
    assert result["entityValidation"] == "NOT_STATICALLY_ENUMERABLE"
```

Also test malformed JSON, unsupported role type/entity type, duplicate role IDs, invalid role IDs, and non-positive node IDs all produce `INVALID_SEMANTIC_ROLE_MANIFEST`.

- [ ] **Step 2: Verify RED on GitHub Actions**

Commit only the new test file. Expected Python collection/test failure: `fem_core.semantic_roles` does not exist or required APIs are missing. Existing repository tests must remain otherwise green.

- [ ] **Step 3: Implement manifest models and parser**

`models.py` defines constants for role types and entity validation values. `manifest.py` must:

```python
def load_semantic_manifest(workspace: Path, manifest_path: str) -> dict[str, Any]:
    path = resolve_workspace_file(workspace, manifest_path)
    payload = json.loads(path.read_text(encoding="utf-8"))
    # validate schema exactly and return normalized roles + manifest sha/path
```

Validation must reject partial manifests rather than returning partial roles.

- [ ] **Step 4: Extend ANSYS static topology with complete `nodeTags`**

In `fem_core/model_inspection.py`, when `exact_explicit_node_count is not None`, expose:

```python
"nodeTags": sorted(explicit_node_ids)
```

Otherwise expose `nodeTags: None` or omit it consistently with the tests. Do not add a second APDL parser.

- [ ] **Step 5: Implement resolver and public API**

Resolver logic:

```python
model = inspect_model(workspace, model_path)
manifest = load_semantic_manifest(workspace, manifest_path)
current = model["bundle"]["bundleFingerprint"]
if manifest["model"]["bundleFingerprint"] != current:
    raise FemCoreError("SEMANTIC_ROLE_MODEL_MISMATCH", ...)
```

Use OpenSees `staticTopology.nodeTags` when complete and ANSYS `manifest.topology.nodeTags` when complete. If complete enumeration exists, require membership; otherwise report `NOT_STATICALLY_ENUMERABLE`.

- [ ] **Step 6: Verify GREEN**

Run the focused Python test file and full Python suite. Expected: all semantic tests pass and no existing test regresses.

- [ ] **Step 7: Commit Task 1 GREEN**

Commit semantic core, Model Intelligence extension, and tests with a focused feature commit.

---

### Task 2: Expose Recorded Run Model Identity Through Result Intelligence

**Files:**
- Modify: `fem_core/result_intelligence.py`
- Test: `tests/python/test_result_intelligence.py`

**Interfaces:**
- Consumes: completed `solver_run` manifest `model` block.
- Produces: `inspect_result()` output field:

```python
"model": {
    "path": str | None,
    "bundleFingerprint": str | None,
}
```

- Does not change any numerical result parsing or unit semantics.

- [ ] **Step 1: Write failing Result Intelligence identity tests**

Add tests proving that a completed run whose manifest records `model.bundleFingerprint` returns the same fingerprint through `inspect_result()`, and that legacy/fixture manifests without one return a non-usable/null fingerprint rather than an invented value.

- [ ] **Step 2: Verify RED**

Commit only the new tests. Expected failure: `inspect_result()` has no `model` field.

- [ ] **Step 3: Implement minimal provenance exposure**

Normalize only recorded fields from `manifest.get("model")`; do not calculate a new bundle fingerprint inside Result Intelligence.

- [ ] **Step 4: Verify GREEN and regression suite**

Run focused Result Intelligence tests, then full Python tests and Ruff.

- [ ] **Step 5: Commit Task 2 GREEN**

Commit the Result Intelligence provenance extension and tests.

---

### Task 3: Role → Result Intelligence → Engineering Evidence Composition

**Files:**
- Create: `fem_core/semantic_roles/evidence.py`
- Modify: `fem_core/evidence/api.py` only if a small reusable projection helper is required
- Test: `tests/python/test_role_evidence.py`

**Interfaces:**
- Consumes: `resolve_semantic_role(...)`, `inspect_result(...)`, existing Result Intelligence query contract, and existing Evidence Center projection.
- Produces:

```python
def project_role_evidence(
    workspace: Path,
    *,
    project_id: str,
    model_path: str,
    manifest_path: str,
    role_id: str,
    run_ref: str,
    evidence_id: str,
    quantity: str,
    component: str,
    operation: str,
    offset: int = 0,
    limit: int = 500,
) -> dict[str, Any]:
    ...
```

- Evidence provenance must retain a `semanticRole` block containing role ID/type/entity, manifest SHA, model bundle fingerprint, and entity-validation basis.

- [ ] **Step 1: Write failing role-evidence tests**

Create a deterministic OpenSees recorded-run fixture whose `model.bundleFingerprint` matches the semantic manifest and assert:

```python
report = project_role_evidence(... role_id="TOWER_BASE_LEFT", quantity="DISPLACEMENT", component="X", operation="SUMMARY")
evidence = report["verifiedEvidence"][0]
assert evidence["metric"]["target"] == {"type": "NODE", "id": 2}
assert evidence["provenance"]["semanticRole"]["roleId"] == "TOWER_BASE_LEFT"
assert evidence["provenance"]["semanticRole"]["modelBundleFingerprint"] == fingerprint
```

Add mismatch test requiring `SEMANTIC_ROLE_RUN_MODEL_MISMATCH` before result query/evidence promotion.

- [ ] **Step 2: Verify RED**

Commit only tests. Expected failure: `project_role_evidence` does not exist.

- [ ] **Step 3: Implement fail-closed composition**

Required order:

```text
resolve role
→ inspect_result(run)
→ require recorded run model bundle fingerprint == resolved semantic model bundle fingerprint
→ build NODE Result Intelligence query
→ use existing run-backed Evidence Center integrity path
→ append semanticRole provenance
```

Do not bypass PR12 artifact hash verification and do not accept caller-supplied result hashes.

- [ ] **Step 4: Verify GREEN**

Run focused role-evidence tests plus all Python tests and Ruff.

- [ ] **Step 5: Commit Task 3 GREEN**

Commit role-aware evidence composition and tests.

---

### Task 4: Python Bridge, TypeScript Client, and Pi SAFE Tools

**Files:**
- Modify: `fem_core/bridge.py`
- Create: `packages/fem-tools/src/semanticTypes.ts`
- Modify: `packages/fem-tools/src/pythonBridge.ts`
- Modify: `packages/fem-tools/src/index.ts`
- Modify: `.pi/extensions/fem-tools.ts`
- Create: `tests/ts/semantic-roles.test.ts`

**Interfaces:**
- Python commands: `semantic.inspect`, `semantic.resolve`, `evidence.projectRole`.
- TypeScript clients: `runFemSemanticInspect()`, `runFemSemanticResolve()`, `runFemRoleEvidenceProject()`.
- Pi tools: `fem_semantic_inspect`, `fem_semantic_resolve`, `fem_evidence_project_role`.

- [ ] **Step 1: Write failing TypeScript bridge tests**

Tests import the three new TS clients and exercise at least `semantic.resolve` through the strict Python bridge using temporary workspace model/manifest files. A role-evidence bridge test must prove the semantic role reaches evidence provenance.

- [ ] **Step 2: Verify RED**

Commit only TS tests. Expected failure at typecheck/import because new clients/types are absent.

- [ ] **Step 3: Add Python bridge commands**

Wire the three commands to the public semantic APIs using existing `_required_text` / payload validation helpers. Keep all operations read-only.

- [ ] **Step 4: Add TypeScript semantic types and clients**

Define explicit interfaces for inspection/resolution output and reuse existing `FemEngineeringEvidenceReport` for role evidence. Export through `packages/fem-tools/src/index.ts`.

- [ ] **Step 5: Add Pi SAFE tools**

Each tool must require explicit `modelPath` and `manifestPath`. Prompt guidance must state:

- never infer role from names/geometry/constraints;
- never rewrite the manifest;
- preserve stale/missing-entity/run-model mismatch errors;
- never invoke a solver;
- never infer units.

- [ ] **Step 6: Verify GREEN**

Run `pnpm typecheck`, `pnpm test:ts`, full Python tests, Ruff, solver smoke checks, and `pnpm fem:health`.

- [ ] **Step 7: Commit Task 4 GREEN**

Commit bridge, types, Pi tools, and TS tests.

---

### Task 5: Documentation, Final Review, and PR13 Closeout

**Files:**
- Create: `docs/architecture/engineering-semantic-roles.md`
- Create: `docs/verification/pr13-engineering-semantic-roles.md`
- Modify: `docs/superpowers/plans/2026-09-05-engineering-semantic-roles-v1.md`
- Update PR #13 metadata only after exact-head verification.

**Interfaces:**
- Documents the explicit-manifest trust model, status semantics, run/model identity gate, Bridge/Pi contracts, and V1 non-goals.

- [ ] **Step 1: Synchronize with current `main` before closeout**

Compare `main...feat/pr13-engineering-semantic-roles-v1`; if behind, merge/rebase safely into the feature branch before final verification.

- [ ] **Step 2: Write architecture and verification docs**

The verification record must distinguish:

- explicit semantic declaration truth;
- static entity-enumeration confidence;
- recorded run/result evidence integrity;
- prohibited heuristic role inference.

Record RED/GREEN CI evidence and exact final test counts.

- [ ] **Step 3: Final diff review**

Confirm no manifest write API, no coordinate/name heuristic, no solver execution from semantic tools, no unit inference, no ELEMENT-role scope creep, no cross-solver comparison, and no duplicate result parser/store.

- [ ] **Step 4: Run exact-final-head repository gate**

Required gate:

```text
pnpm typecheck
pnpm test:ts
python -m pytest
python -m ruff check fem_core tests/python examples/ansys/golden_path
OpenSees adapter availability smoke
ANSYS result-reader import smoke
pnpm fem:health
```

- [ ] **Step 5: Check PR review state and base synchronization**

Require `behind_by=0`, mergeable PR, no unresolved review threads, and no required-change comments before changing Draft state.

- [ ] **Step 6: Mark PR13 Ready for review**

Update the PR description with exact final head/CI evidence and mark Draft → Ready for review. Do not merge without explicit user instruction.
