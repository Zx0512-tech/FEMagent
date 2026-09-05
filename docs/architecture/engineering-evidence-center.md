# Engineering Evidence Center V1

## Purpose

PR12 adds a deterministic evidence boundary between recorded finite-element results and engineering claims.

The Evidence Center does **not** create new solver truth. It consumes Result Intelligence output, binds that output to recorded solver artifacts and run provenance, and exposes only evidence that satisfies the V1 promotion rules as `VERIFIED`.

```text
Model / Load
    ↓
Solver Adapter
    ↓
run_manifest + recorded result artifacts
    ↓
Result Intelligence
  inspect_result()  -> artifact integrity / capabilities
  query_result()    -> deterministic recorded metric
    ↓
Engineering Evidence Center
  project_result_evidence()
  project_engineering_report()
    ↓
evidence.project
    ↓
runFemEvidenceProject()
    ↓
fem_evidence_project
```

The Evidence Center is downstream of solver execution and Result Intelligence. It is read-only and never starts OpenSees or ANSYS.

## Core objects

`EngineeringEvidence` contains:

- `evidenceId`: stable caller-defined evidence identity;
- `claim`: deterministic generic claim text derived from the recorded quantity;
- `status`: `VERIFIED`, `LIMITED`, `INVALID`, or `UNVERIFIED`;
- `artifacts`: artifact path, SHA-256, and deterministic entity reference;
- `metric`: the Result Intelligence metric payload used by the claim;
- `provenance`: run identity, case fingerprint, and solver identity.

`EvidenceArtifactRef` deliberately stores a reference to the recorded artifact rather than copying solver output into a second evidence store.

## Status semantics

### VERIFIED

At the low-level projection boundary, an evidence object is structurally eligible for `VERIFIED` when every referenced artifact has a non-empty artifact identifier and a SHA-256 value.

For the production run-backed API, this SHA is **not accepted from arbitrary caller text**. `project_run_evidence()` first calls production `inspect_result()`. Only an artifact that Result Intelligence reports as `VERIFIED` contributes its recorded SHA to the evidence projection.

Therefore the normal production promotion path is:

```text
recorded run
  -> inspect_result()
  -> artifact hash verification succeeds
  -> query_result()
  -> project_result_evidence()
  -> VERIFIED EngineeringEvidence
```

If Result Intelligence detects an artifact hash mismatch, that domain error is preserved. Evidence projection does not downgrade or hide it.

### LIMITED

An artifact reference exists but no verified SHA is available. The claim is retained as a limitation and is not emitted in `verifiedEvidence`.

### UNVERIFIED

No auditable artifact reference is available. AI-authored summaries, unsupported free text, or raw metrics without artifact binding cannot become verified evidence through this state.

### INVALID

The artifact reference itself is malformed, for example an empty artifact identifier.

## Important trust-boundary distinction

`project_claim()` and `validate_evidence()` are pure deterministic projection primitives. They do not perform filesystem I/O, execute a solver, or recompute file hashes.

They therefore must not be described as independent artifact-integrity verifiers.

For recorded FEM runs, callers that require production-grade verification must use `project_run_evidence()` (or an equivalent future integration that first obtains integrity evidence from a trusted deterministic subsystem). V1's public Agent/Bridge path uses `project_run_evidence()`.

This separation keeps the evidence model testable while preserving the rule that solver-result truth comes from Result Intelligence, not from an LLM or from unverified caller-provided strings.

## Result Intelligence binding

`project_run_evidence()` performs these steps in order:

1. resolve and inspect the recorded run with `inspect_result()`;
2. require Result Intelligence to verify declared result-artifact integrity;
3. query the recorded metric with `query_result()`;
4. select the solver-specific result artifact;
5. project the metric, entity reference, and run provenance into `EngineeringEvidence`;
6. project the evidence into an Engineering Report view.

V1 selects these result artifact roles:

| Solver | Preferred evidence artifact |
| --- | --- |
| OpenSeesPy | `responseCsv` |
| ANSYS MAPDL | `binaryResult` |

If the preferred artifact is absent or not integrity-verified, the projection cannot become `VERIFIED`.

## Metric and entity semantics

The evidence metric retains Result Intelligence fields rather than inventing a second numerical schema. V1 preserves supported fields such as:

- quantity;
- node target;
- normalized component;
- operation;
- unit;
- reference frame;
- abscissa metadata;
- summary or bounded series values.

The artifact entity reference is derived from the deterministic Result Intelligence target and component, for example:

```json
{
  "type": "NODE",
  "id": 2,
  "component": "X"
}
```

This is a solver entity identity, not an engineering semantic role.

PR12 does **not** infer that node 2 is a tower base, girder end, bearing, damper location, or any other structural role. Semantic engineering roles remain a later architecture layer.

## Unit semantics

Evidence projection preserves Result Intelligence unit semantics exactly.

- Proven SI units from controlled OpenSees result contracts remain available.
- ANSYS solver-native values whose model/result unit system is not deterministically proven remain `unit: null`.
- A declared ANSYS load/model unit contract is not silently promoted into a result-unit claim unless Result Intelligence proves that result unit contract.

The Evidence Center never infers units from value magnitude, file names, model geometry, or solver defaults.

## Engineering Report projection

`project_engineering_report()` is a deterministic view over evidence objects.

- `VERIFIED` evidence is emitted under `verifiedEvidence` with its full metric, artifacts, entity reference, and provenance.
- `LIMITED`, `INVALID`, and `UNVERIFIED` evidence is emitted under `limitations` and is never promoted into the verified section.
- `solverRuns` records the run ID, solver, and case fingerprint associated with the projection.

The report projector does not author new engineering conclusions. It only organizes already-projected evidence.

## Bridge and Agent API

FEMagent currently has no HTTP service layer. PR12 therefore extends the existing versioned TypeScript/Python Engineering Tool Bridge instead of introducing a parallel API stack.

### Python bridge command

```text
evidence.project
```

Inputs:

- `projectId`;
- `runRef`;
- `evidenceId`;
- one existing Result Intelligence query object.

### TypeScript client

```text
runFemEvidenceProject()
```

The TypeScript package exposes matching evidence/report types so callers do not need to reinterpret raw Python output.

### Pi tool

```text
fem_evidence_project
```

The Pi tool is SAFE/read-only. Its prompt contract explicitly requires:

- a deterministic existing run;
- an already-resolved node target;
- no role-to-node guessing;
- no unit inference;
- preservation of integrity failures;
- no solver execution.

## Failure behavior

Evidence projection fails closed at the Result Intelligence boundary.

Examples:

- modified recorded result artifact -> `RESULT_ARTIFACT_HASH_MISMATCH`;
- unsupported/invalid Result Intelligence query -> existing Result Intelligence domain error;
- missing verified result artifact -> evidence remains non-verified rather than fabricated;
- unknown unit -> `null`, not an inferred unit;
- unresolved engineering target -> caller must resolve it elsewhere; Evidence Center does not guess.

## V1 non-goals

PR12 intentionally does not add:

- an HTTP server;
- UI or dashboard rendering;
- PDF report generation;
- LLM-authored engineering conclusions;
- semantic engineering role resolution;
- cross-solver ranking or validation;
- optimization runtime;
- new solver execution behavior;
- new Result Intelligence quantities;
- a second result parser or duplicate result store.

## Design invariant

The central invariant is:

> A numerical FEM claim is not promoted to production `VERIFIED` evidence unless the deterministic run/result chain can bind that claim to an integrity-verified recorded artifact and stable run provenance.

The LLM may decide **what** evidence to request. The engineering runtime determines **whether** that evidence is auditable and verified.
