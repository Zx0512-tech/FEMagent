# PR15 — Structural Response Intelligence V1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Expand FEMagent Result Intelligence from primarily NODE response queries into a deterministic NODE + ELEMENT structural-response layer covering proven ANSYS stress/reaction channels, narrowly canonicalized generalized forces, explicit OpenSees structural-response recording, ELEMENT Semantic Roles, and downstream Evidence/Cross-Solver compatibility.

**Architecture:** Add a canonical structural-response vocabulary at the Result Intelligence boundary while keeping acquisition solver-specific. ANSYS reads only proven channels from the integrity-verified binary result; OpenSees records explicitly requested channels through a controlled response plan into hashed run artifacts. Existing Evidence, Semantic Roles, and Cross-Solver Validation are extended rather than replaced.

**Tech Stack:** Python 3.13, pytest, Ruff, TypeScript 5.9, Node 22, pnpm, OpenSeesPy 3.8.0.0, ansys-mapdl-reader 0.56.0, existing FEMagent JSON bridge/Pi extensions.

**Spec:** `docs/superpowers/specs/2026-09-05-structural-response-intelligence-v1-design.md`

## Global Constraints

- Existing NODE queries remain backwards-compatible.
- Structural values are facts only when backed by an integrity-verified artifact or deterministic extraction from one.
- ANSYS physical units remain `null` unless independently proven; PR15 adds no unit inference or conversion.
- Canonical `N/VY/VZ/T/MY/MZ`, `END_I/END_J`, stress location, and damper meanings may be emitted only from explicit supported mappings.
- OpenSees response plans never accept free-form recorder/command strings.
- Unsupported channels fail closed; absence is never converted to numeric zero.
- Semantic Roles remain explicit manifest declarations bound to the Model Bundle fingerprint; PR15 adds ELEMENT but no automatic role inference.
- Result/Evidence/Semantic/Cross-Solver post-processing remains read-only and must not execute a solver.
- PR15 adds no optimization, hidden tolerances, solver ranking, engineering PASS/FAIL, UI, or PDF reporting.
- Every implementation slice follows RED → GREEN TDD and is committed independently.

---

## File Structure

### New focused modules

- `fem_core/structural_response.py` — canonical structural vocabulary, query normalization, controlled channel identity helpers, structural series summary helper.
- `fem_core/opensees_response_plan.py` — strict response-plan schema parser/validator and canonical plan identity/hash helpers.
- `packages/fem-tools/src/structuralResponseTypes.ts` — TypeScript types for response plans and expanded structural result requests/responses.
- `.pi/extensions/structural-response-tools.ts` — SAFE read-only structural inspection/query helpers plus controlled response-plan guidance; no solver execution.

### Existing modules to extend

- `fem_core/ansys_result_reader.py` — deterministic ANSYS reaction-moment/stress/element extractors behind existing binary-reader boundary.
- `fem_core/result_intelligence.py` — NODE + ELEMENT query routing, structural queryCapabilities, hashed structural artifact support, normalized SUMMARY/SERIES response.
- `fem_core/semantic_roles/manifest.py` — accept explicit NODE or ELEMENT entities.
- `fem_core/semantic_roles/resolver.py` — entity-type-aware static validation for nodeTags/elementTags.
- `fem_core/semantic_roles/evidence.py` — preserve ELEMENT target/location structural query identity through role-backed Evidence.
- `fem_core/model_inspection.py` / `fem_core/opensees_python_inspection.py` only if needed to expose already-known complete `elementTags`; no duplicate parsing.
- `fem_core/solvers/opensees_python.py` and `fem_core/solvers/opensees_worker.py` — optional controlled response-plan input on Python-model runs and hashed recorded structural artifact output.
- `fem_core/solvers/base.py`, registry/bridge call signatures only where needed for the optional plan argument while preserving existing callers.
- `fem_core/evidence/result_projection.py` / `fem_core/evidence/api.py` only as needed to preserve `location` and structural metadata without weakening artifact integrity.
- `fem_core/cross_solver/validation.py` — include structural identity fields such as `location`/stress semantics in compatibility checks.
- `fem_core/bridge.py` — expose controlled response-plan-enabled solver calls only through existing solver command family; keep result/semantic/evidence commands read-only.
- `packages/fem-tools/src/resultTypes.ts`, `semanticTypes.ts`, `solverTypes.ts`, `pythonBridge.ts`, `index.ts` — strict union/type expansion without `any` escape hatches.
- `.pi/extensions/fem-tools.ts`, `semantic-tools.ts`, `validation-tools.ts` only if their existing schemas require union expansion; prefer the new focused extension for structural read-side tools.

