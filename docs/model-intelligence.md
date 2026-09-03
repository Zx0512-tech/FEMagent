# Model Intelligence V1

FEMagent separates model inspection evidence from engineering interpretation.

## Output layers

`fem_model_inspect` returns two related structures:

1. `ModelInspectionReport` — what the static inspector observed and whether the file is safe/complete enough to proceed.
2. `FEMModelManifest` — normalized engineering facts that later Skills and solver tools can consume without rereading raw APDL.

## Static facts

Model Intelligence V1 understands ANSYS APDL/CDB-style text and records:

- source path, encoding, size, SHA256
- `/PREP7` presence
- explicit `N`, `E`/`EN`, `NBLOCK`, `EBLOCK`, and `*DO` signals
- `ET` element-type definitions
- `MP` material-property labels grouped by material ID
- `SECTYPE` section definitions
- `CM` component definitions
- explicit `D` constraint labels
- existing `F`, `SF`, `SFE`, and `ACEL` load-command signals
- numeric coordinate bounds when literal `N` coordinates are available
- forbidden APDL command hits (`/SYS`, `/SYP`, `/DELETE`, `~`)

## Validation versus inspection

Inspection remains read-only even for unsafe or incomplete files. A model containing forbidden commands is still inspectable so the Agent can explain the problem, but its `executionEligibility` is `REJECTED` and its ANSYS compatibility is `REJECTED_UNSAFE`.

Incomplete models use `INCOMPLETE`. Parameterized or block-based models use `REQUIRES_SOLVER_INSPECTION` because static text cannot enumerate their final topology reliably.

## Count semantics

A topology count is only populated when its basis is defensible from static text. `null` means unknown, not zero.

For parameterized or `NBLOCK`/`EBLOCK` models, final node/element totals must come from a future controlled solver-inspection step.

## Engineering semantics

Component names are hints, not engineering roles. `CM,GIRDER,ELEM` proves that a component named `GIRDER` exists; it does not by itself prove that the component is the main girder.

Likewise X/Y/Z are coordinate axes only. Longitudinal/transverse/vertical meaning must come from project context, user confirmation, or later deterministic model understanding.

## Migration boundary

The safe static parsing ideas were extracted from momoagent's `ModelImportService`, but FastAPI, platform-store registration, task types, workflow guards, and artifact persistence are intentionally not migrated in PR3.
