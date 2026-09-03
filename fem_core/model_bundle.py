from __future__ import annotations

from hashlib import sha256
from pathlib import Path
from typing import Any

from fem_core.pathing import workspace_relative_path


def _sha256_file(path: Path) -> str:
    return sha256(path.read_bytes()).hexdigest()


def bundle_fingerprint(files: list[dict[str, Any]]) -> str:
    canonical = "".join(
        f"{item['path']!s}\0{item['sha256']!s}\n"
        for item in sorted(files, key=lambda item: str(item["path"]))
    )
    return sha256(canonical.encode("utf-8")).hexdigest()


def discover_bundle(
    workspace: Path,
    entrypoint: Path,
    seed_dependencies: list[dict[str, Any]],
) -> dict[str, Any]:
    root = workspace.resolve()
    entry = entrypoint.resolve()
    entry_relative = workspace_relative_path(root, entry)
    file_roles: dict[str, str] = {entry_relative: "ENTRYPOINT"}
    dependencies: list[dict[str, Any]] = []
    blocked = False

    for raw in seed_dependencies:
        source = str(raw.get("source") or entry_relative)
        reference = str(raw.get("reference") or raw.get("target") or "")
        dependency_type = str(raw.get("type") or "UNKNOWN")
        role = str(raw.get("role") or "UNKNOWN_DEPENDENCY")
        raw_target = raw.get("target")
        explicit_status = raw.get("status")
        target_relative: str | None = None

        if explicit_status == "EXTERNAL_PACKAGE":
            status = "EXTERNAL_PACKAGE"
        elif raw_target is None:
            status = str(explicit_status or "UNRESOLVED")
        else:
            source_parent = (root / source).resolve().parent
            requested = Path(str(raw_target))
            candidate = requested.resolve() if requested.is_absolute() else (source_parent / requested).resolve()
            try:
                candidate.relative_to(root)
            except ValueError:
                status = "BLOCKED_OUTSIDE_WORKSPACE"
                blocked = True
            else:
                if candidate.is_file():
                    status = "RESOLVED_WORKSPACE"
                    target_relative = workspace_relative_path(root, candidate)
                    existing = file_roles.get(target_relative)
                    if existing != "ENTRYPOINT":
                        file_roles[target_relative] = role
                else:
                    status = str(explicit_status or "UNRESOLVED")
                    try:
                        target_relative = workspace_relative_path(root, candidate)
                    except ValueError:
                        target_relative = None

        dependencies.append(
            {
                "source": source,
                "reference": reference,
                "target": target_relative,
                "type": dependency_type,
                "status": status,
            }
        )

    files: list[dict[str, Any]] = []
    for relative, role in sorted(file_roles.items()):
        path = (root / relative).resolve()
        files.append(
            {
                "path": relative,
                "role": role,
                "sha256": _sha256_file(path),
                "sizeBytes": path.stat().st_size,
            }
        )

    fingerprint = bundle_fingerprint(files)
    return {
        "schemaVersion": "1.0",
        "kind": "model_bundle_manifest",
        "bundleId": f"bundle_{fingerprint[:16]}",
        "entrypoint": {
            "path": entry_relative,
            "sha256": _sha256_file(entry),
        },
        "files": files,
        "dependencies": dependencies,
        "bundleFingerprint": fingerprint,
        "integrity": "BLOCKED" if blocked else "VALID",
        "warnings": ["BUNDLE_DEPENDENCY_BLOCKED"] if blocked else [],
    }