### Tests

- `tests/python/test_structural_response.py`
- `tests/python/test_ansys_structural_response.py`
- `tests/python/test_semantic_roles.py`
- `tests/python/test_result_intelligence.py`
- `tests/python/test_semantic_role_evidence.py`
- `tests/python/test_opensees_response_plan.py`
- `tests/python/test_opensees_python_solver.py`
- `tests/python/test_cross_solver_validation.py`
- `tests/ts/structural-response.test.ts`
- existing bridge tests as required.

---

### Task 1: Canonical Structural Response Contract

**Files:**
- Create: `fem_core/structural_response.py`
- Create: `tests/python/test_structural_response.py`

**Interfaces:**
- Produces: `normalize_structural_query(query: dict[str, Any]) -> dict[str, Any]`
- Produces: `summarize_structural_series(abscissa: list[float], values: list[float]) -> dict[str, Any]`
- Produces controlled constants for NODE/ELEMENT target types, structural quantities/components/locations.
- Consumed later by Result Intelligence, ANSYS extractor, OpenSees response-plan validator, Evidence, and Cross-Solver Validation.

- [ ] **Step 1: Write failing tests for canonical query validation**

```python
from fem_core.structural_response import normalize_structural_query


def test_normalizes_element_generalized_force_query():
    query = normalize_structural_query({
        "quantity": "generalized_force",
        "target": {"type": "element", "id": 41},
        "component": "my",
        "location": "end_i",
        "operation": "summary",
    })
    assert query == {
        "quantity": "GENERALIZED_FORCE",
        "target": {"type": "ELEMENT", "id": 41},
        "component": "MY",
        "location": "END_I",
        "operation": "SUMMARY",
    }


def test_rejects_unproven_structural_component():
    with pytest.raises(FemCoreError) as exc:
        normalize_structural_query({
            "quantity": "GENERALIZED_FORCE",
            "target": {"type": "ELEMENT", "id": 41},
            "component": "MAGIC_MOMENT",
            "operation": "SUMMARY",
        })
    assert exc.value.code == "INVALID_RESULT_QUERY"
```

Also cover NODE stress, `PRINCIPAL_STRESS/SEQV`, `DAMPER_RESPONSE/FORCE`, positive entity IDs, allowed `SUMMARY|SERIES`, and location requirements for generalized force.

- [ ] **Step 2: Run RED**

Run: `python -m pytest tests/python/test_structural_response.py -q`

Expected: collection failure `ModuleNotFoundError: fem_core.structural_response`.

- [ ] **Step 3: Implement minimal canonical contract**

Use strict uppercase normalization and explicit sets:

```python
TARGET_TYPES = frozenset({"NODE", "ELEMENT"})
GENERALIZED_FORCE_COMPONENTS = frozenset({"N", "VY", "VZ", "T", "MY", "MZ"})
GENERALIZED_FORCE_LOCATIONS = frozenset({"END_I", "END_J", "SECTION"})
STRESS_COMPONENTS = frozenset({"SX", "SY", "SZ", "SXY", "SYZ", "SXZ"})
PRINCIPAL_STRESS_COMPONENTS = frozenset({"S1", "S2", "S3", "SINT", "SEQV"})
DAMPER_COMPONENTS = frozenset({"FORCE", "DEFORMATION", "VELOCITY", "DISSIPATED_ENERGY"})
```

Keep existing NODE Cartesian quantities compatible; do not assign units or source semantics here.

`summarize_structural_series()` must validate equal non-empty lengths and finite values, then return:

```python
{
    "sampleCount": len(values),
    "min": min(values),
    "max": max(values),
    "absolutePeak": abs(values[peak_index]),
    "abscissaAtAbsolutePeak": abscissa[peak_index],
}
```

Choose the first maximum absolute value deterministically.

- [ ] **Step 4: Run GREEN and regression**

Run:
`python -m pytest tests/python/test_structural_response.py tests/python/test_result_intelligence.py -q`

Expected: all selected tests pass.

- [ ] **Step 5: Commit**

Commit message: `feat: add structural response contract`

---

### Task 2: ANSYS Proven Node Reactions and Stress Extraction

