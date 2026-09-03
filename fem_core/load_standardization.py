from __future__ import annotations

import csv
import io
import math
from hashlib import sha256
from itertools import pairwise
from pathlib import Path
from typing import Any

from fem_core.errors import FemCoreError
from fem_core.load_formats import number_or_none, read_load_table
from fem_core.pathing import (
    resolve_workspace_file,
    resolve_workspace_output,
    workspace_relative_path,
)

UNIT_ALIASES = {
    "m/s²": "m/s2",
    "m/s^2": "m/s2",
    "m/sec2": "m/s2",
    "m/sec^2": "m/s2",
    "m/s2": "m/s2",
    "cm/s²": "cm/s2",
    "cm/s^2": "cm/s2",
    "cm/sec2": "cm/s2",
    "cm/sec^2": "cm/s2",
    "cm/s2": "cm/s2",
    "gal": "cm/s2",
    "mm/s²": "mm/s2",
    "mm/s^2": "mm/s2",
    "mm/sec2": "mm/s2",
    "mm/s2": "mm/s2",
    "g": "g",
    "n": "N",
    "kn": "kN",
}
UNIT_CONVERSIONS = {
    ("FORCE", "N"): (1.0, "N"),
    ("FORCE", "kN"): (1000.0, "N"),
    ("ACCELERATION", "m/s2"): (1.0, "m/s2"),
    ("ACCELERATION", "g"): (9.80665, "m/s2"),
    ("ACCELERATION", "cm/s2"): (0.01, "m/s2"),
    ("ACCELERATION", "mm/s2"): (0.001, "m/s2"),
}


def normalize_unit(unit: str) -> str:
    text = str(unit).strip()
    normalized = UNIT_ALIASES.get(text.lower())
    if normalized is None:
        raise FemCoreError("UNSUPPORTED_SOURCE_UNIT", "Unsupported source unit", details={"sourceUnit": unit})
    return normalized


def standardize_load(
    workspace: Path,
    raw_path: str,
    mapping: dict[str, Any],
    *,
    output_path: str | None = None,
) -> dict[str, Any]:
    source_path = resolve_workspace_file(workspace, raw_path)
    content = source_path.read_bytes()
    table = read_load_table(source_path, content)
    if not table.rows:
        raise FemCoreError("NO_LOAD_DATA", "The load file contains no data rows")
    if not isinstance(mapping, dict):
        raise FemCoreError("INVALID_MAPPING", "Load mapping must be a JSON object")

    load_kind = _required_text(mapping, "loadKind")
    time_config = _time_config(mapping)
    times = _extract_times(table.rows, table.columns, time_config)
    channels = _channels(mapping)
    if not channels:
        raise FemCoreError("NO_LOAD_CHANNELS", "At least one load channel is required")

    output = io.StringIO(newline="")
    writer = csv.writer(output, lineterminator="\n")
    writer.writerow(
        [
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
        ]
    )
    channel_reports: list[dict[str, Any]] = []
    for index, channel in enumerate(channels, start=1):
        value_column = _required_text(channel, "valueColumn")
        if value_column not in table.columns:
            raise FemCoreError(
                "UNKNOWN_VALUE_COLUMN",
                "The mapped load-value column does not exist",
                details={"valueColumn": value_column},
            )
        application_type = _required_text(channel, "applicationType")
        if application_type == "NODAL_FORCE_MATRIX":
            raise FemCoreError(
                "UNSUPPORTED_APPLICATION_TYPE",
                "PR4 supports scalar/long-form channels; NODAL_FORCE_MATRIX is deferred",
            )
        component = _required_text(channel, "component")
        quantity = _required_text(channel, "quantity").upper()
        source_unit_raw = _required_text(channel, "sourceUnit")
        source_unit = normalize_unit(source_unit_raw)
        factor, standard_unit = _unit_conversion(quantity, source_unit)
        scale = _finite_number(channel.get("scale", 1.0), "scale")
        channel_id = str(channel.get("channelId") or f"channel_{index}")
        target_type = str(channel.get("targetType") or "")
        target_id = str(channel.get("targetId") or "")

        for row_number, (time_value, row) in enumerate(zip(times, table.rows, strict=True), start=2):
            value = _required_number(row.get(value_column, ""), row_number, value_column)
            writer.writerow(
                [
                    _format_number(time_value),
                    load_kind,
                    channel_id,
                    application_type,
                    target_type,
                    target_id,
                    component,
                    quantity,
                    _format_number(value * factor * scale),
                    standard_unit,
                ]
            )

        channel_reports.append(
            {
                "channelId": channel_id,
                "valueColumn": value_column,
                "applicationType": application_type,
                "targetType": target_type or None,
                "targetId": target_id or None,
                "component": component,
                "quantity": quantity,
                "sourceUnit": source_unit_raw,
                "normalizedSourceUnit": source_unit,
                "standardUnit": standard_unit,
                "conversionFactor": factor,
                "scale": scale,
            }
        )

    raw = output.getvalue().encode("utf-8")
    digest = sha256(raw).hexdigest()
    destination = _destination(workspace, source_path, sha256(content).hexdigest(), output_path)
    if destination.resolve() == source_path.resolve():
        raise FemCoreError("OUTPUT_OVERWRITES_SOURCE", "Standardized load output may not overwrite the source file")
    if destination.exists() and destination.read_bytes() != raw:
        raise FemCoreError(
            "OUTPUT_PATH_EXISTS",
            "The requested standardized output path already exists with different content",
            details={"path": workspace_relative_path(workspace, destination)},
        )
    destination.write_bytes(raw)

    return {
        "schemaVersion": "1.0",
        "kind": "standardized_load",
        "format": "FEMAGENT_LOAD_CSV_V1",
        "source": {
            "path": workspace_relative_path(workspace, source_path),
            "fileName": source_path.name,
            "sha256": sha256(content).hexdigest(),
            "format": table.format_name,
        },
        "output": {
            "path": workspace_relative_path(workspace, destination),
            "sha256": digest,
            "sizeBytes": len(raw),
            "encoding": "utf-8",
            "delimiter": ",",
        },
        "loadKind": load_kind,
        "sampleCount": len(table.rows),
        "channelCount": len(channels),
        "outputRowCount": len(table.rows) * len(channels),
        "time": {
            "startS": times[0],
            "endS": times[-1],
            "strictlyIncreasing": True,
            "source": time_config,
        },
        "channels": channel_reports,
        "validation": {"nanCount": 0, "timeStrictlyIncreasing": True},
    }


