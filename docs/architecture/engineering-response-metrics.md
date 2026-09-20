# Engineering Response Metrics V1

## Layer position

PR34 sits above Result Intelligence and Engineering Semantic Roles:

```text
Completed solver run
        |
        v
Result Intelligence
 verified scalar channels
        |
        +--------------------+
        |                    |
        v                    v
Semantic Role Manifest   Result SERIES/SUMMARY
 explicit NODE/ELEMENT        |
 roles                        |
        +----------+----------+
                   |
                   v
        Engineering Response Metrics
```

The metric layer is read-only and solver-neutral. Numerical authority remains the recorded solver artifact plus deterministic Result Intelligence readers.

## Supported metrics

### ROLE_ABSOLUTE_PEAK

Maps one explicit engineering role to one recorded scalar response and returns the standard Result Intelligence absolute peak.

Examples:

- `GIRDER_END_RIGHT + DISPLACEMENT X`
- `TOWER_BASE_LEFT + REACTION_FORCE X`
- `TOWER_BASE_ELEMENT + GENERALIZED_FORCE VY @ END_I`

An ELEMENT generalized force is available only when Result Intelligence already exposes an explicit formulation/location mapping. PR34 does not invent ANSYS element-force mappings.

### ROLE_RELATIVE_DISPLACEMENT_PEAK

For two explicit NODE roles:

```text
u_relative(t) = u_target(t) - u_reference(t)
```

The histories must match exactly in unit, reference frame, abscissa semantics, abscissa unit, sample count, and every abscissa value.

No interpolation or resampling is performed.

### ROLE_GROUP_REACTION_RESULTANT_PEAK

For one or more explicit NODE roles:

```text
Rx_total(t) = Σ Rx_i(t)
Ry_total(t) = Σ Ry_i(t)
R(t) = sqrt(Rx_total(t)^2 + Ry_total(t)^2)
```

PR34 reports the peak of `R(t)` and retains the signed X/Y sums at that same sample.

This is intentionally **not**:

```text
Σ sqrt(Rx_i^2 + Ry_i^2)
```

because that would discard cancellation and change the engineering meaning of a total support reaction.

## Full-series paging

Result Intelligence bounds one SERIES query page to 5000 samples.

PR34 composite metrics page through the complete recorded series in 5000-sample chunks. Every page must retain the same response identity and declared total. A zero-length page before the declared end or a changing total is rejected.

This means a long earthquake record is not silently truncated at 5000 samples.

## Semantic identity

Roles are not inferred.

The Semantic Role Manifest must match the exact Model Bundle fingerprint. The completed run must expose the same bundle fingerprint before any metric is promoted.

A declared role may be statically confirmed or not statically enumerable according to the existing Semantic Role contract; PR34 retains that provenance unchanged.

## Units and axes

PR34 performs no unit conversion.

- equal known units may be combined;
- equal unknown units (`null`) may be numerically combined while remaining `null`;
- known/unknown or unequal units are incompatible composite series.

X/Y/Z remain solver/model coordinate components. PR34 does not call X longitudinal, Y transverse, or Z vertical unless separate project evidence establishes that convention.

## Failure behavior

Request/schema and model-identity failures are hard errors.

Within a valid batch, an unavailable metric channel is isolated:

```text
some metrics computed + one unavailable
        ->
status = LIMITED
computed metrics retained
issue emitted for unavailable metric
```

No substitute channel or zero value is fabricated.

## Engineering judgment boundary

PR34 reports response metrics only. It does not decide whether a response is acceptable.

Design-code limits, serviceability limits, seismic performance levels, damper stroke limits, and other PASS/FAIL rules require a separate explicit acceptance contract.
