# PR11 Validation — ANSYS Golden Path V1

## Status

PR11 implementation is complete at the code/documentation level and is undergoing the final documentation-head CI rerun before the pull request is marked ready for review.

## What PR11 proves

PR11 composes the existing production layers into one reproducible ANSYS path:

```text
earthquake XLSX
  -> production Load Intelligence standardization
  -> FEMAGENT_LOAD_CSV_V1
  -> ANSYS preflight with explicit modelUnits
  -> staged canonical-load table/macro + APDL injection
  -> MAPDL process boundary
  -> run_manifest + recorded binary result
  -> production Result Intelligence integrity verification
  -> production nodal displacement query
```

No second solver runner or second result parser was introduced.

## Two evidence levels

### Mandatory CI Golden Path

GitHub-hosted CI has no licensed ANSYS installation. The CI acceptance path therefore uses a strict fake MAPDL **process executable**, while retaining production FEMagent orchestration.

The fake process:

- accepts the real adapter's `-i`, `-o`, and `-j` process contract;
- rejects requested solution commands in build-only input;
- requires the PR10 staged `/INPUT,'femagent_load','mac'` injection in the real-run staged model;
- requires `femagent_load_table.txt` and `femagent_load.mac` in the staged working directory;
- copies the valid `.rst` fixture packaged with `ansys-mapdl-reader` into the job's normal result location.

FEMagent then performs its normal run-manifest binary-result hashing and production `inspect_result()` / `query_result()` processing.

The resulting numerical values are intentionally labelled `CI_FIXTURE_BACKED`. They prove staging, provenance, artifact integrity, and result-reader interoperability. They are **not** claimed to be the numerical response of the checked-in Golden Model.

### Opt-in real ANSYS Golden Path

`examples/ansys/golden_path/run_golden_path.py` provides the real numerical acceptance harness. It requires `FEM_ANSYS_EXECUTABLE` to resolve explicitly to a real MAPDL executable and never scans the machine for ANSYS.

The real path fixes:

- declared model units: `m` / `s`;
- response target: node `2`, X displacement;
- base earthquake amplitude scale: `1.0`;
- comparison earthquake amplitude scale: `2.0`.

A real causality report passes only if:

- both MAPDL runs complete;
- both binary results are recorded and integrity-verified;
- both node-2 X-displacement peaks are finite and non-zero;
- `executionInputFingerprint` changes;
- `caseFingerprint` changes;
- the displacement absolute peak changes by more than:

```text
max(1e-12, 1e-6 * max(abs(base_peak), abs(scaled_peak)))
```

A licensed real ANSYS run was **not executed by GitHub-hosted CI for PR11**. Therefore this validation document does not claim that the real numerical causality check has passed on a licensed ANSYS installation. The harness and its fail-closed/runtime/threshold contracts are implemented and tested; actual real-ANSYS numerical acceptance is opt-in on a configured machine.

## TDD evidence

PR11 preserved explicit RED -> GREEN evidence for each implementation slice:

- Task 1 RED: the new XLSX/Golden Model test was the only new failure because the harness did not exist; 88 pre-existing Python tests remained green.
- Task 1 GREEN: the checked-in APDL model plus deterministic XLSX-to-canonical helpers brought the suite to 89 passing Python tests.
- Task 2 RED: the end-to-end contract failed only because `run_golden_once()` was absent.
- Task 2 GREEN: the production XLSX -> ANSYS adapter -> binary result -> Result Intelligence path passed.
- Task 3 RED: 90 tests passed and only the two new real-causality contract tests failed because `response_changed()` and `run_real_causality_check()` were absent.
- Task 3 GREEN: both functions, CLI, and documentation were implemented and the suite reached 92 passing Python tests.

The RED tests were not weakened to obtain GREEN.

## Regression acceptance matrix

