from __future__ import annotations

import json
from hashlib import sha256
from itertools import pairwise
from pathlib import Path
from typing import Any

from fem_core import result_intelligence_legacy as _legacy
from fem_core.errors import FemCoreError
from fem_core.modal_results import read_modal_result_set
from fem_core.pathing import resolve_workspace_file, workspace_relative_path

_MODAL_QUANTITIES = frozenset({"EIGENVALUE", "NATURAL_FREQUENCY", "PERIOD", "MODE_SHAPE"})


def _sha256_file(path: Path) -> str:
    return sha256(path.read_bytes()).hexdigest()


def _model_identity(manifest: dict[str, Any]) -> dict[str, Any]:
    recorded = manifest.get("model")
    if not isinstance(recorded, dict):
        return {"path": None, "bundleFingerprint": None}
    raw_path = recorded.get("path")
    raw_fingerprint = recorded.get("bundleFingerprint")
    return {
        "path": raw_path if isinstance(raw_path, str) else None,
        "bundleFingerprint": (
            raw_fingerprint
            if isinstance(raw_fingerprint, str) and len(raw_fingerprint) == 64
            else None
        ),
    }


def _verified_modal_artifact(
    workspace: Path,
    manifest: dict[str, Any],
) -> tuple[Path, dict[str, Any], dict[str, Any]]:
    outputs = manifest["outputs"]
    raw_path = outputs.get("modalResults")
    declared_hash = outputs.get("modalResultsSha256")
    if not isinstance(raw_path, str) or not raw_path.strip():
        raise FemCoreError(
            "INVALID_RUN_MANIFEST",
            "Modal solver run must declare modalResults",
        )
    if not isinstance(declared_hash, str) or len(declared_hash) != 64:
        raise FemCoreError(
            "INVALID_RUN_MANIFEST",
            "Modal solver run must declare modalResultsSha256",
        )
    path = resolve_workspace_file(workspace, raw_path)
    actual_hash = _sha256_file(path)
    if actual_hash.lower() != declared_hash.lower():
        raise FemCoreError(
            "RESULT_ARTIFACT_HASH_MISMATCH",
            "Recorded modal result artifact does not match its declared SHA256",
            details={
                "path": raw_path,
                "declaredSha256": declared_hash,
                "actualSha256": actual_hash,
            },
        )
    artifact = {
        "role": "modalResults",
        "path": workspace_relative_path(workspace, path),
        "sha256": actual_hash,
        "declaredSha256": declared_hash,
        "status": "VERIFIED",
    }
    return path, read_modal_result_set(path), artifact


def _modal_capabilities(
    workspace: Path,
    modal_path: Path,
    modal: dict[str, Any],
) -> list[dict[str, Any]]:
    source_artifact = workspace_relative_path(workspace, modal_path)
    capabilities: list[dict[str, Any]] = []
    for result in modal["results"]:
        capability: dict[str, Any] = {
            "quantity": result["quantity"],
            "mode": result["mode"],
            "unit": result["unit"],
            "sourceArtifact": source_artifact,
            "requestId": result["requestId"],
        }
        if result["quantity"] == "MODE_SHAPE":
            capability.update(
                {
                    "target": dict(result["target"]),
                    "component": result["component"],
                    "normalization": result["normalization"],
                }
            )
        capabilities.append(capability)
    return capabilities


def _inspect_modal_result(
    workspace: Path,
    manifest_path: Path,
    manifest: dict[str, Any],
) -> dict[str, Any]:
    artifacts = _legacy._verify_declared_artifacts(workspace, manifest)
    modal_path, modal, modal_artifact = _verified_modal_artifact(workspace, manifest)
    artifacts.append(modal_artifact)
    capabilities = _modal_capabilities(workspace, modal_path, modal)
    summary = manifest.get("summary") if isinstance(manifest.get("summary"), dict) else {}
    return {
        "schemaVersion": "1.0",
        "kind": "result_manifest",
        "runId": manifest["runId"],
        "caseFingerprint": manifest["caseFingerprint"],
        "runManifest": workspace_relative_path(workspace, manifest_path),
        "solver": manifest["solver"],
        "model": _model_identity(manifest),
        "integrity": {"status": "VALID", "artifacts": artifacts},
        "abscissa": None,
        "queryCapabilities": capabilities,
        "observations": summary,
        "warnings": [],
    }


