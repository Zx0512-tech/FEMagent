# ANSYS Canonical Load Application V1

PR10 defines FEMagent's first deterministic external-load application contract for ANSYS MAPDL.

## Supported canonical contract

ANSYS canonical injection accepts exactly one `FEMAGENT_LOAD_CSV_V1` channel with:

- `load_kind = EARTHQUAKE`
- `application_type = UNIFORM_EXCITATION`
- `quantity = ACCELERATION`
- canonical unit `m/s2`
- global Cartesian component X, Y, or Z (including supported aliases)
- no node/element target
- at least two finite samples with strictly increasing `time_s`

Multi-channel excitation, nodal-force matrices, response-spectrum input, rotational excitation, and mode-superposition-specific load vectors are outside PR10.

## Why ANSYS model units must be declared

MAPDL is unitless. A canonical SI acceleration cannot be safely injected unless the model's length and time units are known from deterministic project or user evidence.

When an ANSYS `loadPath` is supplied, pass:

```json
{
  "solverOptions": {
    "modelUnits": {
      "length": "m | cm | mm",
      "time": "s | ms"
    }
  }
}
```

FEMagent never infers these units from coordinates, material magnitudes, file names, common practice, or load magnitude.

Conversion is deterministic:

- `time_model = time_s * timeUnitsPerSecond`
- `accel_model = accel_m_s2 * lengthUnitsPerMeter / timeUnitsPerSecond^2`

## Generated artifacts

For an accepted load FEMagent generates, inside the staged run/build workspace only:

- `femagent_load_table.txt`
- `femagent_load.mac`

The macro defines a TABLE with `*DIM`, reads the table using `*TREAD`, and applies the selected component through `ACEL`.

No implicit sign inversion is introduced. Canonical support/reference-frame acceleration maps directly to the generated MAPDL `ACEL` history.

## Injection rule

A model is injectable only when static inspection proves all of the following:

1. exactly one explicit `ANTYPE,TRANS` command;
2. no explicit `TRNOPT,MSUP` request;
3. no existing active `ACEL` command;
4. at least one explicit solution command (`SOLVE`, `LSSOLVE`, `MSSOLVE`, or `PSOLVE`).

For a real run FEMagent inserts:

```text
/INPUT,'femagent_load','mac'
```

immediately after the unique `ANTYPE,TRANS` line in the staged copy. The user's source Model Bundle is never rewritten.

## Build-only preflight

Preflight stages a sanitized copy, generates the same load table and macro, references the macro before the sanitized solution-stage stop, and invokes MAPDL only as a build/parser validation. It must not advance the requested solve.

A successful canonical preflight reports `CANONICAL_LOAD_INJECTION = PASSED` and `BUILD_ONLY_INSPECTION = PASSED`, with `load.injectionStatus = VALIDATED_FOR_STAGING`.

## Run provenance

A completed canonical ANSYS run records:

- source load SHA256;
- canonical channel metadata;
- declared model units and conversion factors;
- injection hook path/line/command;
- generated table and macro SHA256;
- `injected: true`;
- `executionInputFingerprint`;
- `caseFingerprint` incorporating the execution-input identity.

The execution-input fingerprint changes when the Model Bundle, canonical earthquake input, generated artifacts, model-unit mapping, or hook identity changes.

## Failure modes

Canonical injection fails closed for:

- missing or unsupported model units;
- malformed/noncanonical CSV;
- multiple channels;
- unsupported load kind/application/quantity/unit/component;
- non-global targets;
- non-increasing time;
- missing or ambiguous transient hook;
- `TRNOPT,MSUP`;
- existing `ACEL` conflict;
- missing solution command;
- build-only MAPDL failure;
- staged hook drift between inspection and injection.

When `loadPath` is absent, ANSYS retains the legacy `MODEL_SCRIPT_MANAGED` behavior and requires no PR10 model-unit declaration.
