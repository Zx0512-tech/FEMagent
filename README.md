# FEMagent

Autonomous multi-solver finite element engineering agent runtime.

FEMagent is being built as an Engineering Agent Runtime that can understand finite-element models and loads, operate multiple FEM solvers, analyze results, optimize engineering designs, and preserve auditable evidence of what actually ran.

## Architecture principle

- **LLM decides what to do.**
- **Engineering tools decide what is true.**
- **Solvers decide numerical results.**
- **Artifacts preserve what happened.**

PR1 intentionally contains only the runtime bootstrap. It does **not** migrate solver, model, load, optimization, or evidence business logic from `momoagent`.

## PR1 bootstrap

The first vertical slice is:

```text
Pi Agent
  -> fem_health tool
  -> TypeScript/Python bridge
  -> fem_core
  -> structured JSON result
  -> Pi Agent
```

### Requirements

- Node.js 22+
- pnpm 10+
- Python 3.13+
- A Pi-supported LLM provider configured locally when running the agent itself

### Setup

```bash
pnpm install
python -m venv .venv
```

Windows PowerShell:

```powershell
.\.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev]"
```

Linux/macOS:

```bash
source .venv/bin/activate
python -m pip install -e ".[dev]"
```

### Verify the Python core

```bash
pnpm fem:health
```

Expected shape:

```json
{
  "status": "ok",
  "core": "fem_core",
  "solvers": {
    "ansys": "not_checked",
    "opensees": "not_checked"
  }
}
```

`not_checked` is deliberate in PR1. Solver discovery and real solver execution arrive in later PRs.

### Run FEMagent

After configuring a Pi-supported model/provider locally:

```bash
pnpm femagent -- "Call fem_health and summarize the FEM runtime status."
```

The project-local Pi extension registers `fem_health`, and the SDK-based agent entry point loads that extension explicitly.

### Tests

```bash
pnpm typecheck
pnpm test:ts
python -m pytest
```

## Planned next step

PR2 will turn this bootstrap bridge into the first Engineering Tool Bridge and introduce deterministic model/load inspection contracts without migrating the old fixed Workflow architecture.
