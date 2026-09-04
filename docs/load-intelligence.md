# Load Intelligence V1

Load Intelligence separates four concerns:

1. deterministic file inspection,
2. non-binding mapping suggestion,
3. deterministic standardization from an explicit mapping,
4. later solver-specific application of the canonical artifact.

## Supported source formats

- CSV
- TXT
- DAT
- XLSX (first worksheet, read-only)
- PEER NGA AT1/AT2 acceleration records

Safety limits:

- source upload/read limit: 20 MiB
- maximum data rows: 200,000
- XLSX maximum archive members: 10,000
- XLSX maximum extracted size: 100 MiB

## Inspection outputs

`fem_load_inspect` returns `LoadInspectionReport` schema `1.1` and embeds `LoadManifest` schema `1.0`.

The manifest contains:

- source SHA256 and format
- table structure
- deterministic uniform-time detection
- candidate numeric channels
- unit hints
- self-describing metadata
- non-binding mapping suggestion
- warnings and required confirmations

## Evidence levels

Declared facts and inferred hints must not be conflated.

Examples:

- PEER `DT` and `UNITS OF G`: declared file facts
- `acceleration(g)` column name: declared column-name evidence
- `0.35` looks like a g-valued acceleration: magnitude guess only
- X is longitudinal: not load-file evidence

Magnitude guesses never become executable mappings automatically.

## Mapping suggestion

`suggestedMapping` is designed for the Agent/UI to prefill a candidate mapping. `standardizeDecision` remains `ASK` in V1 because structural component/direction and other engineering bindings may still be unresolved.

`requiredConfirmations` identifies unresolved fields. The Agent should obtain them from trusted project context or the user before standardization.

## Canonical standardization

`fem_load_standardize` accepts an explicit mapping and writes a workspace-confined canonical CSV:

```text
time_s,load_kind,channel_id,application_type,target_type,target_id,component,quantity,value,unit
```

Supported deterministic unit conversions:

- N -> N
- kN -> N
- m/s2 -> m/s2
- g -> m/s2 using 9.80665
- cm/s2 / Gal -> m/s2
- mm/s2 -> m/s2

The tool rejects missing/non-numeric mapped values, non-finite scale factors, unknown columns, unsupported units, and non-increasing time axes.

Generated files default to `.femagent/generated/loads/` and include SHA256 in the returned standardization report. They are deterministic solver-input precursors; standardization itself does not prove a solver consumed the load.

## Solver application boundary

A canonical CSV is solver-neutral until a concrete SolverAdapter accepts it.

PR10 adds the first ANSYS external-load application contract. ANSYS accepts one canonical global earthquake acceleration channel when all of the following are true:

- `load_kind = EARTHQUAKE`
- `application_type = UNIFORM_EXCITATION`
- `quantity = ACCELERATION`
- canonical unit `m/s2`
- one X/Y/Z global component
- no explicit node/element target
- explicit `solverOptions.modelUnits.length` and `.time`

ANSYS model units are not load-file metadata and are never inferred from the canonical record. MAPDL is unitless, so FEMagent requires deterministic model/project/user evidence before converting canonical SI acceleration into model units.

For a supported ANSYS load, preflight validates the transient APDL hook and generated table/macro artifacts without advancing the requested solve. A real run injects only the staged Model Bundle and records load/artifact hashes plus an execution-input fingerprint.

OpenSees keeps its existing controlled load contracts. ANSYS-specific `solverOptions.modelUnits` are not silently reused by OpenSees.

## Multi-channel support

V1 standardization supports a common time axis with multiple scalar channels in canonical long form. Each channel explicitly declares:

- value column
- application type
- target (when applicable)
- component
- quantity
- source unit
- scale

Standardization support does not imply application support. `NODAL_FORCE_MATRIX` traffic canonicalization/application, ANSYS multi-channel earthquake application, and automatic structural target selection remain deferred.
