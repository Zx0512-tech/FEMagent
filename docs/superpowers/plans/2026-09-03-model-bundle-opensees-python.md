# Model Bundle & OpenSees Python Intelligence Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make FEMagent understand, build-inspect and execute real multi-file OpenSees Python model bundles while preserving solver-neutral model identity, workspace confinement, and explicit execution permission.

**Architecture:** Add a solver-neutral bundle discovery/fingerprint layer, an AST-based OpenSees Python inspector and safety classifier, and an isolated build-only worker mode. Extend the existing OpenSees adapter rather than creating solver-specific agent tools. Existing SDOF JSON support remains as the deterministic regression path.

**Tech Stack:** Python 3.13, `ast`, `hashlib`, `pathlib`, OpenSeesPy 3.8.0.0, TypeScript 5.9, Pi Extensions, `femagent.bridge/v1`, pytest, Node test runner, Ruff.

**Spec:** `docs/superpowers/specs/2026-09-03-model-bundle-opensees-python-design.md`

## Global Constraints

- A complete engineering model is a Model Bundle, not necessarily one file.
- All resolved bundle files must remain inside the active FEMagent workspace.
- OpenSees `.py` static inspection must never execute or import the user model.
- Workspace-local Python modules and engineering data files are allowed.
- Network, shell/subprocess, dynamic eval/exec and destructive filesystem behavior are rejected for execution eligibility.
- `os.path` is allowed; `os.system` and `os.popen` are not.
- Dynamic Python topology must not be converted into invented static node/element counts.
- Build-only inspection executes only in an isolated solver worker and must prevent `ops.analyze()` from advancing analysis.
- Real OpenSees model execution remains behind the existing `fem_solver_run` EXECUTION permission gate.
- Do not add OpenSees-specific Pi tool names; extend `fem_model_inspect`, `fem_solver_preflight` and `fem_solver_run`.
- Preserve the PR5 `FEMAGENT_OPENSEES_MODEL_SPEC` SDOF path.

---

### Task 1: Bundle manifest and deterministic fingerprint

**Files:**
- Create: `fem_core/model_bundle.py`
- Test: `tests/python/test_model_bundle.py`

**Interfaces:**
- Produces: `discover_bundle(workspace: Path, entrypoint: Path, seed_dependencies: list[DependencyReference]) -> dict[str, Any]`
- Produces: `bundle_fingerprint(files: list[dict[str, Any]]) -> str`
- Produces: `DependencyReference(source: str, reference: str, target: str | None, dependency_type: str, status: str, role: str | None)`

- [ ] **Step 1: Write failing fingerprint and workspace-dependency tests**

Add tests proving two resolved files produce a stable fingerprint independent of discovery order, changing an included file changes the fingerprint, and a path escaping the workspace yields `BLOCKED_OUTSIDE_WORKSPACE`.

- [ ] **Step 2: Run the focused test and verify RED**

Run: `python -m pytest tests/python/test_model_bundle.py -v`

Expected: import/attribute failure because `fem_core.model_bundle` does not yet exist.

- [ ] **Step 3: Implement the minimal bundle primitives**

Implement workspace-relative path normalization, SHA256 per file, sorted canonical fingerprint input `path + "\0" + sha256 + "\n"`, dependency edge normalization and bundle manifest assembly.

- [ ] **Step 4: Run the focused test and verify GREEN**

Run: `python -m pytest tests/python/test_model_bundle.py -v`

Expected: all Task 1 tests pass.

- [ ] **Step 5: Commit**

Commit message: `feat: add solver-neutral model bundle manifest`

---

### Task 2: OpenSees Python AST inspection and safety classification

**Files:**
- Create: `fem_core/opensees_python_inspection.py`
- Create: `tests/fixtures/opensees_bundle/main.py`
- Create: `tests/fixtures/opensees_bundle/materials.py`
- Create: `tests/fixtures/opensees_bundle/data/mass.csv`
- Create: `tests/fixtures/opensees_unsafe.py`
- Test: `tests/python/test_opensees_python_inspection.py`

**Interfaces:**
- Consumes: bundle helpers from Task 1.
- Produces: `inspect_opensees_python(workspace: Path, raw_path: str) -> dict[str, Any]`.
- Report fields: `schemaVersion`, `kind`, `classification`, `executionEligibility`, `source`, `apiSignals`, `staticTopology`, `dynamicGeneration`, `safetyFindings`, `bundle`, `warnings`.

- [ ] **Step 1: Write failing AST behavior tests**

Tests must prove:

- `import openseespy.opensees as ops` plus `ops.model/node/element` is `MODEL_CONFIRMED`;
- literal node/element calls are counted only when statically recoverable;
- a `for` loop creating nodes marks topology dynamic and node count nullable;
- `from materials import build_materials` discovers the workspace module;
- `pandas.read_csv("data/mass.csv")` discovers the data file;
- `os.path.join` is not unsafe;
- `os.system`, `subprocess`, network imports, `eval` and `exec` create blocking findings;
- outside-workspace literal file reads are blocked.

