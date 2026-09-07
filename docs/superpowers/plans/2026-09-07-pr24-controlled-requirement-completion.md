# PR24 — Controlled Requirement Completion Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a deterministic, source-backed controlled-completion layer that converts supported natural-language engineering requirement drafts into candidate PR21 `EngineeringModelSpec` objects only when explicit evidence, controlled templates, deterministic derivations, and conflict/missing checks all succeed.

**Architecture:** The Agent/LLM extracts a closed `EngineeringRequirementDraft V1`; Python `fem_core.requirements` is the sole authority for draft validation, evidence admission, template application, deterministic derivation, conflict detection, completion status, fingerprints, and candidate ModelSpec assembly. TypeScript and Pi only transport/expose this deterministic result. Downstream PR21 validation, PR22 readiness, and PR23 rendering remain separate and are re-run through their existing public APIs.

**Tech Stack:** Python 3.13, pytest, TypeScript 5.9, TypeBox, Node test runner, existing `fem_core` bridge protocol, Pi extension tools, OpenSees PR23 renderer for final integration proof.

**Spec:** `docs/superpowers/specs/2026-09-07-pr24-controlled-requirement-completion-design.md`

## Global Constraints

- V1 profile is exactly `FRAME_2D_REQUIREMENT_V1` targeting PR21 2D FRAME ModelSpec V1.
- Python never calls an LLM, RAG provider, material database, section database, renderer, or solver from `complete_engineering_requirement()`.
- Facts are a closed tagged union; arbitrary field paths are rejected.
- Every `USER_EXPLICIT` fact must reference exact source evidence copied into the draft.
- Template selection is exact-alias only; no fuzzy, embedding, RAG, or heuristic template matching.
- V1 controlled templates are exactly `SIMPLY_SUPPORTED_BEAM_2D_V1`, `CANTILEVER_BEAM_2D_V1`, and `FIXED_FIXED_BEAM_2D_V1`.
- Templates are optional; explicit no-template PR21-V1 2D FRAME authoring remains supported.
- No unit conversion, magnitude-based unit inference, `Q355 → E`, section-shape-to-`A/Iz`, loads, analysis settings, Semantic Roles, auto-repair, template override, or solver execution.
- Conflicts are never silently overwritten.
- Only `COMPLETE` returns non-null `candidateModelSpec`; `INCOMPLETE`, `CONFLICT`, and `INVALID_DRAFT` return `candidateModelSpec=null`.
- `PR24 COMPLETE != PR22 READY`; consumers still run public PR21 validate and PR22 readiness before PR23 rendering.
- Completion tool is SAFE/read-only and must not call `runFemModelSpecRenderOpenSees`, `runFemSolverRun`, or accept an output path.

---

## File Structure

Create:

- `fem_core/requirements/__init__.py` — public exports only.
- `fem_core/requirements/schema.py` — closed V1 draft schema parsing/normalization and stable schema issues.
- `fem_core/requirements/evidence.py` — source lookup, exact-quote checks, numeric/unit identity checks.
- `fem_core/requirements/templates.py` — exact alias registry and deterministic V1 beam-template expansion.
- `fem_core/requirements/completion.py` — orchestration, conflict/missing logic, deterministic derivations, candidate assembly, fingerprints, PR21 invariant validation.
- `packages/fem-tools/src/requirementTypes.ts` — TypeScript transport types mirroring the deterministic result contract.
- `packages/fem-tools/src/requirementCompletion.ts` — thin bridge helper `runFemRequirementComplete()`.
- `.pi/extensions/requirement-tools.ts` — SAFE/read-only Pi tool registration.
- `tests/python/test_requirement_completion.py` — core schema/evidence/template/completion TDD tests.
- `tests/python/test_requirement_completion_bridge.py` — bridge TDD tests.
- `tests/python/test_requirement_completion_integration.py` — PR21/22/23 production-chain proof.
- `tests/ts/requirement-completion.test.ts` — real TS→Python transport tests.

Modify:

- `fem_core/bridge.py` — import and dispatch `requirement.complete` only.
- `packages/fem-tools/src/index.ts` — export requirement types/helper.
- `apps/agent/src/main.ts` — load `requirement-tools.ts` and allow `fem_requirement_complete`.
- `tests/ts/model-spec-tool-registration.test.ts` or a new dedicated registration test — assert tool load/allow-list and safety boundary.
- PR24 architecture/verification docs during final documentation task.

