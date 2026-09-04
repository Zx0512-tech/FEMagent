# Model Intelligence

FEMagent separates model inspection evidence from engineering interpretation. A model may be a single solver input file or a multi-file `Model Bundle`; the Agent should not assume either shape in advance.

## `fem_model_inspect`

`fem_model_inspect` dispatches by supported model format and returns deterministic inspection evidence without performing the requested FEM solve.

Current model families are:

- ANSYS APDL/CDB-style Model Bundles,
- OpenSees Python entrypoints and their workspace-local Model Bundles.

The TypeScript bridge exposes these through generic model-inspection contracts so downstream tools can branch on the returned format rather than maintaining solver-specific tool names.

## ANSYS APDL/CDB Model Bundle

ANSYS model entrypoints and included script/model members may use:

- `.cdb`,
- `.inp`,
- `.apdl`,
- `.mac`,
- `.dat`,
- `.txt`.

`.txt` and `.dat` are not trusted as models by suffix alone. FEMagent requires deterministic APDL/CDB content signals such as `/PREP7`, `NBLOCK`/`EBLOCK`, `N`/`E`/`ET`/`MP`/`SECTYPE`/`CM`, `/INPUT`, or `*USE` before promoting TXT/DAT as an ANSYS model entrypoint.

### Static APDL evidence

The APDL inspector records defensible source-level facts such as:

- source path, encoding, size, and SHA256,
- `/PREP7` presence,
- explicit `N`, `E`/`EN`, `NBLOCK`, `EBLOCK`, and `*DO` signals,
- `ET` element-type definitions,
- `MP` material-property labels grouped by material ID,
- `SECTYPE` section definitions,
- `CM` component definitions,
- explicit `D` constraint labels,
- existing `F`, `SF`, `SFE`, and `ACEL` load-command signals,
- numeric coordinate bounds when literal `N` coordinates are available,
- forbidden APDL command hits such as `/SYS`, `/SYP`, `/DELETE`, and `~`.

A topology count is populated only when its basis is defensible from static text. `null` means unknown, not zero. Parameterized or block-based APDL can require controlled solver inspection because static text cannot always enumerate the realized topology.

### ANSYS dependency discovery

PR8 follows static `/INPUT` and `*USE` references recursively and emits a bundle manifest containing:

- entrypoint path/hash,
- resolved bundle files and roles,
- dependency type and resolution status,
- SHA256 for every included file,
- deterministic `bundleFingerprint`,
- bundle integrity and warnings.

Missing dependencies or references escaping the active workspace block the bundle. PR8 also blocks absolute include references even when they happen to point inside the workspace, because real execution is performed from a staged copy and an absolute source reference could bypass that staged provenance boundary.

### ANSYS build-only evidence

When static safety, bundle integrity, and runtime availability permit it, `fem_solver_preflight` with `solver: ansys` stages a sanitized copy of the Model Bundle and runs MAPDL in build-only mode.

The staged input stops before `/SOLU`, `SOLVE`, or postprocessing. This establishes build/preflight evidence without intentionally executing the requested analysis. It does not yet provide full realized ANSYS topology or numerical responses; those belong to later Result Intelligence.

## OpenSees Python static inspection

Python inspection is AST-based and does not execute the user's model. It identifies source-level evidence including OpenSees imports/calls, local dependency references, dynamic construction signals, and safety findings.

AST inspection deliberately does **not** pretend that Python source is a fully realized FEM domain. Loops, helper functions, imported modules, and computed tags can make final topology unknowable until model construction occurs inside the solver runtime.

### OpenSees Model Bundle

For an OpenSees Python entrypoint, FEMagent discovers the workspace-local dependency closure and emits a Model Bundle manifest containing:

- the entrypoint,
- resolved bundle files and roles,
- dependency records and resolution status,
- SHA256 for each included file,
- a deterministic `bundleFingerprint`,
- bundle integrity and warnings.

The bundle fingerprint, not the entrypoint SHA alone, is the identity of a multi-file model. Changing a resolved helper module or referenced data file changes the bundle identity even when the entrypoint is unchanged.

### Workspace dependency boundary

Local modules and referenced model data may be included only when they resolve inside the active workspace. A dependency that resolves outside the workspace is blocked rather than silently trusted or copied into execution.

External installed Python packages may be referenced as runtime dependencies, but Model Bundle discovery does not install packages, fetch remote code, or turn arbitrary network/shell behavior into an allowed model dependency.

## Static evidence versus realized solver evidence

For safe OpenSees Python bundles, solver preflight may run **build-only inspection** in an isolated OpenSees worker. The worker permits model construction but intercepts `ops.analyze()` so the requested analysis does not advance.

For ANSYS, build-only preflight uses a sanitized staged APDL bundle and stops before the requested solution/postprocessing stage.

These are deliberately separate evidence layers:

```text
Static source + Model Bundle
        |
        v
Solver-specific build-only inspection
        |
        v
Preflight/build evidence
        |
        v
User-approved real solver execution
        |
        v
Numerical result evidence
```

OpenSees build-only can currently expose realized node/element-domain information. ANSYS PR8 build-only currently establishes safe staged construction/process evidence; detailed domain/result extraction is deferred.

## Engineering semantics

Names are hints, not engineering roles. `CM,GIRDER,ELEM`, a variable named `tower_nodes`, or a module named `bearings.py` can be useful context but do not by themselves prove the engineering meaning of those objects.

Likewise X/Y/Z are coordinate axes only. Longitudinal/transverse/vertical meaning must come from project context, user confirmation, or deterministic model evidence.

## Migration boundary

The APDL static parsing ideas were extracted from momoagent's model-import work. PR6 introduced solver-neutral Model Bundles and OpenSees Python inspection; PR8 extends the same bundle/preflight architecture to ANSYS. FastAPI platform stores, fixed task types, workflow guards, and artifact persistence are intentionally not part of Model Intelligence.