def _raw_structural_payload(workspace: Path, manifest: dict[str, Any]) -> dict[str, Any] | None:
    raw_path = manifest["outputs"].get("structuralResponse")
    if not isinstance(raw_path, str):
        return None
    path = resolve_workspace_file(workspace, raw_path)
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise FemCoreError("INVALID_RESULT_SERIES", "Structural response artifact must be UTF-8 JSON") from exc
    return payload if isinstance(payload, dict) else None


def _has_relative_acceleration(workspace: Path, manifest: dict[str, Any]) -> bool:
    payload = _raw_structural_payload(workspace, manifest)
    if payload is None or not isinstance(payload.get("channels"), list):
        return False
    return any(
        isinstance(channel, dict) and channel.get("quantity") == "RELATIVE_ACCELERATION"
        for channel in payload["channels"]
    )


def _relative_acceleration_identity(raw: dict[str, Any]) -> dict[str, Any]:
    target = raw.get("target")
    target_id = target.get("id") if isinstance(target, dict) else None
    component = raw.get("component")
    if (
        not isinstance(target, dict)
        or target.get("type") != "NODE"
        or not isinstance(target_id, int)
        or isinstance(target_id, bool)
        or target_id <= 0
        or component not in {"X", "Y"}
    ):
        raise FemCoreError(
            "INVALID_RESULT_SERIES",
            "Relative acceleration requires a positive NODE target and X or Y component",
        )
    return {
        "quantity": "RELATIVE_ACCELERATION",
        "target": {"type": "NODE", "id": target_id},
        "component": component,
    }


