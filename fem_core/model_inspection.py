from __future__ import annotations

import re
from hashlib import sha256
from pathlib import Path
from typing import Any

from fem_core.errors import FemCoreError
from fem_core.pathing import resolve_workspace_file, workspace_relative_path
from fem_core.text import decode_engineering_text

MAX_MODEL_BYTES = 50 * 1024 * 1024
SUPPORTED_MODEL_SUFFIXES = frozenset({".cdb", ".inp", ".apdl", ".mac", ".dat", ".txt"})

_NODE_COMMAND = re.compile(r"^\s*n\s*,", re.IGNORECASE)
_ELEMENT_COMMAND = re.compile(r"^\s*(e|en)\s*,", re.IGNORECASE)
_BLOCK_COMMAND = re.compile(r"^\s*(nblock|eblock)\b", re.IGNORECASE)
_DO_LOOP = re.compile(r"^\s*\*do\b", re.IGNORECASE)
_ET_COMMAND = re.compile(r"^\s*et\s*,\s*[^,]+\s*,\s*([^,!\s]+)", re.IGNORECASE)


def inspect_model(workspace: Path, raw_path: str) -> dict[str, Any]:
    path = resolve_workspace_file(workspace, raw_path)
    suffix = path.suffix.lower()
    if suffix not in SUPPORTED_MODEL_SUFFIXES:
        raise FemCoreError(
            "UNSUPPORTED_MODEL_FORMAT",
            "PR2 model inspection supports ANSYS APDL/CDB-style text files only",
            details={"suffix": suffix, "supported": sorted(SUPPORTED_MODEL_SUFFIXES)},
        )

    content = path.read_bytes()
    if not content:
        raise FemCoreError("EMPTY_MODEL_FILE", "The FEM model file is empty")
    if len(content) > MAX_MODEL_BYTES:
        raise FemCoreError("MODEL_FILE_TOO_LARGE", "The FEM model file exceeds the 50 MiB inspection limit")

    text, encoding = decode_engineering_text(content)
    lines = text.splitlines()
    node_commands = 0
    element_commands = 0
    block_commands = 0
    do_loops = 0
    has_prep7 = False
    element_types: set[str] = set()

    for line in lines:
        stripped = line.strip()
        if not stripped or stripped.startswith("!"):
            continue
        lowered = stripped.lower()
        has_prep7 = has_prep7 or lowered.startswith("/prep7")
        node_commands += int(bool(_NODE_COMMAND.match(line)))
        element_commands += int(bool(_ELEMENT_COMMAND.match(line)))
        block_commands += int(bool(_BLOCK_COMMAND.match(line)))
        do_loops += int(bool(_DO_LOOP.match(line)))
        if match := _ET_COMMAND.match(line):
            element_types.add(match.group(1).upper())

    warnings: list[str] = []
    if not has_prep7:
        warnings.append("NO_PREP7_SIGNAL")
    if node_commands == 0 and block_commands == 0:
        warnings.append("NO_NODE_DEFINITION_SIGNAL")
    if element_commands == 0 and block_commands == 0:
        warnings.append("NO_ELEMENT_DEFINITION_SIGNAL")
    if do_loops or block_commands:
        warnings.append("STATIC_COMMAND_COUNTS_ARE_NOT_MODEL_TOTALS")

    return {
        "schemaVersion": "1.0",
        "kind": "model_inspection",
        "inspectionLevel": "STATIC_TEXT_ONLY",
        "format": "ANSYS_APDL_TEXT",
        "source": {
            "path": workspace_relative_path(workspace, path),
            "fileName": path.name,
            "suffix": suffix,
            "sha256": sha256(content).hexdigest(),
            "sizeBytes": len(content),
            "encoding": encoding,
        },
        "summary": {
            "lineCount": len(lines),
            "explicitNodeCommandCount": node_commands,
            "explicitElementCommandCount": element_commands,
            "blockCommandCount": block_commands,
            "doLoopCount": do_loops,
            "parametricSignals": do_loops > 0,
        },
        "elementTypes": sorted(element_types),
        "signals": {"hasPrep7": has_prep7},
        "warnings": warnings,
    }