---

### Task 1: Python Draft Schema and Evidence Admission

**Files:**
- Create: `fem_core/requirements/__init__.py`
- Create: `fem_core/requirements/schema.py`
- Create: `fem_core/requirements/evidence.py`
- Test: `tests/python/test_requirement_completion.py`

**Interfaces:**
- Consumes: raw `dict[str, Any]` draft.
- Produces internal normalized draft structures used by Tasks 2–3.
- Public function is not exposed until Task 3; Task 1 may expose focused helpers inside the package only.

- [ ] **Step 1: Add RED tests for the V1 envelope and closed tagged union**

Add tests that construct the minimal valid envelope:

```python
{
    "schema": "FEMAGENT_ENGINEERING_REQUIREMENT_DRAFT_V1",
    "profile": "FRAME_2D_REQUIREMENT_V1",
    "sources": [{"sourceId": "source_1", "text": "建立一个15m简支梁"}],
    "templateIntent": None,
    "facts": [],
}
```

Assert that unknown top-level fields, duplicate source IDs, unknown fact kinds, malformed evidence objects, unsupported units, non-finite numbers, and non-object drafts produce deterministic schema issues with codes beginning `REQUIREMENT_DRAFT_...`.

Run:

```bash
python -m pytest tests/python/test_requirement_completion.py -k "draft_schema" -v
```

Expected RED reason: `fem_core.requirements` does not exist.

- [ ] **Step 2: Implement exact-key draft parsing and canonical normalization**

In `schema.py`, define constants:

```python
DRAFT_SCHEMA = "FEMAGENT_ENGINEERING_REQUIREMENT_DRAFT_V1"
DRAFT_PROFILE = "FRAME_2D_REQUIREMENT_V1"
```

Define the closed V1 fact kinds from the approved spec, including at minimum:

```text
SPAN
MODEL_UNITS
YOUNGS_MODULUS
SECTION_AREA
SECTION_IZ
NODE_COORDINATE
ELEMENT_CONNECTIVITY
NODE_CONSTRAINT
NODAL_MASS
ELEMENT_MATERIAL_REF
ELEMENT_SECTION_REF
MATERIAL_ID
SECTION_ID
```

Use exact-key checks per fact kind. Reject arbitrary `path` fields entirely.

Canonicalize semantically unordered collections by stable keys without changing user numeric values.

- [ ] **Step 3: Add RED evidence-integrity tests**

Cover:

```text
sourceId missing
quote absent from source text
value=12 with quote="15m"
unit="mm" with quote="15m"
material/section ID fact whose quote does not contain the submitted ID
```

Expected result for malformed evidence is `INVALID_DRAFT` later; at this layer assert stable evidence issue codes:

```text
REQUIREMENT_EVIDENCE_SOURCE_NOT_FOUND
REQUIREMENT_EVIDENCE_QUOTE_NOT_FOUND
REQUIREMENT_EVIDENCE_NUMERIC_MISMATCH
REQUIREMENT_EVIDENCE_UNIT_MISMATCH
```

- [ ] **Step 4: Implement evidence validation**

In `evidence.py`:

```python
def validate_explicit_evidence(
    *,
    sources: dict[str, str],
    fact: dict[str, Any],
) -> list[dict[str, Any]]:
    ...
```

Rules:

- evidence quote must be an exact substring of the referenced source text;
- number-bearing facts must extract the same finite numeric token from the quote;
- unit-bearing facts must contain the same supported unit token;
- no conversion is attempted;
- evidence parsing is deterministic and intentionally narrow.

- [ ] **Step 5: Run Task 1 tests GREEN**

```bash
python -m pytest tests/python/test_requirement_completion.py -k "draft_schema or evidence" -v
python -m ruff check fem_core/requirements tests/python/test_requirement_completion.py
```

Expected: all Task 1 tests pass.

- [ ] **Step 6: Commit Task 1**

```bash
git add fem_core/requirements tests/python/test_requirement_completion.py
git commit -m "feat: add controlled requirement draft evidence contract"
```

