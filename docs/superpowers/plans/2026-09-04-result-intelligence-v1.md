# Result Intelligence V1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add solver-neutral inspection and deterministic query of recorded OpenSees and ANSYS numerical result artifacts.

**Architecture:** A Python Result Intelligence layer resolves a recorded `solver_run` manifest, verifies artifact hashes, dispatches to solver-specific result readers, and returns normalized manifests/queries through the existing versioned TypeScript bridge. OpenSees consumes FEMagent's standard CSV; ANSYS consumes recorded MAPDL binary result files through the optional legacy reader package.

**Tech Stack:** Python 3.13, TypeScript/Node 22, `femagent.bridge/v1`, OpenSeesPy, optional `ansys-mapdl-reader==0.56.0`, pytest, node:test, Ruff.

**Spec:** `docs/superpowers/specs/2026-09-04-result-intelligence-v1-design.md`

## Global Constraints

- Never infer result units that are not proven by the recorded contract.
- Never parse solver logs as numerical response truth.
- Every referenced result artifact stays workspace-bounded and hash-verified when a declared SHA exists.
- Result tools are read-only and never invoke `solver.run`.
- Keep `femagent.bridge/v1`; no protocol-envelope change is needed.
- Keep ANSYS/OpenSees behind solver-neutral result tools.

---

### Task 1: Run manifest resolver and OpenSees result inspection

**Files:**
- Create: `fem_core/result_intelligence.py`
- Test: `tests/python/test_result_intelligence.py`

**Interfaces:**
- Produces: `inspect_result(workspace: Path, run_ref: str) -> dict[str, Any]`
- Produces: internal run-manifest/artifact integrity helpers used by later query dispatch.

- [ ] **Step 1: Write failing tests** for resolving `run_<id>`, a run directory, and `run_manifest.json`; rejecting path escape/malformed manifests; detecting SHA mismatch; and inspecting a controlled OpenSees `response.csv` into a `ResultManifest` with three available nodal quantities.
- [ ] **Step 2: Run the focused test file and confirm RED.**
- [ ] **Step 3: Implement the minimal resolver, integrity checks, strict OpenSees response schema reader, and normalized manifest.**
- [ ] **Step 4: Run focused tests and confirm GREEN.**
- [ ] **Step 5: Commit.**

### Task 2: Deterministic OpenSees result query

**Files:**
- Modify: `fem_core/result_intelligence.py`
- Test: `tests/python/test_result_intelligence.py`

**Interfaces:**
- Produces: `query_result(workspace: Path, run_ref: str, query: dict[str, Any]) -> dict[str, Any]`

- [ ] **Step 1: Write failing tests** for `SUMMARY` displacement query, bounded `SERIES` slicing, component aliases, unsupported node/quantity, sample-limit validation, and arbitrary OpenSees Python bundle returning `RESULT_SERIES_UNAVAILABLE`.
- [ ] **Step 2: Confirm RED.**
- [ ] **Step 3: Implement deterministic OpenSees query mapping and extrema calculations.**
- [ ] **Step 4: Confirm GREEN.**
- [ ] **Step 5: Commit.**

### Task 3: Record ANSYS binary result provenance

**Files:**
- Modify: `fem_core/solvers/ansys.py`
- Modify: `tests/python/test_ansys_solver.py`

**Interfaces:**
- `AnsysAdapter.run()` adds `outputs.binaryResult` and `outputs.binaryResultSha256` only when a staged job result (`.rst/.rth/.rfl/.rmg`) exists.

- [ ] **Step 1: Extend the fake MAPDL runtime test helper to optionally emit `<jobname>.rst`; write a failing provenance test.**
- [ ] **Step 2: Confirm RED.**
- [ ] **Step 3: Implement deterministic staged-job result-file discovery and hash recording.**
- [ ] **Step 4: Confirm GREEN and existing ANSYS tests remain green.**
- [ ] **Step 5: Commit.**

