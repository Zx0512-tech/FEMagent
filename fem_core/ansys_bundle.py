from __future__ import annotations

import re
from hashlib import sha256
from pathlib import Path
from typing import Any

from fem_core.errors import FemCoreError
from fem_core.model_bundle import bundle_fingerprint
from fem_core.pathing import resolve_workspace_file, workspace_relative_path
from fem_core.text import decode_engineering_text

ANSYS_BUNDLE_SUFFIXES = frozenset({".cdb", ".inp", ".apdl", ".mac", ".dat", ".txt"})

_MODEL_SIGNAL_PATTERNS = (
    re.compile(r"^\s*/prep7\b", re.IGNORECASE | re.MULTILINE),
    re.compile(r"^\s*nblock\b", re.IGNORECASE | re.MULTILINE),
    re.compile(r"^\s*eblock\b", re.IGNORECASE | re.MULTILINE),
    re.compile(r"^\s*(?:n|e|en|et|mp|sectype|cm)\s*,", re.IGNORECASE | re.MULTILINE),
    re.compile(r"^\s*/input\s*,", re.IGNORECASE | re.MULTILINE),
    re.compile(r"^\s*\*use\s*,", re.IGNORECASE | re.MULTILINE),
)

_INPUT_COMMAND = re.compile(r"^\s*/input\s*,(.*)$", re.IGNORECASE)
_USE_COMMAND = re.compile(r"^\s*\*use\s*,(.*)$", re.IGNORECASE)


def has_ansys_model_signals(text: str) -> bool:
    return any(pattern.search(text) is not None for pattern in _MODEL_SIGNAL_PATTERNS)


def _clean_field(value: str) -> str:
    return value.strip().strip("'\"")


def _input_target(arguments: str) -> str | None:
    fields = [_clean_field(field) for field in arguments.split(",")]
    if not fields or not fields[0]:
        return None
    filename = fields[0]
    extension = fields[1] if len(fields) > 1 else ""
    directory = fields[2] if len(fields) > 2 else ""
    if extension and not Path(filename).suffix:
        filename = f"{filename}.{extension.lstrip('.')}"
    return str(Path(directory) / filename) if directory else filename


def _use_target(arguments: str) -> str | None:
    first = _clean_field(arguments.split(",", 1)[0])
    if not first:
        return None
    path = Path(first)
    if not path.suffix:
        path = path.with_suffix(".mac")
    return str(path)


def _dependencies_for_text(source: str, text: str) -> list[dict[str, str]]:
    dependencies: list[dict[str, str]] = []
    for line in text.splitlines():
        body = line.split("!", 1)[0].strip()
        if not body:
            continue
        if match := _INPUT_COMMAND.match(body):
            target = _input_target(match.group(1))
            if target:
                dependencies.append(
                    {
                        "source": source,
                        "reference": body[:200],
                        "target": target,
                        "type": "APDL_INPUT",
                        "role": "APDL_INCLUDE",
                    }
                )
            continue
        if match := _USE_COMMAND.match(body):
            target = _use_target(match.group(1))
            if target:
                dependencies.append(
                    {
                        "source": source,
                        "reference": body[:200],
                        "target": target,
                        "type": "APDL_USE",
                        "role": "APDL_MACRO",
                    }
                )
    return dependencies


def _file_record(workspace: Path, path: Path, role: str) -> dict[str, Any]:
    content = path.read_bytes()
    return {
        "path": workspace_relative_path(workspace, path),
        "role": role,
        "sha256": sha256(content).hexdigest(),
        "sizeBytes": len(content),
    }


