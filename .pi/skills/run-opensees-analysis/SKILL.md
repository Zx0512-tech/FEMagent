---
name: run-opensees-analysis
description: Safely inspect, preflight, execute, and interpret OpenSees analyses for controlled JSON models and workspace-bounded Python Model Bundles.
---

# Run an OpenSees analysis

Use this skill when an analysis is intended to execute through the OpenSees SolverAdapter.

## Common sequence

1. Use `fem_solver_status` if OpenSees availability is not already established in the current session.
2. Call `fem_model_inspect` for an unfamiliar model before solver preflight.
3. Call `fem_solver_preflight` before any execution request.
4. If preflight is `BLOCKED`, explain the failed checks and do not call `fem_solver_run`.
5. `fem_solver_run` is an EXECUTION-risk action. The Pi permission gate must obtain user approval immediately before execution.
6. After execution, report only values and provenance returned in the solver run manifest. Do not invent unreturned responses.

## Controlled JSON model path

For `FEMAGENT_OPENSEES_MODEL_SPEC` schema 1.0 with `ELASTIC_SDOF`:

- inspect and standardize unfamiliar source load data before preflight,
- provide a canonical `FEMAGENT_LOAD_CSV_V1` external load,
- do not send a non-canonical source load directly to `fem_solver_run`,
- preserve time-step quality warnings from preflight,
- omitting `loadPath` is invalid for this model contract and must remain blocked by the concrete adapter.

## OpenSees Python Model Bundle path

For a `.py` entrypoint:

- treat all resolved workspace-local Python modules and referenced data files as one Model Bundle,
- require static safety inspection and valid bundle integrity before build inspection or execution,
- never execute a bundle with a dependency that escapes the active workspace,
- allow preflight to perform isolated build-only inspection; `ops.analyze()` is intercepted so the requested analysis does not advance,
- `loadPath` may be omitted when the script owns its load and analysis definition; preflight reports this as `MODEL_SCRIPT_MANAGED`,
- if an external `loadPath` is provided for a Python bundle, treat it as recorded provenance only unless the adapter explicitly reports that it was injected; PR6 records it with `injected: false`,
- real execution stages the resolved bundle under `.femagent/runs/<runId>/model_bundle/` and runs the staged entrypoint in an isolated worker,
- use `bundleFingerprint` and per-file SHA256 values, not the entrypoint SHA alone, as model identity.

## Result provenance

Preserve the available provenance fields for later Artifact/Evidence registration, including:

- `runId` and `caseFingerprint`,
- solver package/engine version,
- model entrypoint SHA256,
- Model Bundle fingerprint and file hashes for Python models,
- external load SHA256 when one is actually part of the run identity,
- result and solver-log paths plus their hashes where returned.

A successful run proves the concrete model bundle/configuration that was actually staged and executed. It does not justify claims about files outside that bundle or responses the solver did not return.
