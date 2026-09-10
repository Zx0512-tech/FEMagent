from __future__ import annotations

from typing import Any

from fem_core.errors import FemCoreError
from fem_core.opensees_response_mapping import (
    derive_response_unit,
    resolve_opensees_response_access,
)


def compact_validation(validation: dict[str, Any]) -> dict[str, Any]:
    return {
        "schema": validation["schema"],
        "status": validation["status"],
        "issues": validation["issues"],
    }


def readiness_issue(code: str, path: str, message: str) -> dict[str, str]:
    return {
        "severity": "ERROR",
        "code": code,
        "path": path,
        "message": message,
    }


def check_model_binding(
    *,
    model_fingerprint: str,
    normalized_analysis: dict[str, Any],
) -> tuple[dict[str, Any], list[dict[str, str]]]:
    received = str(normalized_analysis["modelSpecFingerprint"])
    ok = received == model_fingerprint
    issues = [] if ok else [
        readiness_issue(
            "ANALYSIS_READINESS_MODEL_FINGERPRINT_MISMATCH",
            "analysisSpec.modelSpecFingerprint",
            "AnalysisSpec is not bound to the current normalized ModelSpec fingerprint",
        )
    ]
    return {
        "status": "PASS" if ok else "FAIL",
        "expected": model_fingerprint,
        "received": received,
    }, issues


def check_force_unit_compatibility(
    *,
    normalized_model: dict[str, Any],
    normalized_analysis: dict[str, Any],
) -> tuple[dict[str, Any], list[dict[str, str]]]:
    model_force = str(normalized_model["units"]["force"])
    analysis_force = str(normalized_analysis["units"]["force"])
    ok = model_force == analysis_force
    issues = [] if ok else [
        readiness_issue(
            "ANALYSIS_READINESS_FORCE_UNIT_MISMATCH",
            "analysisSpec.units.force",
            "OpenSees linear-static readiness requires AnalysisSpec force units to match ModelSpec force units",
        )
    ]
    return {
        "status": "PASS" if ok else "FAIL",
        "modelForce": model_force,
        "analysisForce": analysis_force,
    }, issues


def check_load_targets(
    *,
    normalized_model: dict[str, Any],
    load_cases: list[dict[str, Any]],
    path: str,
) -> tuple[dict[str, Any], list[dict[str, str]]]:
    node_ids = {int(node["id"]) for node in normalized_model["nodes"]}
    missing = sorted(
        {
            int(load["nodeId"])
            for load_case in load_cases
            for load in load_case["nodalLoads"]
            if int(load["nodeId"]) not in node_ids
        }
    )
    issues = [
        readiness_issue(
            "ANALYSIS_READINESS_LOAD_NODE_NOT_FOUND",
            path,
            f"Nodal load target node {node_id} does not exist in the bound ModelSpec",
        )
        for node_id in missing
    ]
    return {
        "status": "FAIL" if missing else "PASS",
        "missingNodeIds": missing,
    }, issues


def check_result_targets(
    *,
    normalized_model: dict[str, Any],
    requests: list[dict[str, Any]],
) -> tuple[dict[str, Any], list[dict[str, str]]]:
    node_ids = {int(node["id"]) for node in normalized_model["nodes"]}
    element_ids = {int(element["id"]) for element in normalized_model["elements"]}
    missing_nodes = sorted(
        {
            int(request["target"]["id"])
            for request in requests
            if request.get("target", {}).get("type") == "NODE"
            and int(request["target"]["id"]) not in node_ids
        }
    )
    missing_elements = sorted(
        {
            int(request["target"]["id"])
            for request in requests
            if request.get("target", {}).get("type") == "ELEMENT"
            and int(request["target"]["id"]) not in element_ids
        }
    )
    issues = [
        readiness_issue(
            "ANALYSIS_READINESS_RESULT_NODE_NOT_FOUND",
            "analysisSpec.resultRequests",
            f"Result target node {node_id} does not exist in the bound ModelSpec",
        )
        for node_id in missing_nodes
    ]
    issues.extend(
        readiness_issue(
            "ANALYSIS_READINESS_RESULT_ELEMENT_NOT_FOUND",
            "analysisSpec.resultRequests",
            f"Result target element {element_id} does not exist in the bound ModelSpec",
        )
        for element_id in missing_elements
    )
    return {
        "status": "FAIL" if missing_nodes or missing_elements else "PASS",
        "missingNodeIds": missing_nodes,
        "missingElementIds": missing_elements,
    }, issues


