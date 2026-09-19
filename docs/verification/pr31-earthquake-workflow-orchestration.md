# PR31 Verification — Earthquake Workflow Orchestration

## Implementation status

PR31 composes PR28–PR30 into a controlled earthquake workflow while preserving the existing real-execution permission boundary.

Implementation CI #665:

- run id: `35356976289`
- head: `3d72c769ae248d1f6ffffece8d6eface4971e4eb`
- conclusion: SUCCESS

Passed:

- Typecheck
- TypeScript engineering bridge tests
- Python engineering core tests
- Ruff
- OpenSees adapter availability smoke
- ANSYS result-reader import smoke
- FEM health smoke

## Verified workflow

```text
evidence-backed natural-language draft
  -> PR30 deterministic completion
  -> EngineeringAnalysisSpec V2
  -> solver-specific preparation/preflight
  -> READY_FOR_CONFIRMATION workflow manifest
  -> existing fem_solver_run only
  -> existing interactive permission gate
  -> completed solver run
  -> exact workflow/run identity binding
  -> Result Intelligence SUMMARY queries
  -> structured engineering response summary
```

## OpenSees coverage

The Python suite executes a real generated OpenSees uniform-base workflow:

1. PR30 completion;
2. PR28 readiness;
3. excited-direction positive-mass guard;
4. deterministic render;
5. generated-analysis preflight;
6. real isolated OpenSees run;
7. workflow/run identity binding;
8. Result Intelligence inspection;
9. DISPLACEMENT and REACTION_FORCE SUMMARY extraction.

The workflow also fails closed when no positive nodal mass exists in the excited direction.

## ANSYS coverage

PR31 builds the exact PR29 handoff:

- workspace-local APDL model path;
- current exact APDL Model Bundle fingerprint;
- ModelSpec-derived explicit length/time units;
- candidate AnalysisSpec V2;
- no separate loadPath;
- preserved `targetIdPolicy=IDENTITY`;
- preserved `semanticEquivalence=NOT_MACHINE_PROVEN`.

Adapter-level PR29 tests remain responsible for real ANSYS V2 admission/staging/runtime semantics. PR31 tests verify orchestration and exact transport without pretending APDL↔ModelSpec semantic equivalence is proven.

## Permission boundary

PR31 introduces no workflow execution tool.

The only real execution action remains:

`fem_solver_run`

The existing permission gate still intercepts that tool and now surfaces generated-analysis or ANSYS V2 execution context before approval.

`fem_earthquake_workflow_prepare` and `fem_earthquake_workflow_summarize` do not call `runFemSolverRun`.

## Integrity and no-inference checks

Tests lock:

- canonical load bytes are re-read through PR30;
- AnalysisSpec identity is frozen into workflow provenance;
- generated OpenSees render identity is checked against the completed run;
- ANSYS bundle identity is preserved;
- workflow manifest SHA tampering fails closed;
- completed run solver/analysis/model identities must match the workflow;
- postprocess uses planned Result Intelligence queries only;
- unknown ANSYS units remain unknown;
- no base-shear aggregation or engineering PASS/FAIL is invented.

## Scope audit

Diff base: PR30 head `cff79d689f2f7c6e8416e1b0bb0d54874a11ab6c`.

Production scope is limited to:

- workflow composition;
- bridge/TypeScript transport;
- SAFE workflow Agent tools;
- richer confirmation context on the existing permission gate.

No changes were made to:

- OpenSees SolverAdapter execution semantics;
- ANSYS SolverAdapter execution semantics;
- PR28 renderer mathematics;
- PR29 staged load/control injection;
- Result Intelligence numerical algorithms;
- Semantic Role Manifest writes;
- nonlinear analysis;
- response spectrum;
- optimization.

## Final-head rule

PR31 is not complete until the final closeout HEAD passes the same full CI suite. Only then may the PR move from Draft to Ready for Review.
