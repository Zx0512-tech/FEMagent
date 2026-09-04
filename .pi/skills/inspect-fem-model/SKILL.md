---
name: inspect-fem-model
description: Inspect and reason about an unfamiliar ANSYS APDL/CDB Model Bundle or OpenSees Python Model Bundle before analysis or modification.
---

# Inspect FEM Model

Use this skill when the user provides or references a FEM model whose structure is not already established in the current engineering context.

## Method

1. Locate the model entrypoint in the active workspace.
2. Call `fem_model_inspect` before making structural claims.
3. Branch on the returned model format instead of assuming every model is a single file.
4. Treat `bundleFingerprint` plus the resolved bundle files as the identity of any multi-file model.

### ANSYS APDL/CDB Model Bundle

- Supported ANSYS bundle entrypoint/member suffixes include `.cdb`, `.inp`, `.apdl`, `.mac`, `.dat`, and `.txt`.
- `.txt` and `.dat` are promoted to ANSYS model entrypoints only when deterministic APDL/CDB content signals are present. Ordinary notes/data text must not be treated as a model merely because of the suffix.
- Review `validation.executionEligibility` and `bundle.integrity` before solver preflight.
- Use `manifest` for deterministic static facts such as element types, materials, sections, component definitions, explicit constraints, coordinate bounds, and topology evidence.
- Treat `null` node/element counts as unknown, never as zero.
- Follow `/INPUT` and `*USE` dependency records. Missing, workspace-escaping, or unsupported absolute include dependencies block execution.
- Parameterized or block-based APDL can require build-only solver inspection because static text may not enumerate the realized topology.
- If execution eligibility is `REJECTED`, identify the unsafe APDL evidence and do not execute the model.
- If it is `INCOMPLETE`, explain which structural signals are missing.
- If static inspection and bundle integrity permit it, call `fem_solver_preflight` with `solver: ansys`. Preflight stages a sanitized Model Bundle and stops before `/SOLU`, `SOLVE`, or postprocessing so the requested analysis is not performed.

### OpenSees Python Model Bundle

- Treat the model as a `Model Bundle`, not merely the entrypoint `.py` file.
- Use `bundle.bundleFingerprint` plus the ordered bundle file hashes as the model identity for later runs and evidence.
- Review `bundle.integrity` and dependency statuses before solver preflight. A dependency that resolves outside the active workspace is blocked; do not execute that bundle.
- Static AST inspection establishes source-level facts such as OpenSees imports/calls, dependency references, dynamic construction signals, and safety findings. It does not prove realized node/element topology.
- If static inspection is safe enough to proceed and realized topology matters, call `fem_solver_preflight` with `solver: opensees`. Preflight performs isolated build-only inspection and intercepts `ops.analyze()` so model construction can be observed without advancing the requested analysis.
- Treat build-only node/element tags and coordinates as realized solver-domain evidence. Keep them distinct from AST observations.

## Engineering semantics

Component, variable, function, file, module, and APDL component names are hints, not authoritative engineering roles. A name such as `GIRDER`, `TOWER`, or `bearing_nodes` does not by itself prove that role.

Do not assume X/Y/Z mean longitudinal/transverse/vertical unless that convention is established by project context or the user.

## Boundary

This skill guides reasoning only. Parsing and bundle discovery come from deterministic FEM tools; realized model evidence comes from solver-specific build inspection; numerical results come from actual solver execution and later Result Intelligence. Never replace any of those evidence sources with an LLM inference.
