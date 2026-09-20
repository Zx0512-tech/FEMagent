# Engineering Performance Constraints V1

## Layer position

PR35 turns verified engineering-response metrics into an explicit numerical feasibility decision:

```text
Solver result artifacts
        ↓
Result Intelligence
        ↓
Engineering Semantic Roles
        ↓
PR34 Engineering Response Metrics
        ↓
PR35 Explicit Performance Constraints
        ↓
FEASIBLE / INFEASIBLE / LIMITED
```

PR35 is a deterministic comparison layer. It is not a solver, optimizer, code-check engine, or limit-retrieval system.

## Constraint contract

V1 supports only inclusive upper bounds:

```text
observed absolutePeak <= explicit limit
```

Each constraint references one PR34 `metricId` and supplies:

- `constraintId`;
- `metricId`;
- `operator = MAXIMUM`;
- finite non-negative `limit`;
- explicit `unit`;
- optional `label`.

No tolerance is hidden inside the evaluator.

## Unit boundary

The metric unit must be known and exactly equal to the constraint unit.

PR35 performs no conversion.

Therefore:

```text
0.03 m <= 0.04 m   → evaluable
30 mm <= 0.04 m    → not compared by PR35
unit=null           → NOT_EVALUABLE
```

This deliberately prevents unproven ANSYS solver-native units from being promoted into physical-code checks.

## Status semantics

Per constraint:

- `SATISFIED`
- `VIOLATED`
- `NOT_EVALUABLE`

Overall:

- `FEASIBLE`: all explicit constraints are SATISFIED;
- `INFEASIBLE`: at least one explicit constraint is VIOLATED;
- `LIMITED`: no violation is proven, but one or more constraints are NOT_EVALUABLE.

A proven violation dominates missing information because the conjunction of all constraints is already known to be infeasible.

## Utilization and reserve

For positive limits:

```text
utilization = observed / limit
reserve     = limit - observed
```

For a zero limit:

- observed = 0 → utilization = 0;
- observed > 0 → utilization = null and the constraint is VIOLATED.

The comparison itself is still exact.

## Governing constraint

When every constraint is evaluable, PR35 exposes a descriptive governing constraint.

Normally this is the maximum-utilization constraint. If a zero-limit case prevents a complete utilization comparison, the smallest reserve is used.

If any constraint is NOT_EVALUABLE, the governing constraint is omitted because the full constraint set has not been observed.

This is not a ranking of alternative designs.

## Damper/device metrics

PR35 extends PR34 scalar role peaks with recorded `DAMPER_RESPONSE` channels:

- FORCE;
- DEFORMATION;
- VELOCITY;
- DISSIPATED_ENERGY.

The role must be an explicit ELEMENT role and the response must already exist in Result Intelligence.

This enables constraints such as:

```text
damper peak deformation <= allowable stroke
damper peak force       <= allowable output force
```

without solver-specific guessing.

## Fingerprints

PR35 exposes:

- PR34 metric request fingerprint;
- constraint-set fingerprint;
- evaluation fingerprint.

Constraint order does not change the constraint-set or evaluation fingerprint.

The evaluation fingerprint also binds the recorded run/case/model identity used for the decision.

## Trust boundary

PR35 inherits PR34's existing checks:

- explicit Semantic Role Manifest;
- exact semantic/current-model bundle binding;
- exact completed-run/model bundle binding;
- verified result artifact hashes;
- exact recorded response identities.

A tampered result artifact fails before constraint evaluation.

## Meaning of FEASIBLE

`FEASIBLE` has a deliberately narrow meaning:

> Every explicit numerical constraint supplied in this PR35 request was evaluable and satisfied.

It does not mean:

- globally structurally safe;
- design-code compliant;
- acceptable under unrequested load cases;
- optimized;
- constructible;
- robust to modeling uncertainty.

Those require separate explicit contracts.

## Optimization boundary

PR35 provides the deterministic feasibility oracle needed by a later optimization layer:

```text
candidate parameter set
        ↓
controlled solver execution
        ↓
PR34 response metrics
        ↓
PR35 explicit constraints
        ↓
candidate FEASIBLE / INFEASIBLE
```

Parameter generation, surrogate models, Pareto search, and design ranking remain outside PR35.
