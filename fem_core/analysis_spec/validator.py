from __future__ import annotations

import hashlib
import json
import math
import re
from typing import Any

VALIDATION_SCHEMA = "FEMAGENT_ANALYSIS_SPEC_VALIDATION_V1"

_ID_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_-]{0,63}$")
_MODEL_FINGERPRINT_RE = re.compile(r"^[0-9a-f]{64}$")
_ALLOWED_FORCE_UNITS = {"N", "kN"}
_TOP_LEVEL_KEYS = {
    "schemaVersion",
    "kind",
    "modelSpecFingerprint",
    "analysisType",
    "units",
    "loadCases",
    "resultRequests",
}


def _issue(
    issues: list[dict[str, Any]],
    severity: str,
    code: str,
    path: str,
    message: str,
) -> None:
    issues.append({"severity": severity, "code": code, "path": path, "message": message})


def _is_positive_int(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value > 0


def _is_finite_number(value: Any) -> bool:
    return (
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and math.isfinite(float(value))
    )


def _validate_object_keys(
    value: Any,
    *,
    required: set[str],
    optional: set[str] | None,
    path: str,
    issues: list[dict[str, Any]],
) -> bool:
    if not isinstance(value, dict):
        _issue(
            issues,
            "ERROR",
            "ANALYSIS_SPEC_INVALID_SCHEMA",
            path,
            f"{path or 'AnalysisSpec'} must be a JSON object",
        )
        return False

    allowed = required | (optional or set())
    for key in sorted(set(value) - allowed):
        child_path = f"{path}.{key}" if path else key
        _issue(
            issues,
            "ERROR",
            "ANALYSIS_SPEC_UNKNOWN_FIELD",
            child_path,
            f"Unknown AnalysisSpec field: {child_path}",
        )
    for key in sorted(required - set(value)):
        child_path = f"{path}.{key}" if path else key
        _issue(
            issues,
            "ERROR",
            "ANALYSIS_SPEC_INVALID_SCHEMA",
            child_path,
            f"Required AnalysisSpec field is missing: {child_path}",
        )
    return True


def _validate_exact_keys(
    value: Any,
    expected: set[str],
    path: str,
    issues: list[dict[str, Any]],
) -> bool:
    return _validate_object_keys(
        value,
        required=expected,
        optional=None,
        path=path,
        issues=issues,
    )


def _validate_id_token(value: Any, path: str, issues: list[dict[str, Any]]) -> str | None:
    if not isinstance(value, str) or _ID_RE.fullmatch(value) is None:
        _issue(
            issues,
            "ERROR",
            "ANALYSIS_SPEC_INVALID_ID",
            path,
            f"{path} must match {_ID_RE.pattern}",
        )
        return None
    return value


def _validate_target_id(value: Any, path: str, issues: list[dict[str, Any]]) -> int | None:
    if not _is_positive_int(value):
        _issue(
            issues,
            "ERROR",
            "ANALYSIS_SPEC_INVALID_TARGET_ID",
            path,
            f"{path} must be a positive integer",
        )
        return None
    return value


def _validate_number(
    value: Any,
    path: str,
    issues: list[dict[str, Any]],
) -> int | float | None:
    if not _is_finite_number(value):
        _issue(
            issues,
            "ERROR",
            "ANALYSIS_SPEC_INVALID_NUMBER",
            path,
            f"{path} must be a finite JSON number",
        )
        return None
    return value


def _validate_nodal_loads(
    nodal_loads: Any,
    *,
    path: str,
    issues: list[dict[str, Any]],
) -> None:
    if not isinstance(nodal_loads, list):
        _issue(
            issues,
            "ERROR",
            "ANALYSIS_SPEC_INVALID_SCHEMA",
            path,
            f"{path} must be an array",
        )
        return
    if not nodal_loads:
        _issue(
            issues,
            "ERROR",
            "ANALYSIS_SPEC_INVALID_SCHEMA",
            path,
            f"{path} must contain at least one nodal load",
        )
        return

    seen_nodes: set[int] = set()
    for index, load in enumerate(nodal_loads):
        load_path = f"{path}[{index}]"
        if not _validate_exact_keys(load, {"nodeId", "FX", "FY", "MZ"}, load_path, issues):
            continue

        node_id = _validate_target_id(load.get("nodeId"), f"{load_path}.nodeId", issues)
        if node_id is not None:
            if node_id in seen_nodes:
                _issue(
                    issues,
                    "ERROR",
                    "ANALYSIS_SPEC_DUPLICATE_NODAL_LOAD_TARGET",
                    f"{load_path}.nodeId",
                    f"Duplicate nodal-load target node {node_id}",
                )
            else:
                seen_nodes.add(node_id)

        components = [
            _validate_number(load.get(name), f"{load_path}.{name}", issues)
            for name in ("FX", "FY", "MZ")
        ]
        if all(value is not None for value in components) and all(value == 0 for value in components):
            _issue(
                issues,
                "ERROR",
                "ANALYSIS_SPEC_ZERO_NODAL_LOAD",
                load_path,
                "Each nodal-load record must contain at least one non-zero component",
            )


def _validate_load_cases(spec: dict[str, Any], issues: list[dict[str, Any]]) -> set[str]:
    load_cases = spec.get("loadCases")
    if not isinstance(load_cases, list):
        _issue(
            issues,
            "ERROR",
            "ANALYSIS_SPEC_INVALID_SCHEMA",
            "loadCases",
            "loadCases must be an array",
        )
        return set()
    if len(load_cases) != 1:
        _issue(
            issues,
            "ERROR",
            "ANALYSIS_SPEC_INVALID_LOAD_CASE_COUNT",
            "loadCases",
            "V1 requires exactly one explicit load case",
        )

    valid_ids: set[str] = set()
    seen_ids: set[str] = set()
    for index, load_case in enumerate(load_cases):
        path = f"loadCases[{index}]"
        if not _validate_exact_keys(load_case, {"loadCaseId", "nodalLoads"}, path, issues):
            continue
        load_case_id = _validate_id_token(load_case.get("loadCaseId"), f"{path}.loadCaseId", issues)
        if load_case_id is not None:
            if load_case_id in seen_ids:
                _issue(
                    issues,
                    "ERROR",
                    "ANALYSIS_SPEC_DUPLICATE_ID",
                    f"{path}.loadCaseId",
                    f"Duplicate loadCaseId {load_case_id!r}",
                )
            else:
                seen_ids.add(load_case_id)
                valid_ids.add(load_case_id)
        _validate_nodal_loads(load_case.get("nodalLoads"), path=f"{path}.nodalLoads", issues=issues)
    return valid_ids


def _is_supported_result_request(request: dict[str, Any]) -> bool:
    target = request.get("target")
    if not isinstance(target, dict):
        return False

    quantity = request.get("quantity")
    target_type = target.get("type")
    component = request.get("component")
    has_location = "location" in request
    location = request.get("location")

    if quantity == "DISPLACEMENT":
        return target_type == "NODE" and component in {"X", "Y"} and not has_location
    if quantity == "REACTION_FORCE":
        return target_type == "NODE" and component in {"X", "Y"} and not has_location
    if quantity == "REACTION_MOMENT":
        return target_type == "NODE" and component == "Z" and not has_location
    if quantity == "GENERALIZED_FORCE":
        return (
            target_type == "ELEMENT"
            and component in {"N", "VY", "MZ"}
            and has_location
            and location in {"END_I", "END_J"}
        )
    return False


def _validate_result_requests(
    spec: dict[str, Any],
    *,
    load_case_ids: set[str],
    issues: list[dict[str, Any]],
) -> None:
    requests = spec.get("resultRequests")
    if not isinstance(requests, list):
        _issue(
            issues,
            "ERROR",
            "ANALYSIS_SPEC_INVALID_SCHEMA",
            "resultRequests",
            "resultRequests must be an array",
        )
        return
    if not requests:
        _issue(
            issues,
            "ERROR",
            "ANALYSIS_SPEC_INVALID_SCHEMA",
            "resultRequests",
            "resultRequests must contain at least one request",
        )
        return

    seen_request_ids: set[str] = set()
    required = {"requestId", "loadCaseId", "quantity", "target", "component"}
    for index, request in enumerate(requests):
        path = f"resultRequests[{index}]"
        if not _validate_object_keys(
            request,
            required=required,
            optional={"location"},
            path=path,
            issues=issues,
        ):
            continue

        request_id = _validate_id_token(request.get("requestId"), f"{path}.requestId", issues)
        if request_id is not None:
            if request_id in seen_request_ids:
                _issue(
                    issues,
                    "ERROR",
                    "ANALYSIS_SPEC_DUPLICATE_ID",
                    f"{path}.requestId",
                    f"Duplicate requestId {request_id!r}",
                )
            else:
                seen_request_ids.add(request_id)

        load_case_id = _validate_id_token(request.get("loadCaseId"), f"{path}.loadCaseId", issues)
        if load_case_id is not None and load_case_id not in load_case_ids:
            _issue(
                issues,
                "ERROR",
                "ANALYSIS_SPEC_RESULT_LOAD_CASE_NOT_FOUND",
                f"{path}.loadCaseId",
                f"Result request references unknown load case {load_case_id!r}",
            )

        target = request.get("target")
        target_shape_ok = _validate_exact_keys(target, {"type", "id"}, f"{path}.target", issues)
        if target_shape_ok:
            _validate_target_id(target.get("id"), f"{path}.target.id", issues)

        if not _is_supported_result_request(request):
            _issue(
                issues,
                "ERROR",
                "ANALYSIS_SPEC_UNSUPPORTED_RESULT_REQUEST",
                path,
                "Result request is outside the EngineeringAnalysisSpec V1 whitelist",
            )


def _normalize_spec(spec: dict[str, Any]) -> dict[str, Any]:
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
            for load_case in spec["loadCases"]
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
        "loadCases": load_cases,
        "resultRequests": sorted(result_requests, key=lambda request: request["requestId"]),
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
    issues: list[dict[str, Any]] = []
    if not _validate_exact_keys(spec, _TOP_LEVEL_KEYS, "", issues):
        return {
            "schema": VALIDATION_SCHEMA,
            "status": "INVALID",
            "issues": issues,
            "normalizedSpec": None,
            "analysisSpecFingerprint": None,
        }

    if spec.get("schemaVersion") != "1.0" or spec.get("kind") != "engineering_analysis_spec":
        _issue(
            issues,
            "ERROR",
            "ANALYSIS_SPEC_INVALID_SCHEMA",
            "schemaVersion",
            "V1 requires schemaVersion='1.0' and kind='engineering_analysis_spec'",
        )

    model_fingerprint = spec.get("modelSpecFingerprint")
    if not isinstance(model_fingerprint, str) or _MODEL_FINGERPRINT_RE.fullmatch(model_fingerprint) is None:
        _issue(
            issues,
            "ERROR",
            "ANALYSIS_SPEC_INVALID_MODEL_FINGERPRINT",
            "modelSpecFingerprint",
            "modelSpecFingerprint must be a 64-character lowercase SHA-256 hex string",
        )

    if spec.get("analysisType") != "LINEAR_STATIC":
        _issue(
            issues,
            "ERROR",
            "ANALYSIS_SPEC_UNSUPPORTED_ANALYSIS_TYPE",
            "analysisType",
            "V1 supports analysisType='LINEAR_STATIC' only",
        )

    units = spec.get("units")
    if (
        _validate_exact_keys(units, {"force"}, "units", issues)
        and units.get("force") not in _ALLOWED_FORCE_UNITS
    ):
        _issue(
            issues,
            "ERROR",
            "ANALYSIS_SPEC_UNSUPPORTED_UNIT",
            "units.force",
            f"Unsupported force unit: {units.get('force')!r}",
        )

    load_case_ids = _validate_load_cases(spec, issues)
    _validate_result_requests(spec, load_case_ids=load_case_ids, issues=issues)

    if any(issue["severity"] == "ERROR" for issue in issues):
        return {
            "schema": VALIDATION_SCHEMA,
            "status": "INVALID",
            "issues": issues,
            "normalizedSpec": None,
            "analysisSpecFingerprint": None,
        }

    normalized = _normalize_spec(spec)
    return {
        "schema": VALIDATION_SCHEMA,
        "status": "VALID",
        "issues": issues,
        "normalizedSpec": normalized,
        "analysisSpecFingerprint": _fingerprint(normalized),
    }
