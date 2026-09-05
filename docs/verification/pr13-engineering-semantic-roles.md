# PR13 Validation — Engineering Semantic Roles V1

## Status

PR13 implements the explicit-manifest semantic-role layer and role-based Engineering Evidence composition. This record captures the TDD history, trust boundaries, acceptance coverage, and final closeout criteria.

The pull request must not be marked Ready until the exact final documentation head passes the full repository gate, the branch is synchronized with `main`, and PR review state contains no unresolved required-change feedback.

## What PR13 proves

PR13 establishes this deterministic chain:

```text
explicit Semantic Role Manifest
  -> current Model Bundle fingerprint match
  -> roleId resolves to explicit NODE
  -> static entity validation reported separately
  -> completed run Model Bundle identity match
  -> Result Intelligence artifact/query validation
  -> PR12 Engineering Evidence promotion
  -> semantic provenance retained in evidence
```

It does not infer engineering roles from model structure and does not create a second result parser, evidence store, or solver execution path.

## Trust-boundary contract

PR13 intentionally separates three questions.

| Boundary | What is being established | V1 signal |
| --- | --- | --- |
| Semantic declaration | The project explicitly declares what an engineering role means for this exact Model Bundle. | `status: RESOLVED` after valid manifest + matching `bundleFingerprint`. |
| Static entity confirmation | Model Intelligence can independently prove the declared NODE exists from complete static topology. | `STATICALLY_CONFIRMED` or `NOT_STATICALLY_ENUMERABLE`. |
| Numerical evidence integrity | A completed run from the same Model Bundle contains auditable recorded result evidence for the resolved target. | Result Intelligence integrity + PR12 evidence status. |

A role being `RESOLVED` does not mean static topology is necessarily fully enumerable, and static enumerability does not replace the requirement for recorded result-artifact verification.

## Status-semantics regression

The closeout review identified a state-conflation defect in the first implementation: `resolve_semantic_role()` correctly returned `RESOLVED + NOT_STATICALLY_ENUMERABLE` for a dynamic OpenSees model, while `inspect_semantic_roles()` aggregated the same explicit declaration as top-level `UNRESOLVED`.

That contradicted the approved design because semantic declaration truth and static entity confirmation are separate dimensions.

### RED — CI #226

CI **#226** ran after adding a regression assertion for the dynamic OpenSees case.

Result:

- TypeScript: **15/15 PASS**;
- Python: **117 PASS, 1 FAIL**;
- the single failure was `test_dynamic_opensees_role_is_resolved_but_not_statically_enumerable`;
- observed value: `inspection["status"] == "UNRESOLVED"`;
- required value: `inspection["status"] == "RESOLVED"`.

This isolated the defect to inspection status aggregation; direct role resolution already had the correct entity and confirmation state.

### GREEN — CI #227

Commit:

```text
4670aba00f14f65400713cf2581661f2fc1e5b80
```

The fix makes explicit role resolution status independent of static topology enumeration. Dynamic/non-enumerable models retain the warning and `NOT_STATICALLY_ENUMERABLE`, while the explicit role remains `RESOLVED`.

CI **#227** validated that implementation head:

- `pnpm typecheck` — PASS;
- `pnpm test:ts` — **15/15 PASS**;
- `python -m pytest` — **118/118 PASS**;
- Python emitted **66 existing third-party VTK/NumPy deprecation warnings**;
- Ruff — PASS;
- OpenSees adapter availability smoke — PASS;
- ANSYS result-reader import smoke — PASS;
- `pnpm fem:health` — PASS.

## TDD history by implementation slice

### Task 1 — Manifest / resolver / model binding

**RED CI #206** failed during Python collection with `ModuleNotFoundError: fem_core.semantic_roles` while the existing TypeScript suite remained green.

The GREEN implementation added:

- strict Semantic Role Manifest parsing;
- controlled role vocabulary and NODE-only V1 entities;
- exact Model Bundle fingerprint binding;
- statically enumerable NODE validation;
- dynamic OpenSees `NOT_STATICALLY_ENUMERABLE` handling;
- ANSYS static `nodeTags` exposure where complete enumeration is available.

**GREEN CI #212** passed the repository gate for this slice.

### Task 2 — Recorded run model identity exposure

The RED tests required `inspect_result()` to expose only the model path/fingerprint already recorded in `run_manifest.json`, and to return null/absent identity when not recorded rather than recomputing or guessing it.

**RED CI #213** reached the two new `report["model"]` assertions and failed there while existing tests passed.

The GREEN change added provenance exposure only; it did not inspect model files or change numerical interpretation.

**GREEN CI #214** passed.

### Task 3 — Role -> Result -> Engineering Evidence composition

**RED CI #215** failed during Python collection because `fem_core.semantic_roles.evidence` did not yet exist.

The GREEN implementation added `project_role_evidence()` and preserved the existing PR12 production path:

```text
resolve role
  -> inspect recorded run
  -> require same Model Bundle fingerprint
  -> query Result Intelligence
  -> project_run_evidence()
  -> attach semantic provenance
```

A run from a different model fails with `SEMANTIC_ROLE_RUN_MODEL_MISMATCH` before evidence promotion.

**GREEN CI #217** passed.

### Task 4 — Bridge, TypeScript clients, Pi SAFE tools

Initial RED **CI #218** exposed the expected missing client symbols plus one test-side TypeScript union-narrowing issue. The test fixture was corrected without changing production behavior.

Clean RED **CI #219** then failed only because these intended clients did not yet exist:

```text
runFemSemanticInspect
runFemSemanticResolve
runFemRoleEvidenceProject
```

The GREEN implementation added:

- Python bridge commands `semantic.inspect`, `semantic.resolve`, and `evidence.projectRole`;
- focused TypeScript semantic types;
- three TypeScript bridge clients;
- Result Intelligence model identity typing;
- Pi SAFE tools in `.pi/extensions/semantic-tools.ts`.

The semantic Pi tools were intentionally isolated from the existing large `fem-tools.ts`; they are still auto-loaded by the same `.pi/extensions` mechanism and do not alter the real-solver permission gate.

**GREEN CI #225** passed with TypeScript **15/15**, Python **118/118**, Ruff, both solver-related smoke checks, and health all successful.

## Acceptance matrix

| Requirement | Verification |
| --- | --- |
| Manifest is explicit rather than inferred | Tests construct a workspace-local JSON manifest and resolver consumes only declared `roleId`, `roleType`, and NODE ID. |
| Manifest is bound to exact model identity | Stale fingerprint regression requires `SEMANTIC_ROLE_MODEL_MISMATCH`. |
| Missing node fails when topology is complete | Statically enumerable model with absent declared NODE requires `SEMANTIC_ROLE_ENTITY_NOT_FOUND`. |
| Dynamic topology is represented honestly | Dynamic OpenSees regression requires `RESOLVED + NOT_STATICALLY_ENUMERABLE`; no fake static confirmation is emitted. |
| Inspection and direct resolution share status semantics | Closeout regression #226/#227 verifies explicit dynamic role remains `RESOLVED` in both APIs. |
| Unknown role fails closed | Resolver requires `SEMANTIC_ROLE_NOT_FOUND`. |
| Recorded result belongs to the semantic model | Role-evidence regression compares recorded run `bundleFingerprint` and requires `SEMANTIC_ROLE_RUN_MODEL_MISMATCH` on mismatch. |
| Result artifact integrity is not bypassed | Role evidence reuses PR12 `project_run_evidence()` and therefore production Result Intelligence artifact verification. |
| Semantic provenance survives evidence projection | Tests assert role ID/type/entity, manifest SHA, model fingerprint, and entity-validation state in evidence provenance. |
| Units are not inferred | PR13 copies Result Intelligence/Evidence Center metric semantics; unknown units remain unknown/null. |
| Bridge path is read-only | Semantic bridge commands call inspection/resolution/evidence composition only; no solver adapter run is introduced. |
| Pi tools are SAFE | `fem_semantic_inspect`, `fem_semantic_resolve`, and `fem_evidence_project_role` are read-only tools; real execution confirmation remains attached only to `fem_solver_run`. |
| Existing Result Intelligence is reused | No second result parser/store exists in the PR13 diff. |
| V1 remains NODE-only | Manifest validation rejects unsupported entity types; ELEMENT roles are out of scope. |

## Stable failure behavior

PR13 preserves these semantic domain failures:

```text
INVALID_SEMANTIC_ROLE_MANIFEST
SEMANTIC_ROLE_MODEL_MISMATCH
SEMANTIC_ROLE_NOT_FOUND
SEMANTIC_ROLE_ENTITY_NOT_FOUND
SEMANTIC_ROLE_RUN_MODEL_MISMATCH
```

Existing workspace/path errors and Result Intelligence integrity/query errors are allowed to propagate. The semantic layer does not downgrade them into guessed mappings or unverifiable claims.

## Engineering diff review checklist

The closeout diff must continue to satisfy all of these boundaries:

- **Manifest write API:** none.
- **Automatic role inference:** none.
- **Coordinate/geometry heuristic:** none.
- **Component/variable-name heuristic:** none.
- **Constraint-pattern heuristic:** none.
- **LLM role guessing:** none.
- **ELEMENT role expansion:** none.
- **Solver execution from semantic tools:** none.
- **Result unit inference:** none.
- **Duplicate result parser/store:** none.
- **Cross-solver comparison/ranking:** none.
- **Alignment/resampling:** none.
- **Optimization runtime:** none.
- **UI/PDF reporting:** none.

PR14 may later compare solver-specific responses after each model has independently passed PR13 semantic resolution and PR12 evidence validation. PR13 performs no cross-solver numerical comparison itself.

## Base synchronization at closeout

Before closeout documentation, `main...feat/pr13-engineering-semantic-roles-v1` reported:

```text
behind_by = 0
```

No rebase or merge from `main` was required at that point. This check must be repeated after documentation and before removing Draft state.

## Required exact-final-head repository gate

The final documentation head must pass:

```text
pnpm typecheck
pnpm test:ts
python -m pytest
python -m ruff check fem_core tests/python examples/ansys/golden_path
OpenSees adapter availability smoke
ANSYS result-reader import smoke
pnpm fem:health
```

Expected test counts at the completed implementation baseline are:

```text
TypeScript: 15 tests
Python: 118 tests
```

The final PR description must cite the actual exact-head workflow run rather than relying on an earlier GREEN run.

## Ready-for-review criterion

PR13 may be changed from Draft to **Ready for review** only after all of the following are freshly verified:

1. architecture and verification documents are committed;
2. feature branch is not behind current `main`;
3. final diff remains inside the approved PR13 boundaries;
4. no unresolved review thread or required-change comment exists;
5. full CI succeeds on the exact final head;
6. PR description records the exact final head and verification result.

Ready-for-review is not merge approval. PR13 remains open until the user explicitly requests merge.