---

### Task 2: Controlled Template Registry and Deterministic Beam Expansion

**Files:**
- Create: `fem_core/requirements/templates.py`
- Modify: `tests/python/test_requirement_completion.py`

**Interfaces:**
- Consumes: admitted span fact and optional template intent.
- Produces: template provenance facts and canonical beam topology/constraints.

- [ ] **Step 1: Add RED exact-alias tests**

Cover exact accepted aliases:

```text
简支梁
simply supported beam
悬臂梁
cantilever beam
两端固支梁
双端固支梁
fixed-fixed beam
fixed fixed beam
```

Reject broad/ambiguous aliases such as `固支梁` and wrong template/evidence pairings.

- [ ] **Step 2: Add RED beam-expansion tests**

For accepted span `15 m` + `SIMPLY_SUPPORTED_BEAM_2D_V1`, assert derived topology conceptually equals:

```text
node 1 = (0,0)
node 2 = (15,0)
element 1 = 1 -> 2
node 1 constraints = UX, UY
node 2 constraints = UY
```

For cantilever:

```text
node 1 = fixed UX,UY,RZ
node 2 = free
```

For fixed-fixed:

```text
node 1 = UX,UY,RZ
node 2 = UX,UY,RZ
```

- [ ] **Step 3: Implement the versioned registry**

In `templates.py`, keep code-owned data such as:

```python
TEMPLATE_ALIASES = {
    "SIMPLY_SUPPORTED_BEAM_2D_V1": ("简支梁", "simply supported beam"),
    "CANTILEVER_BEAM_2D_V1": ("悬臂梁", "cantilever beam"),
    "FIXED_FIXED_BEAM_2D_V1": (
        "两端固支梁",
        "双端固支梁",
        "fixed-fixed beam",
        "fixed fixed beam",
    ),
}
```

Template selection must validate the evidence quote against this registry after only the normalization explicitly allowed by the spec.

- [ ] **Step 4: Implement deterministic beam expansion**

Return derived records carrying source metadata:

```text
TEMPLATE_DERIVED + templateId
DETERMINISTIC_DERIVED + ruleId=BEAM_SPAN_COORDINATES_V1
```

Do not emit E/A/Iz, force/time units, loads, or analysis facts.

- [ ] **Step 5: Run Task 2 GREEN**

```bash
python -m pytest tests/python/test_requirement_completion.py -k "template or beam" -v
python -m ruff check fem_core/requirements tests/python/test_requirement_completion.py
```

- [ ] **Step 6: Commit Task 2**

```bash
git add fem_core/requirements/templates.py tests/python/test_requirement_completion.py
git commit -m "feat: add versioned beam requirement templates"
```

---

### Task 3: Completion Engine, Conflict Policy, Derivations, and Candidate ModelSpec

**Files:**
- Create: `fem_core/requirements/completion.py`
- Modify: `fem_core/requirements/__init__.py`
- Modify: `tests/python/test_requirement_completion.py`

**Interfaces:**
- Produces public API:

```python
complete_engineering_requirement(
    draft: dict[str, Any],
) -> dict[str, Any]
```

- Result schema: `FEMAGENT_ENGINEERING_REQUIREMENT_COMPLETION_V1`.
- Status union: `COMPLETE | INCOMPLETE | CONFLICT | INVALID_DRAFT`.

- [ ] **Step 1: Add RED status tests**

Assert:

- malformed evidence → `INVALID_DRAFT`, candidate null;
- `15m简支梁` only → `INCOMPLETE`, candidate null;
- template-vs-explicit support mismatch → `CONFLICT`, candidate null;
- fully specified simple beam → `COMPLETE`, candidate non-null.

- [ ] **Step 2: Add RED deterministic-derivation tests**

Cover exactly the approved rules:

```text
FRAME_2D_PROFILE_FIELDS_V1
CONSISTENT_LENGTH_UNIT_V1
BEAM_SPAN_COORDINATES_V1
SINGLETON_ENTITY_ID_V1
SINGLETON_ELEMENT_BINDING_V1
EMPTY_NODAL_MASS_COLLECTION_V1
```

Verify mixed length units do not convert and become conflict/ambiguity per spec.