def _reaction_required_dof(request: dict[str, Any]) -> str | None:
    quantity = request.get("quantity")
    component = request.get("component")
    if quantity == "REACTION_FORCE" and component == "X":
        return "UX"
    if quantity == "REACTION_FORCE" and component == "Y":
        return "UY"
    if quantity == "REACTION_MOMENT" and component == "Z":
        return "RZ"
    return None


def check_reaction_semantics(
    *,
    normalized_model: dict[str, Any],
    requests: list[dict[str, Any]],
) -> tuple[dict[str, Any], list[dict[str, str]]]:
    node_ids = {int(node["id"]) for node in normalized_model["nodes"]}
    constraints = {
        int(item["nodeId"]): {str(dof) for dof in item["dofs"]}
        for item in normalized_model["constraints"]
    }
    unrestrained: list[str] = []
    issues: list[dict[str, str]] = []
    for request in requests:
        required_dof = _reaction_required_dof(request)
        if required_dof is None or not isinstance(request.get("target"), dict):
            continue
        node_id = int(request["target"]["id"])
        if node_id not in node_ids:
            continue
        if required_dof not in constraints.get(node_id, set()):
            request_id = str(request["requestId"])
            unrestrained.append(request_id)
            issues.append(
                readiness_issue(
                    "ANALYSIS_READINESS_REACTION_DOF_UNRESTRAINED",
                    f"analysisSpec.resultRequests.{request_id}",
                    f"Reaction request {request_id} requires restrained DOF {required_dof}",
                )
            )
    return {
        "status": "FAIL" if unrestrained else "PASS",
        "unrestrainedRequests": sorted(unrestrained),
    }, issues


def build_structural_response_mapping(
    *,
    normalized_model: dict[str, Any],
    requests: list[dict[str, Any]],
) -> tuple[dict[str, Any], list[dict[str, str]]]:
    element_by_id = {int(item["id"]): item for item in normalized_model["elements"]}
    channels: list[dict[str, Any]] = []
    issues: list[dict[str, str]] = []
    failed = False

    for request in requests:
        target = request.get("target")
        if not isinstance(target, dict):
            failed = True
            issues.append(
                readiness_issue(
                    "ANALYSIS_READINESS_RESPONSE_MAPPING_UNAVAILABLE",
                    f"analysisSpec.resultRequests.{request['requestId']}",
                    "No proven OpenSees response mapping is available for a request without a target",
                )
            )
            continue

        element_type: str | None = None
        if target.get("type") == "ELEMENT":
            element = element_by_id.get(int(target["id"]))
            if element is None:
                failed = True
                continue
            if element.get("type") == "ELASTIC_FRAME_2D":
                element_type = "ElasticBeam2d"
        try:
            access = resolve_opensees_response_access(request, element_type=element_type)
            unit = derive_response_unit(request, normalized_model["units"])
        except FemCoreError as exc:
            failed = True
            issues.append(
                readiness_issue(
                    "ANALYSIS_READINESS_RESPONSE_MAPPING_UNAVAILABLE",
                    f"analysisSpec.resultRequests.{request['requestId']}",
                    f"No proven OpenSees response mapping is available: {exc.code}",
                )
            )
            continue

        channel: dict[str, Any] = {
            "requestId": request["requestId"],
            "quantity": request["quantity"],
            "target": dict(target),
            "component": request["component"],
            **access,
            "unit": unit,
        }
        if "location" in request:
            channel["location"] = request["location"]
        channels.append(channel)

    channels.sort(key=lambda item: str(item["requestId"]))
    return {
        "status": "FAIL" if failed else "PASS",
        "channels": channels,
    }, issues


__all__ = [
    "build_structural_response_mapping",
    "check_force_unit_compatibility",
    "check_load_targets",
    "check_model_binding",
    "check_reaction_semantics",
    "check_result_targets",
    "compact_validation",
    "readiness_issue",
]
