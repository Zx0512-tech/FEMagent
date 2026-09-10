from __future__ import annotations

from typing import Any

from fem_core.analysis_spec.opensees_profiles.common import (
    check_model_binding,
    check_result_targets,
    compact_validation,
    readiness_issue,
)
from fem_core.analysis_spec.opensees_profiles.registry import OPENSEES_MODAL_V2
from fem_core.errors import FemCoreError
from fem_core.model_spec.readiness import evaluate_engineering_model_readiness

READINESS_SCHEMA_V2 = "FEMAGENT_ANALYSIS_READINESS_V2"


def _constraint_map(model_spec: dict[str, Any]) -> dict[int, set[str]]:
    return {
        int(item["nodeId"]): {str(dof) for dof in item["dofs"]}
        for item in model_spec["constraints"]
    }


def _positive_translational_mass_dof_count(model_spec: dict[str, Any]) -> int:
    count = 0
    for mass in model_spec["nodalMasses"]:
        if float(mass["mUX"]) > 0.0:
            count += 1
        if float(mass["mUY"]) > 0.0:
            count += 1
    return count


def positive_free_translational_mass_dofs(
    model_spec: dict[str, Any],
) -> list[tuple[int, str]]:
    constraints = _constraint_map(model_spec)
    result: list[tuple[int, str]] = []
    for mass in sorted(model_spec["nodalMasses"], key=lambda item: int(item["nodeId"])):
        node_id = int(mass["nodeId"])
        restrained = constraints.get(node_id, set())
        if float(mass["mUX"]) > 0.0 and "UX" not in restrained:
            result.append((node_id, "X"))
        if float(mass["mUY"]) > 0.0 and "UY" not in restrained:
            result.append((node_id, "Y"))
    return result


def _modal_unit(quantity: str, time_unit: str) -> str:
    if quantity == "EIGENVALUE":
        return f"1/{time_unit}2"
    if quantity == "NATURAL_FREQUENCY":
        return "Hz"
    if quantity == "PERIOD":
        return time_unit
    if quantity == "MODE_SHAPE":
        return "1"
    raise FemCoreError(
        "ANALYSIS_READINESS_RESPONSE_MAPPING_UNAVAILABLE",
        "Unsupported modal response quantity",
        details={"quantity": quantity},
    )


def _build_modal_response_mapping(
    *,
    normalized_model: dict[str, Any],
    requests: list[dict[str, Any]],
) -> tuple[dict[str, Any], list[dict[str, str]]]:
    time_unit = str(normalized_model["units"]["time"])
    component_dof = {"X": 1, "Y": 2, "RZ": 3}
    channels: list[dict[str, Any]] = []
    issues: list[dict[str, str]] = []

    for request in sorted(requests, key=lambda item: str(item["requestId"])):
        request_id = str(request["requestId"])
        quantity = str(request["quantity"])
        try:
            unit = _modal_unit(quantity, time_unit)
        except FemCoreError as exc:
            issues.append(
                readiness_issue(
                    "ANALYSIS_READINESS_RESPONSE_MAPPING_UNAVAILABLE",
                    f"analysisSpec.resultRequests.{request_id}",
                    f"No proven OpenSees modal response mapping is available: {exc.code}",
                )
            )
            continue

        channel: dict[str, Any] = {
            "requestId": request_id,
            "quantity": quantity,
            "mode": int(request["mode"]),
            "unit": unit,
        }
        if quantity in {"EIGENVALUE", "NATURAL_FREQUENCY", "PERIOD"}:
            channel["access"] = "MODAL_EIGENVALUE"
        elif quantity == "MODE_SHAPE":
            component = str(request["component"])
            dof = component_dof.get(component)
            if dof is None:
                issues.append(
                    readiness_issue(
                        "ANALYSIS_READINESS_RESPONSE_MAPPING_UNAVAILABLE",
                        f"analysisSpec.resultRequests.{request_id}",
                        f"No proven OpenSees DOF mapping exists for modal component {component}",
                    )
                )
                continue
            channel.update(
                {
                    "access": "NODE_EIGENVECTOR",
                    "target": dict(request["target"]),
                    "component": component,
                    "dof": dof,
                    "normalization": "OPENSEES_NATIVE",
                }
            )
        channels.append(channel)

    return {
        "status": "FAIL" if issues else "PASS",
        "channels": channels,
    }, issues