**Files:**
- Modify: `fem_core/ansys_result_reader.py`
- Modify: `fem_core/result_intelligence.py`
- Create: `tests/python/test_ansys_structural_response.py`
- Modify: `tests/python/test_result_intelligence.py`

**Interfaces:**
- Consumes `normalize_structural_query()` and `summarize_structural_series()`.
- Produces deterministic ANSYS structural query result dicts with `quantity`, `target`, `component`, optional structural metadata, nullable `unit`, `referenceFrame`, abscissa identity, and values.
- `result.inspect` advertises only capabilities actually proven by the binary fixture/reader.

- [ ] **Step 1: Write RED tests for reaction moment and stress capabilities**

Use existing ANSYS result-reader fixtures/mocks; do not invent a new binary format. Tests should patch/mock the ansys-mapdl-reader object at the same seam used by current tests and prove:

```python
result = query_ansys_structural_result(
    rst_path,
    quantity="PRINCIPAL_STRESS",
    target={"type": "NODE", "id": 10},
    component="SEQV",
)
assert result["unit"] is None
assert result["target"] == {"type": "NODE", "id": 10}
assert result["component"] == "SEQV"
assert result["stressLocation"] == "NODAL_AVERAGED"
```

For reaction moment, use rotational DOF labels only when the fixture proves them. Assert that missing/ambiguous rotational labels do not advertise `REACTION_MOMENT`.

- [ ] **Step 2: Run RED**

Run:
`python -m pytest tests/python/test_ansys_structural_response.py tests/python/test_result_intelligence.py -q`

Expected: missing structural extractor/capability assertions fail.

- [ ] **Step 3: Implement minimal ANSYS structural extractor**

Add a single public entry point behind the existing reader boundary:

```python
def query_ansys_structural_result(
    path: Path,
    *,
    quantity: str,
    target: dict[str, Any],
    component: str,
    location: str | None = None,
) -> dict[str, Any]:
    ...
```

Rules:
- Reuse `_open_result()`; never parse `.rst` independently.
- Reuse existing artifact identity/integrity path through Result Intelligence.
- Reaction moment: map only documented rotational reaction DOFs; canonical component remains X/Y/Z, `unit=None`, `referenceFrame="SOLVER_NATIVE"` unless existing evidence proves more.
- Stress: expose only reader methods demonstrated by tests; preserve whether data are nodal-averaged vs element/native.
- Principal/equivalent stress: emit `S1/S2/S3/SINT/SEQV` only when exact source columns/reader outputs are documented by the fixture/API behavior.
- Catch reader-shape/availability failures and raise `RESULT_SERIES_UNAVAILABLE` with entity/component details.

- [ ] **Step 4: Route through Result Intelligence**

Extend `inspect_result()` ANSYS capabilities conservatively and `query_result()` so NODE structural requests call `query_ansys_structural_result()`. Existing displacement/velocity/acceleration/reaction-force path remains unchanged.

`SUMMARY` must use the canonical summary helper; `SERIES` retains existing sample cap and exact solver-native abscissa.

- [ ] **Step 5: Run GREEN and full Python reader regression**

Run:
`python -m pytest tests/python/test_ansys_result_reader.py tests/python/test_ansys_structural_response.py tests/python/test_result_intelligence.py -q`

Expected: all selected tests pass; unknown ANSYS units remain `None`.

- [ ] **Step 6: Commit**

Commit message: `feat: add proven ANSYS structural responses`

---

### Task 3: Narrow ANSYS ELEMENT Structural Responses and Fail-Closed Mapping

**Files:**
- Modify: `fem_core/ansys_result_reader.py`
- Modify: `fem_core/result_intelligence.py`
- Modify: `tests/python/test_ansys_structural_response.py`
- Modify: `tests/python/test_result_intelligence.py`

**Interfaces:**
- Extends `query_ansys_structural_result()` to ELEMENT stress and only explicitly supported generalized-force formulations.
- No generic array-position mapping is allowed.

- [ ] **Step 1: Write RED tests for ELEMENT stress identity**

Assert the returned structural response distinguishes target/location semantics:

```python
assert result["target"] == {"type": "ELEMENT", "id": 320}
assert result["quantity"] == "STRESS"
assert result["component"] == "SX"
assert result["stressLocation"] in {"ELEMENT", "ELEMENT_NODAL", "INTEGRATION_POINT"}
```

