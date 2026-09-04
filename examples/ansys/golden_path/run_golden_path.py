from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
from typing import Any

from openpyxl import Workbook

from fem_core.errors import FemCoreError
from fem_core.load_standardization import standardize_load
from fem_core.pathing import resolve_workspace_file, resolve_workspace_output
from fem_core.result_intelligence import inspect_result, query_result
from fem_core.solvers.registry import get_solver_adapter

GOLDEN_MODEL_UNITS = {"modelUnits": {"length": "m", "time": "s"}}
BASE_ACCEL_G = (
    0.00,
    0.02,
    0.04,
    0.06,
    0.08,
    0.10,
    0.08,
    0.06,
    0.04,
    0.02,
    0.00,
    -0.02,
    -0.04,
    -0.06,
    -0.08,
    -0.10,
    -0.08,
    -0.06,
    -0.04,
    -0.02,
    0.00,
)


def write_earthquake_xlsx(
    workspace: Path,
    *,
    amplitude_scale: float,
    name: str,
) -> Path:
    destination = resolve_workspace_output(workspace, name)
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "earthquake"
    sheet.append(["time_s", "accel_g"])
    for index, acceleration in enumerate(BASE_ACCEL_G):
        sheet.append([index * 0.05, acceleration * amplitude_scale])
    workbook.save(destination)
    return destination


def standardize_golden_load(workspace: Path, xlsx_path: Path) -> dict[str, Any]:
    root = workspace.resolve()
    source = xlsx_path.resolve()
    source.relative_to(root)
    return standardize_load(
        root,
        source.relative_to(root).as_posix(),
        {
            "version": 1,
            "loadKind": "EARTHQUAKE",
            "timeColumn": "time_s",
            "timeUnit": "s",
            "valueColumn": "accel_g",
            "applicationType": "UNIFORM_EXCITATION",
            "targetType": "",
            "targetId": "",
            "component": "X",
            "quantity": "ACCELERATION",
            "sourceUnit": "g",
            "scale": 1.0,
        },
    )


def _fixture_query_target(binary_path: Path) -> tuple[int, str]:
    try:
        from ansys.mapdl import reader as pymapdl_reader
    except ImportError as exc:
        raise FemCoreError(
            "ANSYS_RESULT_READER_UNAVAILABLE",
            "PR11 CI fixture mode requires the ansys-results dependency",
        ) from exc

    raw = pymapdl_reader.read_binary(str(binary_path), parse_vtk=False)
    node_ids, _ = raw.nodal_solution(0)
    if not len(node_ids):
        raise FemCoreError(
            "GOLDEN_PATH_FIXTURE_RESULT_INVALID",
            "The packaged ANSYS result fixture contains no nodal solution",
        )
    dofs = [str(value).strip().upper() for value in raw.result_dof(0)]
    for source_dof, component in (("UX", "X"), ("UY", "Y"), ("UZ", "Z")):
        if source_dof in dofs:
            return int(node_ids[0]), component
    raise FemCoreError(
        "GOLDEN_PATH_FIXTURE_RESULT_INVALID",
        "The packaged ANSYS result fixture contains no Cartesian displacement DOF",
        details={"dofLabels": dofs},
    )


def run_golden_once(
    workspace: Path,
    *,
    model_path: str,
    xlsx_path: Path,
    fixture_result_mode: bool = False,
) -> dict[str, Any]:
    root = workspace.resolve()
    standardized = standardize_golden_load(root, xlsx_path)
    canonical_path = standardized["output"]["path"]
    adapter = get_solver_adapter("ansys")

    preflight = adapter.preflight(
        root,
        model_path=model_path,
        load_path=canonical_path,
        solver_options=GOLDEN_MODEL_UNITS,
    )
    if preflight.get("status") != "READY":
        raise FemCoreError(
            "GOLDEN_PATH_PREFLIGHT_BLOCKED",
            "ANSYS Golden Path preflight did not reach READY",
            details={"preflight": preflight},
        )

    run = adapter.run(
        root,
        model_path=model_path,
        load_path=canonical_path,
        solver_options=GOLDEN_MODEL_UNITS,
    )
    if run.get("status") != "COMPLETED":
        raise FemCoreError(
            "GOLDEN_PATH_RUN_NOT_COMPLETED",
            "ANSYS Golden Path solver run did not complete",
            details={"status": run.get("status")},
        )
    binary_relative = run.get("outputs", {}).get("binaryResult")
    if not isinstance(binary_relative, str) or not binary_relative:
        raise FemCoreError(
            "GOLDEN_PATH_BINARY_RESULT_REQUIRED",
            "ANSYS Golden Path requires a recorded binary result artifact",
        )

    result_inspection = inspect_result(root, run["runId"])
    if fixture_result_mode:
        binary_path = resolve_workspace_file(root, binary_relative)
        node_id, component = _fixture_query_target(binary_path)
        evidence_mode = "CI_FIXTURE_BACKED"
        evidence_note = (
            "The CI binary result is a packaged parser fixture. Its numerical values are not "
            "claimed as the response of the PR11 Golden Model."
        )
    else:
        node_id, component = 2, "X"
        evidence_mode = "REAL_ANSYS"
        evidence_note = "The binary result was produced by the configured real ANSYS MAPDL runtime."

    result_query = query_result(
        root,
        run["runId"],
        {
            "quantity": "DISPLACEMENT",
            "target": {"type": "NODE", "id": node_id},
            "component": component,
            "operation": "SUMMARY",
        },
    )
    return {
        "schemaVersion": "1.0",
        "kind": "ansys_golden_path_run",
        "evidenceMode": evidence_mode,
        "evidenceNote": evidence_note,
        "standardizedLoad": standardized,
        "preflight": preflight,
        "run": run,
        "resultInspection": result_inspection,
        "resultQuery": result_query,
    }