def evaluate_modal_v2_readiness(
    *,
    model_validation: dict[str, Any],
    analysis_validation: dict[str, Any],
    normalized_model: dict[str, Any],
    normalized_analysis: dict[str, Any],
) -> dict[str, Any]:
    model_fingerprint = model_validation.get("modelSpecFingerprint")
    analysis_fingerprint = analysis_validation.get("analysisSpecFingerprint")
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
            readiness_issue(
                "ANALYSIS_READINESS_MODEL_NOT_READY",
                "modelSpec",
                "The bound EngineeringModelSpec has not passed Model Readiness",
            )
        )
    model_readiness_check = {
        "status": "PASS" if model_ready else "FAIL",
        "report": model_readiness,
    }

    model_binding_check, binding_issues = check_model_binding(
        model_fingerprint=model_fingerprint,
        normalized_analysis=normalized_analysis,
    )
    issues.extend(binding_issues)

    total_positive_dofs = _positive_translational_mass_dof_count(normalized_model)
    free_dofs = positive_free_translational_mass_dofs(normalized_model)
    free_dof_records = [
        {"nodeId": node_id, "component": component}
        for node_id, component in free_dofs
    ]
    modal_mass_ok = total_positive_dofs > 0 and bool(free_dofs)
    if total_positive_dofs == 0:
        issues.append(
            readiness_issue(
                "ANALYSIS_READINESS_MODAL_MASS_REQUIRED",
                "modelSpec.nodalMasses",
                "Modal analysis requires at least one positive translational nodal mass",
            )
        )
    elif not free_dofs:
        issues.append(
            readiness_issue(
                "ANALYSIS_READINESS_MODAL_FREE_MASS_DOF_REQUIRED",
                "modelSpec.nodalMasses",
                "Modal analysis requires positive translational mass on at least one unrestrained DOF",
            )
        )
    modal_mass_check = {
        "status": "PASS" if modal_mass_ok else "FAIL",
        "positiveTranslationalMassDofCount": total_positive_dofs,
        "positiveFreeTranslationalDofCount": len(free_dofs),
        "positiveFreeDofs": free_dof_records,
    }

    definition = normalized_analysis.get("definition")
    if not isinstance(definition, dict) or not isinstance(definition.get("modeCount"), int):
        raise FemCoreError(
            "ANALYSIS_READINESS_INTERNAL_INVARIANT",
            "Valid V2 MODAL AnalysisSpec must provide definition.modeCount",
        )
    requested_mode_count = int(definition["modeCount"])
    upper_bound = len(free_dofs)
    mode_count_ok = upper_bound > 0 and requested_mode_count <= upper_bound
    if upper_bound > 0 and requested_mode_count > upper_bound:
        issues.append(
            readiness_issue(
                "ANALYSIS_READINESS_MODAL_MODE_COUNT_EXCEEDS_DOF_BOUND",
                "analysisSpec.definition.modeCount",
                "Requested modal count exceeds the conservative positive-free-mass DOF bound",
            )
        )
    mode_count_check = {
        "status": "PASS" if mode_count_ok else "FAIL",
        "requested": requested_mode_count,
        "upperBound": upper_bound,
    }

    requests = normalized_analysis["resultRequests"]
    result_targets_check, target_issues = check_result_targets(
        normalized_model=normalized_model,
        requests=requests,
    )
    issues.extend(target_issues)

    response_mapping_check, mapping_issues = _build_modal_response_mapping(
        normalized_model=normalized_model,
        requests=requests,
    )
    issues.extend(mapping_issues)

    checks = {
        "modelReadiness": model_readiness_check,
        "modelBinding": model_binding_check,
        "modalMass": modal_mass_check,
        "modeCount": mode_count_check,
        "resultTargets": result_targets_check,
        "responseMapping": response_mapping_check,
    }
    return {
        "schema": READINESS_SCHEMA_V2,
        "status": "READY" if not issues else "NOT_READY",
        "profile": OPENSEES_MODAL_V2,
        "modelSpecFingerprint": model_fingerprint,
        "analysisSpecFingerprint": analysis_fingerprint,
        "validation": {
            "modelSpec": compact_validation(model_validation),
            "analysisSpec": compact_validation(analysis_validation),
        },
        "checks": checks,
        "issues": issues,
    }


__all__ = [
    "evaluate_modal_v2_readiness",
    "positive_free_translational_mass_dofs",
]