def _channels(mapping: dict[str, Any]) -> list[dict[str, Any]]:
    raw_channels = mapping.get("channels")
    if isinstance(raw_channels, list):
        channels = [dict(channel) for channel in raw_channels if isinstance(channel, dict)]
        if len(channels) != len(raw_channels):
            raise FemCoreError("INVALID_CHANNEL", "Every load channel must be a JSON object")
        return channels
    if mapping.get("version") == 2:
        return []
    return [
        {
            "valueColumn": mapping.get("valueColumn"),
            "applicationType": mapping.get("applicationType"),
            "targetType": mapping.get("targetType"),
            "targetId": mapping.get("targetId"),
            "component": mapping.get("component"),
            "quantity": mapping.get("quantity"),
            "sourceUnit": mapping.get("sourceUnit"),
            "scale": mapping.get("scale", 1.0),
        }
    ]


def _time_config(mapping: dict[str, Any]) -> dict[str, Any]:
    if isinstance(mapping.get("time"), dict):
        raw = dict(mapping["time"])
        return {
            "column": raw.get("column"),
            "stepS": raw.get("stepS"),
            "unit": raw.get("unit", "s"),
        }
    return {
        "column": mapping.get("timeColumn"),
        "stepS": mapping.get("timeStepS"),
        "unit": mapping.get("timeUnit", "s"),
    }


def _extract_times(
    rows: tuple[dict[str, str], ...],
    columns: tuple[str, ...],
    time_config: dict[str, Any],
) -> list[float]:
    time_column = time_config.get("column")
    step_s = time_config.get("stepS")
    unit = str(time_config.get("unit") or "s").lower()
    if unit not in {"s", "ms"}:
        raise FemCoreError("UNSUPPORTED_TIME_UNIT", "Time unit must be s or ms", details={"timeUnit": unit})
    factor = 0.001 if unit == "ms" else 1.0
    if time_column is not None:
        if not isinstance(time_column, str) or time_column not in columns:
            raise FemCoreError("UNKNOWN_TIME_COLUMN", "The mapped time column does not exist", details={"timeColumn": time_column})
        times = [
            _required_number(row.get(time_column, ""), index + 2, time_column) * factor
            for index, row in enumerate(rows)
        ]
    else:
        if step_s is None:
            raise FemCoreError("TIME_STEP_REQUIRED", "A time column or time step is required")
        step = _finite_number(step_s, "timeStepS")
        if step <= 0:
            raise FemCoreError("INVALID_TIME_STEP", "timeStepS must be positive")
        times = [index * step for index in range(len(rows))]
    if any(current <= previous for previous, current in pairwise(times)):
        raise FemCoreError("TIME_NOT_STRICTLY_INCREASING", "Time values must be strictly increasing")
    return times


def _unit_conversion(quantity: str, normalized_unit: str) -> tuple[float, str]:
    conversion = UNIT_CONVERSIONS.get((quantity, normalized_unit))
    if conversion is None:
        raise FemCoreError(
            "UNSUPPORTED_UNIT_CONVERSION",
            "The requested quantity/unit conversion is not supported",
            details={"quantity": quantity, "sourceUnit": normalized_unit},
        )
    return conversion


def _required_text(mapping: dict[str, Any], key: str) -> str:
    value = mapping.get(key)
    if not isinstance(value, str) or not value.strip():
        raise FemCoreError("INVALID_MAPPING", f"Mapping field '{key}' must be a non-empty string", details={"field": key})
    return value.strip()


def _finite_number(value: Any, field: str) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise FemCoreError("INVALID_MAPPING", f"Mapping field '{field}' must be numeric", details={"field": field}) from exc
    if not math.isfinite(number):
        raise FemCoreError("INVALID_MAPPING", f"Mapping field '{field}' must be finite", details={"field": field})
    return number


def _required_number(value: str, row: int, column: str) -> float:
    number = number_or_none(value)
    if number is None or not math.isfinite(number):
        raise FemCoreError(
            "INVALID_NUMERIC_VALUE",
            "Load data contains a missing or non-numeric mapped value",
            details={"row": row, "column": column, "value": value},
        )
    return number


def _destination(workspace: Path, source_path: Path, source_digest: str, output_path: str | None) -> Path:
    if output_path is not None:
        return resolve_workspace_output(workspace, output_path)
    generated = f".femagent/generated/loads/{source_path.stem}-{source_digest[:12]}.standardized.csv"
    return resolve_workspace_output(workspace, generated)


def _format_number(value: float) -> str:
    return format(value, ".15g")
