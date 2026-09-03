# Solver Adapters

FEMagent keeps solver execution behind a narrow deterministic `SolverAdapter` interface:

```text
status() -> runtime availability
preflight() -> model/load compatibility without requested solve
run() -> real solver execution and structured run manifest
```

The Agent chooses when to use the tools. The adapter and solver determine engineering facts and numerical results.

## PR5 OpenSees V1

PR5 introduces the first real solver backend: OpenSeesPy.

The runtime dependency is optional (`pip install -e ".[opensees]"`) so future solver backends can remain modular. CI installs the OpenSees extra and executes a real transient Golden Path. OpenSeesPy 3.8.0.0 is pinned for this first integration baseline.

### Execution isolation

OpenSees executes in a dedicated Python worker process instead of importing the native solver into the JSON bridge process. This provides two important boundaries:

- native solver output such as OpenSees process messages cannot corrupt `femagent.bridge/v1` stdout JSON,
- native solver faults are converted into a stable parent-process error and solver log.

The parent bridge process writes the final structured envelope only after the worker result has been validated.

### Controlled model boundary

PR5 intentionally does not execute arbitrary user OpenSees Python files. The only accepted model contract is:

```text
kind: FEMAGENT_OPENSEES_MODEL_SPEC
schemaVersion: 1.0
modelType: ELASTIC_SDOF
units: m / N / kg / s
```

This is a Solver Runtime Golden Path, not the final OpenSees model-import story.

### Canonical load boundary

PR5 accepts one `FEMAGENT_LOAD_CSV_V1` channel with:

- load kind `EARTHQUAKE`,
- application type `UNIFORM_EXCITATION`,
- quantity `ACCELERATION`,
- unit `m/s2`,
- X/UX/U1/1 component for the one-degree-of-freedom model,
- a strictly increasing uniform time axis.

The actual transient analysis uses an OpenSees elastic zeroLength SDOF, mass-proportional damping corresponding to the requested damping ratio, `UniformExcitation`, Newton iteration, and Newmark average acceleration `(gamma=0.5, beta=0.25)`.

### Run outputs

Every successful run writes under `.femagent/runs/<runId>/`:

- `run_manifest.json`
- `response.csv`
- `result_summary.json`
- `solver.log`

The run manifest records the solver package/engine version, model SHA256, load SHA256, case fingerprint, analysis configuration, output SHA256 values, and the actual peak displacement summary returned by the worker.

Artifact/Evidence persistence remains a later PR. These files are the deterministic precursors.

## Permission boundary

`fem_solver_status` and `fem_solver_preflight` are read/inspection operations.

`fem_solver_run` is an EXECUTION action. A project Pi extension intercepts the tool call and requires an interactive/RPC user confirmation. In print/JSON modes where a confirmation UI is unavailable, the call is blocked rather than silently executed.

## Next expansion

Future adapters must implement the same status/preflight/run boundary. ANSYS, richer OpenSees model types, cancellation/job lifecycle, result queries, and Artifact/Evidence registration should extend this interface rather than creating task-specific solver tools.
