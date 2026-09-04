# PR8 — ANSYS Solver V1 Design

## Goal

Add ANSYS as the second real SolverAdapter while preserving FEMagent's solver-neutral agent-facing contract and the Model Bundle architecture established for OpenSees.

## Model Bundle boundary

ANSYS models may span multiple files. Supported ANSYS bundle member suffixes are:

- `.cdb`
- `.inp`
- `.apdl`
- `.mac`
- `.dat`
- `.txt`

`.txt` and `.dat` are not automatically promoted to model sources. Static inspection classifies them as ANSYS/APDL model or script members only when deterministic APDL/CDB structure signals are present, including `/PREP7`, `NBLOCK`, `EBLOCK`, explicit `N`/`E`/`EN`/`ET`/`MP`/`SECTYPE`/`CM` commands, `/INPUT`, or `*USE`. Otherwise they remain ordinary engineering data dependencies.

The model identity is the deterministic bundle fingerprint built from workspace-relative paths and per-file SHA256 values. Any resolved model/helper/data file change changes the bundle identity.

## Dependency discovery

Static ANSYS bundle discovery resolves workspace-local dependencies referenced through supported APDL include mechanisms. PR8 supports at minimum:

- `/INPUT`
- `*USE`

Resolution is relative to the referencing file and the active workspace. Dependencies outside the workspace are blocked. Missing dependencies are reported as unresolved and block execution when required for model construction. Discovery is recursive and cycle-safe.

## Static inspection

`fem_model_inspect` remains the single model-inspection Tool. For ANSYS entrypoints it returns static APDL/CDB evidence plus Model Bundle metadata. Static inspection may identify topology/material/section/component/constraint signals but must not claim fully realized topology for parameterized, block-based, generated, or include-driven models when static evidence cannot prove totals.

## ANSYS runtime discovery

ANSYS is optional and environment-dependent. `fem_solver_status` with `solver: ansys` reports whether an executable/runtime is configured and available without executing a model.

PR8 does not hard-code a personal installation path. The adapter reads `FEM_ANSYS_EXECUTABLE`; the configured path must resolve to a file. CI tests unconfigured and configured/fake executable behavior without requiring a licensed ANSYS installation.

## Build-only inspection

`fem_solver_preflight` for ANSYS validates bundle safety/integrity and runtime availability. When a runtime is available it invokes an isolated ANSYS process against a staged Model Bundle using a generated build-only wrapper/input. Build-only mode is intended to construct/read the model and collect deterministic logs/inspection artifacts without treating the requested production solution as completed.

The preflight result distinguishes solver unavailable, unsafe/invalid bundle, missing dependency, build failure, and ready for execution. Static inspection and build-only solver evidence remain separate layers.

## Real execution

`fem_solver_run` uses the same generic Tool contract and remains EXECUTION-risk permission gated.

Before execution, FEMagent copies the entire resolved ANSYS Model Bundle into `.femagent/runs/<runId>/model_bundle/`. The real solver executes against the staged entrypoint, not directly against the user's source tree.

Run identity includes solver/runtime identity, entrypoint SHA256, bundle fingerprint, per-file bundle hashes, external load identity when applicable, and execution configuration. The run manifest records logs and generated outputs. PR8 does not yet attempt comprehensive RST post-processing; Result Intelligence remains later work.

## Load behavior

The abstract `SolverAdapter` keeps `load_path` optional. ANSYS model bundles may own their own load definitions. If `loadPath` is supplied in PR8, it is recorded as provenance and `injected: false` unless a concrete supported injection contract explicitly applies it. FEMagent must never claim a provided load affected the analysis unless the adapter records it as injected/applied.

## Agent-facing contract

Do not add task-specific ANSYS tools. Continue to use:

- `fem_model_inspect`
- `fem_solver_status`
- `fem_solver_preflight`
- `fem_solver_run`

Extend the solver enum/union with `ansys`.

## Safety constraints

- No dependency may escape the active workspace.
- No automatic network downloads or runtime installation.
- No hard-coded personal ANSYS installation paths.
- Static inspection does not execute APDL.
- Real solver execution occurs only after successful preflight and the existing EXECUTION permission gate.
- Original model files are never overwritten.

## Testing

CI covers deterministic behavior without requiring licensed ANSYS:

- `.txt` APDL model recognition vs ordinary text data,
- `/INPUT` and `*USE` recursive bundle discovery,
- missing/outside-workspace dependency handling,
- deterministic bundle fingerprint changes,
- solver-status configured/unconfigured behavior,
- preflight/run fail-closed behavior when ANSYS is unavailable,
- generic TypeScript bridge support for `solver: ansys`,
- regression of all OpenSees paths.

A real licensed ANSYS smoke test remains optional/local until such a runtime exists in CI.