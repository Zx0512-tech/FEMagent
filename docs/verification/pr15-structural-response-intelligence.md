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

OpenSees `solverOptions.responsePlanPath` is exposed as a path-only option. The existing fail-fast behavior remains: ANSYS `modelUnits` supplied to OpenSees are rejected as `UNSUPPORTED_SOLVER_OPTIONS` before model-path access. Arbitrary recorder strings/commands/args are not part of the schema.

## Pre-closeout full green gate

CI #296, run `34021667112`, on implementation head `478045472bb19a0ff2d5ee26064c330fa05eaf22` completed all workflow steps successfully.

Observed counts:

```text
TypeScript engineering bridge tests: 18 passed / 18
Python engineering core tests:     171 passed / 171
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

The PR diff was reviewed against the approved spec and implementation plan. At the pre-closeout head:

- branch is based directly on `main` and was `behind_by=0`;
- no optimization runtime is introduced;
- no hidden unit inference/conversion is introduced;
- no generic ANSYS element generalized-force mapping is invented;
- no implicit element stress averaging/max collapse is introduced;
- no arbitrary OpenSees recorder/command injection is exposed;
- Semantic Roles remain explicit manifest declarations;
- structural artifacts are hashed before numerical promotion;
- structural identity is retained through Evidence and Cross-Solver Validation;
- read-only Pi structural tools do not execute a solver;
- no automatic engineering tolerance or PASS/FAIL policy is introduced.

## Final-head rule

The documentation commit is intentionally followed by a fresh exact-head CI run. PR15 must not be marked Ready for review until that final documentation head completes the same full CI gate successfully and the branch remains current with `main` with no review blocker.
