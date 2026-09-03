from __future__ import annotations

import re
from collections import defaultdict
from hashlib import sha256
from pathlib import Path
from typing import Any

from fem_core.errors import FemCoreError
from fem_core.opensees_python_inspection import inspect_opensees_python
from fem_core.pathing import resolve_workspace_file, workspace_relative_path
from fem_core.text import decode_engineering_text

MAX_MODEL_BYTES = 50 * 1024 * 1024
ANSYS_MODEL_SUFFIXES = frozenset({".cdb", ".inp", ".apdl", ".mac", ".dat", ".txt"})
SUPPORTED_MODEL_SUFFIXES = ANSYS_MODEL_SUFFIXES | {".py"}
FORBIDDEN_APDL_COMMANDS = ("/sys", "/syp", "/delete", "~")

_NODE_COMMAND = re.compile(r"^\s*n\s*,", re.IGNORECASE)
_ELEMENT_COMMAND = re.compile(r"^\s*(e|en)\s*,", re.IGNORECASE)
_NBLOCK_COMMAND = re.compile(r"^\s*nblock\b", re.IGNORECASE)
_EBLOCK_COMMAND = re.compile(r"^\s*eblock\b", re.IGNORECASE)
_DO_LOOP = re.compile(r"^\s*\*do\b", re.IGNORECASE)
_ET_COMMAND = re.compile(r"^\s*et\s*,\s*([^,]+)\s*,\s*([^,!\s]+)", re.IGNORECASE)
_MP_COMMAND = re.compile(r"^\s*mp\s*,\s*([^,]+)\s*,\s*([^,]+)", re.IGNORECASE)
_SECTYPE_COMMAND = re.compile(
    r"^\s*sectype\s*,\s*([^,]+)\s*,\s*([^,]+)(?:\s*,\s*([^,]*))?(?:\s*,\s*([^,!]*))?",
    re.IGNORECASE,
)
_COMPONENT_COMMAND = re.compile(r"^\s*cm\s*,\s*([^,]+)\s*,\s*([^,!\s]+)", re.IGNORECASE)
_CONSTRAINT_COMMAND = re.compile(r"^\s*d\s*,\s*([^,]+)\s*,\s*([^,!\s]+)", re.IGNORECASE)
_LOAD_COMMAND = re.compile(r"^\s*(f|sf|sfe|acel)\s*(?:,|$)", re.IGNORECASE)


def _fields(line: str) -> list[str]:
    body = line.split("!", 1)[0]
    return [field.strip() for field in body.split(",")]


def _int_literal(value: str) -> int | None:
    try:
        return int(value.strip())
    except ValueError:
        return None


def _float_literal(value: str) -> float | None:
    try:
        return float(value.strip().replace("D", "E").replace("d", "e"))
    except ValueError:
        return None


def _update_bounds(bounds: dict[str, list[float]], coordinates: tuple[float, float, float]) -> None:
    for axis, value in zip(("x", "y", "z"), coordinates, strict=True):
        bounds[axis][0] = min(bounds[axis][0], value)
        bounds[axis][1] = max(bounds[axis][1], value)


def _coordinate_bounds(bounds: dict[str, list[float]], count: int) -> dict[str, Any] | None:
    if count == 0:
        return None
    return {
        "basis": "EXPLICIT_NUMERIC_N_COMMANDS",
        "sampledNodeCount": count,
        "x": {"min": bounds["x"][0], "max": bounds["x"][1]},
        "y": {"min": bounds["y"][0], "max": bounds["y"][1]},
        "z": {"min": bounds["z"][0], "max": bounds["z"][1]},
    }


def _execution_eligibility(
    *,
    forbidden_hits: list[dict[str, Any]],
    missing_prep7: bool,
    missing_nodes: bool,
    missing_elements: bool,
    requires_solver_inspection: bool,
) -> str:
    if forbidden_hits:
        return "REJECTED"
    if missing_prep7 or missing_nodes or missing_elements:
        return "INCOMPLETE"
    if requires_solver_inspection:
        return "REQUIRES_SOLVER_INSPECTION"
    return "STATICALLY_ELIGIBLE"


def inspect_model(workspace: Path, raw_path: str) -> dict[str, Any]:
    path = resolve_workspace_file(workspace, raw_path)
    if path.suffix.lower() == ".py":
        return inspect_opensees_python(workspace, raw_path)
    return _inspect_ansys_model(workspace, raw_path, path=path)


