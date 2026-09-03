# Model Bundle & OpenSees Python Intelligence Design

## Goal

Upgrade FEMagent from single-file model handling to a solver-neutral **Model Bundle** abstraction, then allow real OpenSees `.py` engineering models to be statically inspected, dependency-resolved, build-inspected in an isolated worker, and executed only after preflight and explicit execution approval.

The same bundle abstraction is intentionally designed for ANSYS multi-file APDL/CDB projects in the next solver PR.

## Core principle

FEMagent reasons about a **complete engineering model bundle**, not a single entry file.

```text
Model Bundle
├── entrypoint
├── source files
├── referenced modules/includes
├── engineering data files
├── dependency graph
├── per-file SHA256
└── bundle fingerprint
```

Static inspection establishes source-code facts only. Build-only inspection establishes the realized solver domain. Real solver execution remains a separate EXECUTION operation.

## Supported PR6 entrypoint

PR6 adds OpenSees Python entrypoints:

- `.py`
- must statically demonstrate OpenSees usage through `openseespy.opensees` imports or recognized OpenSees API calls
- may import workspace-local Python modules
- may read workspace-local engineering data files

Existing ANSYS APDL/CDB inspection remains supported. PR6 does not yet add ANSYS bundle execution; it only introduces bundle-neutral schema and interfaces that PR7 can reuse.

## Model bundle boundary

A bundle is rooted inside the active FEMagent workspace. Every resolved dependency must remain inside that workspace.

Allowed bundle members include:

- Python source modules
- ANSYS APDL/CDB/INP/MAC source files
- CSV/TXT/DAT/JSON/YAML-like engineering data when referenced by model source
- other explicitly supported local engineering assets

The bundle must reject or flag unresolved dependencies and paths escaping the workspace.

### Workspace rule

Allowed:

```text
workspace/project/main.py
workspace/project/materials.py
workspace/project/data/mass.csv
```

Blocked:

```text
../outside.py
/etc/passwd
C:\Users\...\secret.dat
network URLs
```

## Bundle manifest

Introduce a normalized bundle layer above the solver-specific model manifest.

```text
FEMModelBundleManifest
schemaVersion
kind
bundleId
entrypoint
files[]
dependencies[]
bundleFingerprint
integrity
solverCompatibility
modelManifest
warnings[]
```

### Entrypoint

```text
path
format
solver
sha256
```

### Files

Each bundle file records:

```text
path
role
sha256
sizeBytes
```

Initial roles:

- `ENTRYPOINT`
- `PYTHON_MODULE`
- `ENGINEERING_DATA`
- `ANSYS_INCLUDE`
- `UNKNOWN_DEPENDENCY`

### Dependencies

Each dependency edge records:

```text
source
reference
target
type
status
```

Initial dependency types:

- `PYTHON_IMPORT`
- `PYTHON_FILE_READ`
- `ANSYS_INPUT`
- `ANSYS_USE`

Initial status values:

- `RESOLVED_WORKSPACE`
- `EXTERNAL_PACKAGE`
- `UNRESOLVED`
- `BLOCKED_OUTSIDE_WORKSPACE`

External Python packages are not bundle files. They are recorded separately as runtime dependencies.

## Bundle fingerprint

The bundle fingerprint is deterministic and must change when any resolved bundle member changes.

Canonical input:

1. take every resolved bundle file,
2. sort by workspace-relative POSIX path,
3. concatenate `path + "\0" + sha256 + "\n"`,
4. SHA256 the UTF-8 canonical text.

Solver run manifests must use the bundle fingerprint as model identity for bundle-backed runs rather than relying only on the entrypoint SHA256.

## OpenSees static inspection

OpenSees `.py` files are parsed with Python `ast`; static inspection must never import or execute the user model.

The parser detects:

- imports and aliases for `openseespy.opensees`
- recognized OpenSees API calls, including `model`, `node`, `element`, `fix`, `mass`, `uniaxialMaterial`, `section`, `geomTransf`, `timeSeries`, `pattern`, `constraints`, `numberer`, `system`, `integrator`, `algorithm`, `analysis`, `analyze`, `eigen`
- literal model dimensionality when statically recoverable
- explicit literal node/element tags when statically recoverable
- dynamic generation signals such as loops, comprehensions, helper calls, computed tags and imported builders
- local module imports
- common local data reads
- analysis calls present in source