- [ ] **Step 3: Add RED explicit no-template ModelSpec tests**

Build a full explicit 2D frame draft with `templateIntent=null` containing evidenced nodes, elements, constraints, E/A/Iz, units, and explicit or singleton-resolvable bindings. Assert it can become `COMPLETE` without a template.

Also assert missing topology is never invented.

- [ ] **Step 4: Implement completion orchestration**

Processing order:

```text
validate draft schema
→ admit explicit facts using evidence
→ validate/apply optional template
→ apply only allow-listed deterministic derivations
→ detect contradictions without overwrite
→ compute missing + ambiguous
→ if resolvable, assemble candidate ModelSpec
→ run internal validate_engineering_model_spec invariant check
→ compute requirementFingerprint
→ return typed result
```

- [ ] **Step 5: Implement conflict handling**

Use conceptual precedence only for reporting:

```text
USER_EXPLICIT > TEMPLATE_DERIVED > DETERMINISTIC_DERIVED
```

Never silently overwrite. Any incompatible values produce a structured conflict and `status="CONFLICT"`.

- [ ] **Step 6: Implement candidate assembly and PR21 invariant**

Candidate ModelSpec may use only:

```text
admitted USER_EXPLICIT
+ controlled TEMPLATE_DERIVED
+ allow-listed DETERMINISTIC_DERIVED
```

Call existing:

```python
validate_engineering_model_spec(candidate)
```

Only return `COMPLETE` if that internal invariant returns `VALID`. Preserve its `modelSpecFingerprint` in the completion report.

Do not call PR22 or PR23 from this function.

- [ ] **Step 7: Implement deterministic `requirementFingerprint`**

Canonicalize only semantically unordered collections and hash normalized completion-affecting draft content using SHA256, matching the spec identity chain.

- [ ] **Step 8: Run full Python core GREEN**

```bash
python -m pytest tests/python/test_requirement_completion.py -v
python -m pytest tests/python -q
python -m ruff check fem_core tests/python
```

- [ ] **Step 9: Commit Task 3**

```bash
git add fem_core/requirements tests/python/test_requirement_completion.py
git commit -m "feat: complete source-backed engineering requirements"
```

---

### Task 4: Python Bridge Contract

**Files:**
- Modify: `fem_core/bridge.py`
- Create: `tests/python/test_requirement_completion_bridge.py`

**Interfaces:**
- Command: `requirement.complete`
- Payload: `{"draft": {...}}`
- Result: deterministic completion report from Task 3.

- [ ] **Step 1: Add bridge RED tests**

Use existing bridge envelope conventions. Assert a valid request:

```python
{
    "protocol": BRIDGE_PROTOCOL,
    "requestId": "req-1",
    "command": "requirement.complete",
    "payload": {"draft": draft},
}
```

currently fails with `UNKNOWN_COMMAND`.

Also cover missing/non-object `draft` transport errors.

- [ ] **Step 2: Run RED**

```bash
python -m pytest tests/python/test_requirement_completion_bridge.py -v
```

Expected: only `requirement.complete` dispatch is missing.

- [ ] **Step 3: Add the minimal bridge import and dispatch**

In `fem_core/bridge.py`:

```python
from fem_core.requirements import complete_engineering_requirement
```

and:

```python
elif command == "requirement.complete":
    result = complete_engineering_requirement(_required_object(payload, "draft"))
```

No other bridge behavior changes.

- [ ] **Step 4: Run GREEN**

```bash
python -m pytest tests/python/test_requirement_completion_bridge.py -v
python -m pytest tests/python -q
```

- [ ] **Step 5: Commit Task 4**

```bash
git add fem_core/bridge.py tests/python/test_requirement_completion_bridge.py
git commit -m "feat: expose requirement completion bridge command"
```

---

### Task 5: TypeScript Types and Real TS→Python Transport

**Files:**
- Create: `packages/fem-tools/src/requirementTypes.ts`
- Create: `packages/fem-tools/src/requirementCompletion.ts`
- Modify: `packages/fem-tools/src/index.ts`
- Create: `tests/ts/requirement-completion.test.ts`

**Interfaces:**
- Public TS helper:

```ts
runFemRequirementComplete(
  cwd: string,
  draft: FemEngineeringRequirementDraft,
  signal?: AbortSignal,
): Promise<FemEngineeringRequirementCompletion>
```

