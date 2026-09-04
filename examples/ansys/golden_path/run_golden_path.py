from __future__ import annotations

from pathlib import Path
from typing import Any

from openpyxl import Workbook

from fem_core.load_standardization import standardize_load
from fem_core.pathing import resolve_workspace_output

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
