# PR32 Verification — Controlled Repair & Recovery

## Implementation status

PR32 adds a fail-closed recovery layer above PR31.

Implementation CI #679 (run id `35499923936`) passed the full repository suite on head `5c147ac0da4382374ba1b6193b5e918a5318d517`.

## Verified recovery chain

```text
blocked PR31 preparation
  → deterministic repair diagnosis
  → typed repair actions
  → explicit user/operator resolution
  → workflow-input patch only
  → PR30 evidence/model/load validation again
  → PR31 preparation again
  → READY_FOR_CONFIRMATION or still blocked
```

No real solver execution is performed by PR32.

## Supported V1 repairs

User-confirmed input repair:

- explicit NONE damping;
- explicit Rayleigh alphaM/betaK;
- explicit X/Y excitation component;
- explicit response component;
- explicit canonical load selection;
- replacement canonical load artifact path;
- ANSYS solver model path;
- Semantic Role context path pair.

Engineering-context replacement:

- complete revised ModelSpec, including externally justified nodal mass/constraint changes.

Diagnostic-only/manual actions:

- semantic-role ambiguity/missing role;
- model/result semantic conflicts;
- solver unavailable;
- build-only/preflight failures;
- invalid/tampered context.

## Safety guarantees

Tests and tool contracts lock the following:

- no damping default;
- no invented Rayleigh coefficients;
- no invented nodal mass;
- no invented supports/constraints;
- no semantic-role/node guessing;
- no automatic load generation;
- no source model/load file mutation;
- stale/tampered repair-plan fingerprints fail closed;
- repair retry passes evidence-backed changes through PR30 again;
- repair retry passes repaired workflow through PR31 again;
- no `runFemSolverRun` call or repair-specific execution shortcut exists.

Real execution remains exclusively on the existing permission-gated `fem_solver_run`.

## CI #679

Passed:

- Typecheck
- TypeScript engineering bridge tests
- Python engineering core tests
- Ruff
- OpenSees adapter availability smoke
- ANSYS result reader import smoke
- FEM health smoke

## Scope audit

Diff base: `main` at `f091ab90048ac20c962976cc6dacd8f56c2cbe9d`.

Production changes are limited to:

- controlled repair planning/retry;
- bridge transport;
- typed TypeScript client/contracts;
- SAFE Agent repair tools;
- Agent registration.

No changes were made to:

- OpenSees numerical execution;
- ANSYS numerical execution;
- AnalysisSpec renderer mathematics;
- Result Intelligence numerical algorithms;
- solver permission gate;
- optimization/nonlinear/response-spectrum features.

## Final-head rule

A documentation-only closeout commit follows this record. PR32 moves to Ready for Review only after that exact final head passes the same full CI suite.
