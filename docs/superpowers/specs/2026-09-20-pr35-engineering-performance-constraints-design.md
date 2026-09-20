# PR35 — Engineering Performance Constraints V1 Design

## Purpose

PR35 adds a deterministic engineering constraint/performance-evaluation layer above PR34 Engineering Response Metrics.

It answers:

- is the girder-end displacement peak within an explicitly supplied limit?
- is damper deformation/stroke within an explicitly supplied allowable value?
- is damper peak force within an explicitly supplied allowable value?
- are support/tower reaction or recorded member-force peaks within explicit limits?
- does one run satisfy the complete conjunction of declared engineering constraints?

PR35 does not choose limit values, infer code clauses, execute solvers, or optimize parameters.

## Architecture

```text
completed solver run
      +
explicit Semantic Role Manifest
      +
PR34 metric requests
      +
explicit performance constraints
              |
              v
Engineering Performance Evaluation
              |
      +-------+-------+
      |               |
      v               v
metric evidence   limit contract
      |               |
      +-------+-------+
              |
              v
 SATISFIED / VIOLATED / NOT_EVALUABLE
              |
              v
 FEASIBLE / INFEASIBLE / LIMITED
```

## Request contract

Schema:

`FEMAGENT_ENGINEERING_PERFORMANCE_REQUEST_V1`

Fields:

- `metricsRequest`: complete PR34 request;
- `constraints`: non-empty list of explicit constraints.

Every constraint has:

- unique `constraintId`;
- `metricId` referring to exactly one requested PR34 metric;
- `operator = MAXIMUM`;
- finite non-negative `limit`;
- explicit `unit`;
- optional human-readable `label`.

V1 intentionally supports upper-bound constraints only because the immediate engineering scope is displacement, force, reaction, member-force, and device stroke/output limits.

No hidden numerical tolerance is applied:

```text
SATISFIED iff observedAbsolutePeak <= limit
VIOLATED  iff observedAbsolutePeak >  limit
```

A project that requires a tolerance must encode it in the explicit limit value.

## Unit rule

A constraint is evaluable only when the PR34 metric has a known unit and it exactly equals the declared constraint unit.

No conversion is performed.

Examples:

- metric unit `m`, constraint unit `m` -> comparable;
- metric unit `N`, constraint unit `kN` -> NOT_EVALUABLE;
- metric unit `null`, constraint unit `N` -> NOT_EVALUABLE.

This keeps unknown ANSYS solver-native units from being silently interpreted.

## Evaluation status

Each constraint is:

- `SATISFIED`;
- `VIOLATED`;
- `NOT_EVALUABLE`.

Overall:

### FEASIBLE

All declared constraints are evaluable and SATISFIED.

### INFEASIBLE

At least one declared constraint is evaluable and VIOLATED.

This remains INFEASIBLE even if another constraint is unavailable: one proven violation is sufficient to prove that the full conjunction cannot be feasible.

### LIMITED

No violation is proven, but at least one declared constraint is NOT_EVALUABLE.

## Performance fields

For every evaluable constraint PR35 reports:

- observed absolute peak;
- limit;
- exact unit;
- utilization ratio `observed / limit` when limit > 0;
- reserve `limit - observed`;
- peak abscissa;
- metric/semantic provenance.

For limit = 0:

- ratio is `0` when observed = 0;
- ratio is `null` when observed > 0;
- comparison remains exact and deterministic.

No qualitative engineering rating is created.

## Governing constraint

When all constraints are evaluable, PR35 may expose a deterministic `governingConstraint`:

- constraint with maximum utilization when all positive-limit ratios exist;
- otherwise the smallest reserve.

This is descriptive only. It does not rank design alternatives.

When any constraint is NOT_EVALUABLE, governingConstraint is null because the complete constraint set has not been observed.

## PR34 extension for device constraints

PR35 extends PR34 `ROLE_ABSOLUTE_PEAK` to support recorded:

`DAMPER_RESPONSE`

components:

- `FORCE`;
- `DEFORMATION`;
- `VELOCITY`;
- `DISSIPATED_ENERGY`.

The role must be an explicit ELEMENT role. PR35/PR34 do not create a damper channel; it must already be exposed by Result Intelligence.

This enables explicit limits such as damper maximum force and deformation/stroke without adding solver-specific postprocessing guesses.

## Batch/partial behavior

PR34 may return `LIMITED` while retaining computed metrics.

PR35 joins constraints by `metricId`:

- computed referenced metric -> evaluate if unit matches;
- missing/failed referenced metric -> NOT_EVALUABLE;
- unknown constraint metricId -> invalid request.

A metric may exist without a constraint; it remains supporting evidence but does not affect feasibility.

Every constraint must reference one requested metric.

## Determinism and fingerprints

PR35 reports:

- PR34 `requestFingerprint`;
- a canonical `constraintSetFingerprint`;
- a canonical `evaluationFingerprint` over metric request identity + normalized constraints + run/case identity.

Constraint ordering does not change the fingerprints.

## Safety boundary

PR35 does not:

- discover code limits;
- infer allowable displacement or force;
- perform unit conversion;
- infer structural roles;
- transform coordinate systems;
- interpolate/resample series;
- execute ANSYS/OpenSees;
- repair a failed model;
- change device parameters;
- optimize a design;
- claim code compliance beyond the exact supplied numerical constraints.

`FEASIBLE` means only: all explicit PR35 numerical constraints in this request are satisfied.

It does not mean a structure is generally safe or code-compliant.

## Future optimization boundary

PR35 is designed to become the feasibility oracle for a later parameter-search/optimization layer:

```text
candidate parameters
      ↓
solver run
      ↓
PR34 metrics
      ↓
PR35 deterministic constraints
      ↓
FEASIBLE / INFEASIBLE
```

The optimizer itself is not part of PR35.


## Agent integration

PR35 adds one SAFE read-only Agent tool:

`fem_performance_evaluate`

The tool requires a complete PR34 metric request plus explicit upper-bound constraints. Its prompt contract forbids inventing code limits, allowable displacement, device stroke, force capacity, units, or solver execution.

The existing semantic inspection tools remain the only supported way for the Agent to discover declared role IDs. No semantic-role inference is introduced.
