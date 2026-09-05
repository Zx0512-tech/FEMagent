from __future__ import annotations

import json
import re
from hashlib import sha256
from pathlib import Path
from typing import Any

from fem_core.errors import FemCoreError
from fem_core.pathing import resolve_workspace_file, workspace_relative_path
from fem_core.structural_response import normalize_structural_query

_CHANNEL_ID = re.compile(r"^[A-Za-z][A-Za-z0-9_-]{0,63}$")
_TOP_LEVEL_KEYS = {"schemaVersion", "kind", "channels"}
_CHANNEL_KEYS = {"channelId", "quantity", "target", "component", "location"}

# OpenSees ElasticBeam2d localForce returns [N_i, V_i, Mz_i, N_j, V_j, Mz_j].
# This is intentionally the only PR15 V1 generalized-force mapping until another
# formulation is proven by a real runtime test.
_ELASTIC_BEAM_2D_LOCAL_FORCE = {
    ("N", "END_I"): 0,
    ("VY", "END_I"): 1,
    ("MZ", "END_I"): 2,
    ("N", "END_J"): 3,
    ("VY", "END_J"): 4,
    ("MZ", "END_J"): 5,
}


def _invalid(message: str, **details: Any) -> FemCoreError:
    return FemCoreError("INVALID_STRUCTURAL_RESPONSE_PLAN", message, details=details)


def load_opensees_response_plan(workspace: Path, path: str) -> dict[str, Any]:
    plan_path = resolve_workspace_file(workspace, path)
    try:
        content = plan_path.read_bytes()
        payload = json.loads(content.decode("utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise _invalid("OpenSees Structural Response Plan must be valid UTF-8 JSON") from exc

    if not isinstance(payload, dict):
        raise _invalid("OpenSees Structural Response Plan must be a JSON object")
    unknown_top = sorted(set(payload) - _TOP_LEVEL_KEYS)
    if unknown_top:
        raise _invalid("OpenSees Structural Response Plan contains unsupported top-level fields", fields=unknown_top)
    if payload.get("schemaVersion") != "1.0":
        raise _invalid(
            "OpenSees Structural Response Plan schemaVersion must be '1.0'",
            schemaVersion=payload.get("schemaVersion"),
        )
    if payload.get("kind") != "structural_response_plan":
        raise _invalid(
            "OpenSees Structural Response Plan kind must be 'structural_response_plan'",
            kind=payload.get("kind"),
        )

    raw_channels = payload.get("channels")
    if not isinstance(raw_channels, list) or not raw_channels:
        raise _invalid("OpenSees Structural Response Plan channels must be a non-empty array")

    channel_ids: set[str] = set()
    channels: list[dict[str, Any]] = []
    for index, raw_channel in enumerate(raw_channels):
        if not isinstance(raw_channel, dict):
            raise _invalid("Each structural response channel must be a JSON object", channelIndex=index)
        unknown_channel = sorted(set(raw_channel) - _CHANNEL_KEYS)
        if unknown_channel:
            raise _invalid(
                "Structural response channel contains unsupported fields",
                channelIndex=index,
                fields=unknown_channel,
            )
        channel_id = raw_channel.get("channelId")
        if not isinstance(channel_id, str) or _CHANNEL_ID.fullmatch(channel_id) is None:
            raise _invalid(
                "channelId must start with an ASCII letter and contain only letters, digits, _ or -",
                channelIndex=index,
                channelId=channel_id,
            )
        if channel_id in channel_ids:
            raise _invalid("Structural Response Plan contains a duplicate channelId", channelId=channel_id)
        channel_ids.add(channel_id)

        query = {key: value for key, value in raw_channel.items() if key != "channelId"}
        query["operation"] = "SERIES"
        try:
            normalized = normalize_structural_query(query)
        except FemCoreError as exc:
            raise _invalid(
                "Structural response channel identity is invalid",
                channelIndex=index,
                channelId=channel_id,
                reasonCode=exc.code,
            ) from exc
        normalized.pop("operation", None)
        normalized.pop("offset", None)
        normalized.pop("limit", None)
        channels.append({"channelId": channel_id, **normalized})

    return {
        "schemaVersion": "1.0",
        "kind": "structural_response_plan",
        "channels": channels,
        "plan": {
            "path": workspace_relative_path(workspace, plan_path),
            "sha256": sha256(content).hexdigest(),
        },
    }


def opensees_response_mapping(channel: dict[str, Any], *, element_type: str) -> dict[str, Any]:
    if channel.get("quantity") == "GENERALIZED_FORCE" and element_type == "ElasticBeam2d":
        key = (str(channel.get("component")), str(channel.get("location")))
        index = _ELASTIC_BEAM_2D_LOCAL_FORCE.get(key)
        if index is not None:
            return {
                "response": "localForce",
                "index": index,
                "vectorLength": 6,
                "referenceFrame": "ELEMENT_LOCAL",
                "unit": None,
            }
    raise FemCoreError(
        "STRUCTURAL_RESPONSE_MAPPING_UNAVAILABLE",
        "OpenSees element formulation does not have a proven canonical structural-response mapping",
        details={
            "channelId": channel.get("channelId"),
            "quantity": channel.get("quantity"),
            "component": channel.get("component"),
            "location": channel.get("location"),
            "target": channel.get("target"),
            "elementType": element_type,
        },
    )


def validate_opensees_response_plan_domain(
    plan: dict[str, Any],
    *,
    element_types: dict[str, str],
) -> None:
    for channel in plan.get("channels", []):
        target = channel.get("target")
        if not isinstance(target, dict) or target.get("type") != "ELEMENT":
            raise FemCoreError(
                "STRUCTURAL_RESPONSE_MAPPING_UNAVAILABLE",
                "PR15 OpenSees runtime recording currently requires ELEMENT response channels",
                details={"channelId": channel.get("channelId"), "target": target},
            )
        element_id = target.get("id")
        element_type = element_types.get(str(element_id))
        if not isinstance(element_type, str) or not element_type:
            raise FemCoreError(
                "STRUCTURAL_RESPONSE_MAPPING_UNAVAILABLE",
                "OpenSees response plan references an element that is unavailable in the realized domain",
                details={"channelId": channel.get("channelId"), "elementId": element_id},
            )
        opensees_response_mapping(channel, element_type=element_type)


__all__ = [
    "load_opensees_response_plan",
    "opensees_response_mapping",
    "validate_opensees_response_plan_domain",
]