Use only a source method/fixture that identifies element IDs deterministically.

- [ ] **Step 2: Write RED fail-closed generalized-force test**

For an unsupported element formulation/native result vector:

```python
with pytest.raises(FemCoreError) as exc:
    query_ansys_structural_result(
        rst_path,
        quantity="GENERALIZED_FORCE",
        target={"type": "ELEMENT", "id": 320},
        component="MY",
        location="END_I",
    )
assert exc.value.code == "STRUCTURAL_RESPONSE_MAPPING_UNAVAILABLE"
```

- [ ] **Step 3: Run RED**

Run: `python -m pytest tests/python/test_ansys_structural_response.py -q`

Expected: ELEMENT extraction/mapping tests fail before production changes.

- [ ] **Step 4: Implement explicit mapping registry**

Define formulation contracts rather than universal indices. Example shape:

```python
_ANSYS_GENERALIZED_FORCE_MAPPINGS: dict[str, dict[tuple[str, str], int | str]] = {
    # Populate only element formulations proven by repository fixtures/tests.
}
```

If no existing fixture proves a safe N/V/M/T mapping, ship V1 with the registry empty and the fail-closed error tested/documented. Do **not** invent BEAM188/189 positions from memory without a fixture/documented source present in the repository execution environment.

ELEMENT stress support may still ship independently if reader semantics are proven.

- [ ] **Step 5: Run GREEN**

Run:
`python -m pytest tests/python/test_ansys_structural_response.py tests/python/test_result_intelligence.py -q`

Expected: supported element stress passes; unsupported generalized force deterministically fails closed.

- [ ] **Step 6: Commit**

Commit message: `feat: add fail-closed ANSYS element responses`

---

### Task 4: Extend Semantic Roles from NODE to ELEMENT

**Files:**
- Modify: `fem_core/semantic_roles/manifest.py`
- Modify: `fem_core/semantic_roles/resolver.py`
- Modify: `fem_core/semantic_roles/evidence.py`
- Modify: `tests/python/test_semantic_roles.py`
- Modify: `tests/python/test_semantic_role_evidence.py`
- Modify: model inspection only if complete element tags are already internally available but not exposed.

**Interfaces:**
- Semantic manifest entity union becomes `{type: "NODE"|"ELEMENT", id: positive int}`.
- `resolve_semantic_role()` returns the same status model for both entity types.
- Role-backed Evidence passes the resolved entity directly into structural Result Intelligence and preserves `location`/structural metadata.

- [ ] **Step 1: Write RED manifest/resolver tests**

```python
def test_resolves_explicit_element_role_when_element_tags_are_complete(...):
    result = resolve_semantic_role(..., role_id="GIRDER_MIDSPAN")
    assert result["entity"] == {"type": "ELEMENT", "id": 41}
    assert result["status"] == "RESOLVED"
    assert result["entityValidation"] == "STATICALLY_CONFIRMED"
```

Also cover:
- dynamic/incomplete topology → `RESOLVED + NOT_STATICALLY_ENUMERABLE`;
- complete topology missing element → `SEMANTIC_ROLE_ENTITY_NOT_FOUND`;
- NODE behavior unchanged.

- [ ] **Step 2: Run RED**

Run:
`python -m pytest tests/python/test_semantic_roles.py tests/python/test_semantic_role_evidence.py -q`

Expected: manifest rejects ELEMENT before implementation.

- [ ] **Step 3: Implement entity-type-aware manifest parsing**

Replace the NODE-only check with an explicit union:

```python
entity_type = str(entity.get("type") or "").upper()
if entity_type not in {"NODE", "ELEMENT"}:
    raise _invalid(...)
```

Keep the same positive integer ID and no other entity types.

- [ ] **Step 4: Implement entity-type-aware static tag lookup**

Refactor resolver helper to return tags by entity type:

```python
def _static_entity_tags(model: dict[str, Any], entity_type: str) -> set[int] | None:
    ...
```

Use `nodeTags` for NODE and `elementTags` for ELEMENT only when Model Intelligence claims complete/static enumeration. Error details/messages identify the actual entity type.

- [ ] **Step 5: Extend role-backed Evidence query**

Ensure `project_role_evidence()` accepts structural query fields and does not force a NODE target. The resolved semantic entity remains authoritative; caller-supplied target IDs must not override it.

- [ ] **Step 6: Run GREEN**

