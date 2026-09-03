# ANSYS Solver V1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add ANSYS as FEMagent's second SolverAdapter with workspace-bounded multi-file Model Bundles, `.txt/.dat` content recognition, generic preflight/run tools, staged execution, and fail-closed behavior when ANSYS is unavailable.

**Architecture:** Extend the existing solver-neutral Model Bundle and SolverAdapter boundaries rather than adding ANSYS-specific agent tools. Static APDL dependency discovery produces a deterministic bundle; preflight validates bundle/runtime and optionally performs isolated build-only execution; run stages the bundle under `.femagent/runs/<runId>/model_bundle/` before launching the configured ANSYS executable.

**Tech Stack:** Python 3.13, TypeScript/Node 22, Pi Extensions, `femagent.bridge/v1`, subprocess-based solver isolation, pytest, Ruff, Node test runner.

**Spec:** `docs/superpowers/specs/2026-09-03-ansys-solver-v1-design.md`

## Global Constraints

- Supported ANSYS bundle suffixes: `.cdb`, `.inp`, `.apdl`, `.mac`, `.dat`, `.txt`.
- `.txt/.dat` require deterministic APDL/CDB content signals before being treated as model/script sources.
- Minimum dependency mechanisms: `/INPUT` and `*USE`, recursive and cycle-safe.
- All resolved local dependencies must remain inside the active workspace.
- ANSYS executable configuration uses `FEM_ANSYS_EXECUTABLE`; no personal path is hard-coded.
- Agent-facing Tools remain `fem_model_inspect`, `fem_solver_status`, `fem_solver_preflight`, `fem_solver_run`.
- Real `fem_solver_run` remains protected by the existing EXECUTION permission gate.
- Original model files are never overwritten.
- CI must not require a licensed ANSYS installation.

---

### Task 1: ANSYS Model Bundle discovery and TXT/DAT recognition

**Files:**
- Create: `fem_core/ansys_bundle.py`
- Modify: `fem_core/model_inspection.py`
- Test: `tests/python/test_ansys_bundle.py`
- Test fixtures: `tests/fixtures/ansys_bundle/main.txt`, `tests/fixtures/ansys_bundle/geometry.mac`, `tests/fixtures/ansys_bundle/materials.dat`, `tests/fixtures/ansys_bundle/notes.txt`

**Interfaces:**
- Produces: `has_ansys_model_signals(text: str) -> bool`
- Produces: `discover_ansys_bundle(workspace: Path, raw_path: str) -> dict[str, Any]`
- `inspect_model()` consumes the bundle result for ANSYS entrypoints.

- [ ] **Step 1: Write failing tests** proving that APDL-bearing `.txt` is recognized, ordinary `.txt` is rejected as an ANSYS model entrypoint, `/INPUT` and `*USE` dependencies are recursively included, and changing a dependency changes `bundleFingerprint`.
- [ ] **Step 2: Verify RED** through CI/pytest; failures must be caused by missing ANSYS bundle behavior.
- [ ] **Step 3: Implement minimal deterministic parser** for content signals and include references. Resolve `/INPUT` filename/ext fields and `*USE` macro paths relative to the referencing file; recurse with a visited set.
- [ ] **Step 4: Make bundle integrity fail closed** for missing required local includes or workspace escapes, preserving dependency records rather than throwing away evidence.
- [ ] **Step 5: Extend ANSYS model inspection output** with `bundle`, `bundleFingerprint`, and include-driven `REQUIRES_SOLVER_INSPECTION` semantics while keeping existing APDL static facts.
- [ ] **Step 6: Verify GREEN** with the focused Python tests and then the full Python suite.
- [ ] **Step 7: Commit** with `feat: add ANSYS model bundle discovery`.

### Task 2: ANSYS SolverAdapter status and fail-closed preflight

**Files:**
- Create: `fem_core/solvers/ansys.py`
- Modify: `fem_core/solvers/registry.py`
- Test: `tests/python/test_ansys_solver.py`

**Interfaces:**
- Produces: `AnsysAdapter(SolverAdapter)` with `status()`, `preflight()`, `run()`.
- `status()` reads `FEM_ANSYS_EXECUTABLE` and returns `solver: "ANSYS"`, availability, configured path metadata, execution mode, and capabilities.
- Registry accepts `ansys` and returns `AnsysAdapter`.

