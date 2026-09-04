# ANSYS Canonical Load Application V1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [x]`) syntax for completed work.

**Goal:** Make `FEMAGENT_LOAD_CSV_V1` earthquake acceleration deterministically affect a staged ANSYS full-transient run with explicit unit conversion and provenance.

**Architecture:** Add a focused ANSYS canonical-load module that validates one global acceleration channel, converts SI time/acceleration into declared ANSYS model units, and generates deterministic APDL table/macro artifacts. Extend staged ANSYS execution to inject the generated macro only at a unique supported full-transient hook, pass solver-specific options through the existing generic solver bridge, and record the resulting execution identity in preflight/run manifests.

**Tech Stack:** Python 3.13, ANSYS MAPDL batch process adapter, TypeScript/TypeBox Pi tools, pytest, Ruff, existing `femagent.bridge/v1`.

**Spec:** `docs/superpowers/specs/2026-09-04-ansys-canonical-load-v1-design.md`

## Global Constraints

- Source Model Bundle and canonical load files must never be modified.
- ANSYS canonical injection supports exactly one `EARTHQUAKE + UNIFORM_EXCITATION + ACCELERATION` channel in canonical `m/s2`.
- Supported model-unit declarations are length `m|cm|mm` and time `s|ms`; unknown units block injection.
- Real injection supports a unique explicit `ANTYPE,TRANS`, rejects explicit `TRNOPT,MSUP`, rejects existing active `ACEL`, and requires a solution command.
- No implicit sign inversion is applied between canonical support acceleration and `ACEL`.
- `fem_solver_run` remains execution-permission-gated; result truth remains in PR9 Result Intelligence.
- No Evidence state machine, multi-channel earthquake application, nodal-force matrix application, or response-spectrum work in PR10.

---

### Task 1: Canonical ANSYS load validation and unit conversion

**Files:**
- Create: `fem_core/solvers/ansys_load.py`
- Test: `tests/python/test_ansys_load.py`

**Interfaces:**
- Produces: `read_ansys_canonical_uniform_excitation(path: Path, model_units: dict[str, str]) -> dict[str, Any]`
- Produces normalized component, canonical/source hashes, SI samples, model-unit samples, conversion factors, and model-unit metadata.

- [x] Write failing tests for X/Y/Z aliases, nonuniform strictly increasing time, deterministic `m/s2` conversion into `m|cm|mm` and `s|ms`, missing units, malformed schema, multi-channel input, wrong quantity/unit/application, non-global target, and non-increasing time.
- [x] Run only `tests/python/test_ansys_load.py` and verify RED due missing module/functions.
- [x] Implement the strict canonical CSV reader and finite/time/unit validation with stable `FemCoreError` codes.
- [x] Run the focused tests and Ruff until GREEN.
- [x] Commit the Task 1 implementation.

### Task 2: Deterministic APDL artifact generation and model-hook validation

**Files:**
- Modify: `fem_core/solvers/ansys_load.py`
- Modify: `fem_core/solvers/ansys_runner.py`
- Test: `tests/python/test_ansys_load.py`

**Interfaces:**
- Produces: `inspect_ansys_transient_injection(bundle, workspace) -> dict[str, Any]`
- Produces: `write_ansys_uniform_excitation(stage_root, working_directory, load) -> dict[str, Any]`
- Produces: `inject_ansys_uniform_excitation(staged, hook, macro_name) -> dict[str, Any]`

- [x] Add failing tests for unique `ANTYPE,TRANS`, missing/duplicate transient hook, explicit `TRNOPT,MSUP`, existing `ACEL`, missing solve command, deterministic macro/table content, and staged-only source preservation.
- [x] Verify RED before implementation.
- [x] Generate a two-header-line table plus `*DIM/*TREAD/ACEL` macro and SHA256 metadata.
- [x] Implement deterministic hook scanning across ANSYS executable bundle files and real-stage insertion immediately after the unique `ANTYPE,TRANS` line.
- [x] Extend build sanitization so a supplied generated load macro can be referenced before the solution-stage stop, without advancing the requested analysis.
- [x] Run focused tests and Ruff until GREEN.
- [x] Commit Task 2.

