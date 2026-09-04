# ANSYS Golden Path V1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

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

- [ ] **Step 1: Write a failing focused test for the checked-in model and XLSX standardization**

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

- [ ] **Step 2: Verify RED**

Run: `python -m pytest tests/python/test_ansys_golden_path.py::test_golden_inputs_start_as_xlsx_and_standardize_to_canonical -q`

Expected: import/file failure because the PR11 example harness does not exist yet.

- [ ] **Step 3: Add the minimal APDL full-transient Golden Model**

Use a two-node `LINK180` oscillator with deterministic SI-consistent values:

```apdl
/PREP7
ET,1,LINK180
MP,EX,1,10000
MP,DENS,1,100
SECTYPE,1,LINK
SECDATA,0.01
N,1,0,0,0
N,2,1,0,0
TYPE,1
MAT,1
SECNUM,1
E,1,2
D,1,ALL,0
D,2,UY,0
D,2,UZ,0
FINISH
/SOLU
ANTYPE,TRANS
TRNOPT,FULL
LUMPM,ON
AUTOTS,OFF
DELTIM,0.05
OUTRES,NSOL,ALL
TIME,1.0
SOLVE
FINISH
/EXIT,NOSAVE
```

- [ ] **Step 4: Implement deterministic XLSX generation and production standardization**

`write_earthquake_xlsx()` writes `time_s` / `accel_g` with 21 samples from 0.00 to 1.00 s at 0.05 s spacing and the base acceleration sequence:

```python
BASE_ACCEL_G = (
    0.00, 0.02, 0.04, 0.06, 0.08, 0.10, 0.08,
    0.06, 0.04, 0.02, 0.00, -0.02, -0.04, -0.06,
    -0.08, -0.10, -0.08, -0.06, -0.04, -0.02, 0.00,
)
```

`standardize_golden_load()` calls existing `standardize_load()` with explicit `EARTHQUAKE / UNIFORM_EXCITATION / X / ACCELERATION / g` mapping.

- [ ] **Step 5: Run focused test and Ruff**

Run:

```text
python -m pytest tests/python/test_ansys_golden_path.py::test_golden_inputs_start_as_xlsx_and_standardize_to_canonical -q
python -m ruff check examples/ansys/golden_path tests/python/test_ansys_golden_path.py
```

Expected: PASS.

- [ ] **Step 6: Commit Task 1**

Commit message: `feat(pr11): add ANSYS Golden Path inputs`

---

### Task 2: Add the mandatory deterministic CI Golden Path

**Files:**
- Modify: `examples/ansys/golden_path/run_golden_path.py`
- Modify: `tests/python/test_ansys_golden_path.py`

**Interfaces:**
- Consumes: `standardize_golden_load()` and existing ANSYS `preflight/run` APIs.
- Produces: `run_golden_once(workspace: Path, *, model_path: str, xlsx_path: Path, fixture_result_mode: bool = False) -> dict[str, Any]`.
- Produces structured keys: `standardizedLoad`, `preflight`, `run`, `resultInspection`, `resultQuery`, `evidenceMode`.

- [ ] **Step 1: Write a failing end-to-end test with a strict fake MAPDL executable**

The fake executable must parse `-i/-o/-j`, reject solution commands in `build_only.inp`, require `/INPUT,'femagent_load','mac'` in the real staged model, require both generated load files in its working directory, write deterministic runtime output, and copy `ansys.mapdl.reader.examples.rstfile` to `<jobname>.rst`.

The test then calls `run_golden_once(..., fixture_result_mode=True)` and asserts:

```python
assert result["preflight"]["status"] == "READY"
assert result["run"]["status"] == "COMPLETED"
assert result["run"]["injection"]["injected"] is True
assert len(result["run"]["executionInputFingerprint"]) == 64
assert len(result["run"]["caseFingerprint"]) == 64
assert result["resultInspection"]["integrity"]["status"] == "VALID"
assert result["resultQuery"]["quantity"] == "DISPLACEMENT"
assert result["evidenceMode"] == "CI_FIXTURE_BACKED"
```

Also snapshot source model/XLSX bytes before execution and assert they are unchanged.

- [ ] **Step 2: Verify RED**

Run: `python -m pytest tests/python/test_ansys_golden_path.py::test_ci_golden_path_reaches_result_intelligence_without_fake_numerical_claims -q`

Expected: failure because `run_golden_once()` is not implemented.

- [ ] **Step 3: Implement `run_golden_once()` by composing production APIs only**

Required flow:

```python
standardized = standardize_golden_load(workspace, xlsx_path)
adapter = get_solver_adapter("ansys")
preflight = adapter.preflight(
    workspace,
    model_path=model_path,
    load_path=standardized["output"]["path"],
    solver_options=GOLDEN_MODEL_UNITS,
)
if preflight["status"] != "READY":
    raise FemCoreError("GOLDEN_PATH_PREFLIGHT_BLOCKED", ...)
run = adapter.run(...same model/load/options...)
inspection = inspect_result(workspace, run["runId"])
```

For `fixture_result_mode=True`, open the recorded `.rst` with `ansys.mapdl.reader`, obtain the first node from `nodal_solution(0)`, choose the first Cartesian DOF exposed by `result_dof(0)`, and query production `query_result()` for `DISPLACEMENT/SUMMARY`. Label the returned summary `evidenceMode = "CI_FIXTURE_BACKED"`.

