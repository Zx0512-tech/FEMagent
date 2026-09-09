from __future__ import annotations

from typing import Any

from fem_core.analysis_spec.common import SHA256_RE, issue, validate_exact_keys
from fem_core.analysis_spec.v2.modal import validate_v2_modal
from fem_core.analysis_spec.v2.normalization import (
    fingerprint_analysis_spec_v2,
    normalize_analysis_spec_v2,
)
from fem_core.analysis_spec.v2.static import validate_v2_static

VALIDATION_SCHEMA = "FEMAGENT_ANALYSIS_SPEC_VALIDATION_V1"
V2_KEYS = {
    "schemaVersion",
    "kind",
    "modelSpecFingerprint",
    "analysisType",
    "units",
    "definition",
    "resultRequests",
}


def _invalid(issues: list[dict[str, str]]) -> dict[str, Any]:
    return {
        "schema": VALIDATION_SCHEMA,
        "status": "INVALID",
        "issues": issues,
        "normalizedSpec": None,
        "analysisSpecFingerprint": None,
    }


def validate_engineering_analysis_spec_v2(spec: dict[str, Any]) -> dict[str, Any]:
    issues: list[dict[str, str]] = []
    validate_exact_keys(spec, V2_KEYS, "", issues)

    if spec.get("schemaVersion") != "2.0":
        issues.append(
            issue(
                "ANALYSIS_SPEC_INVALID_SCHEMA",
                "schemaVersion",
                "schemaVersion must equal 2.0",
            )
        )
    if spec.get("kind") != "engineering_analysis_spec":
        issues.append(
            issue(
                "ANALYSIS_SPEC_INVALID_SCHEMA",
                "kind",
                "kind must equal engineering_analysis_spec",
            )
        )

    model_fingerprint = spec.get("modelSpecFingerprint")
    if not isinstance(model_fingerprint, str) or SHA256_RE.fullmatch(model_fingerprint) is None:
        issues.append(
            issue(
                "ANALYSIS_SPEC_INVALID_MODEL_FINGERPRINT",
                "modelSpecFingerprint",
                "modelSpecFingerprint must be lowercase SHA-256 hex",
            )
        )

    analysis_type = spec.get("analysisType")
    if analysis_type == "LINEAR_STATIC":
        validate_v2_static(spec, issues)
    elif analysis_type == "MODAL":
        validate_v2_modal(spec, issues)
    else:
        issues.append(
            issue(
                "ANALYSIS_SPEC_UNSUPPORTED_ANALYSIS_TYPE",
                "analysisType",
                f"Unsupported AnalysisSpec V2 analysisType: {analysis_type!r}",
            )
        )

    if issues:
        return _invalid(issues)

    normalized = normalize_analysis_spec_v2(spec)
    return {
        "schema": VALIDATION_SCHEMA,
        "status": "VALID",
        "issues": [],
        "normalizedSpec": normalized,
        "analysisSpecFingerprint": fingerprint_analysis_spec_v2(normalized),
    }
