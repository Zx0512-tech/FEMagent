# PR11 — ANSYS Golden Path V1 Design

## Goal

Prove and package FEMagent's first complete ANSYS end-to-end Golden Path:

```text
ANSYS Model Bundle
+ earthquake XLSX
+ explicit solverOptions.modelUnits
        ↓
Load Intelligence
        ↓
FEMAGENT_LOAD_CSV_V1
        ↓
ANSYS preflight
        ↓
staged canonical-load injection
        ↓
MAPDL execution
        ↓
run_manifest + recorded binary result
        ↓
Result Intelligence
        ↓
fem_result_inspect / fem_result_query
        ↓
verified nodal response
```

PR11 does not add another solver capability layer. It composes the Model, Load, ANSYS Solver, and Result Intelligence capabilities completed through PR10 into one reproducible acceptance path.

## Background

PR10 completed deterministic ANSYS canonical earthquake application:

- one `EARTHQUAKE + UNIFORM_EXCITATION + ACCELERATION` channel;
- explicit `solverOptions.modelUnits`;
- deterministic model-unit conversion;
- deterministic APDL table/macro generation;
- staged-only load injection;
- execution provenance and fingerprints.

Result Intelligence already verifies ANSYS binary-result hashes and reads supported nodal result channels through `ansys-mapdl-reader`.

The remaining gap is system-level proof that a user-facing load source can travel through standardization, solver execution, recorded-result provenance, result inspection, and result query without bypassing those production boundaries.

## Design decision: two-layer Golden Path

PR11 uses two complementary layers.

### Layer A — deterministic CI Golden Path

The required GitHub CI path uses a fake MAPDL process executable but all FEMagent orchestration remains production code.

The fake executable must:

1. accept the same `-i`, `-o`, and `-j` command-line boundary used by the ANSYS adapter;
2. inspect the staged production input rather than the source Model Bundle;
3. fail if the expected PR10 canonical-load injection is absent;
4. fail if build-only input contains requested solve commands;
5. emit deterministic runtime output;
6. copy a valid packaged ANSYS `.rst` fixture from the installed `ansys-mapdl-reader` dependency into the expected job result path.

The copied `.rst` is a parser/integrity fixture, not a numerical solution of the Golden Model. CI therefore proves orchestration, staging, provenance, artifact integrity, and Result Intelligence interoperability. It must not claim that CI fake-runtime numbers are physically caused by the supplied earthquake.

The CI test may discover one queryable node/component from the valid `.rst` fixture and then exercise the production `inspect_result()` and `query_result()` APIs on the actual run manifest produced by `AnsysAdapter.run()`.

### Layer B — opt-in real ANSYS Golden Path

A separate integration harness runs the same Golden Model and earthquake input through a real configured MAPDL executable from `FEM_ANSYS_EXECUTABLE`.

This layer is the numerical execution acceptance path. It is intentionally opt-in because GitHub-hosted CI does not provide a licensed commercial ANSYS installation.

The real integration path must use production Load Intelligence, ANSYS adapter, run manifest, and Result Intelligence APIs. It must not contain an alternate solver runner or alternate result parser.

## Alternatives considered

### 1. Require real ANSYS in ordinary CI

Rejected. This would couple every repository PR to ANSYS licensing, host configuration, and Windows/runtime availability.

### 2. Mock Result Intelligence in CI

Rejected. It would leave the most important solver-to-result contract untested. PR11 should exercise production result-manifest validation and production ANSYS result reading.

### 3. Commit a handcrafted binary Golden `.rst`

Not preferred. `ansys-mapdl-reader` already installs a valid packaged result fixture used by existing tests. Reusing that dependency fixture avoids adding a large opaque binary to the FEMagent repository. The real ANSYS path remains responsible for numerical Golden Model validation.

## Golden Model

PR11 adds a small deterministic APDL full-transient structural example under:

```text
examples/ansys/golden_path/
```

The model should be intentionally minimal: one restrained reference node, one response node, a linear spring and concentrated mass, full transient analysis, fixed time stepping, and result output sufficient for nodal displacement queries.

Required properties:

- explicit `ANTYPE,TRANS`;
- full-transient behavior compatible with PR10 injection;
- no existing `ACEL` command;
- no `TRNOPT,MSUP`;
- at least one real `SOLVE` command;
- output controls sufficient for a binary result with nodal displacement history;
- no external include or dependency that is unnecessary to prove the path.

The reference model uses a declared `m` / `s` unit convention for the Golden Path. FEMagent still does not infer this from model magnitudes; the integration request must explicitly pass:

```json
{
  "modelUnits": {
    "length": "m",
    "time": "s"
  }
}
```

## Golden earthquake input

The acceptance input starts as XLSX, not canonical CSV.

A deterministic fixture generator writes a first worksheet containing:

```text
time_s | accel_g
```

with a short, finite, strictly increasing, uniformly sampled record. The explicit standardization mapping is:

```json
{
  "loadKind": "EARTHQUAKE",
  "timeColumn": "time_s",
  "timeUnit": "s",
  "valueColumn": "accel_g",
  "applicationType": "UNIFORM_EXCITATION",
  "targetType": "",
  "targetId": "",
  "component": "X",
  "quantity": "ACCELERATION",
  "sourceUnit": "g",
  "scale": 1.0
}
```

The Golden Path must call `standardize_load()` and consume the generated `FEMAGENT_LOAD_CSV_V1` output. Tests must not bypass Load Intelligence by writing the canonical CSV directly.

## Reusable validation harness

PR11 adds a small example/verification harness that composes existing production APIs. Its responsibility is orchestration for the example only, not a new runtime abstraction.

The harness performs:

