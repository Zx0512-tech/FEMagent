from __future__ import annotations

from hashlib import sha256
from pathlib import Path
from typing import Any

from fem_core.errors import FemCoreError
from fem_core.load_formats import number_or_none, read_load_table
from fem_core.load_mapping import build_mapping_suggestion, detect_time_column, unit_from_name
from fem_core.pathing import resolve_workspace_file, workspace_relative_path


def inspect_load(workspace: Path, raw_path: str) -> dict[str, Any]:
    path = resolve_workspace_file(workspace, raw_path)
    content = path.read_bytes()
    table = read_load_table(path, content)
    if not table.rows:
        raise FemCoreError("NO_LOAD_DATA", "The load file contains no data rows")

    profiles: list[dict[str, Any]] = []
    for name in table.columns:
        values = [row.get(name, "").strip() for row in table.rows]
        numbers = [number for value in values if (number := number_or_none(value)) is not None]
        profiles.append(
            {
                "name": name,
                "numericCount": len(numbers),
                "missingCount": sum(not value for value in values),
                "min": min(numbers) if numbers else None,
                "max": max(numbers) if numbers else None,
                "unitHint": unit_from_name(name),
                "timeCandidate": False,
            }
        )

    time_detection = detect_time_column(profiles, table.rows)
    for profile in profiles:
        profile["timeCandidate"] = profile["name"] == time_detection.column

    suggestion = build_mapping_suggestion(table, profiles, file_name=path.name)
    suggested_mapping = dict(suggestion.get("mapping") or {})
    selected_value_column = suggested_mapping.get("valueColumn")
    declared_unit = table.metadata.get("declaredUnit")
    channels: list[dict[str, Any]] = []
    for profile in profiles:
        name = str(profile["name"])
        if name == time_detection.column:
            continue
        channels.append(
            {
                "column": name,
                "numericCount": profile["numericCount"],
                "missingCount": profile["missingCount"],
                "min": profile["min"],
                "max": profile["max"],
                "unitHint": declared_unit if table.self_describing and name == "acceleration" else profile["unitHint"],
                "quantityHint": suggested_mapping.get("quantity") if name == selected_value_column else None,
                "selectedBySuggestion": name == selected_value_column,
            }
        )

    warnings = list(table.warnings)
    warnings.extend(str(item) for item in suggestion.get("warnings") or [])
    if time_detection.column is None:
        warnings.append("TIME_MAPPING_REQUIRES_CONFIRMATION")
    if suggestion.get("requiredConfirmations"):
        warnings.append("MAPPING_REQUIRES_CONFIRMATION")
    warnings = sorted(set(warnings))

    source = {
        "path": workspace_relative_path(workspace, path),
        "fileName": path.name,
        "suffix": path.suffix.lower(),
        "sha256": sha256(content).hexdigest(),
        "sizeBytes": len(content),
        "encoding": table.encoding,
    }
    manifest = {
        "schemaVersion": "1.0",
        "kind": "load_manifest",
        "source": source,
        "format": table.format_name,
        "selfDescribing": table.self_describing,
        "structure": {
            "rowCount": len(table.rows),
            "columnCount": len(table.columns),
            "columns": list(table.columns),
            "delimiter": table.delimiter,
            "hasHeader": table.has_header,
        },
        "time": {
            "column": time_detection.column,
            "stepS": time_detection.step_s,
            "uniform": time_detection.uniform,
            "sourceUnit": time_detection.source_unit,
            "basis": time_detection.reason,
        },
        "channels": channels,
        "declaredMetadata": dict(table.metadata),
        "suggestedMapping": suggestion,
        "warnings": warnings,
    }

    return {
        "schemaVersion": "1.1",
        "kind": "load_inspection",
        "inspectionLevel": "SELF_DESCRIBING_RECORD" if table.self_describing else "TABULAR_DATA",
        "format": table.format_name,
        "source": source,
        "rowCount": len(table.rows),
        "columnCount": len(table.columns),
        "delimiter": table.delimiter,
        "hasHeader": table.has_header,
        "columns": profiles,
        "sampleRows": list(table.rows[:8]),
        "declaredMetadata": dict(table.metadata),
        "suggestedMapping": suggestion,
        "manifest": manifest,
        "warnings": warnings,
    }