### Task 4: ANSYS binary result reader and query

**Files:**
- Create: `fem_core/ansys_result_reader.py`
- Modify: `fem_core/result_intelligence.py`
- Modify: `pyproject.toml`
- Modify: `.github/workflows/ci.yml`
- Test: `tests/python/test_ansys_result_reader.py`
- Test: `tests/python/test_result_intelligence.py`

**Interfaces:**
- Produces: ANSYS result descriptor from a MAPDL binary result file.
- Produces: nodal query for `DISPLACEMENT`, `VELOCITY`, `ACCELERATION`, and `REACTION_FORCE`.

- [ ] **Step 1: Add the optional `ansys-results = ["ansys-mapdl-reader==0.56.0"]` dependency and CI installation.**
- [ ] **Step 2: Write failing tests** using a real reader example result file for metadata/DOFs and unit tests for query mapping; include a completed ANSYS run with no binary result returning `LIMITED` rather than fabricated values.
- [ ] **Step 3: Confirm RED.**
- [ ] **Step 4: Implement lazy reader import, `read_binary(..., parse_vtk=False)`, result-set/DOF discovery, nodal time-history queries, and reaction-force iteration. Keep ANSYS physical units and abscissa semantic unit unknown unless proven.**
- [ ] **Step 5: Confirm GREEN.**
- [ ] **Step 6: Commit.**

### Task 5: Bridge, TypeScript contracts, and Pi tools

**Files:**
- Modify: `fem_core/bridge.py`
- Create: `packages/fem-tools/src/resultTypes.ts`
- Modify: `packages/fem-tools/src/pythonBridge.ts`
- Modify: `packages/fem-tools/src/index.ts`
- Modify: `.pi/extensions/fem-tools.ts`
- Modify: `tests/ts/engineering-tools.test.ts`

**Interfaces:**
- Bridge commands: `result.inspect`, `result.query`.
- TypeScript calls: `runFemResultInspect(...)`, `runFemResultQuery(...)`.
- Pi tools: `fem_result_inspect`, `fem_result_query`.

- [ ] **Step 1: Write TypeScript failing bridge tests against synthetic recorded OpenSees run artifacts.**
- [ ] **Step 2: Confirm RED/typecheck failure.**
- [ ] **Step 3: Add Python bridge dispatch, TS result contracts/functions, and Pi tools with read-only guidance.**
- [ ] **Step 4: Confirm TypeScript and Python bridge GREEN.**
- [ ] **Step 5: Commit.**

### Task 6: Result Intelligence Skill and documentation

**Files:**
- Create: `.pi/skills/inspect-fem-results/SKILL.md`
- Modify: `docs/architecture.md`
- Create: `docs/result-intelligence.md`
- Modify: `docs/solver-adapters.md`

- [ ] **Step 1: Document the evidence ladder: run manifest -> artifact integrity -> ResultManifest -> ResultQuery; explicitly separate solver-native result facts from engineering role interpretation.**
- [ ] **Step 2: Document OpenSees known SI semantics versus ANSYS unknown model units/native abscissa semantics.**
- [ ] **Step 3: Document the ANSYS binary-result optional dependency and the `LIMITED` behavior when no binary result is recorded.**
- [ ] **Step 4: Commit.**

### Task 7: Final verification and PR

**Files:**
- Review all PR9 changes.

- [ ] **Step 1: Run fresh full CI on the final head: TypeScript typecheck, TS bridge tests, Python tests, Ruff, OpenSees smoke, health smoke, plus ANSYS result-reader smoke.**
- [ ] **Step 2: Verify no result tool triggers solver execution or writes into source model directories.**
- [ ] **Step 3: Verify PR diff contains no STbridge-specific node IDs/objectives copied from momoagent.**
- [ ] **Step 4: Open PR9 with implemented scope, explicit limitations, and final verification evidence; do not merge automatically.**