def discover_ansys_bundle(workspace: Path, raw_path: str) -> dict[str, Any]:
    root = workspace.resolve()
    entrypoint = resolve_workspace_file(root, raw_path)
    if entrypoint.suffix.lower() not in ANSYS_BUNDLE_SUFFIXES:
        raise FemCoreError(
            "UNSUPPORTED_MODEL_FORMAT",
            "ANSYS Model Bundle entrypoint uses an unsupported suffix",
            details={"suffix": entrypoint.suffix.lower(), "supported": sorted(ANSYS_BUNDLE_SUFFIXES)},
        )

    entry_bytes = entrypoint.read_bytes()
    if not entry_bytes:
        raise FemCoreError("EMPTY_MODEL_FILE", "The ANSYS model entrypoint is empty")
    entry_text, _ = decode_engineering_text(entry_bytes)
    if entrypoint.suffix.lower() in {".txt", ".dat"} and not has_ansys_model_signals(entry_text):
        raise FemCoreError(
            "NOT_ANSYS_MODEL",
            "TXT/DAT entrypoint does not contain deterministic APDL/CDB model signals",
            details={"path": workspace_relative_path(root, entrypoint)},
        )

    # Mechanical APDL /INPUT defaults Dir to the current working directory, and *USE
    # also resolves unqualified macro paths from the working/search path. FEMagent
    # defines the bundle working directory as the entrypoint directory so staged
    # execution can reproduce relative references deterministically.
    working_directory = entrypoint.parent.resolve()
    entry_relative = workspace_relative_path(root, entrypoint)
    roles: dict[str, str] = {entry_relative: "ENTRYPOINT"}
    dependencies: list[dict[str, Any]] = []
    pending: list[Path] = [entrypoint]
    visited: set[str] = set()
    blocked = False

    while pending:
        source_path = pending.pop()
        source_relative = workspace_relative_path(root, source_path)
        if source_relative in visited:
            continue
        visited.add(source_relative)
        content = source_path.read_bytes()
        text, _ = decode_engineering_text(content)

        for dependency in _dependencies_for_text(source_relative, text):
            requested = Path(dependency["target"])
            target_relative: str | None = None
            if requested.is_absolute():
                status = "BLOCKED_ABSOLUTE_REFERENCE"
                blocked = True
                try:
                    target_relative = workspace_relative_path(root, requested.resolve())
                except FemCoreError:
                    target_relative = None
            else:
                candidate = (working_directory / requested).resolve()
                try:
                    candidate.relative_to(root)
                except ValueError:
                    status = "BLOCKED_OUTSIDE_WORKSPACE"
                    blocked = True
                else:
                    target_relative = workspace_relative_path(root, candidate)
                    if candidate.is_file():
                        status = "RESOLVED_WORKSPACE"
                        role = (
                            "ENGINEERING_DATA"
                            if candidate.suffix.lower() not in ANSYS_BUNDLE_SUFFIXES
                            else dependency["role"]
                        )
                        if roles.get(target_relative) != "ENTRYPOINT":
                            roles[target_relative] = role
                        if candidate.suffix.lower() in ANSYS_BUNDLE_SUFFIXES:
                            pending.append(candidate)
                    else:
                        status = "UNRESOLVED"
                        blocked = True

            dependencies.append(
                {
                    "source": source_relative,
                    "reference": dependency["reference"],
                    "target": target_relative,
                    "type": dependency["type"],
                    "status": status,
                }
            )

    files = [_file_record(root, root / relative, role) for relative, role in sorted(roles.items())]
    fingerprint = bundle_fingerprint(files)
    warnings: list[str] = []
    if blocked:
        warnings.append("BUNDLE_DEPENDENCY_BLOCKED")

    return {
        "schemaVersion": "1.0",
        "kind": "model_bundle_manifest",
        "solver": "ANSYS",
        "bundleId": f"bundle_{fingerprint[:16]}",
        "entrypoint": {
            "path": entry_relative,
            "sha256": next(item["sha256"] for item in files if item["path"] == entry_relative),
        },
        "workingDirectory": workspace_relative_path(root, working_directory),
        "files": files,
        "dependencies": dependencies,
        "bundleFingerprint": fingerprint,
        "integrity": "BLOCKED" if blocked else "VALID",
        "warnings": warnings,
    }
