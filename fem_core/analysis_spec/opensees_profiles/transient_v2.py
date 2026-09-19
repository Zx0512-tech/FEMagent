from __future__ import annotations

import math
from pathlib import Path
from typing import Any

from fem_core.analysis_spec.opensees_profiles.common import (
    build_structural_response_mapping,
    check_force_unit_compatibility,
    check_model_binding,
    check_reaction_semantics,
    check_result_targets,
    compact_validation,
    readiness_issue,
)
from fem_core.analysis_spec.opensees_profiles.registry import (
    OPENSEES_TRANSIENT_BASE_V2,
    OPENSEES_TRANSIENT_NODAL_V2,
)
from fem_core.analysis_spec.transient_artifact import (
    acceleration_m_s2_to_model_factor,
    force_n_to_model_factor,
    read_transient_load_artifact,
    seconds_to_model_time_factor,
)
from fem_core.errors import FemCoreError
from fem_core.model_spec.readiness import evaluate_engineering_model_readiness

READINESS_SCHEMA_V2 = "FEMAGENT_ANALYSIS_READINESS_V2"
_TIME_ABS_TOL = 1e-12


def _artifact_issue(exc: FemCoreError) -> dict[str, str]:
    if exc.code == "TRANSIENT_ARTIFACT_NOT_FOUND":
        code = "ANALYSIS_READINESS_LOAD_ARTIFACT_NOT_FOUND"
    elif exc.code == "TRANSIENT_ARTIFACT_HASH_MISMATCH":
        code = "ANALYSIS_READINESS_LOAD_ARTIFACT_HASH_MISMATCH"
    else:
        code = "ANALYSIS_READINESS_LOAD_ARTIFACT_INVALID"
    return readiness_issue(code, "analysisSpec.definition.excitation.loadArtifact", exc.message)


def _load_target_check(
    *,
    normalized_model: dict[str, Any],
    excitation: dict[str, Any],
) -> tuple[dict[str, Any], list[dict[str, str]]]:
    if excitation["type"] != "NODAL_TIME_HISTORY":
        return {"status": "PASS", "missingNodeIds": []}, []
    node_id = int(excitation["nodeId"])
    node_ids = {int(node["id"]) for node in normalized_model["nodes"]}
    if node_id in node_ids:
        return {"status": "PASS", "missingNodeIds": []}, []
    return {"status": "FAIL", "missingNodeIds": [node_id]}, [
        readiness_issue(
            "ANALYSIS_READINESS_LOAD_NODE_NOT_FOUND",
            "analysisSpec.definition.excitation.nodeId",
            f"Transient nodal-force target node {node_id} does not exist in the bound ModelSpec",
        )
    ]


def _expected_channel(excitation: dict[str, Any]) -> dict[str, str]:
    if excitation["type"] == "NODAL_TIME_HISTORY":
        return {
            "applicationType": "NODAL_FORCE",
            "targetType": "NODE",
            "targetId": str(excitation["nodeId"]),
            "component": str(excitation["component"]),
            "quantity": "FORCE",
            "unit": "N",
        }
    return {
        "applicationType": "UNIFORM_EXCITATION",
        "targetType": "",
        "targetId": "",
        "component": str(excitation["component"]),
        "quantity": "ACCELERATION",
        "unit": "m/s2",
    }


def _channel_semantics_check(
    *,
    evidence: dict[str, Any] | None,
    excitation: dict[str, Any],
) -> tuple[dict[str, Any], list[dict[str, str]]]:
    expected = _expected_channel(excitation)
    if evidence is None:
        return {"status": "SKIPPED", "expected": expected, "received": None}, []
    received = {key: str(evidence.get(key, "")) for key in expected}
    ok = received == expected
    issues = [] if ok else [
        readiness_issue(
            "ANALYSIS_READINESS_LOAD_CHANNEL_MISMATCH",
            "analysisSpec.definition.excitation.loadArtifact",
            "Canonical transient load channel semantics do not match the AnalysisSpec excitation",
        )
    ]
    return {
        "status": "PASS" if ok else "FAIL",
        "expected": expected,
        "received": received,
    }, issues


