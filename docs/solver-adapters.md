# Solver Adapters

FEMagent keeps solver execution behind a narrow deterministic `SolverAdapter` interface:

```text
status() -> runtime availability and declared capabilities
preflight(model_path, load_path?) -> compatibility/safety checks without requested solve
run(model_path, load_path?) -> real solver execution and structured run manifest
```

`load_path` is optional at the abstract interface because some solver-native model bundles own their load and analysis definition. Concrete adapters remain responsible for enforcing a load when their model contract requires one.

The Agent chooses when to use the tools. The adapter and solver determine engineering facts and numerical results.

## OpenSeesPy adapter

OpenSeesPy is the first real solver backend. The runtime dependency is optional (`pip install -e ".[opensees]"`) so future solver backends can remain modular. CI installs the OpenSees extra and runs real adapter smoke/analysis tests.

OpenSees execution is isolated from the JSON bridge in dedicated Python worker processes. Native solver output therefore cannot corrupt the `femagent.bridge/v1` stdout contract, and native failures can be converted into stable parent-process errors plus solver logs.

The adapter currently supports two model paths through the same generic `fem_solver_preflight` / `fem_solver_run` tool contract.

## Controlled JSON `ELASTIC_SDOF`

The original controlled model contract remains supported:

```text
kind: FEMAGENT_OPENSEES_MODEL_SPEC
schemaVersion: 1.0
modelType: ELASTIC_SDOF
units: m / N / kg / s
```

This path **requires** an external canonical `FEMAGENT_LOAD_CSV_V1` load. Omitting `loadPath` is rejected by the concrete OpenSees adapter even though the abstract SolverAdapter parameter is optional.

The accepted Golden Path load is one earthquake `UNIFORM_EXCITATION` acceleration channel in `m/s2`, with a supported X-direction alias and a strictly increasing uniform time axis. The transient solve uses the controlled OpenSees SDOF implementation and returns deterministic response artifacts including peak displacement evidence.

## OpenSees Python Model Bundle

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

### Dependency boundary

Resolved local modules and referenced data files must remain inside the active workspace. A dependency that escapes the workspace blocks the bundle. Bundle discovery does not install packages or fetch remote code.

The deterministic bundle identity records each included file SHA256 and a `bundleFingerprint`. Later provenance should use this fingerprint instead of treating the entrypoint hash as the complete model identity.

### Build-only inspection

Preflight executes model construction in an isolated OpenSees worker while intercepting `ops.analyze()`. This allows the adapter to observe the realized domain (for example node/element tags and coordinates) without advancing the requested analysis.

Static AST evidence and build-only solver-domain evidence remain separate; neither is a numerical response result.

### Script-managed loads

For a Python Model Bundle, `loadPath` may be omitted when the model script owns its load and analysis definition. Preflight reports this as `MODEL_SCRIPT_MANAGED`.

If an external `loadPath` is supplied to the current Python-bundle path, it is recorded for provenance but is **not injected** into the script; the adapter reports `injected: false`. The Agent must not claim that a provided file affected the solve unless the run contract says it was actually applied.

### Staged execution

Real Python-bundle execution never runs directly from the user's source tree. After successful preflight and execution permission, the adapter copies the resolved bundle into:

```text
.femagent/runs/<runId>/model_bundle/
```

The isolated worker executes the staged entrypoint. This preserves relative local-module/data references while giving the run a concrete, hashable input set.

The run manifest records the entrypoint SHA256, bundle fingerprint, per-file bundle hashes, solver package/engine version, case fingerprint, analysis/summary information, solver log, and staged bundle location. Artifact/Evidence registration can later build on these deterministic run precursors.

## Permission boundary

`fem_solver_status` and `fem_solver_preflight` are inspection operations. OpenSees Python preflight can execute model **construction** in its isolated build-only worker, but `ops.analyze()` is intercepted.

`fem_solver_run` is an EXECUTION action. The project Pi extension requires user approval before the real solver starts; modes without a usable confirmation path fail closed rather than silently executing.

## Adapter design rule

Future backends should extend the same status/preflight/run boundary instead of creating task-specific solver tools. Solver-specific requirements belong inside adapters; the agent-facing contract stays small and composable.
