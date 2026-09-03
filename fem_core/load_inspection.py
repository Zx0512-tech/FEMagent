from __future__ import annotations

import re
from hashlib import sha256
from pathlib import Path
from typing import Any

from fem_core.errors import FemCoreError
from fem_core.pathing import resolve_workspace_file, workspace_relative_path
from fem_core.text import decode_engineering_text

MAX_LOAD_BYTES = 20 * 1024 * 1024
MAX_ROWS = 200_000
SUPPORTED_LOAD_SUFFIXES = frozenset({".csv", ".txt", ".dat"})
_TIME_NAMES = frozenset({"t", "time", "time_s", "times", "time_sec", "时间", "时间(s)"})


def _number_or_none(value: str) -> float | None:
    text = value.strip()
    if not text:
        return None
    try:
        return float(text.replace("D", "E").replace("d", "e"))
    except ValueError:
        return None


def _split(line: str, delimiter: str) -> list[str]:
    if delimiter == "WHITESPACE":
        return re.split(r"\s+", line.strip())
    return [part.strip() for part in line.split(delimiter)]


def _infer_delimiter(line: str) -> str:
    if "," in line:
        return ","
    if "\t" in line:
        return "\t"
    if ";" in line:
        return ";"
    return "WHITESPACE"


def _unique_columns(values: list[str]) -> list[str]:
    result: list[str] = []
    counts: dict[str, int] = {}
    for index, raw in enumerate(values, start=1):
        base = raw.strip() or f"column_{index}"
        counts[base] = counts.get(base, 0) + 1
        result.append(base if counts[base] == 1 else f"{base}_{counts[base]}")
    return result


def inspect_load(workspace: Path, raw_path: str) -> dict[str, Any]:
    path = resolve_workspace_file(workspace, raw_path)
    suffix = path.suffix.lower()
    if suffix not in SUPPORTED_LOAD_SUFFIXES:
        raise FemCoreError(
            "UNSUPPORTED_LOAD_FORMAT",
            "PR2 load inspection supports CSV/TXT/DAT text files only",
            details={"suffix": suffix, "supported": sorted(SUPPORTED_LOAD_SUFFIXES)},
        )

    content = path.read_bytes()
    if not content:
        raise FemCoreError("EMPTY_LOAD_FILE", "The load file is empty")
    if len(content) > MAX_LOAD_BYTES:
        raise FemCoreError("LOAD_FILE_TOO_LARGE", "The load file exceeds the 20 MiB inspection limit")

    text, encoding = decode_engineering_text(content)
    data_lines = [line.strip() for line in text.splitlines() if line.strip() and not line.lstrip().startswith(("#", "!"))]
    if not data_lines:
        raise FemCoreError("NO_LOAD_DATA", "The load file contains no readable data rows")

    delimiter = _infer_delimiter(data_lines[0])
    first = _split(data_lines[0], delimiter)
    has_header = any(_number_or_none(value) is None for value in first)
    columns = _unique_columns(first) if has_header else [f"column_{index}" for index in range(1, len(first) + 1)]
    raw_rows = data_lines[1:] if has_header else data_lines
    if len(raw_rows) > MAX_ROWS:
        raise FemCoreError("TOO_MANY_LOAD_ROWS", f"Load inspection is limited to {MAX_ROWS} rows")

    parsed_rows = [_split(line, delimiter) for line in raw_rows]
    inconsistent_rows = sum(len(row) != len(columns) for row in parsed_rows)
    normalized_rows = [(row + [""] * len(columns))[: len(columns)] for row in parsed_rows]

    profiles: list[dict[str, Any]] = []
    for index, name in enumerate(columns):
        values = [row[index].strip() for row in normalized_rows]
        numbers = [number for value in values if (number := _number_or_none(value)) is not None]
        profiles.append(
            {
                "name": name,
                "numericCount": len(numbers),
                "missingCount": sum(not value for value in values),
                "min": min(numbers) if numbers else None,
                "max": max(numbers) if numbers else None,
                "timeCandidate": name.strip().lower() in _TIME_NAMES,
            }
        )

    sample_rows = [dict(zip(columns, row, strict=True)) for row in normalized_rows[:5]]
    warnings: list[str] = []
    if inconsistent_rows:
        warnings.append("INCONSISTENT_COLUMN_COUNT")
    if not any(profile["timeCandidate"] for profile in profiles):
        warnings.append("NO_EXPLICIT_TIME_COLUMN_CANDIDATE")

    return {
        "schemaVersion": "1.0",
        "kind": "load_inspection",
        "inspectionLevel": "TABULAR_TEXT",
        "format": suffix.removeprefix(".").upper(),
        "source": {
            "path": workspace_relative_path(workspace, path),
            "fileName": path.name,
            "suffix": suffix,
            "sha256": sha256(content).hexdigest(),
            "sizeBytes": len(content),
            "encoding": encoding,
        },
        "rowCount": len(normalized_rows),
        "columnCount": len(columns),
        "delimiter": delimiter,
        "hasHeader": has_header,
        "columns": profiles,
        "sampleRows": sample_rows,
        "warnings": warnings,
    }
