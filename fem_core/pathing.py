from __future__ import annotations

from pathlib import Path

from fem_core.errors import FemCoreError


def _workspace_candidate(workspace: Path, raw_path: str) -> Path:
    if not isinstance(raw_path, str) or not raw_path.strip():
        raise FemCoreError("INVALID_PATH", "A non-empty file path is required")
    root = workspace.resolve()
    requested = Path(raw_path)
    candidate = requested.resolve() if requested.is_absolute() else (root / requested).resolve()
    try:
        candidate.relative_to(root)
    except ValueError as exc:
        raise FemCoreError(
            "PATH_OUTSIDE_WORKSPACE",
            "Engineering tools may only access paths inside the active workspace",
            details={"path": raw_path},
        ) from exc
    return candidate


def resolve_workspace_file(workspace: Path, raw_path: str) -> Path:
    candidate = _workspace_candidate(workspace, raw_path)
    if not candidate.exists():
        raise FemCoreError("FILE_NOT_FOUND", "The requested engineering file does not exist", details={"path": raw_path})
    if not candidate.is_file():
        raise FemCoreError("NOT_A_FILE", "The requested path is not a file", details={"path": raw_path})
    return candidate


def resolve_workspace_output(workspace: Path, raw_path: str) -> Path:
    candidate = _workspace_candidate(workspace, raw_path)
    if candidate.exists() and not candidate.is_file():
        raise FemCoreError("OUTPUT_NOT_A_FILE", "The requested output path exists and is not a file", details={"path": raw_path})
    candidate.parent.mkdir(parents=True, exist_ok=True)
    return candidate


def workspace_relative_path(workspace: Path, path: Path) -> str:
    return path.resolve().relative_to(workspace.resolve()).as_posix()
