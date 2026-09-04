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
         |                     |
   Model Bundle                |
         |                     |
         +------ Solver Adapters ------+
                 |             |
              OpenSees       ANSYS
                 |             |
                 +------ Real Solver Run
                               |
                    Run / Artifact / Evidence
```

### Pi Agent Runtime

Owns agent reasoning, context, sessions, Skills, Extensions, tool selection, and permission interaction. It does not become a parallel numerical engine.

### Engineering Tools

Expose small composable contracts such as model inspection, load inspection/standardization, solver status, preflight, and solver run. Tool results are structured engineering evidence rather than prompt-shaped prose.

### FEM Engineering Core

Owns deterministic parsing, Model Bundle discovery, load transformation, solver adapters, post-processing, and later evidence/optimization calculations.

### Solver Adapters

Hide concrete solver APIs behind a small common boundary:

```text
status()
preflight(model_path, load_path?)
run(model_path, load_path?)
```

The abstract load path is optional because a solver-native model can own its load definition. Each concrete adapter must still enforce whichever inputs its model contract actually requires.

OpenSeesPy and ANSYS MAPDL are the current real solver adapters. They share the generic agent-facing tools while retaining solver-specific deterministic preflight and execution behavior.

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

Static APDL does not always enumerate realized topology for parameterized/block-based models. PR8 build-only inspection proves that the staged model can be constructed without intentionally advancing the requested solve; detailed ANSYS domain/result extraction remains a later Result Intelligence responsibility.

## Execution provenance

Real solver-native Model Bundles are staged under their run directory before execution:

```text
.femagent/runs/<runId>/model_bundle/
```

The staged bundle, its fingerprint/file hashes, solver/runtime identity, run/case identity, logs, and captured outputs form the precursor to the Artifact/Evidence layer.

For ANSYS, `FEM_ANSYS_EXECUTABLE` is the explicit runtime configuration boundary. FEMagent does not guess or scan installation paths.

## Trust boundary

The architecture follows four rules:

- **LLM decides what to do.**
- **Engineering tools decide deterministic engineering facts.**
- **Solvers decide numerical results.**
- **Artifacts/Evidence preserve what actually happened.**

Agent autonomy may grow, but engineering truth must continue to cross these deterministic boundaries rather than being inferred from model prose.