- [ ] **Step 2: Run focused tests and verify RED**

Run: `python -m pytest tests/python/test_opensees_python_inspection.py -v`

Expected: failure because the OpenSees Python inspector does not exist.

- [ ] **Step 3: Implement minimal AST visitor**

Use `ast.parse` only. Track import aliases, recognized OpenSees calls, literal topology tags, loops/dynamic expressions, local imports, common local file-read calls, and dangerous operations. Recursively inspect only workspace-local modules, guard cycles, and never import user code.

- [ ] **Step 4: Assemble `FEMModelBundleManifest`**

Feed static dependencies into Task 1 bundle discovery, preserve unresolved/external imports, attach per-file hashes and bundle fingerprint, and derive execution eligibility from model classification plus safety findings.

- [ ] **Step 5: Run focused tests and verify GREEN**

Run: `python -m pytest tests/python/test_opensees_python_inspection.py tests/python/test_model_bundle.py -v`

Expected: all pass.

- [ ] **Step 6: Commit**

Commit message: `feat: inspect OpenSees Python model bundles`

---

### Task 3: Make `fem_model_inspect` bundle-aware without breaking ANSYS

**Files:**
- Modify: `fem_core/model_inspection.py`
- Modify: `fem_core/bridge.py`
- Modify: `packages/fem-tools/src/bridgeProtocol.ts`
- Test: `tests/python/test_model_inspection.py`
- Test: `tests/ts/engineering-tools.test.ts`

**Interfaces:**
- `model.inspect` keeps payload `{path}`.
- `.py` dispatches to `inspect_opensees_python`.
- existing APDL/CDB paths keep current behavior but return bundle identity fields where compatible.
- TypeScript adds a discriminated union for ANSYS static inspection and OpenSees Python inspection rather than weakening everything to `unknown`.

- [ ] **Step 1: Write failing Python and TypeScript contract tests**

Add a Python test calling `inspect_model(..., "tests/fixtures/opensees_bundle/main.py")` and a TypeScript bridge test calling `runFemModelInspect` on the same entrypoint. Assert OpenSees classification and bundle fingerprint exist.

- [ ] **Step 2: Verify RED in CI-compatible commands**

Run: `python -m pytest tests/python/test_model_inspection.py -v`

Run: `pnpm test:ts`

Expected: `.py` unsupported/type mismatch before implementation.

- [ ] **Step 3: Implement dispatch and typed contracts**

Dispatch by suffix/model format, preserve old ANSYS schema behavior, and add TypeScript union types for OpenSees Python reports and bundle manifests.

- [ ] **Step 4: Verify GREEN**

Run: `python -m pytest tests/python/test_model_inspection.py tests/python/test_opensees_python_inspection.py -v`

Run: `pnpm typecheck && pnpm test:ts`

Expected: all pass.

- [ ] **Step 5: Commit**

Commit message: `feat: make model inspection bundle-aware`

---

### Task 4: Isolated OpenSees build-only inspection

**Files:**
- Modify: `fem_core/solvers/opensees_worker.py`
- Modify: `fem_core/solvers/opensees.py`
- Test: `tests/python/test_opensees_solver.py`
- Create: `tests/fixtures/opensees_bundle/analysis.py` if a separate fixture is useful for asserting analyze interception.

**Interfaces:**
- Add worker mode `build_inspect` for Python bundle entrypoints.
- Add adapter method/operation returning `OpenSeesBuildInspection` with `nodeTags`, `elementTags`, `nodeCoordinates`, `analysisAdvanced: false`, and captured log metadata.
- `ops.analyze` must be intercepted to return without advancing the domain during build inspection.

- [ ] **Step 1: Write failing real-OpenSees build-only test**

Fixture should build a small model and contain an `ops.analyze(...)` call. The test asserts build inspection returns realized node/element tags and explicitly reports `analysisAdvanced == false`.

- [ ] **Step 2: Run focused solver test and verify RED**

Run: `python -m pytest tests/python/test_opensees_solver.py -v`

Expected: no build-only mode exists.

- [ ] **Step 3: Implement worker build-inspection mode**

Run the entrypoint in the isolated worker with the project directory as working directory and on `sys.path`. Patch/intercept `ops.analyze` during this mode, execute the bundle entrypoint, query OpenSees domain tags/coordinates, write structured result JSON, and always `ops.wipe()` in `finally`.

- [ ] **Step 4: Enforce pre-build safety gate**

The adapter must refuse build inspection when static model inspection says `UNSAFE`, `NOT_OPENSEES_MODEL`, has a blocked outside-workspace dependency, or has unresolved blocking safety findings.

- [ ] **Step 5: Verify GREEN**

Run: `python -m pytest tests/python/test_opensees_solver.py tests/python/test_opensees_python_inspection.py -v`

Expected: real OpenSees build-only test passes and does not advance analysis.

