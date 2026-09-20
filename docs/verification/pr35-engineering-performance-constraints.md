# PR35 Verification — Engineering Performance Constraints V1

## Implementation head

- implementation head: `e8566ff27f30f987487f4d403540a6426a844f5f`
- CI: #736
- run id: `35508441209`
- conclusion: SUCCESS
- TypeScript tests: 75 passed
- Python tests: 516 passed, 9 warnings
- Ruff: passed
- OpenSees availability smoke: passed
- ANSYS result-reader smoke: passed
- FEM health smoke: passed

## Verified behavior

### Explicit upper-bound constraints

Tests cover deterministic `MAXIMUM` evaluation with:

```text
SATISFIED iff absolutePeak <= limit
VIOLATED  iff absolutePeak >  limit
```

Exact equality is SATISFIED; there is no hidden tolerance.

### FEASIBLE

A combined constraint set containing:

- girder displacement limit;
- damper deformation/stroke limit;
- damper force limit;

returns FEASIBLE when every referenced PR34 metric is computed, every unit matches exactly, and every peak is below its limit.

### INFEASIBLE

A damper force peak of 150 N against an explicit 100 N limit returns:

- VIOLATED;
- utilization = 1.5;
- reserve = -50 N;
- overall status = INFEASIBLE.

A proven violation still makes the conjunction INFEASIBLE when another constraint is NOT_EVALUABLE.

### LIMITED

Tests prove LIMITED when:

- metric unit is `m` but the explicit limit uses `mm`;
- metric unit is unknown/null;
- a requested PR34 response channel was not recorded.

No unit conversion, inferred unit, zero substitute, or alternate channel is used.

### Zero limit

A recorded zero response against a zero limit is SATISFIED with utilization 0 and reserve 0.

### Damper response

PR34 is extended and tested for explicit ELEMENT-role `DAMPER_RESPONSE`:

- FORCE;
- DEFORMATION.

The same production path supports the existing controlled vocabulary for VELOCITY and DISSIPATED_ENERGY when those channels are actually recorded.

No damper result channel is invented by PR35.

### Fingerprint determinism

Reordering constraints leaves:

- `constraintSetFingerprint`;
- `evaluationFingerprint`;

unchanged.

### Unknown metric references

A constraint referencing a metricId that was not requested by the embedded PR34 request is rejected as an invalid PR35 request.

### Artifact integrity

Post-run mutation of `structural_response.json` propagates the existing Result Intelligence SHA-256 mismatch before any constraint is evaluated.

### TypeScript / Agent

The TypeScript bridge test executes a real PR35 request through the strict Python bridge and verifies FEASIBLE output and governing-constraint identity.

The new Agent tool is:

`fem_performance_evaluate`

It is SAFE/read-only and explicitly forbids:

- limit inference;
- unit conversion;
- solver execution;
- model repair;
- parameter mutation;
- optimization.

## Scope audit

Relative to PR34, production changes are limited to:

- explicit performance-constraint evaluator;
- PR34 DAMPER_RESPONSE scalar-peak extension;
- bridge command;
- TypeScript request/report/client contracts;
- one SAFE Agent tool and registration.

PR35 does not change:

- ANSYS numerical execution;
- OpenSees numerical execution;
- load generation;
- damping/time-integration mathematics;
- natural-language AnalysisSpec completion;
- controlled repair;
- deterministic ANSYS ModelSpec rendering;
- Result Intelligence readers;
- semantic-role inference;
- unit conversion;
- interpolation/resampling;
- optimization algorithms.

## Final-head rule

This closeout commit changes documentation only. PR35 moves to Ready for Review only after the exact final documentation head passes the complete CI suite.
