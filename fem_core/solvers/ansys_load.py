from __future__ import annotations

import csv
import math
from hashlib import sha256
from itertools import pairwise
from pathlib import Path
from typing import Any

from fem_core.ansys_bundle import ANSYS_BUNDLE_SUFFIXES
from fem_core.errors import FemCoreError
from fem_core.text import decode_engineering_text

CANONICAL_LOAD_COLUMNS = (
    "time_s",
    "load_kind",
    "channel_id",
    "application_type",
    "target_type",
    "target_id",
    "component",
    "quantity",
    "value",
    "unit",
)

_COMPONENT_ALIASES = {
    "X": "X",
    "UX": "X",
    "U1": "X",
    "1": "X",
    "Y": "Y",
    "UY": "Y",
    "U2": "Y",
    "2": "Y",
    "Z": "Z",
    "UZ": "Z",
    "U3": "Z",
    "3": "Z",
}
_LENGTH_UNITS_PER_METER = {"m": 1.0, "cm": 100.0, "mm": 1000.0}
_TIME_UNITS_PER_SECOND = {"s": 1.0, "ms": 1000.0}
_SOLVE_COMMANDS = ("SOLVE", "LSSOLVE", "MSSOLVE", "PSOLVE")
_LOAD_MACRO_NAME = "femagent_load"
_LOAD_TABLE_STEM = "femagent_load_table"
_LOAD_TABLE_PARAMETER = "FEMAGAC"


def _sha256_file(path: Path) -> str:
    return sha256(path.read_bytes()).hexdigest()


def _finite(value: Any, field: str) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise FemCoreError(
            "INVALID_CANONICAL_LOAD",
            f"Canonical load field '{field}' must be numeric",
            details={"field": field, "value": value},
        ) from exc
    if not math.isfinite(number):
        raise FemCoreError(
            "INVALID_CANONICAL_LOAD",
            f"Canonical load field '{field}' must be finite",
            details={"field": field, "value": value},
        )
    return number


def _model_unit_conversion(model_units: dict[str, str]) -> dict[str, Any]:
    if not isinstance(model_units, dict):
        raise FemCoreError(
            "ANSYS_MODEL_UNITS_REQUIRED",
            "ANSYS canonical load injection requires explicit model length/time units",
        )
    length = model_units.get("length")
    time = model_units.get("time")
    if (
        not isinstance(length, str)
        or not length.strip()
        or not isinstance(time, str)
        or not time.strip()
    ):
        raise FemCoreError(
            "ANSYS_MODEL_UNITS_REQUIRED",
            "ANSYS canonical load injection requires explicit model length/time units",
            details={
                "required": {
                    "length": sorted(_LENGTH_UNITS_PER_METER),
                    "time": sorted(_TIME_UNITS_PER_SECOND),
                }
            },
        )
    length = length.strip().lower()
    time = time.strip().lower()
    if length not in _LENGTH_UNITS_PER_METER or time not in _TIME_UNITS_PER_SECOND:
        raise FemCoreError(
            "UNSUPPORTED_ANSYS_MODEL_UNITS",
            "ANSYS canonical load injection supports length m/cm/mm and time s/ms in PR10",
            details={"length": length, "time": time},
        )
    length_factor = _LENGTH_UNITS_PER_METER[length]
    time_factor = _TIME_UNITS_PER_SECOND[time]
    acceleration_factor = length_factor / (time_factor * time_factor)
    return {
        "modelUnits": {
            "length": length,
            "time": time,
            "acceleration": f"{length}/{time}2",
        },
        "conversion": {
            "timeUnitsPerSecond": time_factor,
            "lengthUnitsPerMeter": length_factor,
            "accelerationFactorFromMPerS2": acceleration_factor,
        },
    }


