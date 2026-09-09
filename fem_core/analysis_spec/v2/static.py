from __future__ import annotations

from typing import Any

from fem_core.analysis_spec.common import (
    is_finite_number,
    issue,
    validate_exact_keys,
    validate_id_token,
    validate_positive_target_id,
)

_ALLOWED_FORCE_UNITS = {"N", "kN"}


def _validate_number(value: Any, path: str, issues: list[dict[str, str]]) -> int | float | None:
    if not is_finite_number(value):
        issues.append(
            issue(
                "ANALYSIS_SPEC_INVALID_NUMBER",
                path,
                f"{path} must be a finite JSON number",
            )
        )
        return None
    return value


def _validate_nodal_loads(
    nodal_loads: Any,
    *,
    path: str,
    issues: list[dict[str, str]],
) -> None:
    if not isinstance(nodal_loads, list):
        issues.append(issue("ANALYSIS_SPEC_INVALID_SCHEMA", path, f"{path} must be an array"))
        return
    if not nodal_loads:
        issues.append(
            issue(
                "ANALYSIS_SPEC_INVALID_SCHEMA",
                path,
                f"{path} must contain at least one nodal load",
            )
        )
        return

    seen_nodes: set[int] = set()
    for index, load in enumerate(nodal_loads):
        load_path = f"{path}[{index}]"
        if not validate_exact_keys(load, {"nodeId", "FX", "FY", "MZ"}, load_path, issues):
            continue

        node_id = validate_positive_target_id(load.get("nodeId"), f"{load_path}.nodeId", issues)
        if node_id is not None:
            if node_id in seen_nodes:
                issues.append(
                    issue(
                        "ANALYSIS_SPEC_DUPLICATE_NODAL_LOAD_TARGET",
                        f"{load_path}.nodeId",
                        f"Duplicate nodal-load target node {node_id}",
                    )
                )
            else:
                seen_nodes.add(node_id)

        components = [
            _validate_number(load.get(name), f"{load_path}.{name}", issues)
            for name in ("FX", "FY", "MZ")
        ]
        if all(value is not None for value in components) and all(value == 0 for value in components):
            issues.append(
                issue(
                    "ANALYSIS_SPEC_ZERO_NODAL_LOAD",
                    load_path,
                    "Each nodal-load record must contain at least one non-zero component",
                )
            )


def _validate_load_cases(
    definition: Any,
    issues: list[dict[str, str]],
) -> set[str]:
    if not validate_exact_keys(definition, {"loadCases"}, "definition", issues):
        return set()

    load_cases = definition.get("loadCases")
    if not isinstance(load_cases, list):
        issues.append(
            issue(
                "ANALYSIS_SPEC_INVALID_SCHEMA",
                "definition.loadCases",
                "definition.loadCases must be an array",
            )
        )
        return set()
    if len(load_cases) != 1:
        issues.append(
            issue(
                "ANALYSIS_SPEC_INVALID_LOAD_CASE_COUNT",
                "definition.loadCases",
                "V2 LINEAR_STATIC requires exactly one explicit load case",
            )
        )

    valid_ids: set[str] = set()
    seen_ids: set[str] = set()
    for index, load_case in enumerate(load_cases):
        path = f"definition.loadCases[{index}]"
        if not validate_exact_keys(load_case, {"loadCaseId", "nodalLoads"}, path, issues):
            continue

        load_case_id = validate_id_token(load_case.get("loadCaseId"), f"{path}.loadCaseId", issues)
        if load_case_id is not None:
            if load_case_id in seen_ids:
                issues.append(
                    issue(
                        "ANALYSIS_SPEC_DUPLICATE_ID",
                        f"{path}.loadCaseId",
                        f"Duplicate loadCaseId {load_case_id!r}",
                    )
                )
            else:
                seen_ids.add(load_case_id)
                valid_ids.add(load_case_id)

        _validate_nodal_loads(
            load_case.get("nodalLoads"),
            path=f"{path}.nodalLoads",
            issues=issues,
        )
    return valid_ids


def _is_supported_static_request(request: dict[str, Any]) -> bool:
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
    requests: Any,
    *,
    load_case_ids: set[str],
    issues: list[dict[str, str]],
) -> None:
    if not isinstance(requests, list):
        issues.append(
            issue(
                "ANALYSIS_SPEC_INVALID_SCHEMA",
                "resultRequests",
                "resultRequests must be an array",
            )
        )
        return
    if not requests:
        issues.append(
            issue(
                "ANALYSIS_SPEC_INVALID_SCHEMA",
                "resultRequests",
                "resultRequests must contain at least one request",
            )
        )
        return

    seen_request_ids: set[str] = set()
    required = {"requestId", "loadCaseId", "quantity", "target", "component"}
    for index, request in enumerate(requests):
        path = f"resultRequests[{index}]"
        expected = required | ({"location"} if isinstance(request, dict) and "location" in request else set())
        if not validate_exact_keys(request, expected, path, issues):
            continue

        request_id = validate_id_token(request.get("requestId"), f"{path}.requestId", issues)
        if request_id is not None:
            if request_id in seen_request_ids:
                issues.append(
                    issue(
                        "ANALYSIS_SPEC_DUPLICATE_ID",
                        f"{path}.requestId",
                        f"Duplicate requestId {request_id!r}",
                    )
                )
            else:
                seen_request_ids.add(request_id)

        load_case_id = validate_id_token(request.get("loadCaseId"), f"{path}.loadCaseId", issues)
        if load_case_id is not None and load_case_id not in load_case_ids:
            issues.append(
                issue(
                    "ANALYSIS_SPEC_RESULT_LOAD_CASE_NOT_FOUND",
                    f"{path}.loadCaseId",
                    f"Result request references unknown load case {load_case_id!r}",
                )
            )

        target = request.get("target")
        if validate_exact_keys(target, {"type", "id"}, f"{path}.target", issues):
            validate_positive_target_id(target.get("id"), f"{path}.target.id", issues)

        if not _is_supported_static_request(request):
            issues.append(
                issue(
                    "ANALYSIS_SPEC_UNSUPPORTED_RESULT_REQUEST",
                    path,
                    "Result request is outside the EngineeringAnalysisSpec V2 LINEAR_STATIC whitelist",
                )
            )


def validate_v2_static(spec: dict[str, Any], issues: list[dict[str, str]]) -> None:
    units = spec.get("units")
    if validate_exact_keys(units, {"force"}, "units", issues):
        force_unit = units.get("force")
        if force_unit not in _ALLOWED_FORCE_UNITS:
            issues.append(
                issue(
                    "ANALYSIS_SPEC_UNSUPPORTED_UNIT",
                    "units.force",
                    f"Unsupported force unit: {force_unit!r}",
                )
            )

    load_case_ids = _validate_load_cases(spec.get("definition"), issues)
    _validate_result_requests(
        spec.get("resultRequests"),
        load_case_ids=load_case_ids,
        issues=issues,
    )