Static topology counts must be nullable when dynamic Python code can affect realized topology.

## OpenSees model classification

Static inspection classifies the entrypoint as:

- `MODEL_CONFIRMED`
- `MODEL_LIKELY`
- `NOT_OPENSEES_MODEL`
- `UNSAFE`

`MODEL_CONFIRMED` requires clear OpenSees import/use evidence and model-building calls.

`MODEL_LIKELY` means OpenSees involvement is visible but construction is delegated or too dynamic for static confirmation.

`NOT_OPENSEES_MODEL` cannot proceed through the OpenSees adapter.

`UNSAFE` contains blocked behavior and cannot proceed to build-only or solve.

## Python safety classification

PR6 does not attempt to ban ordinary Python. Real engineering models may use functions, loops, classes, NumPy, math, pathlib, pandas and local helper modules.

Safety classification focuses on side-effect capabilities.

Blocked or execution-rejecting operations include direct or clearly resolved use of:

- `subprocess`
- `socket`
- `requests`
- `urllib` networking
- `ctypes`
- `os.system`
- `os.popen`
- `eval`
- `exec`
- `compile`
- dynamic `importlib` loading of arbitrary paths
- destructive filesystem operations such as `shutil.rmtree`, `Path.unlink`, `os.remove`, `os.unlink`
- writes outside the workspace

`os` itself is not categorically forbidden because engineering scripts may legitimately use `os.path`.

Network access is not part of PR6 and is blocked by policy.

Static safety inspection must emit concrete findings with file path, line number, rule code and severity.

## Dependency discovery

Dependency discovery is recursive for workspace-local Python imports and recognized local data references.

Rules:

- resolve normal `import x` / `from x import y` against the entrypoint directory and workspace package layout
- recurse only into workspace-local modules
- record stdlib/site-package imports as `EXTERNAL_PACKAGE`
- prevent cycles with a visited set
- preserve unresolved imports as warnings rather than inventing targets
- reject any literal referenced file that resolves outside workspace
- keep dynamic/unrecoverable file paths as unresolved dependency evidence

PR6 may support conservative common file-read APIs (`open`, `Path.open`, `numpy.loadtxt`, `numpy.genfromtxt`, `pandas.read_csv`, JSON file opens) when the path is a static string expression resolvable relative to the referencing file or workspace.

## Build-only inspection

Static parsing cannot fully realize arbitrary engineering Python. Therefore OpenSees gains an isolated **build-only inspection** phase.

```text
static inspect
  ↓
safety accepted
  ↓
isolated worker
  ↓
execute bundle with analyze blocked
  ↓
query OpenSees domain
  ↓
realized model report
```

The worker executes the model in a separate Python process with the project directory available for local imports.

During build-only mode, calls that advance analysis must be blocked or intercepted, including at minimum:

- `analyze`
- analysis-time advancement that would execute the requested structural analysis

The worker may allow analysis configuration declarations to run because many OpenSees scripts configure analysis in the same file; it must prevent actual solve advancement.

After execution the worker queries realized domain facts when OpenSees supports them, including:

- node tags
- element tags
- node coordinates
- nodal masses where available
- element connectivity where available

The build report must state that it reflects a solver-instantiated domain, not a completed structural analysis.

## Execution model

Real `.py` execution uses the existing isolated OpenSees worker architecture introduced in PR5.

PR6 must not execute user model Python in the `femagent.bridge/v1` process.

Execution path:

```text
Pi
→ fem_solver_preflight
→ OpenSeesAdapter
→ bundle + build inspection validation
→ EXECUTION confirmation gate
→ fem_solver_run
→ isolated worker
→ OpenSees real solve
```

The worker runs with working directory set to the bundle project directory so workspace-local imports and data references behave like normal engineering scripts.