def read_ansys_canonical_uniform_excitation(
    path: Path,
    model_units: dict[str, str],
) -> dict[str, Any]:
    unit_conversion = _model_unit_conversion(model_units)
    try:
        raw_bytes = path.read_bytes()
        text = raw_bytes.decode("utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        raise FemCoreError(
            "INVALID_CANONICAL_LOAD",
            "ANSYS canonical load must be a readable UTF-8 CSV file",
        ) from exc

    reader = csv.DictReader(text.splitlines())
    if tuple(reader.fieldnames or ()) != CANONICAL_LOAD_COLUMNS:
        raise FemCoreError(
            "UNSUPPORTED_CANONICAL_LOAD",
            "ANSYS PR10 requires FEMAGENT_LOAD_CSV_V1 column order",
            details={"expected": list(CANONICAL_LOAD_COLUMNS), "received": reader.fieldnames},
        )
    rows = list(reader)
    if len(rows) < 2:
        raise FemCoreError("LOAD_TOO_SHORT", "ANSYS transient excitation requires at least two samples")

    channel_ids = {str(row.get("channel_id") or "").strip() for row in rows}
    if len(channel_ids) != 1:
        raise FemCoreError(
            "MULTI_CHANNEL_ANSYS_LOAD_NOT_SUPPORTED",
            "ANSYS PR10 accepts exactly one canonical uniform-excitation channel",
        )

    invariant_fields = {
        key: {str(row.get(key) or "").strip() for row in rows}
        for key in ("load_kind", "application_type", "component", "quantity", "unit")
    }
    if any(len(values) != 1 for values in invariant_fields.values()):
        raise FemCoreError(
            "MULTI_CHANNEL_ANSYS_LOAD_NOT_SUPPORTED",
            "ANSYS PR10 accepts one invariant canonical load channel",
        )

    load_kind = next(iter(invariant_fields["load_kind"])).upper()
    application_type = next(iter(invariant_fields["application_type"])).upper()
    quantity = next(iter(invariant_fields["quantity"])).upper()
    unit = next(iter(invariant_fields["unit"]))
    raw_component = next(iter(invariant_fields["component"])).upper()
    component = _COMPONENT_ALIASES.get(raw_component)
    if (
        load_kind != "EARTHQUAKE"
        or application_type != "UNIFORM_EXCITATION"
        or quantity != "ACCELERATION"
        or unit != "m/s2"
        or component is None
    ):
        raise FemCoreError(
            "UNSUPPORTED_ANSYS_CANONICAL_LOAD",
            "ANSYS PR10 supports EARTHQUAKE + UNIFORM_EXCITATION + ACCELERATION "
            "in m/s2 on X/Y/Z only",
            details={
                "loadKind": load_kind,
                "applicationType": application_type,
                "quantity": quantity,
                "unit": unit,
                "component": raw_component,
            },
        )

    targets = {
        (str(row.get("target_type") or "").strip(), str(row.get("target_id") or "").strip())
        for row in rows
    }
    if targets != {("", "")}:
        raise FemCoreError(
            "ANSYS_UNIFORM_EXCITATION_MUST_BE_GLOBAL",
            "ANSYS ACEL uniform excitation is global and may not carry a node/element target",
            details={"targets": sorted(targets)},
        )

    times_s = [_finite(row.get("time_s"), "time_s") for row in rows]
    values_m_s2 = [_finite(row.get("value"), "value") for row in rows]
    if any(current <= previous for previous, current in pairwise(times_s)):
        raise FemCoreError(
            "TIME_NOT_STRICTLY_INCREASING",
            "ANSYS canonical load time values must be strictly increasing",
        )

    time_factor = float(unit_conversion["conversion"]["timeUnitsPerSecond"])
    acceleration_factor = float(unit_conversion["conversion"]["accelerationFactorFromMPerS2"])
    return {
        "format": "FEMAGENT_LOAD_CSV_V1",
        "path": str(path),
        "sha256": sha256(raw_bytes).hexdigest(),
        "loadKind": "EARTHQUAKE",
        "applicationType": "UNIFORM_EXCITATION",
        "channelId": next(iter(channel_ids)),
        "component": component,
        "quantity": "ACCELERATION",
        "canonicalUnit": "m/s2",
        "sampleCount": len(rows),
        "timesCanonicalS": times_s,
        "valuesCanonicalMPerS2": values_m_s2,
        "timesModel": [value * time_factor for value in times_s],
        "valuesModel": [value * acceleration_factor for value in values_m_s2],
        **unit_conversion,
        "signConvention": "CANONICAL_SUPPORT_ACCELERATION_TO_ACEL_DIRECT",
    }


