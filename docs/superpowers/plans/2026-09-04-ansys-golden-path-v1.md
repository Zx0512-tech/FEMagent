# ANSYS Golden Path V1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [x]`) syntax for tracking.

**Goal:** Prove and package one complete ANSYS path from earthquake XLSX through canonical standardization, staged MAPDL execution, recorded binary result, and Result Intelligence query.

**Architecture:** Add a minimal checked-in APDL Golden Model plus a small example harness that only composes existing production APIs. Mandatory CI uses a fake MAPDL executable that validates staged injection and copies the installed `ansys-mapdl-reader` packaged `.rst` fixture into the normal ANSYS run output path; a separate opt-in real-ANSYS mode runs the same harness with `FEM_ANSYS_EXECUTABLE` and performs a 2x earthquake-amplitude causality check.

**Tech Stack:** Python 3.13, openpyxl, ANSYS MAPDL batch adapter, ansys-mapdl-reader 0.56.0, pytest, Ruff, existing TypeScript CI gates.

**Spec:** `docs/superpowers/specs/2026-09-04-ansys-golden-path-v1-design.md`

## Global Constraints

- Normal GitHub-hosted CI must not depend on a licensed ANSYS installation.
- CI fake-runtime result values are fixture-backed parser/interoperability evidence, not numerical truth for the Golden Model.
- Real ANSYS runtime comes only from `FEM_ANSYS_EXECUTABLE`; no install-path guessing or scanning.
- Golden Model units are explicitly declared as length `m`, time `s`; FEMagent must not infer units from model values.
- Golden response identity for the real path is node `2`, component `X`, quantity `DISPLACEMENT`.
- The real causality check reruns with earthquake amplitude scale `2.0` and requires a finite response change greater than `max(1e-12, 1e-6 * max(abs(base_peak), abs(scaled_peak)))`.
- Source Model Bundle and source XLSX bytes must not be modified by preflight or solver execution.
- Do not add Artifact/Evidence state, semantic roles, cross-solver ranking, optimization, new ANSYS result quantities, multi-channel load support, or real-ANSYS GitHub runner infrastructure.

---

### Task 1: Add the fixed Golden Model and reusable input generator

**Files:**
- Create: `examples/ansys/golden_path/model.inp`
- Create: `examples/ansys/golden_path/run_golden_path.py`
- Test: `tests/python/test_ansys_golden_path.py`

**Interfaces:**
- Produces: `write_earthquake_xlsx(workspace: Path, *, amplitude_scale: float, name: str) -> Path`
- Produces: `standardize_golden_load(workspace: Path, xlsx_path: Path) -> dict[str, Any]`
- Produces checked-in APDL model with node 1 fixed, node 2 response, full transient solve, no `ACEL`, and no `TRNOPT,MSUP`.

- [x] **Step 1: Write a failing focused test for the checked-in model and XLSX standardization**

```python
from examples.ansys.golden_path.run_golden_path import (
    GOLDEN_MODEL_UNITS,
    standardize_golden_load,
    write_earthquake_xlsx,
)


def test_golden_inputs_start_as_xlsx_and_standardize_to_canonical(tmp_path: Path) -> None:
    source = write_earthquake_xlsx(tmp_path, amplitude_scale=1.0, name="earthquake-base.xlsx")
    before = source.read_bytes()
    report = standardize_golden_load(tmp_path, source)
    assert report["format"] == "FEMAGENT_LOAD_CSV_V1"
    assert report["source"]["format"] == "XLSX"
    assert report["loadKind"] == "EARTHQUAKE"
    assert report["channels"][0]["component"] == "X"
    assert report["channels"][0]["standardUnit"] == "m/s2"
    assert source.read_bytes() == before
    assert GOLDEN_MODEL_UNITS == {"modelUnits": {"length": "m", "time": "s"}}
```

- [x] **Step 2: Verify RED**

CI run #164 confirmed the new test was the only new failure because the Golden Path harness did not exist; the 88 pre-existing Python tests remained green.

- [x] **Step 3: Add the minimal APDL full-transient Golden Model**

Implemented the two-node `LINK180` oscillator with explicit full transient analysis, node 1 restraint, node 2 response, fixed time step, no source `ACEL`, and no `TRNOPT,MSUP`.

- [x] **Step 4: Implement deterministic XLSX generation and production standardization**

`write_earthquake_xlsx()` writes `time_s` / `accel_g` with 21 samples from 0.00 to 1.00 s at 0.05 s spacing. `standardize_golden_load()` calls existing `standardize_load()` with explicit `EARTHQUAKE / UNIFORM_EXCITATION / X / ACCELERATION / g` mapping.

- [x] **Step 5: Run focused test and Ruff**

Task 1 reached 89 passing Python tests; the only intermediate issue was Ruff import-block formatting, which was corrected without changing test semantics.

- [x] **Step 6: Commit Task 1**

Task 1 was committed on `feat/pr11-ansys-golden-path-v1` through the RED test, Golden Model/helper implementation, and formatting closure commits.

---

### Task 2: Add the mandatory deterministic CI Golden Path

**Files:**
- Modify: `examples/ansys/golden_path/run_golden_path.py`
- Modify: `tests/python/test_ansys_golden_path.py`

**Interfaces:**
- Consumes: `standardize_golden_load()` and existing ANSYS `preflight/run` APIs.
- Produces: `run_golden_once(workspace: Path, *, model_path: str, xlsx_path: Path, fixture_result_mode: bool = False) -> dict[str, Any]`.
- Produces structured keys: `standardizedLoad`, `preflight`, `run`, `resultInspection`, `resultQuery`, `evidenceMode`.

