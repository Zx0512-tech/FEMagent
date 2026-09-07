from __future__ import annotations

import hashlib
import json
from typing import Any

VALIDATION_SCHEMA = "FEMAGENT_ANALYSIS_SPEC_VALIDATION_V1"


def _normalize_spec(spec: dict[str, Any]) -> dict[str, Any]:
    return {
        "schemaVersion": spec["schemaVersion"],
        "kind": spec["kind"],
        "modelSpecFingerprint": spec["modelSpecFingerprint"],
        "analysisType": spec["analysisType"],
        "units": {"force": spec["units"]["force"]},
        "loadCases": [
            {
                "loadCaseId": case["loadCaseId"],
                "nodalLoads": [dict(load) for load in case["nodalLoads"]],
            }
            for case in spec["loadCases"]
        ],
        "resultRequests": [
            {
                **{key: value for key, value in request.items() if key != "target"},
                "target": dict(request["target"]),
            }
            for request in spec["resultRequests"]
        ],
    }


def _fingerprint(normalized: dict[str, Any]) -> str:
    canonical = json.dumps(
        normalized,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()


def validate_engineering_analysis_spec(spec: dict[str, Any]) -> dict[str, Any]:
    normalized = _normalize_spec(spec)
    return {
        "schema": VALIDATION_SCHEMA,
        "status": "VALID",
        "issues": [],
        "normalizedSpec": normalized,
        "analysisSpecFingerprint": _fingerprint(normalized),
    }
