from __future__ import annotations

from pathlib import Path
from typing import Any

from fem_core import bridge_legacy as _legacy
from fem_core.analysis_spec import evaluate_engineering_analysis_readiness
from fem_core.analysis_spec.opensees_renderer_v2 import render_opensees_analysis
from fem_core.errors import FemCoreError
from fem_core.protocol import BRIDGE_PROTOCOL, error_envelope, success_envelope

_PR28_ANALYSIS_COMMANDS = {"analysis.readiness", "analysis.renderOpenSees"}


def _handle_pr28_analysis_command(
    request: dict[str, Any],
    *,
    workspace: Path,
) -> dict[str, Any]:
    request_id = request.get("requestId") if isinstance(request.get("requestId"), str) else "unknown"
    command = request.get("command") if isinstance(request.get("command"), str) else "unknown"
    try:
        if request.get("protocol") != BRIDGE_PROTOCOL:
            raise FemCoreError(
                "PROTOCOL_MISMATCH",
                "Unsupported FEMagent bridge protocol",
                details={"expected": BRIDGE_PROTOCOL, "received": request.get("protocol")},
            )
        if request_id == "unknown":
            raise FemCoreError("INVALID_REQUEST_ID", "Bridge requestId must be a string")
        payload = request.get("payload", {})
        if not isinstance(payload, dict):
            raise FemCoreError("INVALID_PAYLOAD", "Bridge payload must be a JSON object")
        model_spec = _legacy._required_object(payload, "modelSpec")
        analysis_spec = _legacy._required_object(payload, "analysisSpec")
        if command == "analysis.readiness":
            result = evaluate_engineering_analysis_readiness(
                model_spec,
                analysis_spec,
                workspace=workspace,
            )
        else:
            result = render_opensees_analysis(
                workspace,
                model_spec,
                analysis_spec,
            )
        return success_envelope(request_id=request_id, command=command, result=result)
    except FemCoreError as exc:
        return error_envelope(
            request_id=request_id,
            command=command,
            code=exc.code,
            message=exc.message,
            details=exc.details,
        )
    except Exception:  # noqa: BLE001 - stable process/protocol boundary.
        return error_envelope(
            request_id=request_id,
            command=command,
            code="INTERNAL_ERROR",
            message="The deterministic FEM core failed unexpectedly",
        )


def handle_request(request: Any, *, workspace: Path) -> dict[str, Any]:
    if isinstance(request, dict) and request.get("command") in _PR28_ANALYSIS_COMMANDS:
        return _handle_pr28_analysis_command(request, workspace=workspace)
    return _legacy.handle_request(request, workspace=workspace)


__all__ = ["handle_request"]
