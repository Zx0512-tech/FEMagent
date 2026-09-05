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


__all__ = ["load_opensees_response_plan"]
