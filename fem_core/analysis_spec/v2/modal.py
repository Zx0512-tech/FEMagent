from __future__ import annotations

from typing import Any

from fem_core.analysis_spec.common import (
    is_positive_int,
    issue,
    validate_exact_keys,
    validate_id_token,
    validate_positive_target_id,
)

_SCALAR_MODAL_QUANTITIES = {"EIGENVALUE", "NATURAL_FREQUENCY", "PERIOD"}
_MODE_SHAPE_COMPONENTS = {"X", "Y", "RZ"}


def _validate_mode_count(definition: Any, issues: list[dict[str, str]]) -> int | None:
    if not validate_exact_keys(definition, {"modeCount"}, "definition", issues):
        return None

    mode_count = definition.get("modeCount")
    if not is_positive_int(mode_count):
        issues.append(
            issue(
                "ANALYSIS_SPEC_INVALID_MODE_COUNT",
                "definition.modeCount",
                "definition.modeCount must be a positive integer",
            )
        )
        return None
    return mode_count


def _validate_mode_shape_request(
    request: dict[str, Any],
    *,
    path: str,
    issues: list[dict[str, str]],
) -> None:
    target = request.get("target")
    target_is_object = validate_exact_keys(target, {"type", "id"}, f"{path}.target", issues)
    if target_is_object:
        validate_positive_target_id(target.get("id"), f"{path}.target.id", issues)
        if target.get("type") != "NODE":
            issues.append(
                issue(
                    "ANALYSIS_SPEC_UNSUPPORTED_RESULT_REQUEST",
                    f"{path}.target.type",
                    "MODE_SHAPE requires a NODE target",
                )
            )

    if request.get("component") not in _MODE_SHAPE_COMPONENTS:
        issues.append(
            issue(
                "ANALYSIS_SPEC_UNSUPPORTED_RESULT_REQUEST",
                f"{path}.component",
                "MODE_SHAPE component must be X, Y, or RZ",
            )
        )


def _validate_result_requests(
    requests: Any,
    *,
    mode_count: int | None,
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
    for index, request in enumerate(requests):
        path = f"resultRequests[{index}]"
        quantity = request.get("quantity") if isinstance(request, dict) else None
        if quantity in _SCALAR_MODAL_QUANTITIES:
            expected = {"requestId", "quantity", "mode"}
        elif quantity == "MODE_SHAPE":
            expected = {"requestId", "quantity", "mode", "target", "component"}
        else:
            expected = {"requestId", "quantity", "mode"}

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

        mode = request.get("mode")
        if not is_positive_int(mode):
            issues.append(
                issue(
                    "ANALYSIS_SPEC_INVALID_MODE_INDEX",
                    f"{path}.mode",
                    "mode must be a positive integer",
                )
            )
        elif mode_count is not None and mode > mode_count:
            issues.append(
                issue(
                    "ANALYSIS_SPEC_MODE_EXCEEDS_REQUESTED_COUNT",
                    f"{path}.mode",
                    "Requested mode exceeds definition.modeCount",
                )
            )

        if quantity in _SCALAR_MODAL_QUANTITIES:
            continue
        if quantity == "MODE_SHAPE":
            _validate_mode_shape_request(request, path=path, issues=issues)
            continue

        issues.append(
            issue(
                "ANALYSIS_SPEC_UNSUPPORTED_RESULT_REQUEST",
                f"{path}.quantity",
                "Result request is outside the EngineeringAnalysisSpec V2 MODAL whitelist",
            )
        )


def validate_v2_modal(spec: dict[str, Any], issues: list[dict[str, str]]) -> None:
    validate_exact_keys(spec.get("units"), set(), "units", issues)
    mode_count = _validate_mode_count(spec.get("definition"), issues)
    _validate_result_requests(
        spec.get("resultRequests"),
        mode_count=mode_count,
        issues=issues,
    )
