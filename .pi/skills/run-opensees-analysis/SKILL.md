---
name: run-opensees-analysis
description: Safely prepare, preflight, run, and interpret the controlled OpenSees SolverAdapter Golden Path without confusing model/load hints with executable engineering truth.
---

# Run a controlled OpenSees analysis

Use this skill when an analysis is intended to execute through the OpenSees SolverAdapter.

1. Use `fem_solver_status` if OpenSees availability is not already established in the current session.
2. Inspect and standardize unfamiliar load data before solver preflight. Do not send a non-canonical source file directly to `fem_solver_run`.
3. PR5 supports only `FEMAGENT_OPENSEES_MODEL_SPEC` schema 1.0 with `ELASTIC_SDOF`. It does not execute arbitrary uploaded `.py` scripts.
4. Call `fem_solver_preflight` before any execution request.
5. If preflight is `BLOCKED`, explain the failed checks and do not call `fem_solver_run`.
6. Treat a coarse time-step warning as an engineering quality warning even though Newmark average acceleration is numerically stable for the controlled linear model.
7. `fem_solver_run` is an EXECUTION-risk action. The Pi permission gate must obtain user approval immediately before execution.
8. After execution, report only values returned in the solver run manifest. Do not invent unreturned node/element responses.
9. Preserve `runId`, `caseFingerprint`, model/load SHA256 values, result paths and solver version information for future Evidence registration.
10. A successful PR5 SDOF run proves the SolverAdapter/worker path, not arbitrary OpenSees model support.