PR6 does not promise OS-level sandboxing. Its guaranteed controls are static rejection, workspace path confinement in FEMagent-managed resolution, isolated process execution, explicit permission gating, and captured solver logs. Strong OS/container sandboxing is a later hardening concern.

## Handling scripts that already contain analysis and recorders

OpenSees Python models commonly contain both model building and analysis commands. PR6 should support this reality rather than require users to rewrite the script into a FEMagent-specific JSON model.

For build-only inspection, actual `analyze` execution is intercepted.

For real execution, the original script may execute its own analysis commands. FEMagent records the worker exit state and generated files, and captures available generic OpenSees domain metadata. Generic postprocessing of arbitrary recorder outputs is deferred to Result Intelligence.

The controlled `FEMAGENT_OPENSEES_MODEL_SPEC` SDOF path from PR5 remains supported as a deterministic Golden Path and regression fixture.

## Tool surface

Do not add solver-specific tool explosion.

Keep:

- `fem_model_inspect`
- `fem_solver_status`
- `fem_solver_preflight`
- `fem_solver_run`

`fem_model_inspect` becomes bundle-aware and dispatches by entrypoint format.

`fem_solver_preflight` for OpenSees `.py` consumes bundle inspection/build-inspection facts.

No `fem_opensees_python_execute` tool is introduced.

## Model inspection outputs

For OpenSees Python, `fem_model_inspect` returns a report that includes:

- source entrypoint metadata
- classification
- static OpenSees API signals
- static topology evidence
- dynamic-generation flags
- safety findings
- bundle manifest
- dependency graph
- bundle fingerprint
- execution eligibility

Execution eligibility values remain explicit and should include states equivalent to:

- statically eligible
- requires build inspection
- incomplete / not model
- rejected unsafe

## Run traceability

For bundle-backed OpenSees Python runs, `run_manifest.json` records:

- entrypoint path and SHA256
- bundle fingerprint
- resolved bundle file list with SHA256
- solver/package version
- preflight/build-inspection summary
- execution configuration
- output file hashes

This is a precursor to formal Artifact/Evidence persistence.

## Skills/context behavior

Update the FEM model inspection Skill so the Agent understands:

1. a model may span multiple files,
2. the entrypoint does not define full model identity,
3. unresolved or blocked dependencies matter,
4. AST facts are not realized topology,
5. build-only inspection is required for dynamic OpenSees models,
6. execution still requires preflight and explicit permission.

The Agent must not infer engineering semantics such as bridge girder/tower roles from Python variable or module names alone.

## Testing strategy

Tests must cover:

- workspace-local Python import discovery
- recursive dependency graph with cycles handled
- local CSV/data reference discovery
- outside-workspace dependency rejection
- safe `os.path` usage allowed
- dangerous `os.system` / subprocess / network / eval/exec detection
- OpenSees model confirmation
- dynamic loop-generated topology reported as unknown statically
- deterministic bundle fingerprint changes when an included file changes
- isolated build-only inspection returns realized nodes/elements without running `analyze`
- real OpenSees `.py` execution through the existing bridge/adapter
- TypeScript contract parity
- existing SDOF Golden Path regression remains green

TDD sequence is mandatory: failing tests first, then minimal implementation.

## Out of scope

PR6 does not add:

- ANSYS execution
- complete static interpretation of arbitrary Python
- network access
- OS/container sandboxing
- automatic installation of arbitrary project dependencies
- generic recorder/result parsing for every OpenSees script
- structural semantic labeling from variable names
- Artifact/Evidence database persistence
- model modification
- optimization

## Acceptance criteria

PR6 is complete when a workspace containing a realistic multi-file OpenSees Python project can be:

1. identified as an OpenSees model,
2. recursively represented as a deterministic model bundle,
3. checked for unsafe behavior and workspace escapes,
4. build-inspected in an isolated OpenSees worker without advancing analysis,
5. preflighted using the existing solver tool surface,
6. executed only after the existing EXECUTION permission gate,
7. traced by bundle fingerprint and per-file hashes,
8. verified by CI with real OpenSeesPy execution.
