from __future__ import annotations

from pathlib import Path
from typing import Any

from fem_core.cross_solver import validate_cross_solver
from fem_core.errors import FemCoreError
from fem_core.evidence.api import project_run_evidence
from fem_core.health import build_health_report
from fem_core.load_inspection import inspect_load
from fem_core.load_standardization import standardize_load
from fem_core.model_inspection import inspect_model
from fem_core.model_spec import (
    evaluate_engineering_model_readiness,
    render_opensees_frame_2d,
    validate_engineering_model_spec,
)
from fem_core.protocol import BRIDGE_PROTOCOL, error_envelope, success_envelope
from fem_core.requirements import complete_engineering_requirement
from fem_core.result_intelligence import inspect_result, query_result
from fem_core.semantic_roles import inspect_semantic_roles, resolve_semantic_role
from fem_core.semantic_roles.evidence import project_role_evidence
from fem_core.solvers import get_solver_adapter


def _required_text(payload: dict[str, Any], key: str) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or not value.strip():
        raise FemCoreError("INVALID_ARGUMENT", f"'{key}' must be a non-empty string", details={"field": key})
    return value


def _optional_text(payload: dict[str, Any], key: str) -> str | None:
    value = payload.get(key)
    if value is None:
        return None
    if not isinstance(value, str) or not value.strip():
        raise FemCoreError(
            "INVALID_ARGUMENT",
            f"'{key}' must be a non-empty string when provided",
            details={"field": key},
        )
    return value


def _required_object(payload: dict[str, Any], key: str) -> dict[str, Any]:
    value = payload.get(key)
    if not isinstance(value, dict):
        raise FemCoreError("INVALID_ARGUMENT", f"'{key}' must be a JSON object", details={"field": key})
    return value


def _optional_object(payload: dict[str, Any], key: str) -> dict[str, Any] | None:
    value = payload.get(key)
    if value is None:
        return None
    if not isinstance(value, dict):
        raise FemCoreError(
            "INVALID_ARGUMENT",
            f"'{key}' must be a JSON object when provided",
            details={"field": key},
        )
    return value


def _solver_call_arguments(payload: dict[str, Any]) -> tuple[str, str, str | None, dict[str, Any] | None]:
    solver = _required_text(payload, "solver")
    model_path = _required_text(payload, "modelPath")
    load_path = _optional_text(payload, "loadPath")
    solver_options = _optional_object(payload, "solverOptions")
    normalized_solver = solver.strip().lower()
    if normalized_solver in {"opensees", "openseespy"} and solver_options is not None:
        unsupported = sorted(set(solver_options) - {"responsePlanPath"})
        if unsupported:
            raise FemCoreError(
                "UNSUPPORTED_SOLVER_OPTIONS",
                "OpenSees accepts only solverOptions.responsePlanPath in PR15",
                details={"solver": solver, "unsupported": unsupported},
            )
    if normalized_solver in {"ansys", "mapdl", "ansys-mapdl"} and solver_options is not None:
        unsupported = sorted(set(solver_options) - {"modelUnits"})
        if unsupported:
            raise FemCoreError(
                "UNSUPPORTED_SOLVER_OPTIONS",
                "ANSYS accepts only solverOptions.modelUnits in PR15",
                details={"solver": solver, "unsupported": unsupported},
            )
    return solver, model_path, load_path, solver_options


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
        elif command == "modelSpec.validate":
            result = validate_engineering_model_spec(_required_object(payload, "spec"))
        elif command == "modelSpec.readiness":
            result = evaluate_engineering_model_readiness(_required_object(payload, "spec"))
        elif command == "modelSpec.renderOpenSees":
            result = render_opensees_frame_2d(workspace, _required_object(payload, "spec"))
        elif command == "requirement.complete":
            result = complete_engineering_requirement(_required_object(payload, "draft"))
        elif command == "load.inspect":
            result = inspect_load(workspace, _required_text(payload, "path"))
        elif command == "load.standardize":
            output_path = payload.get("outputPath")
            if output_path is not None and not isinstance(output_path, str):
                raise FemCoreError("INVALID_ARGUMENT", "'outputPath' must be a string when provided")
            result = standardize_load(
                workspace,
                _required_text(payload, "path"),
                _required_object(payload, "mapping"),
                output_path=output_path,
            )
        elif command == "semantic.inspect":
            result = inspect_semantic_roles(
                workspace,
                model_path=_required_text(payload, "modelPath"),
                manifest_path=_required_text(payload, "manifestPath"),
            )
        elif command == "semantic.resolve":
            result = resolve_semantic_role(
                workspace,
                model_path=_required_text(payload, "modelPath"),
                manifest_path=_required_text(payload, "manifestPath"),
                role_id=_required_text(payload, "roleId"),
            )
        elif command == "result.inspect":
            result = inspect_result(workspace, _required_text(payload, "runRef"))
        elif command == "result.query":
            result = query_result(
                workspace,
                _required_text(payload, "runRef"),
                _required_object(payload, "query"),
            )
        elif command == "evidence.project":
            result = project_run_evidence(
                workspace,
                project_id=_required_text(payload, "projectId"),
                run_ref=_required_text(payload, "runRef"),
                evidence_id=_required_text(payload, "evidenceId"),
                query=_required_object(payload, "query"),
            )
        elif command == "evidence.projectRole":
            query = _required_object(payload, "query")
            result = project_role_evidence(
                workspace,
                project_id=_required_text(payload, "projectId"),
                model_path=_required_text(payload, "modelPath"),
                manifest_path=_required_text(payload, "manifestPath"),
                role_id=_required_text(payload, "roleId"),
                run_ref=_required_text(payload, "runRef"),
                evidence_id=_required_text(payload, "evidenceId"),
                quantity=_required_text(query, "quantity"),
                component=_required_text(query, "component"),
                location=query.get("location"),
                operation=_required_text(query, "operation"),
                offset=query.get("offset", 0),
                limit=query.get("limit", 500),
            )
        elif command == "validation.crossSolver":
            result = validate_cross_solver(
                workspace,
                project_id=_required_text(payload, "projectId"),
                left=_required_object(payload, "left"),
                right=_required_object(payload, "right"),
                query=_required_object(payload, "query"),
            )
        elif command == "solver.status":
            result = get_solver_adapter(_required_text(payload, "solver")).status()
        elif command == "solver.preflight":
            solver, model_path, load_path, solver_options = _solver_call_arguments(payload)
            adapter = get_solver_adapter(solver)
            if solver_options is None:
                result = adapter.preflight(
                    workspace,
                    model_path=model_path,
                    load_path=load_path,
                )
            else:
                result = adapter.preflight(
                    workspace,
                    model_path=model_path,
                    load_path=load_path,
                    solver_options=solver_options,
                )
        elif command == "solver.run":
            solver, model_path, load_path, solver_options = _solver_call_arguments(payload)
            adapter = get_solver_adapter(solver)
            if solver_options is None:
                result = adapter.run(
                    workspace,
                    model_path=model_path,
                    load_path=load_path,
                )
            else:
                result = adapter.run(
                    workspace,
                    model_path=model_path,
                    load_path=load_path,
                    solver_options=solver_options,
                )
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
    # This is the process/protocol boundary: unexpected faults must not leak tracebacks
    # or turn into ad-hoc stderr contracts. Convert them to one stable fail-closed envelope.
    except Exception:  # noqa: BLE001
        return error_envelope(
            request_id=request_id,
            command=command,
            code="INTERNAL_ERROR",
            message="The deterministic FEM core failed unexpectedly",
        )
