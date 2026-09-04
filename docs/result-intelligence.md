# Result Intelligence V1

Result Intelligence is FEMagent's read-only numerical result facts layer. It sits after solver execution and before later Artifact/Evidence and cross-solver reasoning.

```text
solver run
  -> run_manifest.json
  -> recorded numerical artifacts
  -> artifact path/SHA verification
  -> solver-specific deterministic reader
  -> ResultManifest
  -> ResultQuery
```

It never invokes a solver and never treats solver logs as numerical response truth.

## Agent-facing tools

### `fem_result_inspect`

Accepts a `run_<id>`, workspace-relative run directory, or `run_manifest.json` path.

It verifies the completed `solver_run` manifest and declared result artifact hashes, then returns:

- run/case identity;
- solver identity;
- `VALID` or `LIMITED` result integrity status;
- verified result artifacts;
- solver-native abscissa metadata;
- deterministic query capabilities;
- recorded run observations;
- warnings about missing result channels or unproven semantics.

A declared SHA mismatch is rejected rather than downgraded into usable data.

### `fem_result_query`

V1 supports one nodal quantity/component at a time:

```json
{
  "runRef": "run_...",
  "quantity": "DISPLACEMENT",
  "target": {"type": "NODE", "id": 2},
  "component": "UX",
  "operation": "SUMMARY"
}
```

Supported quantity names are:

- `DISPLACEMENT`
- `VELOCITY`
- `ACCELERATION`
- `REACTION_FORCE` when present in the solver artifact

Cartesian component aliases include `X/UX/U1/1`, `Y/UY/U2/2`, and `Z/UZ/U3/3`.

`SUMMARY` returns sample count, min, max, absolute peak and the recorded abscissa at the absolute peak. `SERIES` returns a bounded slice with offset/limit metadata. V1 limits one series response to 5000 samples.

## OpenSees result semantics

### Controlled response path

The controlled OpenSees analysis writes FEMagent's standard `response.csv` schema:

```text
time_s
relative_displacement_m
relative_velocity_m_s
relative_acceleration_m_s2
```

This schema itself proves the units, so Result Intelligence may report seconds, metres, metres per second, and metres per second squared.

The V1 controlled path exposes only the response node/DOF recorded by the solver adapter. Querying another node or an unrecorded quantity fails with `RESULT_SERIES_UNAVAILABLE`.

### Arbitrary OpenSees Python bundles

A generic OpenSees Python Model Bundle can own arbitrary recorders. PR9 does not inject or infer a recorder contract into those scripts.

If no FEMagent standard response series exists, inspection returns `LIMITED` with no invented query capability. Existing domain/run observations can still be reported, but they are not substituted for a numerical response series.

## ANSYS MAPDL result semantics

### Binary result provenance

When a staged ANSYS run produces the job's `.rst`, `.rth`, `.rfl`, or `.rmg` file, the solver run manifest records the workspace-relative path and SHA256.

If no binary result file is recorded, Result Intelligence returns `LIMITED` with `ANSYS_BINARY_RESULT_NOT_RECORDED`. It does not parse `ansys.out` into displacements, forces, or convergence facts.

### Binary reader

ANSYS numerical result access uses the optional dependency:

```text
pip install -e ".[ansys-results]"
```

which currently pins `ansys-mapdl-reader==0.56.0`.

The V1 reader opens MAPDL binary results with `read_binary(..., parse_vtk=False)` and supports nodal:

- displacement;
- velocity when present;
- acceleration when present;
- reaction force when present.

### Units and abscissa

MAPDL models are unit-consistent rather than globally SI by definition. A binary value therefore does not prove its physical unit.

PR9 reports ANSYS physical result `unit: null` unless a future deterministic model/project unit contract establishes one. Likewise, MAPDL result-set abscissa values are exposed as `SOLVER_NATIVE_RESULT_ABSCISSA` with `unit: null`; they are not automatically called seconds.

## Integrity and trust rules

Result Intelligence follows these rules:

1. all run/artifact paths remain inside the active workspace;
2. every declared result SHA256 is verified before use;
3. malformed or non-completed run manifests are rejected;
4. OpenSees standard response schema and numeric/time values are validated;
5. unreadable ANSYS binary results fail with stable errors;
6. logs are provenance/diagnostic artifacts, not numerical result channels;
7. an unavailable channel is never replaced with an LLM estimate;
8. `LIMITED` means insufficient standardized numerical evidence, not zero response.

## Engineering semantic boundary

Result Intelligence answers deterministic questions such as:

> What is the recorded X displacement history at node 36?

It does not prove that node 36 is a tower base, girder end, bearing, or damper location. Engineering-role-to-ID resolution belongs to model/project intelligence and must be established before querying a role-specific result.

## Non-goals of V1

- element stress/generalized element-force queries;
- automatic recorder injection into arbitrary OpenSees scripts;
- Artifact/Evidence state machine;
- cross-solver result alignment or correctness ranking;
- engineering semantic role resolution;
- plots/dashboard UI;
- solver execution or reruns.
