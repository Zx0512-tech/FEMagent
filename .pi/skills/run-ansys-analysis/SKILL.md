---
name: run-ansys-analysis
description: Preflight and run a user-approved ANSYS MAPDL Model Bundle through FEMagent's generic solver tools.
---

# Run ANSYS Analysis

Use this skill when the user wants FEMagent to execute an existing ANSYS APDL/CDB-style engineering model.

## Method

1. Call `fem_model_inspect` on the ANSYS entrypoint before solver execution.
2. Treat the model as a Model Bundle. Review the entrypoint, `/INPUT` and `*USE` dependency graph, per-file hashes, `bundleFingerprint`, bundle integrity, and static execution eligibility.
3. Call `fem_solver_status` with `solver: ansys` when runtime availability is unknown.
4. ANSYS runtime configuration comes from `FEM_ANSYS_EXECUTABLE`. If unavailable, report the structured status; do not guess or scan for an installation path.
5. Call `fem_solver_preflight` with `solver: ansys`.
6. Require preflight `READY` before any real solve. In particular, inspect `SOLVER_AVAILABLE`, `ANSYS_MODEL_STATIC_SAFETY`, `MODEL_BUNDLE_INTEGRITY`, and `BUILD_ONLY_INSPECTION`.
7. Build-only preflight stages a sanitized copy of the bundle and stops before `/SOLU`, `SOLVE`, or postprocessing. It must not be described as the requested numerical analysis.
8. `fem_solver_run` is an EXECUTION action. Use it only after successful preflight and the Pi permission gate obtains user approval.
9. Real execution must use the staged Model Bundle under `.femagent/runs/<runId>/model_bundle/`, not the user's original source tree.
10. Report run identity and provenance from the returned manifest: `runId`, `caseFingerprint`, entrypoint SHA256, `bundleFingerprint`, per-file hashes, solver log, runtime output, and staged bundle location.

## Loads

PR8 does not inject an arbitrary external `loadPath` into ANSYS APDL. ANSYS Model Bundles own their load and analysis commands.

If a `loadPath` is provided, the adapter records its path/hash as provenance and reports `injected: false`. Never claim that file affected the ANSYS solve unless a later explicit load-injection contract says it did.

## Result truth boundary

A PR8 ANSYS run with status `COMPLETED` establishes that the configured MAPDL process returned successfully and that requested execution artifacts were captured. PR8 does not yet parse RST/output into engineering response quantities.

Therefore:

- do not invent displacements, forces, stresses, reactions, convergence status, or modal values from the run manifest;
- do not treat process exit code alone as numerical-result validation;
- preserve runtime output and solver logs for the later Result Intelligence layer.

## Safety boundary

Do not execute bundles with rejected static APDL, blocked/missing dependencies, workspace escape, unsupported absolute include references, failed build-only inspection, or unavailable runtime.