def _active_command(line: str) -> str:
    return line.split("!", 1)[0].strip()


def _command_fields(command: str) -> list[str]:
    return [field.strip().upper() for field in command.split(",")]


def inspect_ansys_transient_injection(
    workspace: Path,
    bundle: dict[str, Any],
) -> dict[str, Any]:
    root = workspace.resolve()
    hooks: list[dict[str, Any]] = []
    solve_commands: list[dict[str, Any]] = []
    has_msup = False
    has_acel = False

    for file_info in bundle.get("files", []):
        relative = Path(str(file_info.get("path") or ""))
        if relative.suffix.lower() not in ANSYS_BUNDLE_SUFFIXES:
            continue
        source = (root / relative).resolve()
        try:
            source.relative_to(root)
        except ValueError as exc:
            raise FemCoreError(
                "PATH_OUTSIDE_WORKSPACE",
                "ANSYS injection inspection may only read workspace-local bundle files",
                details={"path": str(relative)},
            ) from exc
        text, _ = decode_engineering_text(source.read_bytes())
        for line_number, line in enumerate(text.splitlines(), start=1):
            command = _active_command(line)
            if not command:
                continue
            fields = _command_fields(command)
            keyword = fields[0]
            if keyword == "ANTYPE" and len(fields) > 1 and fields[1] == "TRANS":
                hooks.append(
                    {
                        "path": relative.as_posix(),
                        "line": line_number,
                        "command": command,
                    }
                )
            if keyword == "TRNOPT" and len(fields) > 1 and fields[1] == "MSUP":
                has_msup = True
            if keyword == "ACEL":
                has_acel = True
            if keyword in _SOLVE_COMMANDS:
                solve_commands.append(
                    {
                        "path": relative.as_posix(),
                        "line": line_number,
                        "command": command,
                    }
                )

    if has_msup:
        raise FemCoreError(
            "ANSYS_MSUP_CANONICAL_LOAD_NOT_SUPPORTED",
            "PR10 canonical ACEL injection supports full transient analysis, not TRNOPT,MSUP",
        )
    if has_acel:
        raise FemCoreError(
            "ANSYS_ACCELERATION_LOAD_CONFLICT",
            "ANSYS Model Bundle already contains an active ACEL command",
        )
    if not hooks:
        raise FemCoreError(
            "ANSYS_TRANSIENT_HOOK_NOT_FOUND",
            "ANSYS canonical load injection requires one explicit ANTYPE,TRANS command",
        )
    if len(hooks) != 1:
        raise FemCoreError(
            "ANSYS_TRANSIENT_HOOK_AMBIGUOUS",
            "ANSYS canonical load injection requires exactly one explicit ANTYPE,TRANS command",
            details={"hooks": hooks},
        )
    if not solve_commands:
        raise FemCoreError(
            "ANSYS_SOLVE_COMMAND_NOT_FOUND",
            "ANSYS canonical load injection requires an explicit solution command",
        )

    hook = hooks[0]
    return {
        **hook,
        "solutionCommandCount": len(solve_commands),
        "transientMode": "FULL",
    }


def _format_apdl_number(value: float) -> str:
    return format(float(value), ".15g")