Run:
`python -m pytest tests/python/test_semantic_roles.py tests/python/test_semantic_role_evidence.py tests/python/test_cross_solver_api.py -q`

Expected: NODE regression and new ELEMENT role tests pass.

- [ ] **Step 7: Commit**

Commit message: `feat: extend semantic roles to elements`

---

### Task 5: OpenSees Structural Response Plan and Hashed Recorded Artifact

**Files:**
- Create: `fem_core/opensees_response_plan.py`
- Modify: `fem_core/solvers/opensees_python.py`
- Modify: `fem_core/solvers/opensees_worker.py`
- Modify: `fem_core/result_intelligence.py`
- Create: `tests/python/test_opensees_response_plan.py`
- Modify: `tests/python/test_opensees_python_solver.py`
- Modify: `tests/python/test_result_intelligence.py`

**Interfaces:**
- Produces `load_opensees_response_plan(workspace: Path, path: str) -> dict[str, Any]`.
- Solver run accepts optional `response_plan_path: str | None`; existing calls with no plan are unchanged.
- Run manifest records response plan SHA/fingerprint and a hashed structural response artifact when requested.
- Result Intelligence reads only the controlled artifact schema and verifies its declared SHA first.

- [ ] **Step 1: Write RED response-plan schema tests**

Valid example:

```json
{
  "schemaVersion": "1.0",
  "kind": "structural_response_plan",
  "channels": [
    {
      "channelId": "damper_force",
      "quantity": "DAMPER_RESPONSE",
      "target": {"type": "ELEMENT", "id": 7},
      "component": "FORCE"
    }
  ]
}
```

Reject:
- unknown top-level kind/version;
- duplicate channelId;
- free-form fields such as `recorder`, `command`, `args`;
- invalid target/component/location combinations;
- empty channels.

- [ ] **Step 2: Run RED**

Run: `python -m pytest tests/python/test_opensees_response_plan.py -q`

Expected: missing module failure.

- [ ] **Step 3: Implement strict plan loader**

Reuse `normalize_structural_query()` per channel but disallow `operation`; store normalized channel identity and SHA256 of the exact UTF-8 JSON bytes. Return workspace-relative plan path and hash provenance.

- [ ] **Step 4: Add controlled solver-run plumbing**

Add optional response-plan path through the OpenSees Python adapter/worker call boundary. Do not inject arbitrary code. The worker receives the normalized plan as a trusted serialized JSON file staged by FEMagent, not LLM-authored Python.

For V1, support only formulations/channels whose OpenSees response semantics are explicitly proven by tests. If repository fixtures do not prove a beam/damper canonical vector mapping, the worker must reject that channel before analysis with `STRUCTURAL_RESPONSE_MAPPING_UNAVAILABLE`; do not silently record native vectors under canonical names.

- [ ] **Step 5: Record deterministic structural artifact**

Use a normalized JSON artifact for V1 to simplify multiple channels:

```json
{
  "schemaVersion": "1.0",
  "kind": "structural_response_series",
  "channels": [
    {
      "channelId": "damper_force",
      "quantity": "DAMPER_RESPONSE",
      "target": {"type": "ELEMENT", "id": 7},
      "component": "FORCE",
      "unit": null,
      "referenceFrame": "ELEMENT_LOCAL",
      "abscissaSemantic": "TIME",
      "abscissaUnit": "s",
      "abscissaValues": [0.0, 0.01],
      "values": [0.0, 10.0]
    }
  ]
}
```

All values finite, equal lengths, deterministic ordering by response-plan channel order. Write `structural_response.json`, compute SHA256, and add `structuralResponse` + `structuralResponseSha256` to run outputs. Record response plan provenance under run manifest.

- [ ] **Step 6: Integrate Result Intelligence artifact verification/query**

Add the artifact/hash pair to `_ARTIFACT_HASH_PAIRS`. `inspect_result()` advertises exactly recorded channels. `query_result()` selects by exact canonical channel identity and applies SUMMARY/SERIES normalization. Hash mismatch continues to raise `RESULT_ARTIFACT_HASH_MISMATCH` before numerical use.

- [ ] **Step 7: Test derived damper energy gate**

If direct energy is not recorded, allow deterministic integration only when the same device has complete, direction-consistent force + deformation/velocity evidence with identical abscissa. Otherwise raise `RESULT_SERIES_UNAVAILABLE`. Never use peak-force × peak-stroke.

