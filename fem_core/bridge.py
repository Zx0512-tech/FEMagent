from __future__ import annotations

from pathlib import Path
from typing import Any

from fem_core import bridge_legacy as _legacy
from fem_core.analysis_requirements import complete_engineering_analysis_requirement
from fem_core.analysis_spec import evaluate_engineering_analysis_readiness
from fem_core.analysis_spec.opensees_renderer_v2 import render_opensees_analysis
from fem_core.errors import FemCoreError
from fem_core.protocol import BRIDGE_PROTOCOL, error_envelope, success_envelope
from fem_core.solvers import get_solver_adapter
from fem_core.workflows import (
    prepare_earthquake_workflow,
    summarize_earthquake_workflow,
)

_PR28_ANALYSIS_COMMANDS = {"analysis.readiness", "analysis.renderOpenSees"}
_PR30_ANALYSIS_REQUIREMENT_COMMANDS = {"analysisRequirement.complete"}
_PR31_EARTHQUAKE_WORKFLOW_COMMANDS = {
    "earthquakeWorkflow.prepare",
    "earthquakeWorkflow.summarize",
}


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


def _handle_pr30_analysis_requirement_command(
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
        semantic_context = payload.get("semanticContext")
        if semantic_context is not None and not isinstance(semantic_context, dict):
            raise FemCoreError(
                "INVALID_ARGUMENT",
                "'semanticContext' must be a JSON object when provided",
                details={"field": "semanticContext"},
            )
        result = complete_engineering_analysis_requirement(
            workspace,
            draft=_legacy._required_object(payload, "draft"),
            model_spec=_legacy._required_object(payload, "modelSpec"),
            load_artifact_path=_legacy._required_text(payload, "loadArtifactPath"),
            semantic_context=semantic_context,
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


def _handle_pr31_earthquake_workflow_command(
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

        if command == "earthquakeWorkflow.prepare":
            semantic_context = payload.get("semanticContext")
            if semantic_context is not None and not isinstance(semantic_context, dict):
                raise FemCoreError(
                    "INVALID_ARGUMENT",
                    "'semanticContext' must be a JSON object when provided",
                    details={"field": "semanticContext"},
                )
            solver_model_path = payload.get("solverModelPath")
            if solver_model_path is not None and (
                not isinstance(solver_model_path, str)
                or not solver_model_path.strip()
            ):
                raise FemCoreError(
                    "INVALID_ARGUMENT",
                    "'solverModelPath' must be a non-empty string when provided",
                    details={"field": "solverModelPath"},
                )
            result = prepare_earthquake_workflow(
                workspace,
                solver=_legacy._required_text(payload, "solver"),
                draft=_legacy._required_object(payload, "draft"),
                model_spec=_legacy._required_object(payload, "modelSpec"),
                load_artifact_path=_legacy._required_text(payload, "loadArtifactPath"),
                semantic_context=semantic_context,
                solver_model_path=solver_model_path,
                solver_adapter_factory=get_solver_adapter,
            )
        else:
            result = summarize_earthquake_workflow(
                workspace,
                workflow_manifest_path=_legacy._required_text(
                    payload,
                    "workflowManifestPath",
                ),
                workflow_manifest_sha256=_legacy._required_text(
                    payload,
                    "workflowManifestSha256",
                ),
                run_ref=_legacy._required_text(payload, "runRef"),
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
    if isinstance(request, dict) and request.get("command") in _PR30_ANALYSIS_REQUIREMENT_COMMANDS:
        return _handle_pr30_analysis_requirement_command(request, workspace=workspace)
    if isinstance(request, dict) and request.get("command") in _PR31_EARTHQUAKE_WORKFLOW_COMMANDS:
        return _handle_pr31_earthquake_workflow_command(request, workspace=workspace)
    return _legacy.handle_request(
        request,
        workspace=workspace,
        solver_adapter_factory=get_solver_adapter,
    )


__all__ = ["get_solver_adapter", "handle_request"]