def _inspect_ansys_model(workspace: Path, raw_path: str, *, path: Path | None = None) -> dict[str, Any]:
    path = path or resolve_workspace_file(workspace, raw_path)
    suffix = path.suffix.lower()
    if suffix not in ANSYS_MODEL_SUFFIXES:
        raise FemCoreError(
            "UNSUPPORTED_MODEL_FORMAT",
            "Model inspection supports ANSYS APDL/CDB text or OpenSees Python entrypoints",
            details={"suffix": suffix, "supported": sorted(SUPPORTED_MODEL_SUFFIXES)},
        )

    content = path.read_bytes()
    if not content:
        raise FemCoreError("EMPTY_MODEL_FILE", "The FEM model file is empty")
    if len(content) > MAX_MODEL_BYTES:
        raise FemCoreError(
            "MODEL_FILE_TOO_LARGE",
            "The FEM model file exceeds the 50 MiB inspection limit",
        )

    text, encoding = decode_engineering_text(content)
    lines = text.splitlines()

    explicit_node_commands = 0
    explicit_element_commands = 0
    nblock_count = 0
    eblock_count = 0
    do_loop_count = 0
    has_prep7 = False

    forbidden_hits: list[dict[str, Any]] = []
    element_types: dict[str, str] = {}
    material_properties: dict[str, set[str]] = defaultdict(set)
    sections: list[dict[str, str | None]] = []
    components: list[dict[str, str]] = []
    constraint_labels: set[str] = set()
    constraint_count = 0
    load_signal_counts: dict[str, int] = defaultdict(int)

    explicit_node_ids: set[int] = set()
    numeric_node_command_count = 0
    coordinate_node_count = 0
    bounds = {
        "x": [float("inf"), float("-inf")],
        "y": [float("inf"), float("-inf")],
        "z": [float("inf"), float("-inf")],
    }

    for line_number, line in enumerate(lines, start=1):
        stripped = line.strip()
        if not stripped or stripped.startswith("!"):
            continue
        lowered = stripped.lower()

        for marker in FORBIDDEN_APDL_COMMANDS:
            if lowered.startswith(marker):
                forbidden_hits.append(
                    {"line": line_number, "marker": marker, "command": stripped[:120]}
                )
                break

        if lowered.startswith("/prep7"):
            has_prep7 = True

        if _NODE_COMMAND.match(line):
            explicit_node_commands += 1
            fields = _fields(line)
            if len(fields) >= 2:
                node_id = _int_literal(fields[1])
                if node_id is not None:
                    explicit_node_ids.add(node_id)
                    numeric_node_command_count += 1
            if len(fields) >= 5:
                xyz = tuple(_float_literal(value) for value in fields[2:5])
                if all(value is not None for value in xyz):
                    coordinates = (float(xyz[0]), float(xyz[1]), float(xyz[2]))
                    _update_bounds(bounds, coordinates)
                    coordinate_node_count += 1
            continue

        if _ELEMENT_COMMAND.match(line):
            explicit_element_commands += 1
            continue
        if _NBLOCK_COMMAND.match(line):
            nblock_count += 1
            continue
        if _EBLOCK_COMMAND.match(line):
            eblock_count += 1
            continue
        if _DO_LOOP.match(line):
            do_loop_count += 1
            continue

        if match := _ET_COMMAND.match(line):
            element_types[match.group(1).strip()] = match.group(2).strip().upper()
            continue
        if match := _MP_COMMAND.match(line):
            material_properties[match.group(2).strip()].add(match.group(1).strip().upper())
            continue
        if match := _SECTYPE_COMMAND.match(line):
            sections.append(
                {
                    "id": match.group(1).strip(),
                    "type": match.group(2).strip().upper(),
                    "subtype": (match.group(3) or "").strip().upper() or None,
                    "name": (match.group(4) or "").strip() or None,
                }
            )
            continue
        if match := _COMPONENT_COMMAND.match(line):
            components.append(
                {"name": match.group(1).strip(), "entity": match.group(2).strip().upper()}
            )
            continue
        if match := _CONSTRAINT_COMMAND.match(line):
            constraint_count += 1
            constraint_labels.add(match.group(2).strip().upper())
            continue
        if match := _LOAD_COMMAND.match(line):
            load_signal_counts[match.group(1).upper()] += 1

    has_node_definitions = explicit_node_commands > 0 or nblock_count > 0
    has_element_definitions = explicit_element_commands > 0 or eblock_count > 0
    parameterized = do_loop_count > 0
    block_based = nblock_count > 0 or eblock_count > 0
    requires_solver_inspection = parameterized or block_based

    issues: list[dict[str, str]] = []
    if not has_prep7:
        issues.append({"code": "MISSING_PREP7", "severity": "ERROR"})
    if not has_node_definitions:
        issues.append({"code": "NO_NODE_DEFINITIONS", "severity": "ERROR"})
    if not has_element_definitions:
        issues.append({"code": "NO_ELEMENT_DEFINITIONS", "severity": "ERROR"})
    if forbidden_hits:
        issues.append({"code": "FORBIDDEN_APDL_COMMAND", "severity": "ERROR"})
    if requires_solver_inspection:
        issues.append({"code": "SOLVER_INSPECTION_REQUIRED", "severity": "INFO"})

    execution_eligibility = _execution_eligibility(
        forbidden_hits=forbidden_hits,
        missing_prep7=not has_prep7,
        missing_nodes=not has_node_definitions,
        missing_elements=not has_element_definitions,
        requires_solver_inspection=requires_solver_inspection,
    )
    validation_status = (
        "REJECTED"
        if execution_eligibility == "REJECTED"
        else "LIMITED"
        if execution_eligibility in {"INCOMPLETE", "REQUIRES_SOLVER_INSPECTION"}
        else "PASSED"
    )

    exact_explicit_node_count = (
        len(explicit_node_ids)
        if explicit_node_commands > 0
        and numeric_node_command_count == explicit_node_commands
        and not requires_solver_inspection
        else None
    )
    node_count_basis = (
        "UNIQUE_EXPLICIT_NODE_IDS"
        if exact_explicit_node_count is not None
        else "UNKNOWN_UNTIL_SOLVER_INSPECTION"
    )
    element_count = explicit_element_commands if not requires_solver_inspection else None
    element_count_basis = (
        "EXPLICIT_ELEMENT_CREATION_COMMANDS"
        if element_count is not None
        else "UNKNOWN_UNTIL_SOLVER_INSPECTION"
    )

    manifest_warnings: list[str] = []
    if requires_solver_inspection:
        manifest_warnings.append("STATIC_TEXT_CANNOT_ENUMERATE_FINAL_TOPOLOGY")
    if coordinate_node_count < explicit_node_commands:
        manifest_warnings.append("COORDINATE_BOUNDS_USE_NUMERIC_EXPLICIT_N_COMMANDS_ONLY")
    if components:
        manifest_warnings.append("COMPONENT_NAMES_DO_NOT_PROVE_ENGINEERING_ROLES")

    return {
        "schemaVersion": "1.1",
        "kind": "model_inspection",
        "inspectionLevel": "STATIC_APDL_V1",
        "format": "ANSYS_APDL_TEXT",
        "source": {
            "path": workspace_relative_path(workspace, path),
            "fileName": path.name,
            "suffix": suffix,
            "sha256": sha256(content).hexdigest(),
            "sizeBytes": len(content),
            "encoding": encoding,
        },
        "validation": {
            "status": validation_status,
            "executionEligibility": execution_eligibility,
            "checks": {
                "prep7": "PASSED" if has_prep7 else "FAILED",
                "nodeDefinitions": "PASSED" if has_node_definitions else "FAILED",
                "elementDefinitions": "PASSED" if has_element_definitions else "FAILED",
                "forbiddenCommandScan": "FAILED" if forbidden_hits else "PASSED",
            },
            "issues": issues,
            "forbiddenCommands": forbidden_hits[:10],
        },
        "summary": {
            "lineCount": len(lines),
            "explicitNodeCommandCount": explicit_node_commands,
            "explicitElementCommandCount": explicit_element_commands,
            "nodeBlockCount": nblock_count,
            "elementBlockCount": eblock_count,
            "doLoopCount": do_loop_count,
            "parametricModel": parameterized,
            "blockBasedModel": block_based,
            "materialDefinitionCount": len(material_properties),
            "sectionDefinitionCount": len(sections),
            "componentDefinitionCount": len(components),
            "explicitConstraintCommandCount": constraint_count,
        },
        "manifest": {
            "schemaVersion": "1.0",
            "modelFormat": "ANSYS_APDL_TEXT",
            "solverCompatibility": {
                "ansys": (
                    "REJECTED_UNSAFE"
                    if forbidden_hits
                    else "INCOMPLETE_MODEL"
                    if execution_eligibility == "INCOMPLETE"
                    else "REQUIRES_SOLVER_INSPECTION"
                    if requires_solver_inspection
                    else "STATIC_TEXT_COMPATIBLE"
                ),
                "opensees": "NOT_DIRECTLY_COMPATIBLE",
            },
            "topology": {
                "nodeCount": {"value": exact_explicit_node_count, "basis": node_count_basis},
                "elementCount": {"value": element_count, "basis": element_count_basis},
                "coordinateBounds": _coordinate_bounds(bounds, coordinate_node_count),
                "elementTypes": [
                    {"id": type_id, "name": name}
                    for type_id, name in sorted(element_types.items())
                ],
            },
            "materials": [
                {"id": material_id, "properties": sorted(properties)}
                for material_id, properties in sorted(material_properties.items())
            ],
            "sections": sections,
            "components": components,
            "boundaries": {
                "explicitConstraintCommandCount": constraint_count,
                "labels": sorted(constraint_labels),
            },
            "existingLoadSignals": [
                {"command": command, "count": count}
                for command, count in sorted(load_signal_counts.items())
            ],
            "generation": {
                "parametric": parameterized,
                "blockBased": block_based,
                "doLoopCount": do_loop_count,
            },
            "warnings": manifest_warnings,
        },
    }
