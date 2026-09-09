from __future__ import annotations

from typing import Any

from fem_core.analysis_spec.common import canonical_sha256


def _normalize_static(spec: dict[str, Any]) -> dict[str, Any]:
    load_cases = sorted(
        (
            {
                "loadCaseId": load_case["loadCaseId"],
                "nodalLoads": sorted(
                    (
                        {
                            "nodeId": load["nodeId"],
                            "FX": load["FX"],
                            "FY": load["FY"],
                            "MZ": load["MZ"],
                        }
                        for load in load_case["nodalLoads"]
                    ),
                    key=lambda load: load["nodeId"],
                ),
            }
            for load_case in spec["definition"]["loadCases"]
        ),
        key=lambda load_case: load_case["loadCaseId"],
    )

    result_requests: list[dict[str, Any]] = []
    for request in spec["resultRequests"]:
        normalized_request: dict[str, Any] = {
            "requestId": request["requestId"],
            "loadCaseId": request["loadCaseId"],
            "quantity": request["quantity"],
            "target": {
                "type": request["target"]["type"],
                "id": request["target"]["id"],
            },
            "component": request["component"],
        }
        if "location" in request:
            normalized_request["location"] = request["location"]
        result_requests.append(normalized_request)

    return {
        "schemaVersion": spec["schemaVersion"],
        "kind": spec["kind"],
        "modelSpecFingerprint": spec["modelSpecFingerprint"],
        "analysisType": spec["analysisType"],
        "units": {"force": spec["units"]["force"]},
        "definition": {"loadCases": load_cases},
        "resultRequests": sorted(result_requests, key=lambda request: request["requestId"]),
    }


def normalize_analysis_spec_v2(spec: dict[str, Any]) -> dict[str, Any]:
    if spec["analysisType"] == "LINEAR_STATIC":
        return _normalize_static(spec)
    raise ValueError(f"Unsupported AnalysisSpec V2 normalization profile: {spec['analysisType']!r}")


def fingerprint_analysis_spec_v2(normalized_spec: dict[str, Any]) -> str:
    return canonical_sha256(normalized_spec)
