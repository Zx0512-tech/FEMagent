# PR10 — ANSYS Canonical Load Application V1

## Goal

Make a standardized `FEMAGENT_LOAD_CSV_V1` earthquake record causally and verifiably affect an ANSYS MAPDL transient solve without modifying the user's source Model Bundle.

## Scope

PR10 supports one externally supplied canonical earthquake channel with:

- `load_kind = EARTHQUAKE`
- `application_type = UNIFORM_EXCITATION`
- `quantity = ACCELERATION`
- canonical physical unit `m/s2`
- one global Cartesian component X/Y/Z (including UX/U1/1, UY/U2/2, UZ/U3/3 aliases)
- no node/component target; this is global support/reference-frame acceleration
- at least two finite samples with strictly increasing `time_s`

Multi-channel earthquake input, nodal-force matrices, response-spectrum input, rotational excitation, mode-superposition-specific load-vector handling, and arbitrary APDL load injection are out of scope.

## Engineering semantics

The canonical record represents global support acceleration. MAPDL applies it with a time-dependent `ACEL` table. FEMagent does not silently invert the sign: the canonical ground/support acceleration is mapped directly to the ACEL reference-frame acceleration. The resulting full-transient displacement solution is solver-native relative response.

ANSYS is unitless, so canonical SI values cannot be injected safely without a deterministic model-unit mapping. When `loadPath` is supplied to the ANSYS adapter, `solverOptions.modelUnits` is required:

```json
{
  "modelUnits": {
    "length": "m | cm | mm",
    "time": "s | ms"
  }
}
```

Conversions are deterministic:

- `time_model = time_s * timeUnitsPerSecond`
- `accel_model = accel_m_s2 * lengthUnitsPerMeter / timeUnitsPerSecond^2`

No model unit is inferred from coordinates, material magnitudes, file names, or common engineering practice.

## APDL generation

For an accepted canonical load, FEMagent generates two staged artifacts:

```text
femagent_load_table.txt
femagent_load.mac
```

The table is UTF-8 text with two header lines followed by time/acceleration pairs in model units. The macro defines a one-dimensional TABLE with `*DIM`, reads it with `*TREAD`, and applies it through `ACEL,%table%,...` on the selected global axis.

Generated files are never written into the user's source model directory. Build-only inspection and real execution receive their own staged copies.

## Injection point

External canonical injection is intentionally fail-closed.

A Model Bundle is injectable only when static inspection finds:

1. exactly one explicit `ANTYPE,TRANS` command across executable APDL bundle members;
2. no explicit `TRNOPT,MSUP` mode-superposition transient request;
3. no existing active `ACEL` command that would conflict with FEMagent-owned global acceleration;
4. at least one solution command (`SOLVE`, `LSSOLVE`, `MSSOLVE`, or `PSOLVE`) somewhere in the bundle.

For a real staged run, FEMagent inserts:

```text
/INPUT,'femagent_load','mac'
```

immediately after the unique explicit `ANTYPE,TRANS` command in the staged copy only. The source bundle remains byte-for-byte unchanged.

For build-only preflight, the sanitized staged model still stops before the requested solution stage. The generated load macro is inserted before that stop so MAPDL can parse the generated table/ACEL input without intentionally advancing the analysis.

If the transient hook is absent/ambiguous, an existing ACEL is present, or mode-superposition transient is requested, preflight is `BLOCKED` with a stable error rather than guessing an injection location.

## Solver contract

`SolverAdapter.preflight()` and `run()` gain an optional `solver_options` object. The bridge and TypeScript layer expose the same object as `solverOptions`.

- OpenSees rejects non-empty solver options in PR10; its existing contracts remain unchanged.
- ANSYS with no `loadPath` remains `MODEL_SCRIPT_MANAGED` and needs no unit options.
- ANSYS with `loadPath` requires a valid canonical load plus `solverOptions.modelUnits`.

Preflight reports a validated planned injection but does not claim the production solve consumed it.

Real run provenance records:

- source canonical load path + SHA256
- canonical format and channel metadata
- model-unit mapping and conversion factors
- generated table path + SHA256
- generated macro path + SHA256
- injection hook file and line/command context
- `injected: true`
- an execution-input fingerprint derived from model bundle fingerprint + canonical load hash + generated artifact hashes + model-unit mapping + hook identity

The existing `caseFingerprint` incorporates this execution-input identity.

## Permission and trust boundary

`fem_solver_preflight` remains an inspection/build-only action. `fem_solver_run` remains EXECUTION permission-gated.

LLM reasoning may choose the unit mapping only when it has deterministic project/user evidence. If model units are unknown, the Agent must ask for/obtain them rather than assuming SI.

## Result boundary

PR10 does not change Result Intelligence. ANSYS numerical truth still comes from recorded `.rst/.rth/.rfl/.rmg` artifacts through `fem_result_inspect` / `fem_result_query`.

## Acceptance criteria

PR10 is complete when tests prove that:

- a valid canonical earthquake load can be converted to model units and staged as deterministic APDL artifacts;
- invalid canonical records and missing/invalid model-unit mappings fail closed;
- ambiguous/non-full-transient/conflicting ANSYS models fail closed;
- build-only inspection validates the generated load path without solving;
- real run executes the staged bundle with the canonical load hook inserted;
- source model/load files are unchanged;
- run manifest proves `injected: true` and records all relevant hashes/conversions;
- changing the canonical load changes the execution/case fingerprint;
- no-load ANSYS model-script-managed behavior remains backward compatible;
- OpenSees existing behavior remains green;
- TypeScript/Pi tool contracts expose the options without adding solver-specific task tools.