def _time_check(
    *,
    evidence: dict[str, Any] | None,
    time_definition: dict[str, Any],
    model_time_unit: str,
) -> tuple[dict[str, Any], list[dict[str, str]]]:
    model_units_per_second = seconds_to_model_time_factor(model_time_unit)
    expected_dt_s = float(time_definition["timeStep"]) / model_units_per_second
    expected_duration_s = float(time_definition["duration"]) / model_units_per_second
    if evidence is None:
        return {
            "status": "SKIPPED",
            "expectedTimeStepS": expected_dt_s,
            "expectedDurationS": expected_duration_s,
        }, []

    issues: list[dict[str, str]] = []
    origin_ok = math.isclose(float(evidence["timeStartS"]), 0.0, rel_tol=0.0, abs_tol=_TIME_ABS_TOL)
    if not origin_ok:
        issues.append(
            readiness_issue(
                "ANALYSIS_READINESS_TIME_ORIGIN_MISMATCH",
                "analysisSpec.definition.excitation.loadArtifact",
                "Transient load artifact must start at canonical time zero",
            )
        )
    dt_ok = math.isclose(
        float(evidence["dtS"]), expected_dt_s, rel_tol=1e-9, abs_tol=_TIME_ABS_TOL
    )
    if not dt_ok:
        issues.append(
            readiness_issue(
                "ANALYSIS_READINESS_TIME_STEP_MISMATCH",
                "analysisSpec.definition.time.timeStep",
                "Transient load artifact sampling interval does not match AnalysisSpec timeStep",
            )
        )
    duration_ok = math.isclose(
        float(evidence["timeEndS"]), expected_duration_s, rel_tol=1e-9, abs_tol=_TIME_ABS_TOL
    )
    if not duration_ok:
        issues.append(
            readiness_issue(
                "ANALYSIS_READINESS_DURATION_MISMATCH",
                "analysisSpec.definition.time.duration",
                "Transient load artifact final time does not match AnalysisSpec duration",
            )
        )
    ratio = float(time_definition["duration"]) / float(time_definition["timeStep"])
    step_count = round(ratio)
    integral_steps = step_count > 0 and math.isclose(ratio, step_count, rel_tol=1e-9, abs_tol=1e-12)
    if not integral_steps and not any(item["code"] == "ANALYSIS_READINESS_DURATION_MISMATCH" for item in issues):
        issues.append(
            readiness_issue(
                "ANALYSIS_READINESS_DURATION_MISMATCH",
                "analysisSpec.definition.time",
                "Transient duration must contain an integer number of analysis steps",
            )
        )
    return {
        "status": "PASS" if not issues else "FAIL",
        "expectedTimeStepS": expected_dt_s,
        "artifactTimeStepS": float(evidence["dtS"]),
        "expectedDurationS": expected_duration_s,
        "artifactTimeStartS": float(evidence["timeStartS"]),
        "artifactTimeEndS": float(evidence["timeEndS"]),
        "analysisSteps": step_count if integral_steps else None,
    }, issues


def _unit_conversions(
    *,
    normalized_model: dict[str, Any],
    excitation: dict[str, Any],
) -> dict[str, Any]:
    model_units = normalized_model["units"]
    time_unit = str(model_units["time"])
    conversions: list[dict[str, Any]] = [
        {
            "quantity": "TIME",
            "sourceUnit": "s",
            "targetUnit": time_unit,
            "factor": seconds_to_model_time_factor(time_unit),
        }
    ]
    if excitation["type"] == "NODAL_TIME_HISTORY":
        force_unit = str(model_units["force"])
        conversions.append(
            {
                "quantity": "FORCE",
                "sourceUnit": "N",
                "targetUnit": force_unit,
                "factor": force_n_to_model_factor(force_unit),
            }
        )
    else:
        factor, target = acceleration_m_s2_to_model_factor(
            str(model_units["length"]), time_unit
        )
        conversions.append(
            {
                "quantity": "ACCELERATION",
                "sourceUnit": "m/s2",
                "targetUnit": target,
                "factor": factor,
            }
        )
    return {"status": "PASS", "conversions": conversions}


def _response_mapping(
    *,
    normalized_model: dict[str, Any],
    requests: list[dict[str, Any]],
    base_excitation: bool,
) -> tuple[dict[str, Any], list[dict[str, str]]]:
    absolute = [item for item in requests if item.get("quantity") == "ABSOLUTE_ACCELERATION"]
    admitted = [item for item in requests if item.get("quantity") != "ABSOLUTE_ACCELERATION"]
    mapping, issues = build_structural_response_mapping(
        normalized_model=normalized_model,
        requests=admitted,
    )
    if base_excitation:
        for channel in mapping["channels"]:
            if channel["quantity"] in {"DISPLACEMENT", "VELOCITY", "RELATIVE_ACCELERATION"}:
                channel["referenceFrame"] = "RELATIVE"
    if absolute:
        mapping["status"] = "FAIL"
        issues.extend(
            readiness_issue(
                "ANALYSIS_READINESS_ABSOLUTE_ACCELERATION_MAPPING_UNPROVEN",
                f"analysisSpec.resultRequests.{request['requestId']}",
                "Absolute acceleration reconstruction is not proven for the PR28 uniform-base OpenSees profile",
            )
            for request in absolute
        )
    return mapping, issues