- [x] **Step 1: Write a failing end-to-end test with a strict fake MAPDL executable**

The fake executable parses `-i/-o/-j`, rejects requested solve commands in `build_only.inp`, requires `/INPUT,'femagent_load','mac'` in the staged real model, requires both generated load files, writes deterministic runtime output, and copies `ansys.mapdl.reader.examples.rstfile` to the normal job result path.

- [x] **Step 2: Verify RED**

CI run #168 confirmed 89 tests passed and the sole new failure was the missing `run_golden_once()` implementation.

- [x] **Step 3: Implement `run_golden_once()` by composing production APIs only**

The implementation calls production `standardize_load()`, ANSYS adapter `preflight()` / `run()`, production `inspect_result()`, and production `query_result()`; it adds no alternate solver runner or result parser.

Fixture mode discovers a queryable Cartesian displacement target from the valid packaged `.rst` and labels evidence `CI_FIXTURE_BACKED`. Real mode fixes node 2 / X and labels evidence `REAL_ANSYS`.

- [x] **Step 4: Assert staging/provenance details**

The end-to-end regression verifies generated load table/macro, staged APDL injection, canonical-load SHA linkage, binary-result SHA, execution/case fingerprints, and source model/XLSX byte preservation.

- [x] **Step 5: Run focused tests and Ruff**

CI run #169 passed Typecheck, TypeScript tests, Python tests, Ruff, OpenSees smoke, ANSYS result-reader smoke, and health.

- [x] **Step 6: Commit Task 2**

Task 2 RED and GREEN changes were committed to the PR11 branch.

---

### Task 3: Add opt-in real ANSYS causality verification and CLI

**Files:**
- Modify: `examples/ansys/golden_path/run_golden_path.py`
- Create: `examples/ansys/golden_path/README.md`
- Modify: `tests/python/test_ansys_golden_path.py`

**Interfaces:**
- Produces: `run_real_causality_check(workspace: Path, *, model_path: str) -> dict[str, Any]`.
- Produces CLI: `python examples/ansys/golden_path/run_golden_path.py --workspace <path>`.

- [x] **Step 1: Write failing unit tests for response-change comparison and runtime fail-closed behavior**

The contract tests fix the response-change threshold and require `GOLDEN_PATH_ANSYS_UNAVAILABLE` when `FEM_ANSYS_EXECUTABLE` is absent.

- [x] **Step 2: Verify RED**

CI run #170 confirmed 90 tests passed and only the two new real-causality contract tests failed because `response_changed()` and `run_real_causality_check()` did not yet exist.

- [x] **Step 3: Implement the two-run real causality check**

The harness generates distinct base and 2.0x XLSX records, runs both through `run_golden_once(..., fixture_result_mode=False)`, and requires finite/non-zero node-2 X-displacement peaks, changed execution/case fingerprints, and the approved deterministic response-change tolerance.

- [x] **Step 4: Add the CLI and README**

The README documents explicit `FEM_ANSYS_EXECUTABLE` configuration, declared `m/s` model units, fixed node-2 X response, and the distinction between CI interoperability evidence and real-ANSYS numerical causality evidence.

- [x] **Step 5: Run focused tests and CLI fail-closed smoke**

Task 3 GREEN CI #172 passed the full repository gates with 92 Python tests and the stable unavailable-runtime behavior covered by regression.

- [x] **Step 6: Commit Task 3**

Task 3 implementation and README were committed to the PR11 branch.

---

### Task 4: Documentation, regression gate, and PR closeout

**Files:**
- Create: `docs/verification/pr11-ansys-golden-path.md`
- Modify: `docs/architecture.md`
- Modify: `docs/solver-adapters.md`
- Modify: `.github/workflows/ci.yml`
- Modify: `docs/superpowers/plans/2026-09-04-ansys-golden-path-v1.md`

**Interfaces:**
- Records exact final-head CI evidence and the distinction between CI protocol evidence and real-ANSYS numerical evidence.

- [x] **Step 1: Run repository-wide CI-equivalent verification on the PR head**

CI run #175 on implementation/documentation head `1afeb771b70766f3ab3e9d189b0cffad0a7fbac9` passed:

```text
pnpm typecheck
pnpm test:ts                         # 12/12 PASS
python -m pytest                     # 92/92 PASS
python -m ruff check fem_core tests/python examples/ansys/golden_path
OpenSees adapter availability smoke
ANSYS result-reader import smoke
pnpm fem:health
```

- [x] **Step 2: Review the PR diff against safety/scope boundaries**

Final review found no source overwrite, no unit guessing, no fake numerical claim, no alternate solver/result runtime, no commercial ANSYS dependency in normal CI, and no PR11 scope creep.

- [x] **Step 3: Write `docs/verification/pr11-ansys-golden-path.md`**

The validation record documents exact CI counts, TDD evidence, fixture-backed versus real numerical evidence, and explicitly states that licensed real ANSYS was not executed by GitHub-hosted CI.

- [x] **Step 4: Update architecture/solver docs**

Architecture and solver-adapter documentation now include the PR11 end-to-end ladder and the opt-in real harness while preserving Result Intelligence's existing ANSYS result-unit semantics.

- [x] **Step 5: Mark this implementation plan complete and rerun CI on the exact final head**

This plan is now marked complete. A fresh full CI run on this documentation-closure head is the final technical gate before PR11 is marked Ready for review.

- [x] **Step 6: Update PR11 from Draft to Ready for review**

After the exact documentation-closure head passes full CI, PR11 will be converted from Draft to Ready for review using PR metadata only, so the verified head SHA does not change. The PR remains open and will not be merged without explicit user instruction.

Do not merge PR11 without explicit user instruction.
