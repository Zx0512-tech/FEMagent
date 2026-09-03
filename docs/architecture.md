# FEMagent Architecture

## Purpose

FEMagent is an Engineering Agent Runtime, not a finite-element solver.

The runtime should be able to inspect engineering assets, choose and operate solver adapters, analyze results, optimize designs, and preserve the provenance of engineering conclusions.

## Responsibility split

```text
Pi Agent Runtime (TypeScript)
        |
        v
Engineering Tools
        |
        v
FEM Engineering Core (Python)
        |
        v
Solver Adapters
  |             |
ANSYS        OpenSees
        |
        v
Run / Artifact / Evidence
```

### Pi runtime

Owns agent reasoning, context, sessions, skills, extensions, and tool selection.

### Engineering tools

Expose small composable contracts to the model. Tools should return structured engineering facts rather than prompt-shaped prose.

### Python FEM core

Owns deterministic engineering parsing, transformation, numerical post-processing, solver adapters, optimization algorithms, and evidence calculations.

### Solvers

Own numerical FEM results. An LLM explanation is never a substitute for a solver result.

## PR1 boundary

PR1 implements only a health bridge. It intentionally reports ANSYS and OpenSees as `not_checked`; real solver discovery begins later.

The first architectural invariant is therefore testable immediately:

```text
Pi tool -> TypeScript bridge -> Python command -> structured JSON
```

Future PRs should extend this same bridge instead of creating independent numerical paths.