| Requirement | Verification |
| --- | --- |
| Input starts as XLSX | Test creates a real XLSX first worksheet with `time_s` / `accel_g`. |
| Production Load Intelligence is used | Golden helper calls existing `standardize_load()` with explicit mapping. |
| Canonical output is real `FEMAGENT_LOAD_CSV_V1` | Standardization report format and SHA provenance are asserted. |
| Model units are explicit | Harness passes `{"modelUnits":{"length":"m","time":"s"}}`; no guessing path exists. |
| Build-only does not solve | Strict fake runtime rejects `/SOLU` / `SOLVE` in `build_only.inp`; preflight records `analysisAdvanced: false`. |
| Canonical load reaches staged APDL | Test requires generated table/macro and `/INPUT,'femagent_load','mac'` in the staged model. |
| Source inputs remain unchanged | Source model and source XLSX bytes are compared before/after the end-to-end run. |
| Run provenance is retained | Test asserts load SHA, injection evidence, `executionInputFingerprint`, `caseFingerprint`, binary path and binary SHA. |
| Production Result Intelligence is reached | End-to-end test calls production `inspect_result()` and `query_result()` against the actual run manifest. |
| Fake numerical claims are prohibited | CI result is explicitly `CI_FIXTURE_BACKED` with a warning note; no Golden Model numerical causality is claimed. |
| Real ANSYS is fail-closed when unavailable | Test removes `FEM_ANSYS_EXECUTABLE` and requires `GOLDEN_PATH_ANSYS_UNAVAILABLE`. |
| Real response causality has a fixed criterion | `response_changed()` tests the exact PR11 tolerance and the real harness requires 1x/2x fingerprint + response changes. |

## Repository gate evidence

GitHub Actions CI run **#175** validated implementation/documentation head `1afeb771b70766f3ab3e9d189b0cffad0a7fbac9` with the expanded PR11 lint scope:

```text
pnpm typecheck
pnpm test:ts
python -m pytest
python -m ruff check fem_core tests/python examples/ansys/golden_path
OpenSees adapter availability smoke
ANSYS result-reader import smoke
pnpm fem:health
```

Results:

- TypeScript typecheck: **PASS**
- TypeScript tests: **12/12 PASS**
- Python tests: **92/92 PASS**
- Ruff, including `examples/ansys/golden_path`: **PASS** (`All checks passed!`)
- OpenSees adapter availability smoke: **PASS**
- ANSYS result-reader import smoke: **PASS**
- FEM core health smoke: **PASS** (`status: ok`)

Python reported **66 warnings**, all from the existing third-party VTK/NumPy deprecation path exercised by ANSYS result reading. There were no test or lint failures.

After this verification/plan closure documentation is committed, the exact final PR head must receive a fresh full CI success before PR11 is marked Ready for review.

## Engineering diff review

The PR diff was reviewed against the approved PR11 boundaries:

- **Source overwrite:** none. The end-to-end test proves model/XLSX source bytes are unchanged; ANSYS injection remains staged-only through the PR10 adapter.
- **Unit guessing:** none. The Golden Path hard-declares the example's `m` / `s` model convention and forwards it through `solverOptions.modelUnits`.
- **Fake numerical claim:** none. CI fixture-backed values are explicitly separated from real solver causality evidence in code, tests, and documentation.
- **Alternate solver/result runtime:** none. The harness composes existing `standardize_load`, ANSYS adapter, `inspect_result`, and `query_result` APIs.
- **Commercial-runtime CI dependency:** none. Normal GitHub CI uses the fake process boundary; no licensed ANSYS or self-hosted runner is required.
- **Scope creep:** none. No Artifact/Evidence state machine, semantic-role resolution, cross-solver ranking, optimization runtime, new load modes, or new result quantities were added.
- **Result unit semantics:** unchanged. PR11 does not reinterpret solver-native ANSYS result units as SI merely because load-conversion units were declared.

## Final merge criterion

PR11 may be marked **Ready for review** only after the exact documentation-closure head passes the full repository CI gate. The pull request remains open for the user's merge decision; this validation step does not merge it.
