from __future__ import annotations

from pathlib import Path
from typing import Any

from fem_core.errors import FemCoreError
from fem_core.health import build_health_report
from fem_core.load_inspection import inspect_load
from fem_core.model_inspection import inspect_model
from fem_core.protocol import BRIDGE_PROTOCOL, error_envelope, success_envelope


def _required_text(payload: dict[str, Any], key: str) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or not value.strip():
        raise FemCoreError("INVALID_ARGUMENT", f"'{key}' must be a non-empty string", details={"field": key})
    return value


def handle_request(request: Any, *, workspace: Path) -> dict[str, Any]:
    request_id = "unknown"
    command = "unknown"
    try:
        if not isinstance(request, dict):
            raise FemCoreError("INVALID_REQUEST", "Bridge request must be a JSON object")
        request_id = request.get("requestId") if isinstance(request.get("requestId"), str) else "unknown"
        command = request.get("command") if isinstance(request.get("command"), str) else "unknown"
        if request.get("protocol") != BRIDGE_PROTOCOL:
            raise FemCoreError(
                "PROTOCOL_MISMATCH",
                "Unsupported FEMagent bridge protocol",
                details={"expected": BRIDGE_PROTOCOL, "received": request.get("protocol")},
            )
        if request_id == "unknown":
            raise FemCoreError("INVALID_REQUEST_ID", "Bridge requestId must be a string")
        if command == "unknown":
            raise FemCoreError("INVALID_COMMAND", "Bridge command must be a string")
        payload = request.get("payload", {})
        if not isinstance(payload, dict):
            raise FemCoreError("INVALID_PAYLOAD", "Bridge payload must be a JSON object")

        if command == "health":
            result = build_health_report()
        elif command == "model.inspect":
            result = inspect_model(workspace, _required_text(payload, "path"))
        elif command == "load.inspect":
            result = inspect_load(workspace, _required_text(payload, "path"))
        else:
            raise FemCoreError("UNKNOWN_COMMAND", "Unknown FEM engineering command", details={"command": command})
        return success_envelope(request_id=request_id, command=command, result=result)
    except FemCoreError as exc:
        return error_envelope(
            request_id=request_id,
            command=command,
            code=exc.code,
            message=exc.message,
            details=exc.details,
        )
    except Exception:
        return error_envelope(
            request_id=request_id,
            command=command,
            code="INTERNAL_ERROR",
            message="The deterministic FEM core failed unexpectedly",
        )
