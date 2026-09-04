---
name: inspect-engineering-load
description: Inspect unfamiliar engineering load files, distinguish declared facts from inferred mapping hints, and prepare a confirmed mapping before deterministic standardization and solver application.
---

# Inspect engineering load data

Use this skill when a user supplies an unfamiliar load/history file or asks FEMagent to prepare load data for analysis.

1. Call `fem_load_inspect` before making claims about columns, sampling interval, units, channels, or physical meaning.
2. Read `manifest.selfDescribing`, `manifest.time`, `manifest.channels`, and `declaredMetadata` first.
3. Treat `suggestedMapping` only as a candidate. It is not frozen engineering truth.
4. PEER NGA AT1/AT2 headers may establish sample interval, sample count, acceleration quantity, and source unit. They do not establish the structural excitation direction.
5. For CSV/TXT/DAT/XLSX, a unit declared in a column name is stronger evidence than a magnitude-based unit hint. Magnitude-based unit hints always require confirmation.
6. Never infer N versus kN from force magnitude. Require an explicit unit declaration or user confirmation.
7. If `requiredConfirmations` is non-empty, resolve those fields from project context or the user before calling `fem_load_standardize`.
8. Do not map X/Y/Z to longitudinal/transverse/vertical unless project context or the user establishes that convention.
9. `fem_load_standardize` validates strict time monotonicity and performs deterministic unit conversion. The standardized output is solver-neutral canonical data; standardization alone does not prove any solver consumed the load.
10. Preserve the standardized output path and SHA256 for later solver/application provenance.
11. For ANSYS PR10 canonical earthquake injection, the standardized load must satisfy the single-channel `EARTHQUAKE + UNIFORM_EXCITATION + ACCELERATION` contract in `m/s2`. ANSYS model length/time units are separate model evidence and must be supplied through `solverOptions.modelUnits`; never infer them from the load file.
12. After ANSYS preflight, distinguish `VALIDATED_FOR_STAGING` from an actual run with `injected: true`. Only the real run manifest proves that the staged APDL was modified to reference the generated load macro.

Current V1 support:
- CSV, TXT, DAT
- XLSX first worksheet
- PEER NGA AT1/AT2 acceleration records
- single-channel mappings
- generic multi-channel long-form mappings
- force standardization to N
- acceleration standardization to m/s2
- ANSYS PR10 application of one canonical global earthquake acceleration channel after explicit model-unit declaration

Not yet supported:
- traffic `NODAL_FORCE_MATRIX` canonicalization/application
- ANSYS multi-channel earthquake application
- response-spectrum application
- automatic structural target selection
