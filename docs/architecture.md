# FEMagent Architecture

## Purpose

FEMagent is an Engineering Agent Runtime, not a finite-element solver.

It combines an agent runtime with deterministic engineering tools so an LLM can decide what to inspect or execute while finite-element solvers remain the authority for numerical results.

## Responsibility split

```text
                     FEMagent
                        |
                 Pi Agent Runtime
                        |
              Engineering Tools
                        |
          TypeScript/Python Bridge
                        |
                FEM Engineering Core
          _________|___________
         |         |           |
      Model      Load        Result
   Intelligence Intelligence  Intelligence
         |         |           ^
   Model Bundle Canonical Load |
         |         |           |
         +------ Solver Adapters ------+
                 |             |
              OpenSees       ANSYS
                 |             |
                 +------ Real Solver Run
                               |
                     run_manifest + results
                               |
                    Artifact / Evidence (later)
```

### Pi Agent Runtime

Owns agent reasoning, context, sessions, Skills, Extensions, tool selection, and permission interaction. It does not become a parallel numerical engine.

### Engineering Tools

Expose small composable contracts such as model inspection, load inspection/standardization, solver status, preflight, solver run, result inspection, and result query. Tool results are structured engineering evidence rather than prompt-shaped prose.

### FEM Engineering Core

Owns deterministic parsing, Model Bundle discovery, load transformation, solver adapters, solver-native result reading, and later evidence/optimization calculations.

### Solver Adapters

Hide concrete solver APIs behind a small common boundary:

```text
status()
preflight(model_path, load_path?, solver_options?)
run(model_path, load_path?, solver_options?)
```

The abstract load path and solver options are optional because a solver-native model can own its load definition and each solver has different execution requirements. Concrete adapters must validate their own options and fail closed rather than silently ignoring solver-specific settings.

OpenSeesPy and ANSYS MAPDL are the current real solver adapters. They share the generic agent-facing tools while retaining solver-specific deterministic preflight and execution behavior.

PR10 introduces the first ANSYS `solverOptions` contract: when an external supported canonical earthquake `loadPath` is supplied, `solverOptions.modelUnits.length` and `.time` are required because MAPDL is unitless. These values must come from deterministic model/project/user evidence; FEMagent does not infer them from numerical magnitudes.

### Result Intelligence

Result Intelligence is a solver-neutral, read-only facts layer over completed runs:

```text
run_manifest.json
  -> workspace/path checks
  -> declared artifact SHA verification
  -> solver-specific deterministic result reader
  -> ResultManifest
  -> ResultQuery
```

`fem_result_inspect` and `fem_result_query` never execute a solver. A successful solver process exit is not itself a numerical result; result claims must come from recorded numerical artifacts.

Controlled OpenSees response artifacts prove SI/time units through their FEMagent schema. ANSYS MAPDL binary results preserve solver-native unit/abscissa semantics when the model's unit system is not deterministically established for result interpretation. `unit: null` therefore remains unknown rather than being inferred as SI.

Result Intelligence also does not resolve engineering roles. A result for node 36 does not prove that node 36 is a tower base or bearing; role-to-ID resolution belongs to deterministic model/project evidence.

### Solvers

Own numerical FEM results. An LLM explanation, static parser, model-name heuristic, or successful process exit is never a substitute for extracted solver-result evidence.

## Model identity

FEMagent does not assume that a model is one file.

For multi-file models the deterministic unit of identity is a `Model Bundle`:

```text
entrypoint
  + resolved workspace-local dependencies
  + per-file SHA256
  -> deterministic bundleFingerprint
```

A helper/include/data-file change therefore changes the model identity even when the entrypoint file itself is unchanged.

Dependencies that escape the active workspace are blocked. Bundle discovery does not install missing packages, fetch remote code, or authorize arbitrary shell/network behavior.

ANSYS bundle members may use `.cdb`, `.inp`, `.apdl`, `.mac`, `.dat`, or `.txt`; TXT/DAT entrypoints are promoted to models only when APDL/CDB content signals are present. `/INPUT` and `*USE` references form the current deterministic ANSYS dependency graph.

## Load identity and application

Load inspection and standardization are separate from solver application:

```text
source load
  -> fem_load_inspect
  -> explicit confirmed mapping
  -> fem_load_standardize
  -> FEMAGENT_LOAD_CSV_V1
  -> solver-specific preflight/application
```

The canonical CSV is a deterministic data artifact, not proof of solver consumption.

For ANSYS PR10, one canonical `EARTHQUAKE + UNIFORM_EXCITATION + ACCELERATION` channel in `m/s2` can be applied after explicit model-unit declaration. FEMagent converts the record into declared MAPDL model units, creates deterministic `femagent_load_table.txt` and `femagent_load.mac` artifacts, validates a unique supported full-transient hook, and modifies only a staged bundle copy.

No-load ANSYS runs remain `MODEL_SCRIPT_MANAGED`. Unsupported/malformed external loads or unknown model units block canonical injection rather than falling back silently to provenance-only behavior.