1. ensure the source XLSX exists or generate the deterministic fixture;
2. call `standardize_load()`;
3. call ANSYS `preflight()` with canonical `load_path` and explicit model units;
4. require `READY` before execution;
5. call ANSYS `run()` with the same canonical load and solver options;
6. require `COMPLETED` and a recorded binary result;
7. call `inspect_result()` on the returned `runId`;
8. choose or accept a concrete queryable nodal displacement target;
9. call `query_result()` with `SUMMARY` and optionally `SERIES`;
10. emit one structured JSON summary of the end-to-end evidence.

The harness must never guess ANSYS installation paths or model units.

## CI Golden Path acceptance

A new focused Python test must prove the complete deterministic flow from XLSX to Result Intelligence.

The test must assert at least:

- XLSX is standardized through production `standardize_load()`;
- canonical output has `FEMAGENT_LOAD_CSV_V1` semantics and SHA256 provenance;
- ANSYS preflight is `READY`;
- build-only does not execute the requested solve;
- real-run staging contains `femagent_load_table.txt` and `femagent_load.mac`;
- staged APDL contains the PR10 `/INPUT,'femagent_load','mac'` hook;
- source Model Bundle bytes are unchanged;
- source XLSX bytes are unchanged;
- run status is `COMPLETED`;
- run manifest contains canonical load identity, injection evidence, `executionInputFingerprint`, and `caseFingerprint`;
- a binary result path and SHA256 are recorded;
- `inspect_result()` returns ANSYS result evidence with valid artifact integrity;
- `query_result()` returns a deterministic nodal displacement query result from the recorded binary artifact;
- the queried result is explicitly treated as fixture-backed CI evidence, not as Golden Model numerical truth.

## Real ANSYS acceptance

The opt-in real integration harness is successful only when:

- `FEM_ANSYS_EXECUTABLE` resolves to an executable file;
- preflight is `READY`;
- MAPDL returns success;
- a fresh binary result is recorded by the run manifest;
- Result Intelligence verifies the result hash;
- the Golden response node exposes X displacement;
- the query contains at least two result samples for the transient analysis;
- the absolute peak displacement is finite and non-zero;
- changing the earthquake amplitude in a second run changes the `executionInputFingerprint` and `caseFingerprint`;
- for the real solver path, the changed earthquake also changes the queried displacement response beyond a small deterministic tolerance chosen in the implementation plan.

The exact numerical peak value is not frozen in PR11 because solver-version/platform differences may affect floating-point details. PR11 freezes engineering invariants and causality instead of one brittle decimal answer.

## CI and workflow strategy

The existing Linux CI remains mandatory and continues to run:

```text
pnpm typecheck
pnpm test:ts
python -m pytest
python -m ruff check fem_core tests/python
OpenSees smoke
ANSYS result-reader smoke
health smoke
```

The new deterministic Golden Path test is part of `python -m pytest`, so it is mandatory on every PR.

PR11 may add an opt-in real-ANSYS integration entry point, but it must not make the normal GitHub-hosted CI depend on ANSYS licensing or installation.

If a GitHub Actions real-ANSYS workflow is added, it must be manually triggered or self-hosted and fail closed when runtime configuration is absent; absence of that commercial environment must not make normal CI red.

## Result and unit semantics

PR11 does not redesign Result Intelligence.

Even though the Golden Model's integration request explicitly declares `m` and `s` for load conversion, PR11 does not silently upgrade all ANSYS binary result units unless the existing Result Intelligence contract already propagates deterministic unit evidence for that result path.

A result value with `unit: null` remains acceptable where the current Result Intelligence contract says the binary result unit system is unproven. PR11 tests end-to-end evidence flow, not an unrelated result-unit redesign.

## Failure behavior

The Golden Path fails closed when:

- XLSX standardization mapping is invalid;
- canonical load is malformed;
- model units are missing/unsupported;
- ANSYS runtime is unavailable;
- transient injection hook is unsupported or ambiguous;
- build-only inspection fails;
- solver execution fails;
- binary result is not recorded;
- declared binary result hash does not match the file;
- requested nodal result channel is unavailable.

No failure may fall back to invented result values or solver-log-derived numerical claims.

## Scope boundaries

PR11 explicitly excludes:

- Artifact/Evidence state machine;
- engineering semantic roles such as tower-base/bearing resolution;
- cross-solver comparison/ranking;
- optimization runtime;
- multi-channel earthquake application;
- nodal-force matrices;
- response spectrum;
- rotational excitation;
- new ANSYS result quantities beyond the existing Result Intelligence contract;
- automatic ANSYS installation discovery;
- a second solver execution abstraction.

## Files expected to change

Likely additions/modifications are intentionally narrow:

```text
examples/ansys/golden_path/model.inp
examples/ansys/golden_path/README.md
examples/ansys/golden_path/run_golden_path.py
tests/python/test_ansys_golden_path.py
docs/verification/pr11-ansys-golden-path.md
.github/workflows/...                 # only if an opt-in real-ANSYS workflow is justified
```

Existing production modules should only change when the end-to-end test exposes a genuine missing contract. PR11 should prefer composition over refactoring.

## Completion criteria

PR11 is complete when:

1. the mandatory deterministic CI Golden Path runs from generated XLSX through production Load Intelligence, ANSYS adapter, run provenance, production Result Intelligence inspection, and production result query;
2. the real-ANSYS example/harness can run the same path with `FEM_ANSYS_EXECUTABLE` and explicit model units;
3. documentation clearly distinguishes fake-runtime protocol evidence from real-ANSYS numerical evidence;
4. all existing repository gates remain green;
5. final diff review confirms no source overwrite, no unit guessing, no fake numerical claim, no commercial-runtime hard dependency in normal CI, and no PR11 scope creep.
