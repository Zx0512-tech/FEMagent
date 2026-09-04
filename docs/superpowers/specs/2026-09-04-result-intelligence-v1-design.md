# Result Intelligence V1 Design

## Goal

Add a solver-neutral result facts layer that can inspect completed FEMagent runs and answer deterministic result queries without rerunning a solver.

## Architectural position

```text
Solver Run
  -> run_manifest.json + solver-native result artifacts
  -> Result Intelligence
       -> ResultManifest
       -> deterministic ResultQuery
  -> later Artifact/Evidence / Cross-Solver Validation
```

Result Intelligence never decides whether one solver is more trustworthy than another. It reports what a recorded run and its result artifacts contain.

## Agent-facing tools

Keep the tool surface small:

- `fem_result_inspect(runRef)` — validate a completed run and enumerate result capabilities/facts.
- `fem_result_query(runRef, query)` — answer one deterministic result query from recorded artifacts.

Both are SAFE read operations. They do not invoke a solver and do not modify source models.

`runRef` accepts either a workspace-relative run directory / manifest path or a `run_<id>` under `.femagent/runs/`.

## ResultManifest

`fem_result_inspect` returns a normalized document containing:

- `schemaVersion`, `kind`, `runId`, `caseFingerprint`, solver identity;
- manifest/result artifact integrity checks;
- source artifacts and their declared/actual SHA256;
- solver-native abscissa metadata;
- available deterministic query quantities/components;
- run summary/observations already emitted by the solver adapter;
- warnings when numerical result channels are unavailable or units/axis semantics cannot be proven.

Integrity states are `VALID`, `LIMITED`, or `INVALID`. A hash mismatch is invalid evidence and is rejected. A completed run with no standardized numerical series can be `LIMITED` rather than fabricated into a result.

## Query contract

V1 queries are nodal series queries:

```json
{
  "quantity": "DISPLACEMENT | VELOCITY | ACCELERATION | REACTION_FORCE",
  "target": {"type": "NODE", "id": 101},
  "component": "X | Y | Z | UX | UY | UZ | ...",
  "operation": "SUMMARY | SERIES",
  "offset": 0,
  "limit": 500
}
```

The numeric node ID above is only an interface example; it carries no built-in engineering-role meaning.

`SUMMARY` returns sample count, min, max, absolute peak, and abscissa at the absolute peak. `SERIES` returns a bounded slice. The maximum V1 series return is 5000 samples.

The response must identify source artifact, target, component, quantity, reference frame, unit when proven, and abscissa semantics.

## OpenSees support

### Controlled ELASTIC_SDOF path

Consume the already generated `response.csv` and `result_summary.json`. Supported quantities are relative displacement, relative velocity, and relative acceleration at the recorded response node/DOF.

The source schema proves SI units and time seconds, so Result Intelligence may report `m`, `m/s`, `m/s2`, and `s`.

### Arbitrary OpenSees Python Model Bundle

PR6 script-run currently records domain summary but does not impose a standard response recorder contract. Result Intelligence must expose those run observations but return no invented response series. Querying an unavailable series fails with a stable `RESULT_SERIES_UNAVAILABLE` code.

A future recorder API can extend this without changing the Result Intelligence tool surface.

## ANSYS support

### Binary result provenance

PR9 extends `AnsysAdapter.run` to record a generated MAPDL binary result file (`.rst`, `.rth`, `.rfl`, or `.rmg`) when one exists for the staged job name, including workspace-relative path and SHA256.

### Reader

Use optional `ansys-mapdl-reader==0.56.0`, which supports Python 3.13 and reads MAPDL binary result files without parsing console text.

V1 supports:

- nodal displacement (`NSL`),
- nodal velocity (`VEL`) when present,
- nodal acceleration (`ACC`) when present,
- nodal reaction force by iterating recorded result sets.

The reader exposes result-set values and DOF labels. FEMagent must not assume those values are seconds or that MAPDL model units are SI unless project evidence declares that elsewhere. Therefore ANSYS V1 reports solver-native abscissa and `unit: null` for physical result quantities by default, plus explicit warnings.

If a completed ANSYS run has no recorded binary result file, inspection returns `LIMITED` with `ANSYS_BINARY_RESULT_NOT_RECORDED`; it does not parse `ansys.out` into numerical truth.

## Integrity rules

- Resolve all referenced artifacts inside the active workspace.
- Verify every declared SHA256 before using an artifact.
- Reject malformed `solver_run` manifests.
- Reject unsupported/tampered OpenSees response CSV schemas.
- Reject invalid/unreadable ANSYS binary result files with stable errors.
- Do not treat solver logs as response results.

## Migration boundary

Reuse from momoagent only the concepts of standardized timeseries/summary and solver postprocessing. Do not migrate STbridge-specific node IDs, tower-base maps, damper objective names, optimization coupling, Platform Store, or workflow/task machinery.

## Non-goals for PR9

- Artifact/Evidence state machine.
- Cross-solver alignment or correctness ranking.
- Engineering semantic role resolution (e.g. “tower base” -> node set).
- ANSYS stress/element-force generalized queries.
- OpenSees arbitrary-script automatic recorder injection.
- Plot/UI/dashboard generation.
