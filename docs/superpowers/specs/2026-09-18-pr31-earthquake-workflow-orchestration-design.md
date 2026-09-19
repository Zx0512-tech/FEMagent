# PR31 — Earthquake Workflow Orchestration Design

Date: 2026-09-18

## Purpose

PR31 composes PR28–PR30 into one controlled earthquake-analysis workflow without creating a new solver execution bypass.

```text
natural-language engineering request
        ↓
PR30 evidence-backed analysis completion
        ↓
EngineeringAnalysisSpec V2
        ↓
deterministic preparation
        ├─ OpenSees: Analysis Readiness → render → solver preflight
        └─ ANSYS: exact APDL bundle inspection → PR29 solver preflight
        ↓
READY_FOR_CONFIRMATION
        ↓
existing fem_solver_run only
        ↓
existing permission gate / human confirmation
        ↓
isolated real solver execution
        ↓
PR31 deterministic postprocess
        ├─ run/workflow identity binding
        ├─ Result Intelligence integrity check
        ├─ planned SUMMARY queries
        └─ structured engineering response summary
```

PR31 never calls a real solver from the workflow preparation or postprocessing commands. Real execution remains exclusively on `fem_solver_run`.

## Public workflow states

Preparation:

- `NEEDS_INPUT` — PR30 completion is incomplete/ambiguous/invalid.
- `ANALYSIS_NOT_READY` — OpenSees generated-analysis readiness or workflow-specific dynamic-mass checks fail.
- `PREFLIGHT_BLOCKED` — concrete solver preflight is blocked.
- `READY_FOR_CONFIRMATION` — exact solver run request is frozen into a workflow manifest.

Postprocess:

- `COMPLETED` — run identity matches and every planned result summary is available.
- `LIMITED` — run identity matches but one or more planned result queries are unavailable.

## Inputs

`earthquakeWorkflow.prepare` accepts:

- solver: `opensees | ansys`
- PR30 analysis requirement draft
- EngineeringModelSpec
- canonical load artifact path
- optional Semantic Role context
- ANSYS solver model path when solver=ansys

The LLM does not submit dt, duration, load SHA, ModelSpec fingerprint, AnalysisSpec fingerprint, generated OpenSees paths, or ANSYS bundle fingerprint.

## OpenSees preparation

PR31:

1. runs PR30 completion;
2. requires candidate AnalysisSpec V2;
3. evaluates PR28 Analysis Readiness;
4. for uniform-base generated OpenSees, additionally requires at least one positive translational nodal mass in the excited direction because this renderer has no other mass source;
5. renders the verified PR28 generated analysis;
6. preflights the exact generated bundle;
7. freezes the exact `fem_solver_run` request:
   - generated `analysisPath`
   - `responsePlanPath`
   - `analysisManifestPath`
   - no external `loadPath`.

## ANSYS preparation

PR31:

1. runs PR30 completion;
2. inspects the exact APDL Model Bundle;
3. derives model length/time units only from validated ModelSpec units;
4. binds PR29 admission to the current APDL bundle fingerprint;
5. preserves `semanticEquivalence=NOT_MACHINE_PROVEN`;
6. preflights through the existing ANSYS SolverAdapter;
7. freezes the exact `fem_solver_run` request with:
   - solver model path
   - modelUnits
   - ansysV2.analysisSpec
   - ansysV2.confirmedBundleFingerprint
   - no external `loadPath`.

PR31 does not claim the APDL bundle is semantically equivalent to the ModelSpec.

## Human confirmation boundary

PR31 adds no execution tool.

The Agent must pass `solverRunRequest` from a READY workflow verbatim to existing `fem_solver_run`. The existing permission gate remains the only interactive approval boundary.

PR31 enhances the confirmation message with controlled analysis context when present, including analysis type/direction and exact bundle/render identity.

## Workflow manifest

A READY preparation writes:

`.femagent/workflows/<workflowId>/workflow_manifest.json`

It records:

- workflow schema/id/fingerprint;
- solver;
- ModelSpec and AnalysisSpec fingerprints;
- exact canonical load identity;
- exact frozen solver run request;
- concrete solver preflight report;
- solver binding provenance;
- planned result queries.

The manifest is not authority for solver execution by itself. SolverAdapter revalidates all execution inputs again.

## Postprocess

`earthquakeWorkflow.summarize` accepts the workflow manifest path and a completed run reference.

It:

1. verifies the workflow manifest;
2. loads the exact run manifest;
3. verifies solver identity;
4. verifies AnalysisSpec identity:
   - OpenSees via `generatedAnalysis.analysisSpecFingerprint`;
   - ANSYS via `analysis.analysisSpecFingerprint`;
5. verifies solver-specific model binding where recorded;
6. calls Result Intelligence;
7. queries each planned AnalysisSpec result request with `SUMMARY`;
8. returns structured peak/min/max/sample information without adding an engineering PASS/FAIL judgment.

Unknown ANSYS units remain unknown.

## Non-goals

- no new real-execution tool;
- no permission-gate bypass;
- no arbitrary workflow scripting;
- no auto repair;
- no response-spectrum analysis;
- no nonlinear analysis;
- no optimization;
- no automatic Semantic Role Manifest writes;
- no automatic role/node inference;
- no base-shear aggregation;
- no engineering acceptance/pass-fail judgment.
