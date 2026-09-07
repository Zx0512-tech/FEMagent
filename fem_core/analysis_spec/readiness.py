from __future__ import annotations

from typing import Any

from fem_core.analysis_spec.validator import validate_engineering_analysis_spec
from fem_core.errors import FemCoreError
from fem_core.model_spec.readiness import evaluate_engineering_model_readiness
from fem_core.model_spec.validator import validate_engineering_model_spec
from fem_core.opensees_response_mapping import (
    derive_response_unit,
    resolve_opensees_response_access,
)

READINESS_SCHEMA = "FEMAGENT_ANALYSIS_READINESS_V1"
READINESS_PROFILE = "OPENSEES_FRAME_2D_LINEAR_STATIC_V1"


def _compact_validation(validation: dict[str, Any]) -> dict[str, Any]:
    return {
        "schema": validation["schema"],
        "status": validation["status"],
        "issues": validation["issues"],
    }


def _issue(code: str, path: str, message: str) -> dict[str, str]:
    return {
        "severity": "ERROR",
        "code": code,
        "path": path,
        "message": message,
    }


def _skipped_checks() -> dict[str, dict[str, Any]]:
    return {
        "modelReadiness": {"status": "SKIPPED"},
        "modelBinding": {"status": "SKIPPED"},
        "unitCompatibility": {"status": "SKIPPED"},
        "loadTargets": {"status": "SKIPPED", "missingNodeIds": []},
        "resultTargets": {
            "status": "SKIPPED",
            "missingNodeIds": [],
            "missingElementIds": [],
        },
        "reactionSemantics": {"status": "SKIPPED", "unrestrainedRequests": []},
        "responseMapping": {"status": "SKIPPED", "channels": []},
    }


def _invalid_spec_result(
    model_validation: dict[str, Any],
    analysis_validation: dict[str, Any],
) -> dict[str, Any]:
    issues: list[dict[str, str]] = []
    if model_validation["status"] != "VALID":
        issues.append(
            _issue(
                "ANALYSIS_READINESS_INVALID_MODEL_SPEC",
                "modelSpec",
                "Analysis Readiness requires an intrinsically valid EngineeringModelSpec",
            )
        )
    if analysis_validation["status"] != "VALID":
        issues.append(
            _issue(
                "ANALYSIS_READINESS_INVALID_ANALYSIS_SPEC",
                "analysisSpec",
                "Analysis Readiness requires an intrinsically valid EngineeringAnalysisSpec",
            )
        )
    return {
        "schema": READINESS_SCHEMA,
        "status": "INVALID_SPEC",
        "profile": READINESS_PROFILE,
        "modelSpecFingerprint": model_validation.get("modelSpecFingerprint"),
        "analysisSpecFingerprint": analysis_validation.get("analysisSpecFingerprint"),
        "validation": {
            "modelSpec": _compact_validation(model_validation),
            "analysisSpec": _compact_validation(analysis_validation),
        },
        "checks": _skipped_checks(),
        "issues": issues,
    }


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


