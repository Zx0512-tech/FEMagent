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
                 |
             Real Solver Run
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

### Solvers

Own numerical FEM results. An LLM explanation, static parser, or model-name heuristic is never a substitute for a solver result.

## Model identity

FEMagent does not assume that a model is one file.

For multi-file models, especially OpenSees Python, the deterministic unit of identity is a `Model Bundle`:

```text
entrypoint
  + resolved workspace-local modules
  + referenced workspace-local data
  + per-file SHA256
  -> deterministic bundleFingerprint
```

A helper/data-file change therefore changes the model identity even when the entrypoint file itself is unchanged.

Dependencies that escape the active workspace are blocked. Bundle discovery does not install missing packages, fetch remote code, or authorize arbitrary shell/network behavior.

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
        |
        v
numerical result evidence
```

This allows dynamic Python models to be understood without pretending that an AST can enumerate everything a solver will construct.

## Execution provenance

A real OpenSees Python Model Bundle is staged under the run directory before execution:

```text
.femagent/runs/<runId>/model_bundle/
```

The staged bundle, its fingerprint/file hashes, solver version, run/case identity, logs, and result artifacts form the precursor to the Artifact/Evidence layer.

## Trust boundary

The architecture follows four rules:

- **LLM decides what to do.**
- **Engineering tools decide deterministic engineering facts.**
- **Solvers decide numerical results.**
- **Artifacts/Evidence preserve what actually happened.**

Agent autonomy may grow, but engineering truth must continue to cross these deterministic boundaries rather than being inferred from model prose.