If implementation complexity would require a second numerical subsystem or interpolation, leave derived energy unavailable in V1 and test that fail-closed behavior; the spec explicitly allows direct solver energy as the first valid path.

- [ ] **Step 8: Run GREEN**

Run:
`python -m pytest tests/python/test_opensees_response_plan.py tests/python/test_opensees_python_solver.py tests/python/test_result_intelligence.py -q`

Expected: plan validation, hashed artifact, exact channel query, and integrity failure tests pass.

- [ ] **Step 9: Commit**

Commit message: `feat: add OpenSees structural response recording`

---

### Task 6: Evidence, Cross-Solver, TypeScript Bridge, and Pi Surface

**Files:**
- Modify: `fem_core/evidence/result_projection.py`
- Modify: `fem_core/evidence/api.py` only if needed for structural metadata passthrough.
- Modify: `fem_core/cross_solver/validation.py`
- Modify: `fem_core/bridge.py`
- Create/Modify: `packages/fem-tools/src/structuralResponseTypes.ts`
- Modify: `packages/fem-tools/src/resultTypes.ts`
- Modify: `packages/fem-tools/src/semanticTypes.ts`
- Modify: `packages/fem-tools/src/solverTypes.ts`
- Modify: `packages/fem-tools/src/pythonBridge.ts`
- Modify: `packages/fem-tools/src/index.ts`
- Create: `.pi/extensions/structural-response-tools.ts`
- Create: `tests/ts/structural-response.test.ts`
- Modify: Python Evidence/Cross-Solver tests.

**Interfaces:**
- Existing result/evidence/semantic commands carry NODE|ELEMENT and optional `location`/stress semantics.
- Existing `validation.crossSolver` compares structural identity fields before numeric comparison.
- Optional response-plan solver argument is explicit and permissioned exactly like the solver run itself.

- [ ] **Step 1: Write Python RED tests for Evidence structural provenance**

Assert role-backed Evidence retains:

```python
assert evidence["claim"]["target"] == {"type": "ELEMENT", "id": 41}
assert evidence["claim"]["quantity"] == "GENERALIZED_FORCE"
assert evidence["claim"]["component"] == "MY"
assert evidence["claim"]["location"] == "END_I"
```

Artifact hash mismatch remains a hard error.

- [ ] **Step 2: Write Cross-Solver RED identity tests**

Two VERIFIED structural evidence records are `NOT_COMPARABLE` when any of these differ:
- location (`END_I` vs `END_J`);
- stress location/averaging semantics;
- element-local vs global/solver-native reference frame;
- known unit vs `null`.

When identity matches and unit is known/equal, reuse PR14 absolutePeak comparison exactly; do not add tolerances.

- [ ] **Step 3: Write TypeScript RED bridge tests**

Test expanded structural query and ELEMENT semantic resolution across the existing Python bridge. If response-plan-enabled solver run is exposed in TypeScript, typecheck must require a path string only; no recorder string/args union exists.

Run: `pnpm typecheck && pnpm test:ts`

Expected RED: missing structural types/client/schema support.

- [ ] **Step 4: Implement Python Evidence/Cross-Solver passthrough**

Add structural identity fields without changing Evidence verification status rules. Cross-Solver compares normalized exact fields and emits stable limitation codes such as `CROSS_SOLVER_LOCATION_MISMATCH` / `CROSS_SOLVER_STRESS_SEMANTICS_MISMATCH` where appropriate.

- [ ] **Step 5: Implement strict TypeScript unions and bridge support**

Represent:

```ts
type FemResultTarget =
  | { type: "NODE"; id: number }
  | { type: "ELEMENT"; id: number };
```

Add exact structural quantity/component/location unions. Do not use `any` for the new response types.

- [ ] **Step 6: Add Pi SAFE structural tools**

Create `.pi/extensions/structural-response-tools.ts` with read-only inspect/query helpers using existing result bridge calls. Tool descriptions explicitly forbid inventing element IDs, units, local-axis mappings, and unavailable channels. Do not add solver-execution permission to this extension.

- [ ] **Step 7: Run GREEN**

Run:
`pnpm typecheck && pnpm test:ts && python -m pytest tests/python/test_semantic_role_evidence.py tests/python/test_cross_solver_validation.py tests/python/test_cross_solver_api.py -q`

Expected: all selected checks pass.

- [ ] **Step 8: Commit**

