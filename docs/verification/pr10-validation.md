# PR10 Validation — ANSYS Canonical Load Application V1

## Status

PR10 implementation and regression coverage are complete on the feature branch. This document records the verification evidence used to mark the pull request ready for human merge review.

## Implemented acceptance scope

PR10 closes the first ANSYS external canonical-load application path:

- `FEMAGENT_LOAD_CSV_V1` single-channel `EARTHQUAKE + UNIFORM_EXCITATION + ACCELERATION` validation;
- explicit ANSYS `solverOptions.modelUnits` (`m|cm|mm` and `s|ms`) with no unit guessing;
- deterministic canonical-to-model-unit conversion;
- deterministic `femagent_load_table.txt` and `femagent_load.mac` generation;
- fail-closed full-transient hook/conflict inspection;
- build-only validation that does not intentionally advance the requested solve;
- staged-only real APDL injection, never source-model rewriting;
- run provenance containing load identity, model-unit mapping, generated artifact hashes, injection evidence, `executionInputFingerprint`, and `caseFingerprint`;
- Python bridge, TypeScript bridge/types, Pi TypeBox schema, Skills, and architecture documentation;
- OpenSees fail-closed behavior for ANSYS-specific `solverOptions.modelUnits`.

## Regression acceptance matrix

| Requirement | Verification |
| --- | --- |
| Legacy ANSYS workflow without external load is preserved | No-load preflight/run remains `MODEL_SCRIPT_MANAGED`; canonical-injection check is absent. |
| Missing ANSYS model units fail closed | Canonical preflight is `BLOCKED` with `ANSYS_MODEL_UNITS_REQUIRED`. |
| XLSX → canonical CSV → ANSYS macro → staged APDL is traceable | Regression creates XLSX, standardizes to `FEMAGENT_LOAD_CSV_V1`, generates the macro/table, and verifies staged `/INPUT,'femagent_load','mac'`. |
| Source model/load remain unchanged | Real-run regression compares source bytes before/after staged execution. |
| Build-only does not execute the requested solve | Sanitized build path removes/stops before solution commands and records `analysisAdvanced: false`. |
| Real run records injection evidence | Manifest asserts `injected: true`, hook path/line, macro/table SHA256, generated output paths, and execution identity. |
| Earthquake input changes execution identity | Direct regression proves both `executionInputFingerprint` and `caseFingerprint` change. |
| Model Bundle changes execution identity | Direct regression proves `bundleFingerprint`, `executionInputFingerprint`, and `caseFingerprint` change. |
| Generated artifact changes execution identity | Changing declared model length unit changes generated table SHA256 and execution/case fingerprints. |
| OpenSees does not consume ANSYS modelUnits | Bridge regression returns `UNSUPPORTED_SOLVER_OPTIONS` for non-empty ANSYS-specific options. |

## CI-equivalent gate

GitHub Actions workflow `Engineering tool bridge` executes the repository-native final gates:

```text
pnpm typecheck
pnpm test:ts
python -m pytest
python -m ruff check fem_core tests/python
OpenSees adapter availability smoke
ANSYS result reader import smoke
pnpm fem:health
```

Verified code-head evidence before this documentation-only closure commit:

- TypeScript typecheck: PASS
- TypeScript tests: **12/12 PASS**
- Python tests: **88/88 PASS**
- Python lint: **PASS** (`All checks passed!`)
- OpenSees adapter availability smoke: PASS
- ANSYS result-reader import smoke: PASS
- FEM core health smoke: PASS (`status: ok`)

Python reported 42 warnings from the third-party VTK/NumPy compatibility layer used by result-reader tests. They are deprecation warnings, not test or lint failures.

## Engineering diff review

The PR diff was reviewed against the PR10 safety boundaries:

- **Source overwrite:** none. Real injection occurs only after Model Bundle staging; injection path checks remain confined to the staging root.
- **Unit guessing:** none. Canonical ANSYS application requires explicit supported model length/time units.
- **Sign inversion:** none. Canonical support/reference-frame acceleration maps directly to `ACEL`; the sign convention is recorded in provenance.
- **Read-only/requested-solve boundary:** preflight uses sanitized build-only staging and does not intentionally advance the requested analysis.
- **Scope creep:** no Evidence state machine, ANSYS multi-channel application, nodal-force matrix application, response spectrum, or mode-superposition load-vector support was added.
- **Result truth:** solver process completion remains distinct from numerical result truth; Result Intelligence retains responsibility for recorded-result interpretation.

## Final merge criterion

After this documentation closure commit, the PR must receive a fresh full CI success on its exact final head. Only then should PR10 be labeled **Ready for merge**. The PR remains open for human merge decision.