def response_changed(base_peak: float, scaled_peak: float) -> bool:
    base = float(base_peak)
    scaled = float(scaled_peak)
    if not math.isfinite(base) or not math.isfinite(scaled):
        return False
    tolerance = max(1.0e-12, 1.0e-6 * max(abs(base), abs(scaled)))
    return abs(scaled - base) > tolerance


def run_real_causality_check(
    workspace: Path,
    *,
    model_path: str,
) -> dict[str, Any]:
    root = workspace.resolve()
    adapter = get_solver_adapter("ansys")
    runtime = adapter.status()
    if not runtime.get("available"):
        raise FemCoreError(
            "GOLDEN_PATH_ANSYS_UNAVAILABLE",
            "The real ANSYS Golden Path requires FEM_ANSYS_EXECUTABLE to resolve to an executable file",
            details={
                "reason": runtime.get("reason"),
                "configuredPath": runtime.get("configuredPath"),
            },
        )

    base_xlsx = write_earthquake_xlsx(
        root,
        amplitude_scale=1.0,
        name=".femagent/generated/golden_path/earthquake-base.xlsx",
    )
    scaled_xlsx = write_earthquake_xlsx(
        root,
        amplitude_scale=2.0,
        name=".femagent/generated/golden_path/earthquake-scale-2.xlsx",
    )
    base = run_golden_once(
        root,
        model_path=model_path,
        xlsx_path=base_xlsx,
        fixture_result_mode=False,
    )
    scaled = run_golden_once(
        root,
        model_path=model_path,
        xlsx_path=scaled_xlsx,
        fixture_result_mode=False,
    )

    base_peak = float(base["resultQuery"]["summary"]["absolutePeak"])
    scaled_peak = float(scaled["resultQuery"]["summary"]["absolutePeak"])
    if not math.isfinite(base_peak) or not math.isfinite(scaled_peak) or base_peak == 0.0 or scaled_peak == 0.0:
        raise FemCoreError(
            "GOLDEN_PATH_CAUSALITY_FAILED",
            "Real ANSYS Golden Path requires finite non-zero node-2 X displacement peaks",
            details={"basePeak": base_peak, "scaledPeak": scaled_peak},
        )

    base_execution = base["run"]["executionInputFingerprint"]
    scaled_execution = scaled["run"]["executionInputFingerprint"]
    base_case = base["run"]["caseFingerprint"]
    scaled_case = scaled["run"]["caseFingerprint"]
    fingerprints_changed = base_execution != scaled_execution and base_case != scaled_case
    displacement_changed = response_changed(base_peak, scaled_peak)
    if not fingerprints_changed or not displacement_changed:
        raise FemCoreError(
            "GOLDEN_PATH_CAUSALITY_FAILED",
            "Doubling the earthquake amplitude did not change both execution identity and real ANSYS response",
            details={
                "executionFingerprintChanged": base_execution != scaled_execution,
                "caseFingerprintChanged": base_case != scaled_case,
                "responseChanged": displacement_changed,
                "basePeak": base_peak,
                "scaledPeak": scaled_peak,
            },
        )

    return {
        "schemaVersion": "1.0",
        "kind": "ansys_golden_path_causality",
        "status": "PASSED",
        "response": {"node": 2, "component": "X", "quantity": "DISPLACEMENT"},
        "base": {
            "amplitudeScale": 1.0,
            "runId": base["run"]["runId"],
            "executionInputFingerprint": base_execution,
            "caseFingerprint": base_case,
            "absolutePeak": base_peak,
        },
        "scaled": {
            "amplitudeScale": 2.0,
            "runId": scaled["run"]["runId"],
            "executionInputFingerprint": scaled_execution,
            "caseFingerprint": scaled_case,
            "absolutePeak": scaled_peak,
        },
        "checks": {
            "executionFingerprintChanged": True,
            "caseFingerprintChanged": True,
            "responseChanged": True,
        },
    }


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the FEMagent PR11 real ANSYS Golden Path causality check")
    parser.add_argument("--workspace", default=".", help="FEMagent workspace root")
    parser.add_argument(
        "--model-path",
        default="examples/ansys/golden_path/model.inp",
        help="Workspace-relative ANSYS Golden Model path",
    )
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    report = run_real_causality_check(Path(args.workspace), model_path=args.model_path)
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
