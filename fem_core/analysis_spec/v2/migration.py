from __future__ import annotations

import copy
from typing import Any

from fem_core.analysis_spec.v1 import validate_engineering_analysis_spec_v1
from fem_core.analysis_spec.validator import validate_engineering_analysis_spec

MIGRATION_SCHEMA = "FEMAGENT_ANALYSIS_SPEC_MIGRATION_V1_TO_V2"


def _failure(status: str, schema_version: Any) -> dict[str, Any]:
    return {
        "schema": MIGRATION_SCHEMA,
        "status": status,
        "source": {
            "schemaVersion": schema_version,
            "analysisSpecFingerprint": None,
        },
        "target": None,
        "candidateSpec": None,
    }


def migrate_engineering_analysis_spec_v1_to_v2(spec: dict[str, Any]) -> dict[str, Any]:
    """Pure deterministic migration from valid V1 linear static intent to V2 static intent."""
    if not isinstance(spec, dict):
        return _failure("INVALID_SOURCE", None)

    schema_version = spec.get("schemaVersion")
    if schema_version != "1.0":
        return _failure("UNSUPPORTED_SOURCE", schema_version)

    source_validation = validate_engineering_analysis_spec_v1(spec)
    if source_validation["status"] != "VALID":
        return _failure("INVALID_SOURCE", schema_version)

    normalized_v1 = source_validation["normalizedSpec"]
    if normalized_v1["analysisType"] != "LINEAR_STATIC":
        return _failure("UNSUPPORTED_SOURCE", schema_version)

    candidate = {
        "schemaVersion": "2.0",
        "kind": "engineering_analysis_spec",
        "modelSpecFingerprint": normalized_v1["modelSpecFingerprint"],
        "analysisType": "LINEAR_STATIC",
        "units": copy.deepcopy(normalized_v1["units"]),
        "definition": {
            "loadCases": copy.deepcopy(normalized_v1["loadCases"]),
        },
        "resultRequests": copy.deepcopy(normalized_v1["resultRequests"]),
    }

    target_validation = validate_engineering_analysis_spec(candidate)
    if target_validation["status"] != "VALID":
        raise RuntimeError("V1 to V2 migration produced an invalid V2 AnalysisSpec candidate")

    return {
        "schema": MIGRATION_SCHEMA,
        "status": "MIGRATED",
        "source": {
            "schemaVersion": "1.0",
            "analysisSpecFingerprint": source_validation["analysisSpecFingerprint"],
        },
        "target": {
            "schemaVersion": "2.0",
            "analysisSpecFingerprint": target_validation["analysisSpecFingerprint"],
        },
        "candidateSpec": target_validation["normalizedSpec"],
    }
