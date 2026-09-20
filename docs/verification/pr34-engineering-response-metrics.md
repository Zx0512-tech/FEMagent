# PR34 Verification — Engineering Response Metrics V1

## Implementation head

- head: `0017ea8aaf83b220938e1c4bbe02fc1df4b83ef7`
- CI: #721
- run id: `35507428681`
- conclusion: SUCCESS
- TypeScript tests: 73 passed
- Python tests: 504 passed, 9 warnings
- Ruff: passed
- OpenSees adapter smoke: passed
- ANSYS result-reader smoke: passed
- FEM health smoke: passed

## Verified behavior

### Explicit engineering identity

Metric computation requires:

1. a valid explicit Semantic Role Manifest;
2. exact manifest/current-model bundle binding;
3. exact completed-run/current-semantic-model bundle binding;
4. VALID Result Intelligence artifact integrity.

No role is created from coordinates, names, constraints, topology, response magnitude, or LLM interpretation.

### Scalar role peaks

Fixture-backed tests prove:

- GIRDER_END NODE displacement absolute peak;
- TOWER_BASE ELEMENT generalized-force shear peak with explicit `END_I`;
- role/entity type mismatch fails instead of substituting another result identity.

### Relative displacement

PR34 computes:

`target - reference`

from complete recorded NODE displacement histories.

Tests prove signed peak value, peak magnitude, peak time, and exact sample count.

### Reaction resultant

PR34 computes simultaneous signed support reactions:

`sqrt((ΣRx)^2 + (ΣRy)^2)`

Tests cover:

- one support/tower-base resultant;
- multiple-role total reaction resultant;
- signed component sums retained at the resultant peak.

### Exact alignment / no resampling

Composite metrics require identical:

- run and case identity;
- units;
- reference frame;
- abscissa semantic/unit;
- sample count;
- every abscissa value.

A deliberately shifted Y-reaction time sample returns a LIMITED metric issue with `ENGINEERING_RESPONSE_METRIC_SERIES_MISMATCH`; no interpolation occurs.

### Long histories

A 5001-sample relative-displacement test crosses the Result Intelligence 5000-sample page boundary and proves that PR34 assembles the full series rather than truncating it.

### Partial batch behavior

When one requested channel is unavailable:

- valid metrics remain in the report;
- the missing metric is represented by an issue;
- status becomes `LIMITED`;
- no zero/substitute result is created.

### Artifact integrity

A post-run edit to the recorded structural-response artifact is rejected through the existing Result Intelligence SHA-256 check before metric promotion.

### TypeScript / Agent surface

The TypeScript bridge test proves the public metrics client crosses the strict Python bridge and returns deterministic metric values.

The Agent exposes:

- `fem_response_metrics_compute` — SAFE/read-only;
- existing `fem_semantic_inspect` and `fem_semantic_resolve` — SAFE/read-only role discovery/resolution.

No new solver execution shortcut exists.

## Scope audit

Production changes are limited to:

- new read-only engineering-response metric computation;
- bridge command;
- TypeScript metric contracts/client;
- one SAFE metric Agent tool;
- exposing existing SAFE semantic inspection/resolution tools in the default Agent surface.

PR34 does not change:

- ANSYS numerical execution;
- OpenSees numerical execution;
- PR29 load/damping/time-control mathematics;
- PR30 natural-language AnalysisSpec completion;
- PR31 solver execution orchestration;
- PR32 repair mutation rules;
- PR33 deterministic ANSYS rendering;
- existing Result Intelligence numerical readers;
- semantic role inference;
- unit conversion;
- interpolation/resampling;
- engineering acceptance judgments;
- optimization.

## Final-head rule

This verification/architecture closeout is documentation-only. PR34 moves to Ready for Review only after the exact final documentation head passes the full CI suite.
