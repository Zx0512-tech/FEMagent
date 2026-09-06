# PR15 Verification — Structural Response Intelligence V1

## Scope

This record covers PR15 Structural Response Intelligence V1 on branch `feat/pr15-structural-response-intelligence-v1`.

The implementation extends deterministic FEMagent postprocessing from primarily nodal kinematic/reaction responses to controlled structural NODE/ELEMENT responses while preserving artifact integrity, explicit semantic identity, and fail-closed solver-specific mapping rules.

## Verification method

PR15 was developed with RED -> GREEN TDD slices. Hosted CI installs:

- Node.js 22;
- pnpm 10;
- Python 3.13;
- OpenSeesPy 3.8.0.0;
- ansys-mapdl-reader 0.56.0.

The CI gate runs:

```text
pnpm typecheck
pnpm test:ts
python -m pytest
python -m ruff check fem_core tests/python examples/ansys/golden_path
OpenSees adapter availability smoke
ANSYS result reader import smoke
pnpm fem:health
```

## TDD checkpoints

### Structural response contract

Task 1 RED deliberately failed because `fem_core.structural_response` did not yet exist. After the canonical query vocabulary/validation and summary helper were implemented, CI #253 completed green after a Ruff-only `SIM102` cleanup.

### ANSYS nodal structural response

CI #256 completed green with real packaged `.rst` data from `ansys-mapdl-reader`. Tests exercise nodal averaged stress plus principal/equivalent stress extraction and verify that physical units remain `null` when the recorded model unit system is not proven.

No hosted test claims a live licensed MAPDL solve for this feature.

### ANSYS element fail-closed boundary

Task 3 first exposed a test-fixture misunderstanding of the third-party `element_stress()` return order; the fixture was corrected before production changes. The clean RED then required stable structural-response failures for insufficient element location/formulation semantics. CI #259 completed green.

The implemented V1 behavior does not average or maximize multi-valued element-nodal stress data implicitly and does not invent generic `N/V/M/T` mappings for arbitrary ANSYS element formulations.

### ELEMENT Semantic Roles

Task 4 RED showed the expected NODE-only manifest restriction. The GREEN implementation added explicit `NODE | ELEMENT` entities while preserving exact Model Bundle fingerprint binding and static existence checks where topology is completely enumerable. CI #262 completed green.

### OpenSees Structural Response Plan

The strict plan loader was introduced through a missing-module RED and completed GREEN in CI #264.

The runtime slice then used a real OpenSeesPy elastic 2D beam fixture. PR15 validates the element formulation before analysis, records a controlled `localForce` mapping, writes a hashed `structural_response.json`, and queries `GENERALIZED_FORCE / MZ / END_I` through Result Intelligence. An unproven `zeroLength` generalized-force mapping is rejected before analysis. CI #269 completed green.

### Evidence and Cross-Solver structural identity

CI #271 produced a clean structural RED for three missing behaviors:

- role-backed Evidence did not yet accept `location`;
- Cross-Solver comparison did not distinguish generalized-force location;
- Cross-Solver comparison did not distinguish stress averaging/location semantics.

After implementation, CI #276 completed green. Evidence also selects the actual Result Intelligence source artifact, so OpenSees structural claims bind to the verified structural-response artifact rather than an unrelated standard nodal response CSV.

### TypeScript structural contract

Task 6 TypeScript RED at head `2e334d9e8170e9fca942b319f63099b9b306b60f` failed typecheck specifically because the public contract did not yet permit:

- `ELEMENT` targets;
- structural `location` on result queries;
- structural `location` on role-backed Evidence queries.

The subsequent implementation added discriminated structural result types while preserving existing nodal component aliases as backward-compatible inputs.

### Cross-Solver public API location propagation

CI #291 (run `34021313422`) was a clean RED after the TypeScript layer was green:

- TypeScript: 18/18 passed;
- Python: 170 passed, 1 failed;
- the sole failure proved that `END_I` was not propagated from the public Cross-Solver API into either side's role-backed Evidence request.

The API was corrected to preserve optional structural `location` for both sides.