def evaluate_engineering_analysis_readiness(
    model_spec: dict[str, Any],
    analysis_spec: dict[str, Any],
) -> dict[str, Any]:
    model_validation = validate_engineering_model_spec(model_spec)
    analysis_validation = validate_engineering_analysis_spec(analysis_spec)
    if model_validation["status"] != "VALID" or analysis_validation["status"] != "VALID":
        return _invalid_spec_result(model_validation, analysis_validation)

    normalized_model = model_validation["normalizedSpec"]
    normalized_analysis = analysis_validation["normalizedSpec"]
    model_fingerprint = model_validation["modelSpecFingerprint"]
    analysis_fingerprint = analysis_validation["analysisSpecFingerprint"]
    if not isinstance(normalized_model, dict) or not isinstance(normalized_analysis, dict):
        raise FemCoreError(
            "ANALYSIS_READINESS_INTERNAL_INVARIANT",
            "Valid Engineering Specs must provide normalized representations",
        )
    if not isinstance(model_fingerprint, str) or not isinstance(analysis_fingerprint, str):
        raise FemCoreError(
            "ANALYSIS_READINESS_INTERNAL_INVARIANT",
            "Valid Engineering Specs must provide deterministic fingerprints",
        )

    issues: list[dict[str, str]] = []

    model_readiness = evaluate_engineering_model_readiness(normalized_model)
    model_ready = model_readiness.get("status") == "READY"
    if not model_ready:
        issues.append(
            _issue(
                "ANALYSIS_READINESS_MODEL_NOT_READY",
                "modelSpec",
                "The bound EngineeringModelSpec has not passed Model Readiness",
            )
        )
    model_readiness_check = {
        "status": "PASS" if model_ready else "FAIL",
        "report": model_readiness,
    }

    bound_fingerprint = normalized_analysis["modelSpecFingerprint"]
    binding_ok = bound_fingerprint == model_fingerprint
    if not binding_ok:
        issues.append(
            _issue(
                "ANALYSIS_READINESS_MODEL_FINGERPRINT_MISMATCH",
                "analysisSpec.modelSpecFingerprint",
                "AnalysisSpec is not bound to the current normalized ModelSpec fingerprint",
            )
        )
    model_binding_check = {
        "status": "PASS" if binding_ok else "FAIL",
        "expected": model_fingerprint,
        "received": bound_fingerprint,
    }

    model_force = normalized_model["units"]["force"]
    analysis_force = normalized_analysis["units"]["force"]
    units_ok = model_force == analysis_force
    if not units_ok:
        issues.append(
            _issue(
                "ANALYSIS_READINESS_FORCE_UNIT_MISMATCH",
                "analysisSpec.units.force",
                "PR26 requires AnalysisSpec force units to exactly match ModelSpec force units",
            )
        )
    unit_check = {
        "status": "PASS" if units_ok else "FAIL",
        "modelForce": model_force,
        "analysisForce": analysis_force,
    }

    node_ids = {int(node["id"]) for node in normalized_model["nodes"]}
    element_ids = {int(element["id"]) for element in normalized_model["elements"]}

    missing_load_nodes = sorted(
        {
            int(load["nodeId"])
            for load_case in normalized_analysis["loadCases"]
            for load in load_case["nodalLoads"]
            if int(load["nodeId"]) not in node_ids
        }
    )
    for node_id in missing_load_nodes:
        issues.append(
            _issue(
                "ANALYSIS_READINESS_LOAD_NODE_NOT_FOUND",
                "analysisSpec.loadCases",
                f"Nodal load target node {node_id} does not exist in the bound ModelSpec",
            )
        )
    load_targets_check = {
        "status": "FAIL" if missing_load_nodes else "PASS",
        "missingNodeIds": missing_load_nodes,
    }

    missing_result_nodes = sorted(
        {
            int(request["target"]["id"])
            for request in normalized_analysis["resultRequests"]
            if request["target"]["type"] == "NODE"
            and int(request["target"]["id"]) not in node_ids
        }
    )
    missing_result_elements = sorted(
        {
            int(request["target"]["id"])
            for request in normalized_analysis["resultRequests"]
            if request["target"]["type"] == "ELEMENT"
            and int(request["target"]["id"]) not in element_ids
        }
    )
    for node_id in missing_result_nodes:
        issues.append(
            _issue(
                "ANALYSIS_READINESS_RESULT_NODE_NOT_FOUND",
                "analysisSpec.resultRequests",
                f"Result target node {node_id} does not exist in the bound ModelSpec",
            )
        )
    for element_id in missing_result_elements:
        issues.append(
            _issue(
                "ANALYSIS_READINESS_RESULT_ELEMENT_NOT_FOUND",
                "analysisSpec.resultRequests",
                f"Result target element {element_id} does not exist in the bound ModelSpec",
            )
        )
    result_targets_check = {
        "status": "FAIL" if missing_result_nodes or missing_result_elements else "PASS",
        "missingNodeIds": missing_result_nodes,
        "missingElementIds": missing_result_elements,
    }

    constraints = {
        int(item["nodeId"]): set(str(dof) for dof in item["dofs"])
        for item in normalized_model["constraints"]
    }
    unrestrained_requests: list[str] = []
    for request in normalized_analysis["resultRequests"]:
        required_dof = _reaction_required_dof(request)
        if required_dof is None:
            continue
        node_id = int(request["target"]["id"])
        if node_id not in node_ids:
            continue
        if required_dof not in constraints.get(node_id, set()):
            request_id = str(request["requestId"])
            unrestrained_requests.append(request_id)
            issues.append(
                _issue(
                    "ANALYSIS_READINESS_REACTION_DOF_UNRESTRAINED",
                    f"analysisSpec.resultRequests.{request_id}",
                    f"Reaction request {request_id} requires restrained DOF {required_dof}",
                )
            )
    reaction_check = {
        "status": "FAIL" if unrestrained_requests else "PASS",
        "unrestrainedRequests": sorted(unrestrained_requests),
    }

    element_by_id = {int(item["id"]): item for item in normalized_model["elements"]}
    response_channels: list[dict[str, Any]] = []
    mapping_failed = False
    for request in normalized_analysis["resultRequests"]:
        target = request["target"]
        element_type: str | None = None
        if target["type"] == "ELEMENT":
            element = element_by_id.get(int(target["id"]))
            if element is None:
                mapping_failed = True
                continue
            if element.get("type") == "ELASTIC_FRAME_2D":
                element_type = "ElasticBeam2d"
        try:
            access = resolve_opensees_response_access(request, element_type=element_type)
            unit = derive_response_unit(request, normalized_model["units"])
        except FemCoreError as exc:
            mapping_failed = True
            issues.append(
                _issue(
                    "ANALYSIS_READINESS_RESPONSE_MAPPING_UNAVAILABLE",
                    f"analysisSpec.resultRequests.{request['requestId']}",
                    f"No proven OpenSees response mapping is available: {exc.code}",
                )
            )
            continue
        channel: dict[str, Any] = {
            "requestId": request["requestId"],
            "quantity": request["quantity"],
            "target": dict(request["target"]),
            "component": request["component"],
            **access,
            "unit": unit,
        }
        if "location" in request:
            channel["location"] = request["location"]
        response_channels.append(channel)
    response_channels.sort(key=lambda item: str(item["requestId"]))
    response_mapping_check = {
        "status": "FAIL" if mapping_failed else "PASS",
        "channels": response_channels,
    }

    checks = {
        "modelReadiness": model_readiness_check,
        "modelBinding": model_binding_check,
        "unitCompatibility": unit_check,
        "loadTargets": load_targets_check,
        "resultTargets": result_targets_check,
        "reactionSemantics": reaction_check,
        "responseMapping": response_mapping_check,
    }
    ready = not issues
    return {
        "schema": READINESS_SCHEMA,
        "status": "READY" if ready else "NOT_READY",
        "profile": READINESS_PROFILE,
        "modelSpecFingerprint": model_fingerprint,
        "analysisSpecFingerprint": analysis_fingerprint,
        "validation": {
            "modelSpec": _compact_validation(model_validation),
            "analysisSpec": _compact_validation(analysis_validation),
        },
        "checks": checks,
        "issues": issues,
    }


__all__ = [
    "READINESS_PROFILE",
    "READINESS_SCHEMA",
    "evaluate_engineering_analysis_readiness",
]