- [ ] **Step 6: Commit**

Commit message: `feat: add isolated OpenSees build inspection`

---

### Task 5: Preflight and real `.py` execution through the existing SolverAdapter

**Files:**
- Modify: `fem_core/solvers/opensees.py`
- Modify: `fem_core/bridge.py`
- Modify: `packages/fem-tools/src/bridgeProtocol.ts`
- Modify: `packages/fem-tools/src/pythonBridge.ts`
- Test: `tests/python/test_opensees_solver.py`
- Test: `tests/ts/engineering-tools.test.ts`

**Interfaces:**
- `fem_solver_preflight` accepts OpenSees `.py` entrypoint configuration and returns bundle/build inspection evidence.
- `fem_solver_run` accepts the same configuration and executes the original entrypoint only after the existing Pi EXECUTION permission gate.
- Bundle-backed run manifests record `entrypointSha256`, `bundleFingerprint`, and resolved bundle files.

- [ ] **Step 1: Write failing preflight and real-run tests**

Python test: a safe multi-file `.py` bundle preflights successfully and real execution creates a run manifest containing the bundle fingerprint.

TypeScript test: `runFemSolverPreflight` returns OpenSees Python bundle/build evidence through `femagent.bridge/v1`. The real run bridge test uses the small safe fixture and verifies run manifest identity fields.

- [ ] **Step 2: Verify RED**

Run: `python -m pytest tests/python/test_opensees_solver.py -v`

Run: `pnpm test:ts`

Expected: current adapter only supports PR5 controlled JSON spec.

- [ ] **Step 3: Extend adapter preflight**

Recognize `.py`, invoke static bundle inspection, require safe classification, invoke build-only inspection for dynamic/realized domain evidence, and return deterministic preflight checks.

- [ ] **Step 4: Extend real worker execution**

Execute the original safe entrypoint in the existing isolated worker; capture stdout/stderr into solver logs; preserve user-created recorder files inside the run workspace when feasible; do not execute the user model in the bridge process.

- [ ] **Step 5: Extend run manifest identity**

Record entrypoint SHA256, bundle fingerprint, resolved bundle file hashes, static classification and build-inspection summary. Preserve PR5 SDOF manifest fields for JSON-spec runs.

- [ ] **Step 6: Verify GREEN**

Run: `python -m pytest tests/python/test_opensees_solver.py -v`

Run: `pnpm typecheck && pnpm test:ts`

Expected: both controlled SDOF and multi-file `.py` OpenSees paths pass.

- [ ] **Step 7: Commit**

Commit message: `feat: run OpenSees Python model bundles`

---

### Task 6: Agent context, documentation and full regression

**Files:**
- Modify: `.pi/skills/inspect-fem-model/SKILL.md`
- Modify: `.pi/skills/run-opensees-analysis/SKILL.md`
- Modify: `docs/model-intelligence.md`
- Modify/Create: `docs/solver-adapters.md`
- Modify: `.github/workflows/ci.yml` only if an explicit additional smoke is necessary.

**Interfaces:**
- Skills teach bundle identity, dependency interpretation, static-vs-realized topology and build-only requirements.
- No new Pi tool name is introduced.

- [ ] **Step 1: Update skills with the approved engineering behavior**

Document that models may span files, bundle fingerprint is model identity, AST facts are not realized topology, local dependencies are allowed inside workspace, and execution requires safe preflight + permission.

- [ ] **Step 2: Document bundle/OpenSees Python contracts**

Document manifest fields, safety findings, build-only semantics, limitations and examples of safe multi-file projects.

- [ ] **Step 3: Run full verification**

Run:

```text
pnpm typecheck
pnpm test:ts
python -m pytest
python -m ruff check fem_core tests/python
python -m fem_core.cli bridge   # via existing health/solver CI smoke path
```

Expected: all existing and new tests pass, OpenSees availability smoke passes, no ANSYS/Load Intelligence regressions.

- [ ] **Step 4: Review PR diff for scope**

Confirm no arbitrary network enabling, no generic shell execution, no automatic package installation, no solver-specific Pi tool proliferation and no removal of the SDOF regression path.

- [ ] **Step 5: Commit**

Commit message: `docs: define model bundle agent behavior`

---

## Self-review

- Spec coverage: bundle identity, local imports/data, workspace confinement, OpenSees AST facts, safety classification, build-only inspection, real execution, traceability, Skills and tests are each mapped to a task.
- Placeholder scan: no TBD/TODO steps are used; each task has explicit outputs and verification commands.
- Type consistency: `FEMModelBundleManifest`, `OpenSeesBuildInspection`, existing `model.inspect`/`solver.preflight`/`solver.run`, and bundle fingerprint semantics are used consistently across tasks.

## Execution mode

The user explicitly requested execution of PR6 after approving the design, so this plan will be executed inline in the current session with CI checkpoints rather than waiting for a separate execution-choice round trip.