### Pi surfaces and solver option boundary

PR15 adds read-only Structural Response Pi tools and extends Semantic/Cross-Solver tools to NODE/ELEMENT structural identities. These read-only tools call Result Intelligence/Evidence only and do not execute a solver.

OpenSees `solverOptions.responsePlanPath` is exposed as a path-only option. Arbitrary recorder strings/commands/args are not part of the schema.

The final closeout review found one asymmetric fail-fast boundary: the Bridge already rejected ANSYS `modelUnits` when sent to OpenSees, but an OpenSees-only `responsePlanPath` sent to ANSYS reached the adapter and attempted model access. CI #299 (run `34021930326`) proved the issue with one clean failing regression:

```text
TypeScript: 18 passed / 18
Python:     171 passed, 1 failed
Expected:   UNSUPPORTED_SOLVER_OPTIONS
Observed:   FILE_NOT_FOUND
```

The root cause was solver-specific option validation being present only for the OpenSees branch of the Bridge. The final fix uses symmetric Bridge-level allowlists before adapter/model access:

- OpenSees / OpenSeesPy: only `responsePlanPath`;
- ANSYS / MAPDL / ANSYS-MAPDL: only `modelUnits`.

CI #300, run `34023429680`, on head `5dddbb29a41fe7f9dc185b922de8756ba0b08b10` completed green after this correction.

## Pre-documentation final candidate gate

CI #300 produced the final implementation counts before this verification-record commit:

```text
TypeScript engineering bridge tests: 18 passed / 18
Python engineering core tests:     172 passed / 172
Python warnings:                    300
Ruff:                               PASS
OpenSees availability smoke:        PASS
ANSYS result-reader import smoke:   PASS
fem:health:                         PASS
```

The 300 warnings are third-party VTK/NumPy deprecation warnings emitted by ANSYS reader fixtures:

```text
tests/python/test_ansys_golden_path.py:          40
tests/python/test_ansys_result_reader.py:        26
tests/python/test_ansys_structural_response.py: 194
tests/python/test_result_intelligence.py:        40
```

They did not hide test or lint failures.

## Solver realism and limitations

### OpenSees

Hosted CI actually installs and executes OpenSeesPy. PR15's structural response runtime is therefore exercised with a real OpenSeesPy analysis, controlled element-response acquisition, artifact creation, integrity verification, and Result Intelligence query.

### ANSYS

Hosted CI does **not** execute a licensed ANSYS MAPDL process for PR15. ANSYS structural postprocessing is exercised against packaged real binary `.rst` fixtures using the production `ansys-mapdl-reader` path.

Therefore PR15 verifies the ANSYS binary result reader and fail-closed semantics, but it does not claim that a licensed local MAPDL installation executed a new PR15 structural model in hosted CI. A local licensed-ANSYS end-to-end test remains valuable production-readiness validation.

## Architecture review checklist

The PR diff was reviewed against the approved spec and implementation plan. At closeout:

- branch is based directly on `main` and was `behind_by=0` before the final documentation commit;
- no optimization runtime is introduced;
- no hidden unit inference/conversion is introduced;
- no generic ANSYS element generalized-force mapping is invented;
- no implicit element stress averaging/max collapse is introduced;
- no arbitrary OpenSees recorder/command injection is exposed;
- solver-specific options fail closed before adapter/model access when supplied to the wrong solver family;
- Semantic Roles remain explicit manifest declarations;
- structural artifacts are hashed before numerical promotion;
- structural identity is retained through Evidence and Cross-Solver Validation;
- read-only Pi structural tools do not execute a solver;
- no automatic engineering tolerance or PASS/FAIL policy is introduced.

## Final-head rule

This verification-record commit is the last repository-file write planned for PR15 closeout. A fresh CI run on its exact resulting head is therefore the authoritative final gate. The PR may be marked Ready for review only if that exact-head run completes all steps green, the branch remains `behind_by=0`, and no review/comment blocker appears. The exact final run/head is recorded in PR metadata rather than followed by another documentation commit, avoiding an infinite documentation-commit/CI cycle.
