# PR30 — Controlled Natural-Language Analysis Completion Implementation Plan

## Goal

Produce an evidence-backed `EngineeringAnalysisSpec V2` for uniform-base transient earthquake analysis without allowing the LLM to invent model identity, load identity, time controls, damping, or semantic target mappings.

## Tasks

### Task 1 — Draft schema + evidence contract
Create `fem_core/analysis_requirements/` with strict V1 draft validation and exact quote evidence validation.

### Task 2 — Deterministic context binding
Validate ModelSpec, hash/read the canonical load artifact, derive fixed time controls, and validate the earthquake channel/component.

### Task 3 — Result target completion
Support explicit NODE targets and exact semantic-role-type resolution. Fail closed on missing/ambiguous roles and unrestrained reaction DOFs.

### Task 4 — Candidate AnalysisSpec assembly
Build V2 TRANSIENT + UNIFORM_BASE_EXCITATION candidates, assign deterministic request IDs, and require intrinsic AnalysisSpec validation before COMPLETE.

### Task 5 — Bridge + TypeScript + Pi tool
Add one SAFE `fem_analysis_requirement_complete` tool and `analysisRequirement.complete` bridge command. No render/run action.

### Task 6 — Verification
Add Python and TypeScript tests for COMPLETE, missing damping, artifact mismatch/channel conflict, semantic-role resolution/ambiguity, reaction restraint, direct node targets, and bridge transport.

Run the full repository CI and keep PR30 Draft until the final head is green.
