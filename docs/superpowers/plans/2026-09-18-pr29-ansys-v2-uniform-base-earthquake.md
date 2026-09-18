# PR29 — ANSYS V2 Uniform-Base Earthquake Execution Implementation Plan

**Goal:** Execute EngineeringAnalysisSpec V2 uniform-base earthquake intent through the existing ANSYS MAPDL adapter with fail-closed admission, deterministic staged controls, provenance, and existing Result Intelligence.

**Stack:** PR29 is stacked on PR28 branch `feat/pr28-v2-readiness-opensees-renderers`.

**CI note:** GitHub Actions quota is currently exhausted. Implement tests TDD-first, but do not mark final verification green until fresh CI can run.

## Task 1 — ANSYS V2 admission contract

Create `fem_core/solvers/ansys_v2_analysis.py` and `tests/python/test_ansys_v2_analysis.py`.

Admission must validate the V2 profile, current bundle fingerprint confirmation, explicit model units, load artifact identity/channel/time, X/Y excitation only, fixed result whitelist, statically proven node targets, reaction restraint semantics, one transient hook, solve hook, and absence of conflicting ACEL/damping.

## Task 2 — Deterministic PR29 staged controls

Extend `fem_core/solvers/ansys_load.py` with deterministic analysis-control construction/injection immediately before the verified solve command.

Controls: full transient, AUTOTS off, exact DELTIM/TIME, NONE or RAYLEIGH coefficients, NSOL/RSOL output. Source bytes remain untouched.

## Task 3 — SolverAdapter integration

Extend `AnsysAdapter.preflight/run`:

- detect `solverOptions.ansysV2`;
- forbid simultaneous external `loadPath`;
- derive canonical load from AnalysisSpec;
- re-verify bundle/artifact before run;
- stage load + controls;
- include `analysisAdmission`, `generatedAnalysis`, and execution identity in reports/manifests.

Legacy ANSYS loadPath behavior remains unchanged.

## Task 4 — Bridge and TypeScript contract

Extend `FemSolverOptions` and Pi TypeBox schema with `ansysV2.analysisSpec` and `confirmedBundleFingerprint`.

Keep the existing generic solver tools. No new LLM-visible ANSYS V2 execution tool.

## Task 5 — Result/provenance integration tests

Add tests proving:

- V2 READY preflight on a deterministic explicit APDL fixture;
- bundle fingerprint mismatch fails closed;
- artifact tamper fails closed;
- unsupported profile/result request fails closed;
- run stages but never modifies source;
- run manifest records AnalysisSpec/bundle/load/control identity;
- generated .rst remains queryable through existing Result Intelligence contract when a real/fixture result is available.

## Task 6 — Scope and regression audit

Run, when Actions quota returns:

```bash
pnpm typecheck
pnpm test:ts
python -m pytest
python -m ruff check fem_core tests/python examples/ansys/golden_path
python -c "from fem_core.solvers import get_solver_adapter; print(get_solver_adapter('opensees').status())"
python -c "from ansys.mapdl import reader; assert callable(reader.read_binary)"
pnpm fem:health
```

PR29 remains Draft until this fresh suite is green.