def write_ansys_uniform_excitation(
    working_directory: Path,
    load: dict[str, Any],
) -> dict[str, Any]:
    working_directory.mkdir(parents=True, exist_ok=True)
    table_path = working_directory / f"{_LOAD_TABLE_STEM}.txt"
    macro_path = working_directory / f"{_LOAD_MACRO_NAME}.mac"
    times = list(load["timesModel"])
    values = list(load["valuesModel"])
    if len(times) != len(values) or not times:
        raise FemCoreError(
            "INVALID_CANONICAL_LOAD",
            "ANSYS generated load requires matching non-empty time/value arrays",
        )

    table_lines = [
        "! FEMagent PR10 generated canonical uniform excitation",
        "! time_model acceleration_model",
    ]
    table_lines.extend(
        f"{_format_apdl_number(time)}\t{_format_apdl_number(value)}"
        for time, value in zip(times, values, strict=True)
    )
    table_path.write_text("\n".join(table_lines) + "\n", encoding="utf-8")

    component = str(load["component"])
    acel_by_component = {
        "X": f"ACEL,%{_LOAD_TABLE_PARAMETER}%,0,0",
        "Y": f"ACEL,0,%{_LOAD_TABLE_PARAMETER}%,0",
        "Z": f"ACEL,0,0,%{_LOAD_TABLE_PARAMETER}%",
    }
    try:
        acel_command = acel_by_component[component]
    except KeyError as exc:
        raise FemCoreError(
            "UNSUPPORTED_ANSYS_CANONICAL_LOAD",
            "Generated ANSYS uniform excitation requires X, Y, or Z",
            details={"component": component},
        ) from exc

    macro_lines = [
        "! FEMagent PR10 generated uniform excitation",
        f"*DIM,{_LOAD_TABLE_PARAMETER},TABLE,{len(times)},1,1,TIME",
        f"*TREAD,{_LOAD_TABLE_PARAMETER},{_LOAD_TABLE_STEM},txt,,2",
        acel_command,
    ]
    macro_path.write_text("\n".join(macro_lines) + "\n", encoding="utf-8")
    return {
        "tablePath": str(table_path),
        "tableSha256": _sha256_file(table_path),
        "macroPath": str(macro_path),
        "macroSha256": _sha256_file(macro_path),
        "parameter": _LOAD_TABLE_PARAMETER,
        "component": component,
        "includeCommand": f"/INPUT,'{_LOAD_MACRO_NAME}','mac'",
    }


def inject_ansys_uniform_excitation(
    stage_root: Path,
    hook: dict[str, Any],
    *,
    macro_name: str = _LOAD_MACRO_NAME,
) -> dict[str, Any]:
    root = stage_root.resolve()
    target = (root / str(hook["path"])).resolve()
    try:
        target.relative_to(root)
    except ValueError as exc:
        raise FemCoreError(
            "INVALID_MODEL_BUNDLE_PATH",
            "ANSYS injection hook escaped the staged bundle root",
            details={"path": hook.get("path")},
        ) from exc
    if not target.is_file():
        raise FemCoreError(
            "ANSYS_INJECTION_HOOK_CHANGED",
            "ANSYS staged injection hook file does not exist",
            details={"path": hook.get("path")},
        )

    text, _ = decode_engineering_text(target.read_bytes())
    lines = text.splitlines()
    line_index = int(hook["line"]) - 1
    if line_index < 0 or line_index >= len(lines):
        raise FemCoreError(
            "ANSYS_INJECTION_HOOK_CHANGED",
            "ANSYS staged injection hook line is no longer present",
        )
    expected = _command_fields(str(hook["command"]))
    received = _command_fields(_active_command(lines[line_index]))
    if expected != received:
        raise FemCoreError(
            "ANSYS_INJECTION_HOOK_CHANGED",
            "ANSYS staged injection hook no longer matches inspected source",
            details={"expected": hook["command"], "received": lines[line_index]},
        )

    include_command = f"/INPUT,'{macro_name}','mac'"
    lines.insert(line_index + 1, include_command)
    target.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return {
        "injected": True,
        "hook": dict(hook),
        "includeCommand": include_command,
        "stagedHookFile": str(target),
        "stagedHookFileSha256": _sha256_file(target),
    }
