from __future__ import annotations

from typing import Any

from fem_core import __version__

BRIDGE_PROTOCOL = "femagent.bridge/v1"


def success_envelope(*, request_id: str, command: str, result: Any) -> dict[str, Any]:
    return {
        "protocol": BRIDGE_PROTOCOL,
        "requestId": request_id,
        "ok": True,
        "result": result,
        "meta": {"coreVersion": __version__, "command": command},
    }


def error_envelope(
    *,
    request_id: str,
    command: str,
    code: str,
    message: str,
    details: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "protocol": BRIDGE_PROTOCOL,
        "requestId": request_id,
        "ok": False,
        "error": {"code": code, "message": message, "details": details or {}},
        "meta": {"coreVersion": __version__, "command": command},
    }
