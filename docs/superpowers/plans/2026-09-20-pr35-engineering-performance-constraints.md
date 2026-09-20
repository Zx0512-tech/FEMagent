# PR35 — Engineering Performance Constraints V1 Implementation Plan

## Task 1 ✅
Define the strict explicit constraint request, normalization, fingerprints, unit rules, and FEASIBLE/INFEASIBLE/LIMITED semantics.

## Task 2 ✅
Extend PR34 scalar role metrics with recorded DAMPER_RESPONSE ELEMENT channels so force/deformation device limits can reuse the same evidence path.

## Task 3 ✅
Implement deterministic MAXIMUM constraint evaluation, utilization/reserve fields, per-constraint provenance, missing-metric handling, and governing-constraint reporting.

## Task 4 ✅
Add bridge, TypeScript request/report contracts, client, and one SAFE read-only Agent tool. Do not add solver execution or limit inference.

## Task 5 ✅
Add Python/TypeScript coverage for feasible, violated, mixed/limited, exact equality, zero limits, unit mismatch, unknown metric references, damper force/deformation constraints, ordering-invariant fingerprints, result tamper propagation, and Agent safety.

## Task 6 ✅
Run full CI, perform stacked-scope audit, write verification closeout, and move PR35 to Ready for Review only after exact final-head CI passes.


## Closeout

Implementation CI #736 (run id `35508441209`) passed on implementation head `e8566ff27f30f987487f4d403540a6426a844f5f`.

- TypeScript tests: 75 passed.
- Python tests: 516 passed, 9 warnings.
- Ruff: passed.
- OpenSees availability smoke: passed.
- ANSYS result-reader smoke: passed.
- FEM health smoke: passed.

A documentation-only exact final-head CI must remain green before PR35 moves to Ready for Review.