See `docs/architecture/load-pipeline.md` and `docs/solver/ansys-canonical-load.md` for the detailed contract.

## Static inspection and solver inspection

Source inspection and realized solver state are intentionally separate evidence layers.

For OpenSees Python:

```text
fem_model_inspect
        |
        v
AST safety + dependency discovery
        |
        v
Model Bundle
        |
        v
fem_solver_preflight
        |
        v
isolated build-only OpenSees worker
(ops.analyze intercepted)
        |
        v
realized domain evidence
        |
        v
user-approved fem_solver_run
```

For ANSYS APDL/CDB without an external canonical load:

```text
fem_model_inspect
        |
        v
static APDL safety + /INPUT/*USE discovery
        |
        v
ANSYS Model Bundle
        |
        v
fem_solver_preflight
        |
        v
staged sanitized build-only MAPDL run
(stops before requested solution/postprocessing)
        |
        v
READY / BLOCKED evidence
        |
        v
user-approved staged fem_solver_run
```

For ANSYS PR10 canonical load application:

```text
FEMAGENT_LOAD_CSV_V1 + explicit modelUnits
        |
        v
canonical validation + unit conversion
        |
        v
transient hook/conflict inspection
        |
        v
staged build-only bundle
+ generated table/macro
(no requested solve)
        |
        v
READY / BLOCKED
        |
        v
user-approved run
        |
        v
fresh staged bundle
+ generated artifacts
+ staged-only APDL injection
        |
        v
MAPDL execution + run provenance
```

Static APDL does not always enumerate realized topology for parameterized/block-based models. Build-only inspection proves that the staged model/input can be constructed without intentionally advancing the requested solve; numerical response truth is then read from recorded solver result artifacts through Result Intelligence.

## PR11 ANSYS Golden Path

PR11 proves the first complete ANSYS composition across the existing intelligence/runtime boundaries:

```text
earthquake XLSX
        |
        v
Load Intelligence
        |
        v
FEMAGENT_LOAD_CSV_V1
        |
        v
explicit solverOptions.modelUnits
        |
        v
ANSYS preflight
        |
        v
staged table/macro + APDL injection
        |
        v
MAPDL execution
        |
        v
run_manifest + recorded binary result
        |
        v
Result Intelligence integrity verification
        |
        v
nodal displacement ResultQuery
```

The path has two evidence layers with deliberately different claims:

- **Mandatory CI Golden Path:** a strict fake MAPDL process validates the real staging/injection process boundary and supplies the valid `.rst` fixture packaged with `ansys-mapdl-reader`. Production run-manifest hashing and production Result Intelligence are still exercised. The fixture's numerical values are parser/interoperability evidence only and are not attributed to the Golden Model.
- **Opt-in real ANSYS Golden Path:** a configured `FEM_ANSYS_EXECUTABLE` solves the checked-in full-transient example. The harness fixes the response identity to node 2 X displacement, reruns with earthquake amplitude scales `1.0` and `2.0`, and requires both execution identity and real displacement response to change.

PR11 therefore adds no second solver runner and no second result parser. It proves that the existing Model/Load/Solver/Result boundaries compose into a reproducible end-to-end path.

The example and real causality harness live at `examples/ansys/golden_path/`.

## Execution and result provenance

Real solver-native Model Bundles are staged under their run directory before execution:

```text
.femagent/runs/<runId>/model_bundle/
```

The staged bundle, its fingerprint/file hashes, solver/runtime identity, run/case identity, logs, and captured outputs form the precursor to the Artifact/Evidence layer.

For a PR10 canonical ANSYS run, provenance additionally binds:

- canonical load source SHA256;
- declared model units and conversion factors;
- generated table and macro SHA256;
- transient hook path/line/command;
- staged injection evidence;
- `executionInputFingerprint`.

`executionInputFingerprint` is derived from the model bundle identity, canonical load identity, generated artifacts, model-unit mapping, and hook identity. `caseFingerprint` incorporates that execution-input identity so relevant input changes cannot retain the same case identity.

For ANSYS, `FEM_ANSYS_EXECUTABLE` is the explicit runtime configuration boundary. FEMagent does not guess or scan installation paths. When the staged MAPDL job produces a binary result (`.rst`, `.rth`, `.rfl`, or `.rmg`), its path and SHA256 are recorded in the run manifest so Result Intelligence can verify and read it later.

The result evidence ladder is:

```text
solver_run
 -> run manifest
 -> recorded numerical artifact
 -> artifact integrity
 -> ResultManifest
 -> ResultQuery
 -> engineering explanation
```

Later Artifact/Evidence work can build stronger run-validity state on top of this layer without making Result Intelligence a workflow controller.

## Trust boundary

The architecture follows four rules:

- **LLM decides what to do.**
- **Engineering tools decide deterministic engineering facts.**
- **Solvers decide numerical results.**
- **Artifacts/Evidence preserve what actually happened.**

Agent autonomy may grow, but engineering truth must continue to cross these deterministic boundaries rather than being inferred from model prose.