### Task 3: Integrate canonical injection into ANSYS preflight and run provenance

**Files:**
- Modify: `fem_core/solvers/base.py`
- Modify: `fem_core/solvers/ansys.py`
- Modify: `fem_core/solvers/opensees.py`
- Test: `tests/python/test_ansys_solver.py`
- Test: `tests/python/test_opensees_solver.py` or existing OpenSees coverage file(s)

**Interfaces:**
- `SolverAdapter.preflight(..., solver_options: dict[str, Any] | None = None)`
- `SolverAdapter.run(..., solver_options: dict[str, Any] | None = None)`
- ANSYS consumes `solver_options["modelUnits"]` only when `load_path` is provided.

- [x] Add RED tests proving no-load ANSYS remains `MODEL_SCRIPT_MANAGED`, canonical load requires model units, invalid load/hook blocks preflight, build-only records validated load artifacts, real run records `injected: true`, generated paths/hashes/hook/conversion data, source files remain unchanged, and load changes alter fingerprints.
- [x] Add an OpenSees regression test that non-empty unsupported solver options fail closed while omitted options preserve existing behavior.
- [x] Implement the new optional base-interface argument and concrete adapter behavior.
- [x] Make ANSYS preflight generate/build-check the load in the build-inspection stage and return `CANONICAL_LOAD_INJECTION` checks.
- [x] Make ANSYS real run stage the model, generate load artifacts, inject only the staged transient hook, execute MAPDL, and include execution-input identity in the run manifest/case fingerprint.
- [x] Run Python tests/Ruff until GREEN.
- [x] Commit Task 3.

### Task 4: Bridge and Pi tool contract

**Files:**
- Modify: `fem_core/bridge.py`
- Modify: `packages/fem-tools/src/pythonBridge.ts`
- Modify: `packages/fem-tools/src/solverTypes.ts`
- Modify: `.pi/extensions/fem-tools.ts`
- Test: `tests/ts/engineering-tools.test.ts`

**Interfaces:**
- Bridge payload adds optional `solverOptions` for `solver.preflight` and `solver.run`; protocol remains `femagent.bridge/v1`.
- Pi tool schema exposes optional `solverOptions.modelUnits.length` and `.time`.

- [x] Add RED TypeScript bridge tests for ANSYS canonical preflight option transport and keep existing solver tests unchanged.
- [x] Pass `solverOptions` through Python bridge with object validation.
- [x] Extend TypeScript bridge signatures/types without weakening solver-name discrimination.
- [x] Update Pi descriptions/guidelines so unknown ANSYS model units block injection and provided canonical load is no longer called provenance-only.
- [x] Run Typecheck and TS tests until GREEN.
- [x] Commit Task 4.

### Task 5: Skills, docs, and final verification

**Files:**
- Modify: `.pi/skills/run-ansys-analysis/SKILL.md`
- Modify: `.pi/skills/inspect-engineering-load/SKILL.md`
- Modify: `docs/load-intelligence.md`
- Modify: `docs/solver-adapters.md`
- Modify: `docs/architecture.md`

**Interfaces:**
- Documents the exact first supported ANSYS external-load contract and unit-evidence rule.

- [x] Update Skills to teach: inspect/standardize load, establish ANSYS model length/time units from deterministic context, preflight with solver options, inspect injection evidence, request execution permission, then use Result Intelligence.
- [x] Update docs to remove the PR8 statement that external ANSYS loads are never injected, while preserving model-script-managed behavior when `loadPath` is absent.
- [x] Run final CI-equivalent checks: TypeScript typecheck, TS tests, Python tests, Ruff, OpenSees smoke, ANSYS result-reader smoke, health smoke.
- [x] Review PR diff for source overwrite, unit guessing, sign inversion, solver execution during read-only tools, or scope creep.
- [x] Update PR description with implemented scope/limitations and leave PR open for merge.
