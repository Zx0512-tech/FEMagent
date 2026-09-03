---
name: inspect-fem-model
description: Inspect and reason about an unfamiliar finite-element model before analysis or modification.
---

# Inspect FEM Model

Use this skill when the user provides or references a FEM model whose structure is not already established in the current engineering context.

## Method

1. Locate the model file in the active workspace.
2. Call `fem_model_inspect` before making structural claims.
3. Read `validation.executionEligibility` first.
4. Use `manifest` for deterministic facts such as element types, materials, sections, component definitions, explicit constraints, coordinate bounds, and static topology evidence.
5. Treat `null` node/element counts as unknown, never as zero.
6. If the model is parameterized or block-based, state that final topology requires a controlled solver-inspection step.
7. If execution eligibility is `REJECTED`, identify the unsafe APDL evidence and do not execute the model.
8. If it is `INCOMPLETE`, explain which structural signals are missing.
9. Component names may suggest a possible engineering role, but do not promote a name such as `GIRDER` or `TOWER` into an authoritative role without additional evidence or user confirmation.
10. Do not assume X/Y/Z mean longitudinal/transverse/vertical unless that convention is established by project context or the user.

## Boundary

This skill guides reasoning only. It does not parse APDL itself and does not execute ANSYS. Engineering facts must come from the Tool result and future solver-inspection evidence.