- [ ] **Step 1: Add TS RED tests**

Test a real bridge call using a temporary/workspace-safe draft fixture and assert:

```text
15m simple support only -> INCOMPLETE
fully specified beam -> COMPLETE
candidateModelSpec present only on COMPLETE
```

The RED failure should be missing exports/types, not Python logic.

- [ ] **Step 2: Run RED**

```bash
pnpm test:ts
```

- [ ] **Step 3: Implement transport-only types**

Mirror the Python contract in `requirementTypes.ts`, including exact status union and source/provenance fields. Do not reproduce completion logic in TypeScript.

- [ ] **Step 4: Implement the bridge helper**

In `requirementCompletion.ts`:

```ts
import { runFemCoreRequest } from "./pythonBridge.js";
import type {
  FemEngineeringRequirementCompletion,
  FemEngineeringRequirementDraft,
} from "./requirementTypes.js";

export async function runFemRequirementComplete(
  cwd: string,
  draft: FemEngineeringRequirementDraft,
  signal?: AbortSignal,
): Promise<FemEngineeringRequirementCompletion> {
  return await runFemCoreRequest<FemEngineeringRequirementCompletion>(
    cwd,
    "requirement.complete",
    { draft },
    { signal },
  );
}
```

- [ ] **Step 5: Export from package index**

Export requirement types and `runFemRequirementComplete`; avoid adding engineering logic to `pythonBridge.ts` unless the repository convention requires it.

- [ ] **Step 6: Run GREEN**

```bash
pnpm typecheck
pnpm test:ts
```

- [ ] **Step 7: Commit Task 5**

```bash
git add packages/fem-tools/src tests/ts/requirement-completion.test.ts
git commit -m "feat: add typed requirement completion transport"
```

---

### Task 6: SAFE Pi Tool and Agent Allow-List

**Files:**
- Create: `.pi/extensions/requirement-tools.ts`
- Modify: `apps/agent/src/main.ts`
- Modify/Create: `tests/ts/model-spec-tool-registration.test.ts` or `tests/ts/requirement-tool-registration.test.ts`

**Interfaces:**
- Tool name: `fem_requirement_complete`
- Input: `{ draft: FemEngineeringRequirementDraft }`
- Calls: `runFemRequirementComplete(ctx.cwd, params.draft, signal)` only.

- [ ] **Step 1: Add registration RED tests**

Assert source-level/tool-registration invariants:

```text
fem_requirement_complete is registered
apps/agent loads requirement-tools.ts
agent allow-list includes fem_requirement_complete
requirement-tools.ts does not reference runFemSolverRun
requirement-tools.ts does not reference runFemModelSpecRenderOpenSees
no outputPath parameter exists
```

- [ ] **Step 2: Run RED**

```bash
pnpm test:ts
```

Expected: only new registration/safety assertions fail.

- [ ] **Step 3: Implement `requirement-tools.ts`**

Register a SAFE/read-only tool with guidelines requiring:

- exact source copying;
- exact evidence for every `USER_EXPLICIT` fact;
- no knowledge/LLM assumptions labeled explicit;
- no invented E/A/Iz/units;
- exact reporting of missing/ambiguous/conflicts;
- public PR21/PR22 before PR23 rendering;
- no claim that COMPLETE means READY/solver success.

- [ ] **Step 4: Add extension path and tool allow-list**

Modify `apps/agent/src/main.ts`:

```ts
resolve(cwd, ".pi/extensions/requirement-tools.ts")
```

and include:

```text
fem_requirement_complete
```

before ModelSpec validation tools in the normal workflow ordering.

- [ ] **Step 5: Run GREEN**

```bash
pnpm typecheck
pnpm test:ts
```

- [ ] **Step 6: Commit Task 6**

```bash
git add .pi/extensions/requirement-tools.ts apps/agent/src/main.ts tests/ts
git commit -m "feat: expose safe requirement completion tool"
```

---

### Task 7: PR21→PR22→PR23 End-to-End Integration Proof

**Files:**
- Create: `tests/python/test_requirement_completion_integration.py`

**Interfaces:**
- Uses production APIs:

```python
complete_engineering_requirement
validate_engineering_model_spec
evaluate_engineering_model_readiness
render_opensees_frame_2d
```

- [ ] **Step 1: Add a fully specified simple-support fixture builder in the test**

Use source messages that explicitly evidence:

```text
15m simple-support beam
m / N / s
E = 2.06e11
A = 0.02
Iz = 8e-5
```

Use the exact units/number forms accepted by Task 1 evidence parsing.

- [ ] **Step 2: Assert the production chain**

```text
completion.status == COMPLETE
candidateModelSpec != null
PR21 validation == VALID
PR22 readiness == READY
PR23 render == RENDERED
```

Then inspect the generated script using existing Model Intelligence where practical and assert literal static topology/no analysis commands remain compatible with PR23 guarantees.

- [ ] **Step 3: Add negative integration proof**

For `建立一个15m简支梁` alone:

```text
completion == INCOMPLETE
candidateModelSpec == null
renderer is never invoked
```

- [ ] **Step 4: Run GREEN**

```bash
python -m pytest tests/python/test_requirement_completion_integration.py -v
python -m pytest tests/python -q
```

- [ ] **Step 5: Commit Task 7**

```bash
git add tests/python/test_requirement_completion_integration.py
git commit -m "test: prove requirement completion to OpenSees render chain"
```

---

### Task 8: Documentation, Verification Record, and Final Exact-Head CI

**Files:**
- Create: `docs/architecture/controlled-requirement-completion.md`
- Create: `docs/verification/pr24-controlled-requirement-completion.md`
- Modify: PR #20 metadata/body only after implementation is complete; do not merge.

**Interfaces:**
- Documents the final implemented capability and trust boundary.

- [ ] **Step 1: Write architecture documentation**

Document:

```text
natural language -> Agent extraction -> source-backed RequirementDraft
-> Python completion -> candidate ModelSpec
-> PR21 -> PR22 -> PR23
```

Explicitly distinguish:

```text
USER_EXPLICIT
TEMPLATE_DERIVED
DETERMINISTIC_DERIVED
MISSING / AMBIGUOUS / CONFLICT
```

and state templates are optional, not a global model whitelist.

- [ ] **Step 2: Write verification record**

Record exact test commands and intended evidence categories, but do not hard-code a final head SHA before the final documentation commit. Final CI/head evidence belongs in PR metadata/comment so recording it does not mutate the verified head.

- [ ] **Step 3: Run final full CI-equivalent locally where available**

```bash
pnpm typecheck
pnpm test:ts
python -m pytest
python -m ruff check fem_core tests/python examples/ansys/golden_path
python -c "from fem_core.solvers import get_solver_adapter; s=get_solver_adapter('opensees').status(); assert s['available'], s"
python -c "from ansys.mapdl import reader; assert callable(reader.read_binary)"
pnpm fem:health
```

- [ ] **Step 4: Commit final docs**

```bash
git add docs/architecture/controlled-requirement-completion.md docs/verification/pr24-controlled-requirement-completion.md
git commit -m "docs: record PR24 architecture and verification"
```

- [ ] **Step 5: Verify exact-head GitHub CI**

For the final branch head, require the PR-triggered CI run to finish `completed/success`. Inspect job steps and logs, not only the aggregate status. Confirm at minimum:

```text
TypeScript typecheck PASS
TypeScript tests PASS
Python tests PASS
Ruff PASS
OpenSees availability smoke PASS
ANSYS result reader smoke PASS
fem:health status=ok
```

- [ ] **Step 6: Final diff boundary check**

Compare `main...feat/pr24-controlled-requirement-completion` and verify no unintended production changes in:

```text
PR21 validator semantics
PR22 readiness semantics
PR23 renderer mapping semantics
solver adapters
ANSYS production behavior
Result/Load Intelligence
Knowledge/RAG truth separation
Semantic Roles
cross-solver validation
optimization
```

- [ ] **Step 7: Update PR #20 and mark Ready for Review**

PR body must include:

```text
implementation summary
trust boundary
supported templates + no-template path
TDD RED/GREEN evidence
final head SHA
exact-head CI run ID/result
final diff boundary
explicit statement: not merged
```

Do not merge without explicit user permission.
