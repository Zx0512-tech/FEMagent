# FEMagent Agent Guidelines

## Mission

FEMagent is an autonomous engineering agent runtime for operating finite-element engineering software such as ANSYS and OpenSees.

It is not a new FEM solver and it is not a port of momoagent's fixed workflow engine.

## Architecture constitution

1. LLM decides what to do.
2. Engineering tools decide what is true.
3. Solvers decide numerical results.
4. Artifacts preserve what happened.

## Boundaries

- TypeScript owns the Pi agent runtime, tool registration, agent context, and interaction layer.
- Python `fem_core` owns deterministic engineering logic and solver-facing functionality.
- Do not make LLM prose the source of exact engineering values.
- Do not invoke solver executables directly from arbitrary model-generated shell commands once dedicated solver adapters exist.
- Do not add a second truth path for engineering calculations in the UI or prompt layer.
- Do not migrate `EngineeringTaskProposal`, `CapabilityRegistry`, `CapabilityDispatcher`, `WorkflowDefinition`, `WorkflowGuard`, or legacy task-type compatibility from momoagent unless a future design explicitly calls for it.
- Prefer small composable engineering tools over large fixed workflows.

## PR1 scope

PR1 proves only:

`Pi -> fem_health -> TypeScript/Python bridge -> fem_core -> JSON -> Pi`

No model parsing, load parsing, FEM execution, optimization, web UI, or evidence store should be added in PR1.

## Development commands

- `pnpm typecheck`
- `pnpm test:ts`
- `python -m pytest`
- `pnpm fem:health`

Keep changes minimal, testable, and cross-platform where practical. Windows is a first-class target because ANSYS integration will run there later.
