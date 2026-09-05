from __future__ import annotations

import json
import re
from hashlib import sha256
from pathlib import Path
from typing import Any

from fem_core.errors import FemCoreError
from fem_core.pathing import resolve_workspace_file, workspace_relative_path

from .models import ROLE_TYPES

_ROLE_ID = re.compile(r"^[A-Z][A-Z0-9_]{0,63}$")
_SHA256 = re.compile(r"^[0-9a-fA-F]{64}$")
_ENTITY_TYPES = {"NODE", "ELEMENT"}


def _invalid(message: str, **details: Any) -> FemCoreError:
    return FemCoreError(
        "INVALID_SEMANTIC_ROLE_MANIFEST",
        message,
        details=details,
    )


def load_semantic_manifest(workspace: Path, manifest_path: str) -> dict[str, Any]:
    path = resolve_workspace_file(workspace, manifest_path)
    try:
        content = path.read_bytes()
        payload = json.loads(content.decode("utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise _invalid("Semantic Role Manifest must be valid UTF-8 JSON") from exc

    if not isinstance(payload, dict):
        raise _invalid("Semantic Role Manifest must be a JSON object")
    if payload.get("schemaVersion") != "1.0":
        raise _invalid(
            "Semantic Role Manifest schemaVersion must be '1.0'",
            schemaVersion=payload.get("schemaVersion"),
        )
    if payload.get("kind") != "engineering_semantic_roles":
        raise _invalid(
            "Semantic Role Manifest kind must be 'engineering_semantic_roles'",
            kind=payload.get("kind"),
        )

    model = payload.get("model")
    if not isinstance(model, dict):
        raise _invalid("Semantic Role Manifest model must be a JSON object")
    fingerprint = model.get("bundleFingerprint")
    if not isinstance(fingerprint, str) or _SHA256.fullmatch(fingerprint) is None:
        raise _invalid("model.bundleFingerprint must be a 64-character SHA-256 value")

    raw_roles = payload.get("roles")
    if not isinstance(raw_roles, list) or not raw_roles:
        raise _invalid("Semantic Role Manifest roles must be a non-empty array")

    role_ids: set[str] = set()
    roles: list[dict[str, Any]] = []
    for index, raw_role in enumerate(raw_roles):
        if not isinstance(raw_role, dict):
            raise _invalid("Each semantic role must be a JSON object", roleIndex=index)

        role_id = raw_role.get("roleId")
        if not isinstance(role_id, str) or _ROLE_ID.fullmatch(role_id) is None:
            raise _invalid(
                "roleId must start with an uppercase ASCII letter and contain only A-Z, 0-9, or _",
                roleIndex=index,
                roleId=role_id,
            )
        if role_id in role_ids:
            raise _invalid("Semantic Role Manifest contains a duplicate roleId", roleId=role_id)
        role_ids.add(role_id)

        role_type = raw_role.get("roleType")
        if not isinstance(role_type, str) or role_type not in ROLE_TYPES:
            raise _invalid(
                "Semantic Role Manifest contains an unsupported roleType",
                roleIndex=index,
                roleType=role_type,
                supported=sorted(ROLE_TYPES),
            )

        entity = raw_role.get("entity")
        entity_type = entity.get("type") if isinstance(entity, dict) else None
        if entity_type not in _ENTITY_TYPES:
            raise _invalid(
                "PR15 semantic roles support only NODE or ELEMENT entities",
                roleIndex=index,
                entityType=entity_type,
            )
        entity_id = entity.get("id")
        if not isinstance(entity_id, int) or isinstance(entity_id, bool) or entity_id <= 0:
            raise _invalid(
                "Semantic role entity id must be a positive integer",
                roleIndex=index,
                entityType=entity_type,
                entityId=entity_id,
            )

        roles.append(
            {
                "roleId": role_id,
                "roleType": role_type,
                "entity": {"type": entity_type, "id": entity_id},
            }
        )

    return {
        "schemaVersion": "1.0",
        "kind": "engineering_semantic_roles",
        "model": {"bundleFingerprint": fingerprint.lower()},
        "roles": roles,
        "manifest": {
            "path": workspace_relative_path(workspace, path),
            "sha256": sha256(content).hexdigest(),
        },
    }
