# PR32 — Controlled Repair & Recovery Design

## Purpose

PR32 adds a fail-closed recovery layer above PR31. It diagnoses a blocked earthquake workflow, emits only typed repair actions, applies only user-confirmed resolutions, then reruns the existing deterministic preparation chain.

It never edits source model/load files and never starts a real solver.

```text
PR31 blocked preparation
        ↓
controlled repair plan
        ↓
typed actions
        ↓
user/operator resolution
        ↓
deterministic patch of workflow input only
        ↓
PR31 prepare again
        ↓
READY_FOR_CONFIRMATION or still blocked
```

## Repair classes

V1 recognizes:

- missing damping;
- missing excitation component;
- missing result component;
- missing ANSYS model path;
- missing OpenSees excited-direction nodal mass;
- canonical load/context conflicts;
- semantic-role missing/ambiguity;
- unrestrained reaction request;
- solver unavailable/build-preflight failures;
- invalid/tampered context.

## Allowed automatic input transformations

Only after an explicit resolution:

- add explicit NONE damping with exact source quote;
- add explicit Rayleigh alphaM/betaK with exact source quote;
- add/replace explicit X/Y excitation component with exact source quote;
- set a missing result component with exact source quote and fact index;
- replace the full ModelSpec with a user-supplied ModelSpec;
- replace the canonical load artifact path with a user-selected path;
- provide/replace ANSYS solverModelPath.

No numeric mass is invented. No constraint is invented. No semantic role is guessed. No load is generated. No solver is executed.

Semantic ambiguity remains a clarification action in V1: the user must update the requirement/semantic context so PR30 can resolve deterministically.

## Integrity

A repair plan records canonical fingerprints of:

- original workflow input;
- failed preparation;
- ordered action set.

Retry recomputes the plan and rejects stale/tampered plan fingerprints.

## Statuses

Repair plan:

- NO_REPAIR_NEEDED
- USER_ACTION_REQUIRED
- OPERATOR_ACTION_REQUIRED
- MANUAL_ENGINEERING_CHANGE_REQUIRED
- UNSUPPORTED_FAILURE

Retry:

- RECOVERED_TO_READY
- RETRY_STILL_BLOCKED
- INVALID_RESOLUTION

Real execution remains exclusively on existing permission-gated `fem_solver_run`.
