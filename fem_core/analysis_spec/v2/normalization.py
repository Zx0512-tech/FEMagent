from __future__ import annotations

import copy
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


def _normalize_modal(spec: dict[str, Any]) -> dict[str, Any]:
    result_requests: list[dict[str, Any]] = []
    for request in spec["resultRequests"]:
        normalized_request: dict[str, Any] = {
            "requestId": request["requestId"],
            "quantity": request["quantity"],
            "mode": request["mode"],
        }
        if request["quantity"] == "MODE_SHAPE":
            normalized_request["target"] = {
                "type": request["target"]["type"],
                "id": request["target"]["id"],
            }
            normalized_request["component"] = request["component"]
        result_requests.append(normalized_request)

    return {
        "schemaVersion": spec["schemaVersion"],
        "kind": spec["kind"],
        "modelSpecFingerprint": spec["modelSpecFingerprint"],
        "analysisType": spec["analysisType"],
        "units": {},
        "definition": {"modeCount": spec["definition"]["modeCount"]},
        "resultRequests": sorted(result_requests, key=lambda request: request["requestId"]),
    }


def _normalize_transient(spec: dict[str, Any]) -> dict[str, Any]:
    definition = spec["definition"]
    damping = definition["damping"]
    if damping["type"] == "NONE":
        normalized_damping: dict[str, Any] = {"type": "NONE"}
    else:
        normalized_damping = {
            "type": "RAYLEIGH",
            "alphaM": damping["alphaM"],
            "betaK": damping["betaK"],
        }

    excitation = definition["excitation"]
    artifact = {
        "path": excitation["loadArtifact"]["path"],
        "sha256": excitation["loadArtifact"]["sha256"],
    }
    if excitation["type"] == "NODAL_TIME_HISTORY":
        normalized_excitation: dict[str, Any] = {
            "type": "NODAL_TIME_HISTORY",
            "nodeId": excitation["nodeId"],
            "component": excitation["component"],
            "quantity": "FORCE",
            "loadArtifact": artifact,
        }
        normalized_units = {"force": spec["units"]["force"]}
    else:
        normalized_excitation = {
            "type": "UNIFORM_BASE_EXCITATION",
            "component": excitation["component"],
            "quantity": "ACCELERATION",
            "loadArtifact": artifact,
        }
        normalized_units = {}

    result_requests: list[dict[str, Any]] = []
    for request in spec["resultRequests"]:
        normalized_request: dict[str, Any] = {
            "requestId": request["requestId"],
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
        "units": normalized_units,
        "definition": {
            "time": {
                "timeStep": definition["time"]["timeStep"],
                "duration": definition["time"]["duration"],
            },
            "damping": normalized_damping,
            "excitation": normalized_excitation,
        },
        "resultRequests": sorted(result_requests, key=lambda request: request["requestId"]),
    }


def normalize_analysis_spec_v2(spec: dict[str, Any]) -> dict[str, Any]:
    if spec["analysisType"] == "LINEAR_STATIC":
        return _normalize_static(spec)
    if spec["analysisType"] == "MODAL":
        return _normalize_modal(spec)
    if spec["analysisType"] == "TRANSIENT":
        return _normalize_transient(spec)
    raise ValueError(f"Unsupported AnalysisSpec V2 normalization profile: {spec['analysisType']!r}")


def fingerprint_payload(normalized_spec: dict[str, Any]) -> dict[str, Any]:
    payload = copy.deepcopy(normalized_spec)
    if payload["analysisType"] == "TRANSIENT":
        del payload["definition"]["excitation"]["loadArtifact"]["path"]
    return payload


def fingerprint_analysis_spec_v2(normalized_spec: dict[str, Any]) -> str:
    return canonical_sha256(fingerprint_payload(normalized_spec))
