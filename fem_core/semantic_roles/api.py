from __future__ import annotations

from pathlib import Path
from typing import Any

from .resolver import inspect_semantic_roles as _inspect_semantic_roles
from .resolver import resolve_semantic_role as _resolve_semantic_role


def inspect_semantic_roles(
    workspace: Path,
    *,
    model_path: str,
    manifest_path: str,
) -> dict[str, Any]:
    return _inspect_semantic_roles(
        workspace,
        model_path=model_path,
        manifest_path=manifest_path,
    )


def resolve_semantic_role(
    workspace: Path,
    *,
    model_path: str,
    manifest_path: str,
    role_id: str,
) -> dict[str, Any]:
    return _resolve_semantic_role(
        workspace,
        model_path=model_path,
        manifest_path=manifest_path,
        role_id=role_id,
    )