For the real path, query node 2 / X and label `evidenceMode = "REAL_ANSYS"`.

- [ ] **Step 4: Assert staging/provenance details**

The focused test must additionally verify:

```text
run.outputs.generatedLoadTable exists
run.outputs.generatedLoadMacro exists
staged model contains /INPUT,'femagent_load','mac'
run.load.sourceSha256 == standardized.output.sha256
run.outputs.binaryResultSha256 is 64 hex chars
```

- [ ] **Step 5: Run focused tests and Ruff**

Run:

```text
python -m pytest tests/python/test_ansys_golden_path.py -q
python -m ruff check examples/ansys/golden_path tests/python/test_ansys_golden_path.py
```

Expected: PASS.

- [ ] **Step 6: Commit Task 2**

Commit message: `test(pr11): prove ANSYS CI Golden Path end to end`

---

### Task 3: Add opt-in real ANSYS causality verification and CLI

**Files:**
- Modify: `examples/ansys/golden_path/run_golden_path.py`
- Create: `examples/ansys/golden_path/README.md`
- Modify: `tests/python/test_ansys_golden_path.py`

**Interfaces:**
- Produces: `run_real_causality_check(workspace: Path, *, model_path: str) -> dict[str, Any]`.
- Produces CLI: `python examples/ansys/golden_path/run_golden_path.py --workspace <path>`.

- [ ] **Step 1: Write failing unit tests for response-change comparison and runtime fail-closed behavior**

Test the exact threshold function:

```python
assert response_changed(1.0e-4, 2.0e-4) is True
assert response_changed(1.0e-4, 1.0e-4 + 1.0e-13) is False
```

Also clear `FEM_ANSYS_EXECUTABLE` and assert the real harness raises a stable `FemCoreError` rather than scanning for ANSYS.

- [ ] **Step 2: Verify RED**

Run the two new focused tests and confirm failure because the functions do not exist.

- [ ] **Step 3: Implement the two-run real causality check**

Generate distinct `earthquake-base.xlsx` and `earthquake-scale-2.xlsx`; run both through `run_golden_once(..., fixture_result_mode=False)`; compare:

```python
base_peak = float(base["resultQuery"]["summary"]["absolutePeak"])
scaled_peak = float(scaled["resultQuery"]["summary"]["absolutePeak"])
```

Require finite/non-zero base/scaled peaks, changed execution/case fingerprints, and `response_changed(base_peak, scaled_peak)`.

Return a structured `kind: "ansys_golden_path_causality"` report with both run IDs/fingerprints/peaks and `status: "PASSED"`.

- [ ] **Step 4: Add the CLI and README**

README must show Windows configuration without hard-coded personal paths:

```powershell
$env:FEM_ANSYS_EXECUTABLE="C:\path\to\ansys.exe"
python examples/ansys/golden_path/run_golden_path.py --workspace .
```

Document that the checked-in model uses explicit `m/s`, node 2 X displacement, and that only the real harness proves numerical causality.

- [ ] **Step 5: Run focused tests and CLI fail-closed smoke**

Run:

```text
python -m pytest tests/python/test_ansys_golden_path.py -q
python -m ruff check examples/ansys/golden_path tests/python/test_ansys_golden_path.py
```

Expected: PASS.

- [ ] **Step 6: Commit Task 3**

Commit message: `feat(pr11): add opt-in real ANSYS causality harness`

---

### Task 4: Documentation, regression gate, and PR closeout

**Files:**
- Create: `docs/verification/pr11-ansys-golden-path.md`
- Modify: `docs/architecture.md`
- Modify: `docs/solver-adapters.md`
- Modify: `docs/superpowers/plans/2026-09-04-ansys-golden-path-v1.md`

**Interfaces:**
- Records exact final-head CI evidence and the distinction between CI protocol evidence and real-ANSYS numerical evidence.

- [ ] **Step 1: Run repository-wide CI-equivalent verification on the PR head**

Required gates:

```text
pnpm typecheck
pnpm test:ts
python -m pytest
python -m ruff check fem_core tests/python examples/ansys/golden_path
OpenSees adapter availability smoke
ANSYS result-reader import smoke
pnpm fem:health
```

- [ ] **Step 2: Review the PR diff against safety/scope boundaries**

Confirm no source overwrite, no unit guessing, no fake numerical claim, no alternate solver/result runtime, no commercial ANSYS dependency in normal CI, and no PR11 scope creep.

- [ ] **Step 3: Write `docs/verification/pr11-ansys-golden-path.md`**

Record exact final test counts and explain:

```text
CI Golden Path = orchestration/provenance/result-reader interoperability evidence
Real ANSYS Golden Path = actual numerical causality evidence
```

If a real ANSYS run was not executed in GitHub Actions, state that explicitly rather than claiming it passed.

- [ ] **Step 4: Update architecture/solver docs**

Add the PR11 end-to-end ladder and instructions for the opt-in real harness; preserve Result Intelligence's existing unit semantics.

- [ ] **Step 5: Mark this implementation plan complete and rerun CI on the exact final head**

All checkboxes must reflect verified work. Do not mark the PR Ready for merge until the documentation-only final head also passes full CI.

- [ ] **Step 6: Update PR11 from Draft to Ready for review**

PR body must list implementation scope, final head SHA, test counts, known third-party warnings, and the fact that real ANSYS numerical execution remains opt-in unless independently executed with a licensed runtime.

Do not merge PR11 without explicit user instruction.
