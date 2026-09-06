# Structural Response Intelligence V1

## Status

PR15 introduces a deterministic structural-response layer on top of FEMagent's existing Model Intelligence, solver adapters, Result Intelligence, Engineering Evidence, Semantic Roles, and Cross-Solver Validation.

The layer does not turn the LLM into a finite-element postprocessor. Solver-specific readers and controlled recorders remain the numerical authority; the agent may only reason from normalized, artifact-backed outputs.

## Data flow

```text
Explicit model + optional response plan
              |
              v
        Solver Adapter
       /              \
  ANSYS MAPDL       OpenSeesPy
      |                 |
 recorded .rst     controlled recorder
      |                 |
      +------ structural response artifact
                          |
                  Result Intelligence
                          |
                  Engineering Evidence
                          |
              NODE / ELEMENT Semantic Role
                          |
               Cross-Solver Validation
```

## Canonical structural query contract

Structural queries preserve four pieces of identity:

- target: `NODE` or `ELEMENT` plus positive solver-native ID;
- quantity;
- component;
- optional location when the response definition requires it.

Operations remain `SUMMARY` or bounded `SERIES`.

### NODE quantities

Existing nodal channels remain supported through their existing contracts:

- `DISPLACEMENT`
- `VELOCITY`
- `ACCELERATION`
- `REACTION_FORCE`

PR15 adds vocabulary for:

- `REACTION_MOMENT`
- `STRESS`
- `PRINCIPAL_STRESS`

`REACTION_MOMENT` is vocabulary, not a promise that every recorded result exposes rotational reactions. A solver/result reader advertises it only when the artifact proves that channel.

### Stress components

Canonical tensor components:

- `SX`, `SY`, `SZ`
- `SXY`, `SYZ`, `SXZ`

Canonical principal/equivalent components:

- `S1`, `S2`, `S3`
- `SINT`
- `SEQV`

Stress location/averaging semantics are evidence metadata. `NODAL_AVERAGED` and element-nodal/native stress are not silently treated as equivalent.

### ELEMENT generalized force

Canonical components:

- `N`
- `VY`, `VZ`
- `T`
- `MY`, `MZ`

Canonical location is explicit:

- `END_I`
- `END_J`
- `SECTION`

A generalized-force query cannot omit a required location. FEMagent never assumes that solver-native vector positions map to this vocabulary without a formulation-specific mapping proven by deterministic code and regression tests.

### Damper response vocabulary

The controlled vocabulary includes:

- `FORCE`
- `DEFORMATION`
- `VELOCITY`
- `DISSIPATED_ENERGY`

This vocabulary does not create a result channel. The channel must be directly recorded or deterministically derivable from complete compatible evidence. PR15 does not use peak-force times peak-stroke as an energy substitute and does not interpolate mismatched histories.

## ANSYS acquisition boundary

ANSYS structural responses are extracted from a recorded MAPDL binary result artifact using `ansys-mapdl-reader`.

PR15 proves the following reader path with packaged real `.rst` data:

- nodal averaged Cartesian stress;
- principal stress;
- stress intensity;
- von Mises/equivalent stress.

### ANSYS unit rule

ANSYS binary values remain `unit: null` unless the recorded run/result contract independently proves the model unit system. Result magnitude, APDL conventions, file names, or LLM judgment are not sufficient evidence of physical units.

### ANSYS element-stress boundary

The legacy reader may return multiple element-nodal stress values for one element. PR15 does not collapse that matrix to a scalar by implicit averaging, maximum selection, or location guessing.

When the requested canonical identity is not sufficiently specified, Result Intelligence fails closed with a stable structural-response error instead of inventing a scalar.

### ANSYS generalized-force boundary

PR15 does not claim generic ANSYS `N/V/M/T` extraction. Element formulations encode result vectors differently. Until a formulation-specific mapping is explicitly proven, generalized-force extraction is unavailable and fails closed with `STRUCTURAL_RESPONSE_MAPPING_UNAVAILABLE`.

## OpenSees acquisition boundary

OpenSees differs from an ANSYS `.rst`: many element responses must be captured during analysis. PR15 therefore adds an explicit Structural Response Plan.

### Structural Response Plan

The plan is workspace-local UTF-8 JSON with a fixed schema and a non-empty ordered channel list. Each channel contains canonical target/quantity/component/location identity.

The loader rejects:

- unsupported schema/kind;
- duplicate channel IDs;
- arbitrary `recorder`, `command`, or `args` fields;
- invalid canonical response identities;
- empty plans.

