# PR31 — Earthquake Workflow Orchestration Implementation Plan

## Task 1 — Workflow preparation contract ✅

Implement deterministic workflow states and exact frozen solver-run requests.

## Task 2 — OpenSees orchestration ✅

Compose PR30 completion → PR28 readiness → uniform-base mass guard → renderer → generated-analysis preflight.

## Task 3 — ANSYS orchestration ✅

Compose PR30 completion → APDL bundle inspection → PR29 exact-bundle/model-unit solver preflight while preserving semantic-equivalence limitation.

## Task 4 — Workflow manifest + postprocess ✅

Persist immutable preparation provenance and bind completed runs back to the planned AnalysisSpec before Result Intelligence SUMMARY queries.

## Task 5 — Bridge + TypeScript + Agent tools ✅

Add SAFE prepare/summarize tools only. Keep real execution exclusively on existing permission-gated `fem_solver_run`.

## Task 6 — Verification ✅

Add real OpenSees end-to-end workflow coverage, ANSYS request/admission transport coverage, fail-closed identity/mass tests, TypeScript bridge/tool-surface tests, scope audit, and final full-suite CI.


## Closeout

Implementation CI #665 (run id `35356976289`) passed Typecheck, TypeScript tests, Python tests, Ruff, OpenSees smoke, ANSYS result-reader smoke, and FEM health on implementation head `3d72c769ae248d1f6ffffece8d6eface4971e4eb`.

The final closeout commit adds only verification documentation plus a summarize-bridge fail-closed transport test. PR31 must remain Draft until that final HEAD also passes the complete CI suite.
