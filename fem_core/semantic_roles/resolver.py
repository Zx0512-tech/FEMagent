from __future__ import annotations

from pathlib import Path
from typing import Any

from fem_core.errors import FemCoreError
from fem_core.model_inspection import inspect_model

from .manifest import load_semantic_manifest
from .models import NOT_STATICALLY_ENUMERABLE, RESOLVED, STATICALLY_CONFIRMED


def _current_fingerprint(model: dict[str, Any]) -> str:
    bundle = model.get("bundle")
    fingerprint = bundle.get("bundleFingerprint") if isinstance(bundle, dict) else None
    if not isinstance(fingerprint, str) or len(fingerprint) != 64:
        raise FemCoreError(
            "SEMANTIC_ROLE_MODEL_MISMATCH",
            "Current model does not expose a usable Model Bundle fingerprint",
        )
    return fingerprint.lower()


def _static_node_tags(model: dict[str, Any]) -> set[int] | None:
    model_format = model.get("format")
    if model_format == "OPENSEES_PYTHON":
        if model.get("dynamicGeneration") is True:
            return None
        topology = model.get("staticTopology")
        tags = topology.get("nodeTags") if isinstance(topology, dict) else None
        if isinstance(tags, list) and all(isinstance(tag, int) and not isinstance(tag, bool) for tag in tags):
            return set(tags)
        return None

    if model_format == "ANSYS_APDL_TEXT":
        manifest = model.get("manifest")
        topology = manifest.get("topology") if isinstance(manifest, dict) else None
        tags = topology.get("nodeTags") if isinstance(topology, dict) else None
        if isinstance(tags, list) and all(isinstance(tag, int) and not isinstance(tag, bool) for tag in tags):
            return set(tags)
        return None

    return None


def _bind_manifest_to_model(
    model: dict[str, Any],
    semantic_manifest: dict[str, Any],
) -> tuple[str, set[int] | None]:
    current = _current_fingerprint(model)
    declared = semantic_manifest["model"]["bundleFingerprint"]
    if declared != current:
        raise FemCoreError(
            "SEMANTIC_ROLE_MODEL_MISMATCH",
            "Semantic Role Manifest is stale for the current Model Bundle",
            details={
                "manifestBundleFingerprint": declared,
                "modelBundleFingerprint": current,
            },
        )
    return current, _static_node_tags(model)


def _role_result(
    role: dict[str, Any],
    *,
    node_tags: set[int] | None,
    model_fingerprint: str,
    manifest_sha256: str,
) -> dict[str, Any]:
    node_id = role["entity"]["id"]
    if node_tags is not None and node_id not in node_tags:
        raise FemCoreError(
            "SEMANTIC_ROLE_ENTITY_NOT_FOUND",
            "Semantic role references a NODE that is absent from the statically enumerable model",
            details={"roleId": role["roleId"], "nodeId": node_id},
        )

    entity_validation = STATICALLY_CONFIRMED if node_tags is not None else NOT_STATICALLY_ENUMERABLE
    return {
        "roleId": role["roleId"],
        "roleType": role["roleType"],
        "entity": dict(role["entity"]),
        "status": RESOLVED,
        "entityValidation": entity_validation,
        "modelBundleFingerprint": model_fingerprint,
        "manifestSha256": manifest_sha256,
    }


def inspect_semantic_roles(
    workspace: Path,
    *,
    model_path: str,
    manifest_path: str,
) -> dict[str, Any]:
    model = inspect_model(workspace, model_path)
    semantic_manifest = load_semantic_manifest(workspace, manifest_path)
    model_fingerprint, node_tags = _bind_manifest_to_model(model, semantic_manifest)
    manifest_meta = semantic_manifest["manifest"]

    roles = [
        _role_result(
            role,
            node_tags=node_tags,
            model_fingerprint=model_fingerprint,
            manifest_sha256=manifest_meta["sha256"],
        )
        for role in semantic_manifest["roles"]
    ]
    not_statically_enumerable = any(
        role["entityValidation"] == NOT_STATICALLY_ENUMERABLE for role in roles
    )
    warnings = (
        [
            {
                "code": "SEMANTIC_ROLE_ENTITY_NOT_STATICALLY_ENUMERABLE",
                "message": "Current Model Intelligence cannot fully enumerate NODE topology; explicit role declarations are retained without static entity confirmation",
            }
        ]
        if not_statically_enumerable
        else []
    )

    source = model.get("source") if isinstance(model.get("source"), dict) else {}
    return {
        "schemaVersion": "1.0",
        "kind": "semantic_role_inspection",
        "status": RESOLVED,
        "model": {
            "path": source.get("path", model_path),
            "bundleFingerprint": model_fingerprint,
        },
        "manifest": dict(manifest_meta),
        "roles": roles,
        "warnings": warnings,
    }


def resolve_semantic_role(
    workspace: Path,
    *,
    model_path: str,
    manifest_path: str,
    role_id: str,
) -> dict[str, Any]:
    model = inspect_model(workspace, model_path)
    semantic_manifest = load_semantic_manifest(workspace, manifest_path)
    model_fingerprint, node_tags = _bind_manifest_to_model(model, semantic_manifest)

    role = next((item for item in semantic_manifest["roles"] if item["roleId"] == role_id), None)
    if role is None:
        raise FemCoreError(
            "SEMANTIC_ROLE_NOT_FOUND",
            "Requested engineering semantic role is not declared in the manifest",
            details={"roleId": role_id},
        )

    result = _role_result(
        role,
        node_tags=node_tags,
        model_fingerprint=model_fingerprint,
        manifest_sha256=semantic_manifest["manifest"]["sha256"],
    )
    return {
        "schemaVersion": "1.0",
        "kind": "semantic_role_resolution",
        **result,
    }
