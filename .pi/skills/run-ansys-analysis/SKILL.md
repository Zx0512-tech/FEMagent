---
name: run-ansys-analysis
description: Preflight and run a user-approved ANSYS MAPDL Model Bundle, including PR10 canonical earthquake injection when explicitly requested.
---

# Run ANSYS Analysis

Use this skill when the user wants FEMagent to execute an existing ANSYS APDL/CDB-style engineering model.

## Method

1. Call `fem_model_inspect` on the ANSYS entrypoint before solver execution.
2. Treat the model as a Model Bundle. Review the entrypoint, `/INPUT` and `*USE` dependency graph, per-file hashes, `bundleFingerprint`, bundle integrity, and static execution eligibility.
3. Call `fem_solver_status` with `solver: ansys` when runtime availability is unknown.
4. ANSYS runtime configuration comes from `FEM_ANSYS_EXECUTABLE`. If unavailable, report the structured status; do not guess or scan for an installation path.
5. If the analysis uses an external engineering load, inspect it with `fem_load_inspect`, resolve every required confirmation, and call `fem_load_standardize` to produce `FEMAGENT_LOAD_CSV_V1` before solver preflight.
6. For ANSYS canonical external-load injection, establish the model length/time units from deterministic project/user evidence. Pass them as `solverOptions.modelUnits`. Never infer ANSYS units from coordinates, material magnitudes, file names, or common practice.
7. Call `fem_solver_preflight` with `solver: ansys`, the model path, and—when used—the canonical `loadPath` plus the declared `solverOptions.modelUnits`.
8. Require preflight `READY` before any real solve. Inspect `SOLVER_AVAILABLE`, `ANSYS_MODEL_STATIC_SAFETY`, `MODEL_BUNDLE_INTEGRITY`, `CANONICAL_LOAD_INJECTION` when present, and `BUILD_ONLY_INSPECTION`.
9. Build-only preflight stages a sanitized copy, generates/loads the canonical APDL artifacts when applicable, and must not advance the requested solve.
10. `fem_solver_run` is an EXECUTION action. Use it only after successful preflight and the Pi permission gate obtains user approval. Reuse the exact same canonical `loadPath` and `solverOptions.modelUnits` that produced READY preflight.
11. Real execution must use the staged Model Bundle under `.femagent/runs/<runId>/model_bundle/`, never the user's original source tree.
12. Report run identity and provenance from the returned manifest: `runId`, `caseFingerprint`, `bundleFingerprint`, load/source hashes, generated artifact hashes, `executionInputFingerprint`, injection hook evidence, solver log, runtime output, and staged bundle location.

## Loads

When `loadPath` is omitted, the ANSYS Model Bundle remains `MODEL_SCRIPT_MANAGED` and owns its analysis/load commands.

PR10 supports exactly one external canonical earthquake channel with:

- `EARTHQUAKE`
- `UNIFORM_EXCITATION`
- `ACCELERATION`
- canonical unit `m/s2`
- global X/Y/Z component
- no explicit node/element target

With a supported canonical load, FEMagent converts values into declared ANSYS model units, generates `femagent_load_table.txt` and `femagent_load.mac`, validates a unique full-transient hook, and injects `/INPUT,'femagent_load','mac'` into the staged APDL only.

Canonical injection fails closed if model units are missing/unsupported, the canonical contract is invalid, the transient hook is missing/ambiguous, `TRNOPT,MSUP` is present, an active `ACEL` already exists, or no solution command is found.

## Result truth boundary

A completed ANSYS run establishes successful MAPDL process execution and captured artifacts. Numerical engineering claims must come from `fem_result_inspect` / `fem_result_query`, not from the run manifest or solver log alone.

Therefore:

- do not invent displacements, forces, stresses, reactions, convergence status, or modal values from provenance;
- do not treat process exit code alone as numerical-result validation;
- if ANSYS Result Intelligence cannot prove units, report units as unknown instead of assuming SI.

## Safety boundary

Do not execute bundles with rejected static APDL, blocked/missing dependencies, workspace escape, unsupported absolute include references, failed canonical-load validation, failed build-only inspection, or unavailable runtime. Never rewrite the user's source Model Bundle during canonical-load application.