Commit message: `feat: connect structural responses to evidence and bridge`

---

### Task 7: End-to-End Verification, Architecture Docs, and PR Closeout

**Files:**
- Create: `docs/architecture/structural-response-intelligence.md`
- Create: `docs/verification/pr15-structural-response-intelligence.md`
- Modify tests only if final review reveals a missing approved-spec regression.

**Interfaces:**
- No new product interfaces should be introduced during closeout.

- [ ] **Step 1: Run complete PR15 acceptance scenarios**

At minimum verify:
1. Existing NODE result query still works.
2. Proven ANSYS structural channel returns normalized response with `unit=null` unless proved.
3. Unsupported ANSYS generalized-force formulation fails closed rather than guessing.
4. Explicit ELEMENT Semantic Role resolves and projects structural Evidence.
5. OpenSees response plan rejects free-form recorder commands.
6. Recorded OpenSees structural artifact is hash-checked before query.
7. Structural Cross-Solver identity mismatches return `NOT_COMPARABLE`.
8. No read-only structural tool executes a solver.

- [ ] **Step 2: Run full local/CI-equivalent gate**

Run:

```bash
pnpm typecheck
pnpm test:ts
python -m pytest
python -m ruff check fem_core tests/python examples/ansys/golden_path
python -c "from fem_core.solvers import get_solver_adapter; s=get_solver_adapter('opensees').status(); assert s['available'], s"
python -c "from ansys.mapdl import reader; assert callable(reader.read_binary)"
pnpm fem:health
```

Expected: zero test/lint/typecheck failures. Existing third-party warnings may remain documented but cannot hide failures.

- [ ] **Step 3: Write architecture document**

Document:
- canonical structural contract;
- solver-specific acquisition boundary;
- ANSYS unit-null rule;
- exact supported vs unavailable mappings;
- OpenSees response-plan security boundary;
- ELEMENT semantic-role trust model;
- Evidence/Cross-Solver integration;
- V1 exclusions.

- [ ] **Step 4: Write verification document**

Record exact RED/GREEN CI run IDs/head SHAs, final test counts, warnings, and whether a licensed real ANSYS structural fixture was actually exercised. Never claim real licensed ANSYS validation unless the run proves it.

- [ ] **Step 5: Fresh final diff/spec review**

Compare branch to current `main` and verify:
- no optimization code;
- no unit inference/conversion;
- no free-form OpenSees command injection;
- no hidden stress averaging;
- no generic N/V/M/T array-position guesses;
- no solver execution in read-only tools;
- no unapproved semantic role inference.

- [ ] **Step 6: Run exact-final-head CI**

After documentation is committed, trigger/observe CI on that exact final head. Read complete job output and record exact TS/Python counts and every gate conclusion.

- [ ] **Step 7: Review PR metadata/blockers**

Confirm current `main` relationship, mergeability, reviews, threads, comments, and no new blocker. Update PR body with implemented scope, verification evidence, and explicit verification limitations.

- [ ] **Step 8: Mark PR Ready for Review**

Only after exact-final-head CI is green and blocker review is clean. Do **not** merge PR15 without explicit user instruction.

---

## Plan Self-Review

### Spec coverage

- Canonical NODE + ELEMENT response contract: Task 1.
- ANSYS reaction moment/stress: Task 2.
- ANSYS element stress/narrow generalized force mapping: Task 3.
- ELEMENT Semantic Roles: Task 4.
- OpenSees controlled response plan + hashed artifact: Task 5.
- Damper channels/energy fail-closed gate: Task 5.
- Evidence structural provenance: Task 6.
- Structural Cross-Solver compatibility: Task 6.
- TypeScript/Bridge/Pi surface: Task 6.
- Documentation, exact final verification, no-merge closeout: Task 7.

### Type consistency

- Target union is consistently `NODE | ELEMENT` with positive integer `id`.
- `GENERALIZED_FORCE` uses controlled `N/VY/VZ/T/MY/MZ` and explicit location.
- `STRESS` and `PRINCIPAL_STRESS` preserve source/location semantics.
- `DAMPER_RESPONSE` uses controlled component names and never infers axes/units.
- Existing `SUMMARY|SERIES` operation vocabulary is retained.

### Placeholder scan

No implementation step relies on TBD/TODO or unspecified error handling. Where repository fixtures cannot prove a generalized-force mapping, the required behavior is explicitly fail-closed rather than speculative implementation.