def _read_v2_structural_response(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise FemCoreError("INVALID_RESULT_SERIES", "Structural response artifact must be UTF-8 JSON") from exc
    if (
        not isinstance(payload, dict)
        or payload.get("schemaVersion") != "1.0"
        or payload.get("kind") != "structural_response_series"
        or not isinstance(payload.get("channels"), list)
        or not payload["channels"]
    ):
        raise FemCoreError("INVALID_RESULT_SERIES", "Structural response artifact has an invalid schema")

    seen_ids: set[str] = set()
    channels: list[dict[str, Any]] = []
    for index, raw in enumerate(payload["channels"]):
        if not isinstance(raw, dict):
            raise FemCoreError("INVALID_RESULT_SERIES", "Structural response channel must be an object")
        channel_id = raw.get("channelId")
        if not isinstance(channel_id, str) or not channel_id or channel_id in seen_ids:
            raise FemCoreError("INVALID_RESULT_SERIES", "Structural response channelId must be unique")
        seen_ids.add(channel_id)
        if raw.get("quantity") == "RELATIVE_ACCELERATION":
            normalized = _relative_acceleration_identity(raw)
        else:
            query: dict[str, Any] = {
                "quantity": raw.get("quantity"),
                "target": raw.get("target"),
                "component": raw.get("component"),
                "operation": "SERIES",
            }
            if "location" in raw:
                query["location"] = raw.get("location")
            normalized = _legacy.normalize_structural_query(query)

        abscissa_raw = raw.get("abscissaValues")
        values_raw = raw.get("values")
        if not isinstance(abscissa_raw, list) or not isinstance(values_raw, list) or not values_raw:
            raise FemCoreError("INVALID_RESULT_SERIES", "Structural response channel must contain samples")
        if len(abscissa_raw) != len(values_raw):
            raise FemCoreError("INVALID_RESULT_SERIES", "Structural response sample counts do not match")
        abscissa = [
            _legacy._finite(value, column="abscissaValues", row_number=index)
            for value in abscissa_raw
        ]
        values = [
            _legacy._finite(value, column="values", row_number=index)
            for value in values_raw
        ]
        if any(current <= previous for previous, current in pairwise(abscissa)):
            raise FemCoreError(
                "INVALID_RESULT_SERIES",
                "Transient structural response time must be strictly increasing",
            )
        reference_frame = raw.get("referenceFrame")
        abscissa_semantic = raw.get("abscissaSemantic")
        unit = raw.get("unit")
        abscissa_unit = raw.get("abscissaUnit")
        if not isinstance(reference_frame, str) or not reference_frame:
            raise FemCoreError("INVALID_RESULT_SERIES", "Structural response referenceFrame is required")
        if not isinstance(abscissa_semantic, str) or not abscissa_semantic:
            raise FemCoreError("INVALID_RESULT_SERIES", "Structural response abscissaSemantic is required")
        if unit is not None and not isinstance(unit, str):
            raise FemCoreError("INVALID_RESULT_SERIES", "Structural response unit must be string or null")
        if abscissa_unit is not None and not isinstance(abscissa_unit, str):
            raise FemCoreError("INVALID_RESULT_SERIES", "Structural response abscissaUnit must be string or null")
        if raw.get("quantity") == "RELATIVE_ACCELERATION" and reference_frame != "RELATIVE":
            raise FemCoreError(
                "INVALID_RESULT_SERIES",
                "Relative acceleration must preserve the RELATIVE reference frame",
            )
        channel: dict[str, Any] = {
            "channelId": channel_id,
            "quantity": normalized["quantity"],
            "target": normalized["target"],
            "component": normalized["component"],
            "unit": unit,
            "referenceFrame": reference_frame,
            "abscissaSemantic": abscissa_semantic,
            "abscissaUnit": abscissa_unit,
            "abscissaValues": abscissa,
            "values": values,
        }
        if "location" in normalized:
            channel["location"] = normalized["location"]
        channels.append(channel)
    return {"channels": channels}


def _inspect_v2_structural_result(
    workspace: Path,
    manifest_path: Path,
    manifest: dict[str, Any],
) -> dict[str, Any]:
    artifacts = _legacy._verify_declared_artifacts(workspace, manifest)
    raw_path = manifest["outputs"].get("structuralResponse")
    if not isinstance(raw_path, str):
        raise FemCoreError("INVALID_RUN_MANIFEST", "V2 transient run is missing structuralResponse")
    response_path = resolve_workspace_file(workspace, raw_path)
    response = _read_v2_structural_response(response_path)
    source_artifact = workspace_relative_path(workspace, response_path)
    capabilities: list[dict[str, Any]] = []
    for channel in response["channels"]:
        capability: dict[str, Any] = {
            "quantity": channel["quantity"],
            "component": channel["component"],
            "target": dict(channel["target"]),
            "unit": channel["unit"],
            "referenceFrame": channel["referenceFrame"],
            "sourceArtifact": source_artifact,
            "sourceChannelId": channel["channelId"],
        }
        if "location" in channel:
            capability["location"] = channel["location"]
        capabilities.append(capability)
    first = response["channels"][0]
    summary = manifest.get("summary") if isinstance(manifest.get("summary"), dict) else {}
    return {
        "schemaVersion": "1.0",
        "kind": "result_manifest",
        "runId": manifest["runId"],
        "caseFingerprint": manifest["caseFingerprint"],
        "runManifest": workspace_relative_path(workspace, manifest_path),
        "solver": manifest["solver"],
        "model": _model_identity(manifest),
        "integrity": {"status": "VALID", "artifacts": artifacts},
        "abscissa": {
            "semantic": first["abscissaSemantic"],
            "unit": first["abscissaUnit"],
            "sampleCount": len(first["abscissaValues"]),
            "start": first["abscissaValues"][0],
            "end": first["abscissaValues"][-1],
        },
        "queryCapabilities": capabilities,
        "observations": summary,
        "warnings": [],
    }


def inspect_result(workspace: Path, run_ref: str) -> dict[str, Any]:
    manifest_path, manifest = _legacy._load_run_manifest(workspace, run_ref)
    if str(manifest["solver"]["name"]).upper() != "OPENSEESPY":
        return _legacy.inspect_result(workspace, run_ref)
    if isinstance(manifest["outputs"].get("modalResults"), str):
        return _inspect_modal_result(workspace, manifest_path, manifest)
    if _has_relative_acceleration(workspace, manifest):
        return _inspect_v2_structural_result(workspace, manifest_path, manifest)
    return _legacy.inspect_result(workspace, run_ref)


def _validated_modal_query(query: dict[str, Any]) -> dict[str, Any]:
    quantity = query.get("quantity")
    operation = query.get("operation")
    mode = query.get("mode")
    if quantity not in _MODAL_QUANTITIES:
        raise FemCoreError("INVALID_RESULT_QUERY", "Modal result quantity is unsupported")
    if operation != "VALUE":
        raise FemCoreError("INVALID_RESULT_QUERY", "Modal result query operation must be VALUE")
    if not isinstance(mode, int) or isinstance(mode, bool) or mode <= 0:
        raise FemCoreError("INVALID_RESULT_QUERY", "Modal result query mode must be a positive integer")
    normalized: dict[str, Any] = {
        "quantity": quantity,
        "mode": mode,
        "operation": "VALUE",
    }
    if quantity == "MODE_SHAPE":
        target = query.get("target")
        target_id = target.get("id") if isinstance(target, dict) else None
        component = query.get("component")
        if (
            not isinstance(target, dict)
            or target.get("type") != "NODE"
            or not isinstance(target_id, int)
            or isinstance(target_id, bool)
            or target_id <= 0
            or component not in {"X", "Y", "RZ"}
        ):
            raise FemCoreError(
                "INVALID_RESULT_QUERY",
                "MODE_SHAPE VALUE query requires a positive NODE target and X, Y, or RZ component",
            )
        normalized["target"] = {"type": "NODE", "id": target_id}
        normalized["component"] = component
    elif "target" in query or "component" in query:
        raise FemCoreError(
            "INVALID_RESULT_QUERY",
            "Scalar modal VALUE queries do not accept target or component",
        )
    return normalized


def _query_modal(
    workspace: Path,
    manifest: dict[str, Any],
    normalized: dict[str, Any],
) -> dict[str, Any]:
    modal_path, modal, _ = _verified_modal_artifact(workspace, manifest)
    match: dict[str, Any] | None = None
    for result in modal["results"]:
        if result["quantity"] != normalized["quantity"] or result["mode"] != normalized["mode"]:
            continue
        if normalized["quantity"] == "MODE_SHAPE" and (
            result.get("target") != normalized["target"]
            or result.get("component") != normalized["component"]
        ):
            continue
        match = result
        break
    if match is None:
        raise FemCoreError(
            "RESULT_SERIES_UNAVAILABLE",
            "The recorded run does not contain the requested modal value",
            details={"quantity": normalized["quantity"], "mode": normalized["mode"]},
        )
    response: dict[str, Any] = {
        "schemaVersion": "1.0",
        "kind": "result_query",
        "runId": manifest["runId"],
        "caseFingerprint": manifest["caseFingerprint"],
        "solver": manifest["solver"],
        "quantity": match["quantity"],
        "mode": match["mode"],
        "operation": "VALUE",
        "unit": match["unit"],
        "value": match["value"],
        "source": {
            "artifact": workspace_relative_path(workspace, modal_path),
            "requestId": match["requestId"],
        },
    }
    if match["quantity"] == "MODE_SHAPE":
        response.update(
            {
                "target": dict(match["target"]),
                "component": match["component"],
                "normalization": match["normalization"],
            }
        )
    return response


def _validated_v2_structural_query(query: dict[str, Any]) -> dict[str, Any]:
    if query.get("quantity") != "RELATIVE_ACCELERATION":
        return _legacy._validated_query(query)
    operation = query.get("operation")
    if not isinstance(operation, str) or operation.strip().upper() not in {"SUMMARY", "SERIES"}:
        raise FemCoreError(
            "INVALID_RESULT_QUERY",
            "Relative acceleration query operation must be SUMMARY or SERIES",
        )
    target = query.get("target")
    target_id = target.get("id") if isinstance(target, dict) else None
    if (
        not isinstance(target, dict)
        or str(target.get("type") or "").upper() != "NODE"
        or not isinstance(target_id, int)
        or isinstance(target_id, bool)
        or target_id <= 0
    ):
        raise FemCoreError("INVALID_RESULT_QUERY", "Relative acceleration requires a positive NODE target")
    component = _legacy._normalized_component(query.get("component"))
    if component not in {"X", "Y"}:
        raise FemCoreError("INVALID_RESULT_QUERY", "Relative acceleration supports X or Y components")
    offset, limit = _legacy._validated_paging(query)
    return {
        "quantity": "RELATIVE_ACCELERATION",
        "operation": operation.strip().upper(),
        "target": {"type": "NODE", "id": target_id},
        "component": component,
        "offset": offset,
        "limit": limit,
    }


def _query_v2_structural(
    workspace: Path,
    manifest: dict[str, Any],
    result_manifest: dict[str, Any],
    normalized: dict[str, Any],
) -> dict[str, Any]:
    capability = _legacy._matching_capability(result_manifest, normalized)
    source_channel_id = capability.get("sourceChannelId")
    raw_path = manifest["outputs"].get("structuralResponse")
    if not isinstance(source_channel_id, str) or not isinstance(raw_path, str):
        raise FemCoreError("RESULT_SERIES_UNAVAILABLE", "This OpenSees run did not record the requested response")
    response_file = resolve_workspace_file(workspace, raw_path)
    structural = _read_v2_structural_response(response_file)
    channel = next(
        (item for item in structural["channels"] if item["channelId"] == source_channel_id),
        None,
    )
    if channel is None:
        raise FemCoreError("RESULT_SERIES_UNAVAILABLE", "Recorded structural response channel is missing")
    response = _legacy._base_query_response(
        result_manifest,
        normalized,
        unit=channel["unit"],
        reference_frame=channel["referenceFrame"],
        abscissa_semantic=channel["abscissaSemantic"],
        abscissa_unit=channel["abscissaUnit"],
        source={
            "artifact": workspace_relative_path(workspace, response_file),
            "channelId": source_channel_id,
        },
    )
    return _legacy._attach_summary_or_series(
        response,
        normalized,
        abscissa=channel["abscissaValues"],
        values=channel["values"],
    )


def query_result(workspace: Path, run_ref: str, query: dict[str, Any]) -> dict[str, Any]:
    manifest_path, manifest = _legacy._load_run_manifest(workspace, run_ref)
    del manifest_path
    if (
        str(manifest["solver"]["name"]).upper() == "OPENSEESPY"
        and isinstance(manifest["outputs"].get("modalResults"), str)
        and query.get("quantity") in _MODAL_QUANTITIES
    ):
        return _query_modal(workspace, manifest, _validated_modal_query(query))
    if str(manifest["solver"]["name"]).upper() == "OPENSEESPY" and _has_relative_acceleration(
        workspace, manifest
    ):
        normalized = _validated_v2_structural_query(query)
        result_manifest = inspect_result(workspace, run_ref)
        return _query_v2_structural(workspace, manifest, result_manifest, normalized)
    return _legacy.query_result(workspace, run_ref, query)


__all__ = ["inspect_result", "query_result"]