- [ ] **Step 1: Write failing tests** for no environment variable, nonexistent configured executable, executable fake file, and registry lookup.
- [ ] **Step 2: Verify RED** before production implementation.
- [ ] **Step 3: Implement `status()`** without launching ANSYS; never search arbitrary machine paths in PR8.
- [ ] **Step 4: Implement preflight static checks** using `discover_ansys_bundle`/model inspection. If the solver is unavailable, return a structured `BLOCKED` preflight rather than attempting execution.
- [ ] **Step 5: Add optional external-load provenance** with `injected: false`; no PR8 load injection claim.
- [ ] **Step 6: Verify GREEN** focused and full Python tests.
- [ ] **Step 7: Commit** with `feat: add ANSYS solver status and preflight`.

### Task 3: Isolated build-only and staged real execution

**Files:**
- Modify: `fem_core/solvers/ansys.py`
- Create: `fem_core/solvers/ansys_runner.py`
- Test: `tests/python/test_ansys_solver.py`

**Interfaces:**
- Produces internal staging helper that copies exactly the resolved bundle files into a generated run/build directory.
- Produces subprocess command construction for configured ANSYS executable.
- `preflight()` optionally performs build-only process execution when runtime is available.
- `run()` produces a `solver_run` manifest with bundle identity and output/log hashes.

- [ ] **Step 1: Write failing tests** using a temporary fake executable script that records arguments and emits deterministic files; do not require ANSYS licensing.
- [ ] **Step 2: Verify RED** because build/run process support is absent.
- [ ] **Step 3: Implement staging** under `.femagent/build-inspections/<id>/model_bundle/` for build-only and `.femagent/runs/<runId>/model_bundle/` for real runs.
- [ ] **Step 4: Implement generated ANSYS invocation** with isolated stdout/stderr capture, timeout, nonzero-exit handling, and logs. Command construction must use the configured executable and staged input only.
- [ ] **Step 5: Implement build-only result** that records inspection/run logs and deterministic bundle metadata without claiming a production solution result.
- [ ] **Step 6: Implement real run manifest** with `runId`, `caseFingerprint`, solver identity, entrypoint SHA, bundle fingerprint, per-file hashes, load provenance, staged bundle root, and solver log hashes.
- [ ] **Step 7: Verify GREEN** with fake-runtime tests and full Python regression.
- [ ] **Step 8: Commit** with `feat: add staged ANSYS execution`.

### Task 4: TypeScript bridge and Pi Tool contract

**Files:**
- Modify: `packages/fem-tools/src/bridgeProtocol.ts`
- Modify: `.pi/extensions/fem-tools.ts`
- Test: `tests/ts/engineering-tools.test.ts`

**Interfaces:**
- Solver literal union becomes `"opensees" | "ansys"`.
- Solver status/preflight/run types accept discriminated `ANSYS` and `OPENSEESPY` results without weakening bridge envelope validation.

- [ ] **Step 1: Write failing TypeScript tests** for `runFemSolverStatus(..., "ansys")` and fail-closed ANSYS preflight through the real TS→Python bridge.
- [ ] **Step 2: Verify RED** due to the current OpenSees-only TS contract.
- [ ] **Step 3: Extend discriminated solver types** and Pi TypeBox solver union with `ansys`.
- [ ] **Step 4: Update Tool prompt guidelines** to state that ANSYS bundles may be multi-file and `.txt/.dat` are content-classified; preflight must precede execution.
- [ ] **Step 5: Verify GREEN** with `pnpm typecheck` and TS tests.
- [ ] **Step 6: Commit** with `feat: expose ANSYS through generic solver tools`.

### Task 5: Skills, docs, and verification

**Files:**
- Modify: `.pi/skills/inspect-fem-model/SKILL.md`
- Create: `.pi/skills/run-ansys-analysis/SKILL.md`
- Modify: `docs/model-intelligence.md`
- Modify: `docs/solver-adapters.md`
- Modify: `docs/architecture.md`

**Interfaces:**
- Skills describe method only; deterministic facts remain Tool/Solver outputs.

- [ ] **Step 1: Update model-inspection Skill** for ANSYS multi-file bundles, TXT/DAT content recognition, include dependency integrity, and static-vs-build evidence.
- [ ] **Step 2: Add ANSYS execution Skill** requiring status → inspect → preflight → EXECUTION confirmation → run, and forbidding claims that non-injected external loads affected the solve.
- [ ] **Step 3: Update architecture docs** to show OpenSees and ANSYS as concrete SolverAdapters and record the staged Model Bundle execution boundary.
- [ ] **Step 4: Run full verification**: TypeScript typecheck, TS bridge tests, all Python tests, Ruff, OpenSees availability smoke, health smoke. ANSYS deterministic tests use fake executables only.
- [ ] **Step 5: Review PR diff** for hard-coded machine paths, network/runtime installation, source-tree writes, and task-specific ANSYS tools; all must be absent.
- [ ] **Step 6: Open PR8** against `main`, keep it unmerged, and report CI evidence.
