# ANSYS Golden Path V1

This example exercises FEMagent's complete real-ANSYS path:

```text
earthquake XLSX
→ FEMAGENT_LOAD_CSV_V1
→ ANSYS preflight
→ staged canonical-load injection
→ MAPDL full-transient solve
→ recorded binary result
→ Result Intelligence
→ node 2 X-displacement query
```

## Golden Model contract

`model.inp` is intentionally small and deterministic. The example declares, rather than infers, the following model convention:

```json
{
  "modelUnits": {
    "length": "m",
    "time": "s"
  }
}
```

Reference node 1 is restrained. Response node 2 is the fixed Golden Path result target. The source model contains `ANTYPE,TRANS` / `TRNOPT,FULL`, no source `ACEL`, and no mode-superposition transient request. FEMagent injects the canonical earthquake only into a staged copy.

## Prerequisites

Install FEMagent with ANSYS result support and configure a real MAPDL executable explicitly. FEMagent does not scan for ANSYS installations.

PowerShell example:

```powershell
python -m pip install -e ".[ansys-results]"
$env:FEM_ANSYS_EXECUTABLE="C:\path\to\ansys.exe"
python examples/ansys/golden_path/run_golden_path.py --workspace .
```

Use the actual MAPDL executable path installed and licensed on the machine. Do not copy the placeholder path literally.

## What the harness verifies

The harness generates two XLSX records under `.femagent/generated/golden_path/`:

- base amplitude, scale `1.0`;
- scaled amplitude, scale `2.0`.

Both records travel through production `standardize_load()`, ANSYS `preflight()` / `run()`, and production Result Intelligence. A successful report requires:

- both ANSYS runs to complete;
- both binary results to be recorded and integrity-verified;
- node 2 X displacement to be queryable;
- finite non-zero displacement peaks;
- different `executionInputFingerprint` values;
- different `caseFingerprint` values;
- a displacement-peak change larger than the PR11 deterministic comparison tolerance.

The test checks causality/change, not one solver-version-specific decimal answer.

## CI versus real numerical evidence

Normal GitHub CI does **not** run licensed ANSYS. It uses a strict fake MAPDL process to prove staging, injection, run provenance, binary-artifact recording, and Result Intelligence interoperability. That fake process copies the valid result fixture packaged with `ansys-mapdl-reader`.

Therefore CI fixture values are **not** claimed as the numerical response of `model.inp`.

Only a run of this real harness with a configured `FEM_ANSYS_EXECUTABLE` establishes the PR11 real-ANSYS numerical causality evidence.
