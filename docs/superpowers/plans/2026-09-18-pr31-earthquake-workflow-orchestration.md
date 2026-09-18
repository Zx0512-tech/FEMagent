# PR31 — Earthquake Workflow Orchestration Implementation Plan

## Task 1 — Workflow preparation contract

Implement deterministic workflow states and exact frozen solver-run requests.

## Task 2 — OpenSees orchestration

Compose PR30 completion → PR28 readiness → uniform-base mass guard → renderer → generated-analysis preflight.

## Task 3 — ANSYS orchestration

Compose PR30 completion → APDL bundle inspection → PR29 exact-bundle/model-unit solver preflight while preserving semantic-equivalence limitation.

## Task 4 — Workflow manifest + postprocess

Persist immutable preparation provenance and bind completed runs back to the planned AnalysisSpec before Result Intelligence SUMMARY queries.

## Task 5 — Bridge + TypeScript + Agent tools

Add SAFE prepare/summarize tools only. Keep real execution exclusively on existing permission-gated `fem_solver_run`.

## Task 6 — Verification

Add real OpenSees end-to-end workflow coverage, ANSYS request/admission transport coverage, fail-closed identity/mass tests, TypeScript bridge/tool-surface tests, scope audit, and final full-suite CI.
