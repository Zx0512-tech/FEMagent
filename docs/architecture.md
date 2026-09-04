# FEMagent Architecture

## Purpose

FEMagent is an Engineering Agent Runtime, not a finite-element solver.

It combines an agent runtime with deterministic engineering tools so an LLM can decide what to inspect or execute while finite-element solvers remain the authority for numerical results.

## Responsibility split

```text
                     FEMagent
                        |
                 Pi Agent Runtime
                        |
              Engineering Tools
                        |
          TypeScript/Python Bridge
                        |
                FEM Engineering Core
          _________|___________
         |         |           |
      Model      Load        Result
   Intelligence Intelligence  Intelligence
         |                     ^
   Model Bundle                |
         |                     |
         +------ Solver Adapters ------+
                 |             |
              OpenSees       ANSYS
                 |             |
                 +------ Real Solver Run
                               |
                     run_manifest + results
                               |
                    Artifact / Evidence (later)
```

### Pi Agent Runtime

Owns agent reasoning, context, sessions, Skills, Extensions, tool selection, and permission interaction. It does not become a parallel numerical engine.

### Engineering Tools

Expose small composable contracts such as model inspection, load inspection/standardization, solver status, preflight, solver run, result inspection, and result query. Tool results are structured engineering evidence rather than prompt-shaped prose.

### FEM Engineering Core

Owns deterministic parsing, Model Bundle discovery, load transformation, solver adapters, solver-native result reading, and later evidence/optimization calculations.

### Solver Adapters

Hide concrete solver APIs behind a small common boundary:

```text
status()
preflight(model_path, load_path?)
run(model_path, load_path?)
```

The abstract load path is optional because a solver-native model can own its load definition. Each concrete adapter must still enforce whichever inputs its model contract actually requires.

OpenSeesPy and ANSYS MAPDL are the current real solver adapters. They share the generic agent-facing tools while retaining solver-specific deterministic preflight and execution behavior.

### Result Intelligence

Result Intelligence is a solver-neutral, read-only facts layer over completed runs:

```text
run_manifest.json
  -> workspace/path checks
  -> declared artifact SHA verification
  -> solver-specific deterministic result reader
  -> ResultManifest
  -> ResultQuery
```

`fem_result_inspect` and `fem_result_query` never execute a solver. A successful solver process exit is not itself a numerical result; result claims must come from recorded numerical artifacts.

Controlled OpenSees response artifacts prove SI/time units through their FEMagent schema. ANSYS MAPDL binary results preserve solver-native unit/abscissa semantics when the model's unit system is not deterministically declared. `unit: null` therefore remains unknown rather than being inferred as SI.

Result Intelligence also does not resolve engineering roles. A result for node 36 does not prove that node 36 is a tower base or bearing; role-to-ID resolution belongs to deterministic model/project evidence.

### Solvers

Own numerical FEM results. An LLM explanation, static parser, model-name heuristic, or successful process exit is never a substitute for extracted solver-result evidence.

## Model identity

FEMagent does not assume that a model is one file.

For multi-file models the deterministic unit of identity is a `Model Bundle`:

```text
entrypoint
  + resolved workspace-local dependencies
  + per-file SHA256
  -> deterministic bundleFingerprint
```

A helper/include/data-file change therefore changes the model identity even when the entrypoint file itself is unchanged.

Dependencies that escape the active workspace are blocked. Bundle discovery does not install missing packages, fetch remote code, or authorize arbitrary shell/network behavior.

ANSYS bundle members may use `.cdb`, `.inp`, `.apdl`, `.mac`, `.dat`, or `.txt`; TXT/DAT entrypoints are promoted to models only when APDL/CDB content signals are present. `/INPUT` and `*USE` references form the current deterministic ANSYS dependency graph.

## Static inspection and solver inspection

Source inspection and realized solver state are intentionally separate evidence layers.

For OpenSees Python:

```text
fem_model_inspect
        |
        v
AST safety + dependency discovery
        |
        v
Model Bundle
        |
        v
fem_solver_preflight
        |
        v
isolated build-only OpenSees worker
(ops.analyze intercepted)
        |
        v
realized domain evidence
        |
        v
user-approved fem_solver_run
```

For ANSYS APDL/CDB:

```text
fem_model_inspect
        |
        v
static APDL safety + /INPUT/*USE discovery
        |
        v
ANSYS Model Bundle
        |
        v
fem_solver_preflight
        |
        v
staged sanitized build-only MAPDL run
(stops before /SOLU / SOLVE / postprocessing)
        |
        v
READY / BLOCKED evidence
        |
        v
user-approved staged fem_solver_run
```

Static APDL does not always enumerate realized topology for parameterized/block-based models. Build-only inspection proves that the staged model can be constructed without intentionally advancing the requested solve; numerical response truth is then read from recorded solver result artifacts through Result Intelligence.

## Execution and result provenance

Real solver-native Model Bundles are staged under their run directory before execution:

```text
.femagent/runs/<runId>/model_bundle/
```

The staged bundle, its fingerprint/file hashes, solver/runtime identity, run/case identity, logs, and captured outputs form the precursor to the Artifact/Evidence layer.

For ANSYS, `FEM_ANSYS_EXECUTABLE` is the explicit runtime configuration boundary. FEMagent does not guess or scan installation paths. When the staged MAPDL job produces a binary result (`.rst`, `.rth`, `.rfl`, or `.rmg`), its path and SHA256 are recorded in the run manifest so Result Intelligence can verify and read it later.

The result evidence ladder is:

```text
solver_run
 -> run manifest
 -> recorded numerical artifact
 -> artifact integrity
 -> ResultManifest
 -> ResultQuery
 -> engineering explanation
```

Later Artifact/Evidence work can build stronger run-validity state on top of this layer without making Result Intelligence a workflow controller.

## Trust boundary

The architecture follows four rules:

- **LLM decides what to do.**
- **Engineering tools decide deterministic engineering facts.**
- **Solvers decide numerical results.**
- **Artifacts/Evidence preserve what actually happened.**

Agent autonomy may grow, but engineering truth must continue to cross these deterministic boundaries rather than being inferred from model prose.
