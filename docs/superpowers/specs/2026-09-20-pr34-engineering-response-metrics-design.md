# PR34 — Engineering Response Metrics V1 Design

## Purpose

PR34 adds a deterministic engineering-metric layer above Result Intelligence and explicit Engineering Semantic Roles.

It answers engineering questions such as:

- 梁端 X 向位移峰值 / girder-end X displacement peak;
- 塔底 X 向反力峰值 / tower-base horizontal reaction peak;
- 塔底构件端剪力峰值 when a recorded ELEMENT generalized-force channel exists;
- one bearing/support reaction resultant;
- total reaction resultant of several explicitly declared supports;
- relative displacement peak between two explicitly declared NODE roles.

PR34 is read-only. It never executes a solver, never changes a model, never creates semantic roles, and never makes code/check PASS/FAIL judgments.

## Trust boundary

A metric may use an engineering role only when:

1. the role is explicitly present in a valid Semantic Role Manifest;
2. that manifest matches the exact current Model Bundle fingerprint;
3. the completed run exposes the same Model Bundle fingerprint;
4. Result Intelligence validates the recorded result artifact;
5. every numerical channel used by the metric is actually queryable.

Coordinates, names, constraints, topology, LLM guesses, and result magnitudes never create roles.

## Public request

Schema:

`FEMAGENT_ENGINEERING_RESPONSE_METRIC_REQUEST_V1`

Request context:

- `runRef`
- `modelPath`
- `semanticManifestPath`
- non-empty `metrics`

Metric IDs are unique `^[A-Za-z][A-Za-z0-9_-]{0,63}$`.

## Metric types

### 1. ROLE_ABSOLUTE_PEAK

One explicit semantic role and one recorded scalar response channel.

Supported identities:

- NODE: DISPLACEMENT, VELOCITY, ACCELERATION, RELATIVE_ACCELERATION, REACTION_FORCE, REACTION_MOMENT;
- ELEMENT: GENERALIZED_FORCE with explicit END_I / END_J / SECTION location.

The metric delegates numerical extrema to Result Intelligence SUMMARY.

Output retains:

- absolutePeak;
- min/max;
- abscissaAtAbsolutePeak;
- unit;
- referenceFrame;
- target/quantity/component/location;
- semantic-role provenance.

### 2. ROLE_RELATIVE_DISPLACEMENT_PEAK

Two distinct explicit NODE roles:

- targetRoleId;
- referenceRoleId;
- component X or Y.

At every exactly aligned recorded sample:

`relative = target displacement - reference displacement`

No interpolation, resampling, phase shifting, or coordinate transformation is allowed.

Output includes the signed value at the absolute peak and the absolute peak magnitude.

### 3. ROLE_GROUP_REACTION_RESULTANT_PEAK

One or more distinct explicit NODE role IDs and components exactly `["X","Y"]`.

For each recorded sample:

`sumX = Σ reaction_X(role_i)`

`sumY = Σ reaction_Y(role_i)`

`resultant = sqrt(sumX^2 + sumY^2)`

The metric reports the maximum resultant and the signed component sums at that sample.

This supports both:

- one support/bearing reaction resultant;
- total resultant over several explicitly declared supports.

It is a vector sum of simultaneous signed reactions, not a sum of individual magnitudes.

## Series compatibility

Composite metrics require every input series to have exactly compatible:

- runId and caseFingerprint;
- unit (including null == null only);
- referenceFrame;
- abscissa semantic;
- abscissa unit;
- total sample count;
- every abscissa value.

No unit conversion is performed. Unknown ANSYS units remain null.

PR34 pages Result Intelligence SERIES requests in bounded chunks and verifies the reported total on every page. It does not truncate a metric at the normal 5000-sample query-page limit.

## Batch behavior

Context/schema/semantic-model/run-model identity failures are hard errors.

Individual metric channel-availability/mapping failures are isolated:

- successful metrics are retained;
- failed metrics become issues;
- report status is `COMPLETED` when all metrics compute;
- report status is `LIMITED` when at least one requested metric cannot be computed.

No zero or substitute value is fabricated.

## Output

Schema:

`FEMAGENT_ENGINEERING_RESPONSE_METRICS_V1`

The report records:

- run identity;
- semantic manifest identity;
- metric results;
- per-metric issues;
- no engineering acceptance verdict.

## Non-goals

- automatic role inference;
- automatic role-manifest creation;
- unit conversion;
- axis transformation;
- interpolation/resampling;
- code compliance;
- acceptance thresholds;
- response-spectrum metrics;
- fatigue/fracture metrics;
- optimization objective ranking;
- solver execution.


## Agent integration

PR34 adds one SAFE read-only Agent tool:

`fem_response_metrics_compute`

Because metric requests must use explicit role IDs rather than inferred engineering meaning, the default Agent surface also exposes the existing SAFE semantic inspection/resolution tools:

- `fem_semantic_inspect`
- `fem_semantic_resolve`

This does not add semantic-role creation or inference.
