from __future__ import annotations

from typing import Any

from fem_core.analysis_spec.opensees_profiles.common import (
    build_structural_response_mapping,
    check_force_unit_compatibility,
    check_load_targets,
    check_model_binding,
    check_reaction_semantics,
    check_result_targets,
    compact_validation,
    readiness_issue,
)
from fem_core.analysis_spec.opensees_profiles.registry import OPENSEES_STATIC_V2
from fem_core.errors import FemCoreError
from fem_core.model_spec.readiness import evaluate_engineering_model_readiness

READINESS_SCHEMA_V2 = "FEMAGENT_ANALYSIS_READINESS_V2"


def evaluate_static_v2_readiness(
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

    unit_check, unit_issues = check_force_unit_compatibility(
        normalized_model=normalized_model,
        normalized_analysis=normalized_analysis,
    )
    issues.extend(unit_issues)

    definition = normalized_analysis.get("definition")
    if not isinstance(definition, dict) or not isinstance(definition.get("loadCases"), list):
        raise FemCoreError(
            "ANALYSIS_READINESS_INTERNAL_INVARIANT",
            "Valid V2 LINEAR_STATIC AnalysisSpec must provide definition.loadCases",
        )
    load_cases = definition["loadCases"]
    requests = normalized_analysis["resultRequests"]

    load_targets_check, load_issues = check_load_targets(
        normalized_model=normalized_model,
        load_cases=load_cases,
        path="analysisSpec.definition.loadCases",
    )
    issues.extend(load_issues)

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

    response_mapping_check, mapping_issues = build_structural_response_mapping(
        normalized_model=normalized_model,
        requests=requests,
    )
    issues.extend(mapping_issues)

    checks = {
        "modelReadiness": model_readiness_check,
        "modelBinding": model_binding_check,
        "unitCompatibility": unit_check,
        "loadTargets": load_targets_check,
        "resultTargets": result_targets_check,
        "reactionSemantics": reaction_check,
        "responseMapping": response_mapping_check,
    }
    return {
        "schema": READINESS_SCHEMA_V2,
        "status": "READY" if not issues else "NOT_READY",
        "profile": OPENSEES_STATIC_V2,
        "modelSpecFingerprint": model_fingerprint,
        "analysisSpecFingerprint": analysis_fingerprint,
        "validation": {
            "modelSpec": compact_validation(model_validation),
            "analysisSpec": compact_validation(analysis_validation),
        },
        "checks": checks,
        "issues": issues,
    }


__all__ = ["evaluate_static_v2_readiness"]