The exact plan bytes are hashed and recorded as provenance.

### Controlled runtime recording

PR15 does not inject caller-authored OpenSees recorder commands. The isolated OpenSees worker wraps the controlled analysis boundary, validates each requested mapping before numerical advancement, and samples only a mapping registered by deterministic FEMagent code.

V1 includes a proven two-dimensional elastic beam mapping for OpenSees `localForce`, exercised in CI with a real OpenSeesPy `ElasticBeam2d`/`elasticBeamColumn` element. The mapping preserves element-local end identity such as `MZ @ END_I`.

Unsupported formulations such as an unproven `zeroLength` generalized-force mapping are rejected before analysis rather than interpreted heuristically.

### Structural response artifact

Recorded channels are written to a deterministic `structural_response.json` artifact. The run manifest records:

- response-plan path and SHA256;
- structural-response artifact path and SHA256.

Result Intelligence verifies the declared artifact hash before advertising or querying structural values.

## Result Intelligence integration

Result Intelligence normalizes supported structural results into the existing result-query shape, preserving:

- quantity;
- target;
- component;
- location when present;
- stress location/averaging semantics when present;
- unit;
- reference frame;
- abscissa semantic/unit;
- summary or bounded series;
- source artifact.

`SUMMARY` retains the standard fields:

- `sampleCount`
- `min`
- `max`
- `absolutePeak`
- `abscissaAtAbsolutePeak`

Artifact hash mismatch remains a hard error before numerical promotion.

## Engineering Evidence integration

PR15 does not add a second evidence system. Structural results pass through the existing Engineering Evidence Center.

Evidence projection now retains structural identity fields such as `location` and stress semantics. Artifact selection follows the actual Result Intelligence source artifact: an OpenSees structural response claim binds to the verified `structural_response.json`, not an unrelated legacy `response.csv`.

Evidence verification status rules are unchanged.

## Semantic Roles: NODE and ELEMENT

Engineering Semantic Role Manifests now permit explicit entities of type:

- `NODE`
- `ELEMENT`

Examples:

```text
TOWER_BASE_LEFT -> NODE 1024
GIRDER_MIDSPAN  -> ELEMENT 41
DAMPER_LEFT     -> ELEMENT 875
```

The trust model remains unchanged:

1. role mappings are explicit user/project declarations;
2. the manifest is bound to an exact Model Bundle fingerprint;
3. static existence is confirmed only when Model Intelligence can completely enumerate the relevant entity type;
4. non-enumerable topology remains explicit rather than guessed.

No component-name, coordinate, constraint, connectivity, or LLM heuristic is promoted to a resolved role.

## Cross-Solver Validation integration

Cross-Solver Validation continues to compare two independently verified role-backed Evidence records.

For structural responses, compatibility additionally requires exact identity for:

- canonical quantity/component/operation;
- explicit location when present;
- stress location/averaging semantics;
- reference frame;
- known and equal units.

Different solver-native NODE/ELEMENT IDs are allowed when both sides resolve the same explicit semantic role.

Cross-Solver Validation still performs no unit conversion, reference-frame transform, tolerance judgment, solver ranking, or automatic engineering PASS/FAIL.

## TypeScript and Pi surfaces

TypeScript exposes controlled NODE/ELEMENT structural request unions and `responsePlanPath` as a path-only solver option.

Read-only Pi tools include dedicated structural response inspection/query surfaces plus ELEMENT-aware semantic and cross-solver tools. These tools have no solver-execution permission and explicitly forbid inventing entity IDs, units, locations, local-axis mappings, averaging rules, or unsupported result channels.

Solver execution remains permission-gated through the existing solver tool. For OpenSees PR15, `solverOptions.responsePlanPath` is the only new structural option; it points to the strict JSON plan and is not a free-form recorder interface. ANSYS `modelUnits` and OpenSees `responsePlanPath` remain solver-specific and are rejected when supplied to the wrong contract.

## V1 exclusions

Structural Response Intelligence V1 intentionally excludes:

- generic ANSYS element-force mapping across arbitrary element formulations;
- silent element stress averaging or extrema collapse;
- hidden unit inference/conversion;
- coordinate/reference-frame transformation;
- time-history resampling/interpolation;
- arbitrary OpenSees recorder or command injection;
- automatic engineering-role inference;
- automatic stress/code compliance checks;
- fatigue/fracture assessment;
- optimization;
- solver ranking;
- implicit acceptance tolerances or PASS/FAIL judgments.

These exclusions are fail-closed boundaries, not missing numerical values to be filled by the LLM.
