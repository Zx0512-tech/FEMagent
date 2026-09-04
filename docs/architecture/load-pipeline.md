# Load Pipeline Architecture

FEMagent separates load understanding, canonicalization, solver application, and result interpretation into distinct trust boundaries.

## Pipeline

```text
source engineering load
        ↓
fem_load_inspect
        ↓
explicit confirmed mapping
        ↓
fem_load_standardize
        ↓
FEMAGENT_LOAD_CSV_V1
        ↓
solver-specific preflight/application
        ↓
staged solver execution
        ↓
run_manifest.json + solver-native outputs
        ↓
fem_result_inspect / fem_result_query
```

## 1. Inspection is not execution truth

`fem_load_inspect` may suggest mappings, but suggestions are not executable truth. Units, component/direction, application semantics, and targets must be established explicitly before standardization.

## 2. Canonicalization is solver-neutral

`fem_load_standardize` converts supported source formats into `FEMAGENT_LOAD_CSV_V1` with deterministic unit conversion and time validation. The canonical CSV is the boundary between source-data interpretation and solver-specific application.

The canonical file itself does not choose solver targets or mutate a model.

## 3. Solver application is explicit

Solver adapters decide whether a canonical load can be consumed.

### OpenSees

Controlled OpenSees contracts retain their existing solver-specific behavior. ANSYS-only `solverOptions.modelUnits` are rejected rather than ignored.

### ANSYS PR10

For ANSYS, a supplied canonical `loadPath` means FEMagent attempts the supported canonical uniform-excitation path. Because MAPDL is unitless, explicit model length/time units are mandatory.

```text
canonical load csv
        ↓
solverOptions.modelUnits
        ↓
unit conversion
        ↓
femagent_load_table.txt
+ femagent_load.mac
        ↓
validated transient hook
        ↓
staged APDL injection
        ↓
ANSYS MAPDL run
```

No source model is rewritten. Generated artifacts and the `/INPUT` insertion exist only inside build/run staging directories.

## 4. Preflight and run are different evidence levels

Preflight may prove that:

- the solver is available;
- the Model Bundle is statically eligible;
- dependencies are confined and valid;
- the canonical load contract is valid;
- units are declared and supported;
- an unambiguous transient hook exists;
- generated artifacts can be build-checked without advancing the requested solve.

Preflight does **not** claim the production analysis consumed the load.

A completed run records actual staged injection evidence plus generated artifact hashes and an execution-input fingerprint.

## 5. Execution identity

ANSYS canonical execution identity binds together:

- Model Bundle fingerprint;
- canonical load SHA256;
- declared model units and conversion factors;
- generated table SHA256;
- generated macro SHA256;
- transient hook identity.

Changing any of these changes `executionInputFingerprint`. The solver run `caseFingerprint` incorporates this identity.

## 6. Result boundary

Successful solver process completion is not equivalent to validated engineering response. Numerical claims remain behind Result Intelligence (`fem_result_inspect` and `fem_result_query`), which reads recorded outputs and reports available integrity/unit evidence.
