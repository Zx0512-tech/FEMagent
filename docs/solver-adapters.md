# Solver Adapters

FEMagent keeps solver execution behind a narrow deterministic `SolverAdapter` interface:

```text
status() -> runtime availability and declared capabilities
preflight(model_path, load_path?) -> compatibility/safety checks without requested solve
run(model_path, load_path?) -> real solver execution and structured run manifest
```

`load_path` is optional at the abstract interface because some solver-native model bundles own their load and analysis definition. Concrete adapters remain responsible for enforcing a load when their model contract requires one.

The Agent chooses when to use the tools. The adapter and solver determine engineering facts and numerical results. Result Intelligence reads recorded numerical artifacts after execution; it does not extend `SolverAdapter` into a query API.

## OpenSeesPy adapter

OpenSeesPy is a real solver backend. The runtime dependency is optional (`pip install -e ".[opensees]"`) so solver backends remain modular. CI installs the OpenSees extra and runs real adapter smoke/analysis tests.

OpenSees execution is isolated from the JSON bridge in dedicated Python worker processes. Native solver output therefore cannot corrupt the `femagent.bridge/v1` stdout contract, and native failures can be converted into stable parent-process errors plus solver logs.

The adapter supports two model paths through the same generic `fem_solver_preflight` / `fem_solver_run` tool contract.

### Controlled JSON `ELASTIC_SDOF`

The controlled model contract remains supported:

```text
kind: FEMAGENT_OPENSEES_MODEL_SPEC
schemaVersion: 1.0
modelType: ELASTIC_SDOF
units: m / N / kg / s
```

This path **requires** an external canonical `FEMAGENT_LOAD_CSV_V1` load. Omitting `loadPath` is rejected by the concrete OpenSees adapter even though the abstract SolverAdapter parameter is optional.

The accepted Golden Path load is one earthquake `UNIFORM_EXCITATION` acceleration channel in `m/s2`, with a supported X-direction alias and a strictly increasing uniform time axis. The transient solve uses the controlled OpenSees SDOF implementation and records `response.csv`/summary artifacts. Their controlled schema establishes SI response units and seconds, so PR9 Result Intelligence can query the recorded displacement, velocity, and acceleration deterministically.

### OpenSees Python Model Bundle

A `.py` entrypoint is treated as a Model Bundle rather than a trusted standalone script.

Before a real run:

```text
fem_model_inspect
    -> Python AST safety/model inspection
    -> workspace-local dependency discovery
    -> Model Bundle fingerprint
    -> fem_solver_preflight
    -> isolated build-only inspection
    -> READY/BLOCKED
```

Resolved local modules and referenced data files must remain inside the active workspace. Bundle discovery does not install packages or fetch remote code.

Preflight executes model construction in an isolated OpenSees worker while intercepting `ops.analyze()`. This allows realized solver-domain evidence to be observed without advancing the requested analysis.

For a Python Model Bundle, `loadPath` may be omitted when the model script owns its load and analysis definition. If an external `loadPath` is supplied to the current Python-bundle path, it is recorded for provenance but is **not injected** into the script.

Real execution stages the resolved bundle under:

```text
.femagent/runs/<runId>/model_bundle/
```

and executes the staged entrypoint rather than the user's original source tree.

Arbitrary OpenSees Python scripts do not automatically receive a FEMagent standard recorder. If a run did not produce the controlled response schema, Result Intelligence reports `LIMITED` rather than inventing a response channel.

## ANSYS MAPDL adapter

ANSYS MAPDL is FEMagent's second real SolverAdapter while preserving the same generic tool surface.

### Runtime discovery

ANSYS runtime configuration is explicit:

```text
FEM_ANSYS_EXECUTABLE=/path/to/ansys/mapdl/executable
```

The adapter does not scan the machine or hard-code installation paths. `fem_solver_status` returns structured availability/configuration evidence and fails closed when the configured path is missing or invalid.

### ANSYS Model Bundle

Supported model/script member suffixes are:

```text
.cdb .inp .apdl .mac .dat .txt
```

TXT/DAT entrypoints require deterministic APDL/CDB content signals before they are treated as models. `/INPUT` and `*USE` references are recursively resolved inside the workspace and included in the bundle fingerprint.

Missing dependencies, workspace escapes, and unsupported absolute includes block preflight.

### Build-only preflight

`fem_solver_preflight` with `solver: ansys` performs:

```text
static APDL safety
+ Model Bundle integrity
+ runtime availability
+ staged sanitized build-only MAPDL run
```

The build-only staged copy stops before `/SOLU`, `SOLVE`, or postprocessing. The user's source files are never rewritten.

A successful build-only inspection is required for preflight `READY`.

### Script-managed loads

The current ANSYS adapter does not inject arbitrary canonical load files into APDL. The ANSYS Model Bundle owns its load and analysis commands.

When `loadPath` is provided, its path and SHA256 are recorded for provenance and the preflight/run contract reports `injected: false`. The Agent must not claim that such a file affected the solve.

### Staged real execution

After preflight `READY` and execution permission, `fem_solver_run` copies the complete resolved ANSYS bundle into:

```text
.femagent/runs/<runId>/model_bundle/
```

MAPDL runs with the staged bundle working directory as its CWD so relative `/INPUT` behavior remains inside the staged provenance boundary.

The run manifest records:

- `runId`,
- `caseFingerprint`,
- entrypoint SHA256,
- `bundleFingerprint`,
- per-file bundle hashes,
- configured runtime identity,
- staged bundle root,
- MAPDL output,
- solver log and hashes,
- the staged job's `.rst`, `.rth`, `.rfl`, or `.rmg` path/SHA when such a binary result exists.

### Result boundary

`COMPLETED` means the configured MAPDL process returned successfully and execution artifacts were captured. Numerical engineering claims still require Result Intelligence.

PR9 reads a recorded MAPDL binary result through the optional extra:

```text
pip install -e ".[ansys-results]"
```

which currently pins `ansys-mapdl-reader==0.56.0`. V1 can query nodal displacement, velocity, acceleration, and reaction force when those result records exist.

MAPDL's model unit system is not inferred from the binary result. Result Intelligence therefore returns `unit: null` for ANSYS physical quantities unless separate deterministic model/project evidence establishes units. Result-set abscissa values likewise remain `SOLVER_NATIVE_RESULT_ABSCISSA` with an unknown unit instead of being silently labelled seconds.

If no binary result was recorded, the run remains inspectable but numerical result integrity is `LIMITED`. FEMagent does not parse `ansys.out` or `solver.log` into numerical response truth.

## Permission boundary

`fem_solver_status` and `fem_solver_preflight` are inspection operations. Solver-specific preflight may perform controlled build-only model construction, but it must not intentionally advance the requested analysis.

`fem_solver_run` is an EXECUTION action. The Pi extension requires user approval before the real solver starts; modes without a usable confirmation path fail closed rather than silently executing.

`fem_result_inspect` and `fem_result_query` are SAFE read-only operations over recorded run artifacts. They do not need execution permission because they never invoke a solver or rewrite source models.

## Adapter design rule

Future backends should extend the same status/preflight/run boundary instead of creating task-specific solver tools. Solver-specific execution requirements belong inside adapters; solver-specific result decoding belongs behind Result Intelligence. The agent-facing contract stays small and composable.