def evaluate_transient_v2_readiness(
    *,
    model_validation: dict[str, Any],
    analysis_validation: dict[str, Any],
    normalized_model: dict[str, Any],
    normalized_analysis: dict[str, Any],
    workspace: Path | None,
) -> dict[str, Any]:
    model_fingerprint = model_validation.get("modelSpecFingerprint")
    analysis_fingerprint = analysis_validation.get("analysisSpecFingerprint")
    if not isinstance(model_fingerprint, str) or not isinstance(analysis_fingerprint, str):
        raise FemCoreError(
            "ANALYSIS_READINESS_INTERNAL_INVARIANT",
            "Valid Engineering Specs must provide deterministic fingerprints",
        )

    definition = normalized_analysis.get("definition")
    if not isinstance(definition, dict):
        raise FemCoreError(
            "ANALYSIS_READINESS_INTERNAL_INVARIANT",
            "Valid V2 TRANSIENT AnalysisSpec must provide definition",
        )
    excitation = definition.get("excitation")
    time_definition = definition.get("time")
    if not isinstance(excitation, dict) or not isinstance(time_definition, dict):
        raise FemCoreError(
            "ANALYSIS_READINESS_INTERNAL_INVARIANT",
            "Valid V2 TRANSIENT AnalysisSpec must provide time and excitation definitions",
        )
    profile = (
        OPENSEES_TRANSIENT_NODAL_V2
        if excitation["type"] == "NODAL_TIME_HISTORY"
        else OPENSEES_TRANSIENT_BASE_V2
    )
    base_excitation = profile == OPENSEES_TRANSIENT_BASE_V2
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

    if excitation["type"] == "NODAL_TIME_HISTORY":
        unit_check, unit_issues = check_force_unit_compatibility(
            normalized_model=normalized_model,
            normalized_analysis=normalized_analysis,
        )
        issues.extend(unit_issues)
    else:
        unit_check = {"status": "PASS", "modelForce": normalized_model["units"]["force"], "analysisForce": None}

    load_target_check, load_target_issues = _load_target_check(
        normalized_model=normalized_model,
        excitation=excitation,
    )
    issues.extend(load_target_issues)

    requests = normalized_analysis["resultRequests"]
    result_targets_check, target_issues = check_result_targets(
        normalized_model=normalized_model,
        requests=requests,
    )
    issues.extend(target_issues)
    reaction_check, reaction_issues = check_reaction_semantics(
        normalized_model=normalized_model,
        requests=requests,
    )
    issues.extend(reaction_issues)

    evidence: dict[str, Any] | None = None
    if workspace is None:
        artifact_check: dict[str, Any] = {"status": "FAIL", "evidence": None}
        issues.append(
            readiness_issue(
                "ANALYSIS_READINESS_WORKSPACE_REQUIRED",
                "workspace",
                "Transient readiness requires the active workspace to verify the referenced load artifact",
            )
        )
    else:
        try:
            evidence = read_transient_load_artifact(workspace, excitation["loadArtifact"])
        except FemCoreError as exc:
            artifact_check = {"status": "FAIL", "evidence": None, "artifactErrorCode": exc.code}
            issues.append(_artifact_issue(exc))
        else:
            artifact_check = {"status": "PASS", "evidence": evidence}

    excitation_check, excitation_issues = _channel_semantics_check(
        evidence=evidence,
        excitation=excitation,
    )
    issues.extend(excitation_issues)
    time_check, time_issues = _time_check(
        evidence=evidence,
        time_definition=time_definition,
        model_time_unit=str(normalized_model["units"]["time"]),
    )
    issues.extend(time_issues)
    conversion_check = _unit_conversions(
        normalized_model=normalized_model,
        excitation=excitation,
    )
    response_mapping_check, mapping_issues = _response_mapping(
        normalized_model=normalized_model,
        requests=requests,
        base_excitation=base_excitation,
    )
    issues.extend(mapping_issues)

    checks = {
        "modelReadiness": model_readiness_check,
        "modelBinding": model_binding_check,
        "unitCompatibility": unit_check,
        "loadTargets": load_target_check,
        "resultTargets": result_targets_check,
        "reactionSemantics": reaction_check,
        "loadArtifact": artifact_check,
        "excitationSemantics": excitation_check,
        "timeCompatibility": time_check,
        "unitConversions": conversion_check,
        "responseMapping": response_mapping_check,
    }
    return {
        "schema": READINESS_SCHEMA_V2,
        "status": "READY" if not issues else "NOT_READY",
        "profile": profile,
        "modelSpecFingerprint": model_fingerprint,
        "analysisSpecFingerprint": analysis_fingerprint,
        "validation": {
            "modelSpec": compact_validation(model_validation),
            "analysisSpec": compact_validation(analysis_validation),
        },
        "checks": checks,
        "issues": issues,
    }


__all__ = ["evaluate_transient_v2_readiness"]