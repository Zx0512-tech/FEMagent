from __future__ import annotations

import copy
import hashlib
import json
import math
import re
from pathlib import Path
from typing import Any

from fem_core.errors import FemCoreError
from fem_core.result_intelligence import inspect_result, query_result
from fem_core.semantic_roles import inspect_semantic_roles

REQUEST_SCHEMA = "FEMAGENT_ENGINEERING_RESPONSE_METRIC_REQUEST_V1"
REPORT_SCHEMA = "FEMAGENT_ENGINEERING_RESPONSE_METRICS_V1"
_PAGE_SIZE = 5000
_METRIC_ID = re.compile(r"^[A-Za-z][A-Za-z0-9_-]{0,63}$")
_ROLE_ID = re.compile(r"^[A-Z][A-Z0-9_]{0,63}$")
_NODE_PEAK_QUANTITIES = frozenset(
    {
        "DISPLACEMENT",
        "VELOCITY",
        "ACCELERATION",
        "RELATIVE_ACCELERATION",
        "REACTION_FORCE",
        "REACTION_MOMENT",
    }
)
_NODE_COMPONENTS = frozenset({"X", "Y", "Z"})
_GENERALIZED_FORCE_COMPONENTS = frozenset({"N", "VY", "VZ", "T", "MY", "MZ"})
_GENERALIZED_FORCE_LOCATIONS = frozenset({"END_I", "END_J", "SECTION"})


def _canonical_hash(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        ).encode("utf-8")
    ).hexdigest()


def _invalid(message: str, **details: Any) -> FemCoreError:
    return FemCoreError(
        "INVALID_ENGINEERING_RESPONSE_METRIC_REQUEST",
        message,
        details=details,
    )


def _exact_keys(
    value: Any,
    expected: set[str],
    *,
    subject: str,
) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise _invalid(f"{subject} must be a JSON object", subject=subject)
    received = set(value)
    if received != expected:
        raise _invalid(
            f"{subject} fields do not match the PR34 contract",
            subject=subject,
            missing=sorted(expected - received),
            unknown=sorted(received - expected),
        )
    return value


def _metric_id(raw: Any, *, index: int) -> str:
    if not isinstance(raw, str) or _METRIC_ID.fullmatch(raw) is None:
        raise _invalid(
            "metricId must start with an ASCII letter and contain only letters, digits, '_' or '-'",
            metricIndex=index,
            metricId=raw,
        )
    return raw


def _role_id(raw: Any, *, subject: str) -> str:
    if not isinstance(raw, str) or _ROLE_ID.fullmatch(raw) is None:
        raise _invalid(
            "Semantic role ids must match the explicit Semantic Role Manifest roleId grammar",
            subject=subject,
            roleId=raw,
        )
    return raw


def _validate_absolute_peak(
    metric: dict[str, Any],
    *,
    index: int,
) -> dict[str, Any]:
    allowed = {"metricId", "type", "roleId", "quantity", "component"}
    if "location" in metric:
        allowed.add("location")
    _exact_keys(metric, allowed, subject=f"metrics[{index}]")
    quantity = metric.get("quantity")
    component = metric.get("component")
    location = metric.get("location")
    if quantity not in _NODE_PEAK_QUANTITIES | {"GENERALIZED_FORCE"}:
        raise _invalid(
            "ROLE_ABSOLUTE_PEAK quantity is unsupported",
            metricIndex=index,
            quantity=quantity,
        )
    if not isinstance(component, str) or not component:
        raise _invalid(
            "ROLE_ABSOLUTE_PEAK component is required",
            metricIndex=index,
        )
    if quantity == "GENERALIZED_FORCE":
        if component not in _GENERALIZED_FORCE_COMPONENTS:
            raise _invalid(
                "GENERALIZED_FORCE component is unsupported",
                metricIndex=index,
                component=component,
            )
        if location not in _GENERALIZED_FORCE_LOCATIONS:
            raise _invalid(
                "GENERALIZED_FORCE metric requires END_I, END_J, or SECTION location",
                metricIndex=index,
                location=location,
            )
    else:
        if location is not None:
            raise _invalid(
                "NODE role peak metrics do not accept location",
                metricIndex=index,
            )
        if component not in _NODE_COMPONENTS:
            raise _invalid(
                "NODE role peak component must be X, Y, or Z",
                metricIndex=index,
                component=component,
            )
        if quantity == "RELATIVE_ACCELERATION" and component not in {"X", "Y"}:
            raise _invalid(
                "RELATIVE_ACCELERATION supports X or Y only",
                metricIndex=index,
                component=component,
            )
    normalized = {
        "metricId": _metric_id(metric.get("metricId"), index=index),
        "type": "ROLE_ABSOLUTE_PEAK",
        "roleId": _role_id(
            metric.get("roleId"),
            subject=f"metrics[{index}].roleId",
        ),
        "quantity": quantity,
        "component": component,
    }
    if location is not None:
        normalized["location"] = location
    return normalized


def _validate_relative_displacement(
    metric: dict[str, Any],
    *,
    index: int,
) -> dict[str, Any]:
    _exact_keys(
        metric,
        {
            "metricId",
            "type",
            "targetRoleId",
            "referenceRoleId",
            "component",
        },
        subject=f"metrics[{index}]",
    )
    target = _role_id(
        metric.get("targetRoleId"),
        subject=f"metrics[{index}].targetRoleId",
    )
    reference = _role_id(
        metric.get("referenceRoleId"),
        subject=f"metrics[{index}].referenceRoleId",
    )
    if target == reference:
        raise _invalid(
            "Relative displacement requires two distinct semantic role ids",
            metricIndex=index,
            roleId=target,
        )
    component = metric.get("component")
    if component not in {"X", "Y"}:
        raise _invalid(
            "Relative displacement component must be X or Y",
            metricIndex=index,
            component=component,
        )
    return {
        "metricId": _metric_id(metric.get("metricId"), index=index),
        "type": "ROLE_RELATIVE_DISPLACEMENT_PEAK",
        "targetRoleId": target,
        "referenceRoleId": reference,
        "component": component,
    }


def _validate_group_reaction_resultant(
    metric: dict[str, Any],
    *,
    index: int,
) -> dict[str, Any]:
    _exact_keys(
        metric,
        {"metricId", "type", "roleIds", "components"},
        subject=f"metrics[{index}]",
    )
    raw_roles = metric.get("roleIds")
    if not isinstance(raw_roles, list) or not raw_roles:
        raise _invalid(
            "ROLE_GROUP_REACTION_RESULTANT_PEAK requires at least one roleId",
            metricIndex=index,
        )
    if len(raw_roles) > 32:
        raise _invalid(
            "ROLE_GROUP_REACTION_RESULTANT_PEAK accepts at most 32 roleIds",
            metricIndex=index,
        )
    roles = [
        _role_id(item, subject=f"metrics[{index}].roleIds")
        for item in raw_roles
    ]
    if len(set(roles)) != len(roles):
        raise _invalid(
            "ROLE_GROUP_REACTION_RESULTANT_PEAK roleIds must be unique",
            metricIndex=index,
        )
    components = metric.get("components")
    if (
        not isinstance(components, list)
        or len(components) != 2
        or set(components) != {"X", "Y"}
    ):
        raise _invalid(
            "ROLE_GROUP_REACTION_RESULTANT_PEAK components must contain exactly X and Y",
            metricIndex=index,
            components=components,
        )
    return {
        "metricId": _metric_id(metric.get("metricId"), index=index),
        "type": "ROLE_GROUP_REACTION_RESULTANT_PEAK",
        "roleIds": sorted(roles),
        "components": ["X", "Y"],
    }


def _validate_request(request: Any) -> dict[str, Any]:
    request = _exact_keys(
        request,
        {
            "schema",
            "runRef",
            "modelPath",
            "semanticManifestPath",
            "metrics",
        },
        subject="request",
    )
    if request.get("schema") != REQUEST_SCHEMA:
        raise _invalid(
            f"request.schema must equal {REQUEST_SCHEMA}",
            schema=request.get("schema"),
        )
    for field in ("runRef", "modelPath", "semanticManifestPath"):
        value = request.get(field)
        if not isinstance(value, str) or not value.strip():
            raise _invalid(
                f"{field} must be a non-empty string",
                field=field,
            )
    raw_metrics = request.get("metrics")
    if not isinstance(raw_metrics, list) or not raw_metrics:
        raise _invalid("metrics must be a non-empty array")
    if len(raw_metrics) > 50:
        raise _invalid("PR34 accepts at most 50 metrics per request")

    metrics: list[dict[str, Any]] = []
    metric_ids: set[str] = set()
    for index, raw in enumerate(raw_metrics):
        if not isinstance(raw, dict):
            raise _invalid(
                "Each metric must be a JSON object",
                metricIndex=index,
            )
        metric_type = raw.get("type")
        if metric_type == "ROLE_ABSOLUTE_PEAK":
            metric = _validate_absolute_peak(raw, index=index)
        elif metric_type == "ROLE_RELATIVE_DISPLACEMENT_PEAK":
            metric = _validate_relative_displacement(raw, index=index)
        elif metric_type == "ROLE_GROUP_REACTION_RESULTANT_PEAK":
            metric = _validate_group_reaction_resultant(raw, index=index)
        else:
            raise _invalid(
                "Unsupported PR34 metric type",
                metricIndex=index,
                metricType=metric_type,
            )
        metric_id = metric["metricId"]
        if metric_id in metric_ids:
            raise _invalid(
                "metricId values must be unique",
                metricId=metric_id,
            )
        metric_ids.add(metric_id)
        metrics.append(metric)

    metrics.sort(key=lambda item: str(item["metricId"]))
    return {
        "schema": REQUEST_SCHEMA,
        "runRef": request["runRef"],
        "modelPath": request["modelPath"],
        "semanticManifestPath": request["semanticManifestPath"],
        "metrics": metrics,
    }


def _role_provenance(role: dict[str, Any]) -> dict[str, Any]:
    return {
        "roleId": role["roleId"],
        "roleType": role["roleType"],
        "entity": copy.deepcopy(role["entity"]),
        "entityValidation": role["entityValidation"],
        "manifestSha256": role["manifestSha256"],
        "modelBundleFingerprint": role["modelBundleFingerprint"],
    }


def _role(
    roles: dict[str, dict[str, Any]],
    role_id: str,
) -> dict[str, Any]:
    result = roles.get(role_id)
    if result is None:
        raise FemCoreError(
            "ENGINEERING_RESPONSE_METRIC_ROLE_NOT_FOUND",
            "Requested engineering metric role is not declared in the bound Semantic Role Manifest",
            details={"roleId": role_id},
        )
    return result


def _query_for_role(
    role: dict[str, Any],
    *,
    quantity: str,
    component: str,
    operation: str,
    location: str | None = None,
    offset: int | None = None,
    limit: int | None = None,
) -> dict[str, Any]:
    query: dict[str, Any] = {
        "quantity": quantity,
        "target": copy.deepcopy(role["entity"]),
        "component": component,
        "operation": operation,
    }
    if location is not None:
        query["location"] = location
    if offset is not None:
        query["offset"] = offset
    if limit is not None:
        query["limit"] = limit
    return query


def _validate_role_response_identity(
    role: dict[str, Any],
    *,
    quantity: str,
) -> None:
    entity_type = role["entity"]["type"]
    if quantity == "GENERALIZED_FORCE":
        if entity_type != "ELEMENT":
            raise FemCoreError(
                "ENGINEERING_RESPONSE_METRIC_ROLE_ENTITY_MISMATCH",
                "GENERALIZED_FORCE metrics require an explicit ELEMENT semantic role",
                details={
                    "roleId": role["roleId"],
                    "entity": role["entity"],
                },
            )
        return
    if entity_type != "NODE":
        raise FemCoreError(
            "ENGINEERING_RESPONSE_METRIC_ROLE_ENTITY_MISMATCH",
            "Nodal engineering response metrics require an explicit NODE semantic role",
            details={
                "roleId": role["roleId"],
                "entity": role["entity"],
                "quantity": quantity,
            },
        )


def _absolute_peak_metric(
    workspace: Path,
    *,
    run_ref: str,
    metric: dict[str, Any],
    roles: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    role = _role(roles, metric["roleId"])
    _validate_role_response_identity(role, quantity=metric["quantity"])
    query = _query_for_role(
        role,
        quantity=metric["quantity"],
        component=metric["component"],
        operation="SUMMARY",
        location=metric.get("location"),
    )
    response = query_result(workspace, run_ref, query)
    summary = response.get("summary")
    if not isinstance(summary, dict):
        raise FemCoreError(
            "ENGINEERING_RESPONSE_METRIC_SUMMARY_UNAVAILABLE",
            "Result Intelligence did not return SUMMARY evidence for the requested role metric",
            details={"metricId": metric["metricId"]},
        )
    result: dict[str, Any] = {
        "metricId": metric["metricId"],
        "type": metric["type"],
        "status": "COMPUTED",
        "role": _role_provenance(role),
        "quantity": response.get("quantity"),
        "target": copy.deepcopy(response.get("target")),
        "component": response.get("component"),
        "unit": response.get("unit"),
        "referenceFrame": response.get("referenceFrame"),
        "abscissa": copy.deepcopy(response.get("abscissa")),
        "sampleCount": summary.get("sampleCount"),
        "min": summary.get("min"),
        "max": summary.get("max"),
        "absolutePeak": summary.get("absolutePeak"),
        "abscissaAtAbsolutePeak": summary.get("abscissaAtAbsolutePeak"),
        "source": copy.deepcopy(response.get("source")),
    }
    if "location" in response:
        result["location"] = response["location"]
    return result


def _page_identity(response: dict[str, Any]) -> dict[str, Any]:
    return {
        "runId": response.get("runId"),
        "caseFingerprint": response.get("caseFingerprint"),
        "quantity": response.get("quantity"),
        "target": copy.deepcopy(response.get("target")),
        "component": response.get("component"),
        "location": response.get("location"),
        "unit": response.get("unit"),
        "referenceFrame": response.get("referenceFrame"),
        "abscissa": copy.deepcopy(response.get("abscissa")),
        "source": copy.deepcopy(response.get("source")),
    }


def _full_series(
    workspace: Path,
    *,
    run_ref: str,
    role: dict[str, Any],
    quantity: str,
    component: str,
    location: str | None = None,
) -> dict[str, Any]:
    offset = 0
    identity: dict[str, Any] | None = None
    total: int | None = None
    abscissa: list[float] = []
    values: list[float] = []

    while total is None or offset < total:
        response = query_result(
            workspace,
            run_ref,
            _query_for_role(
                role,
                quantity=quantity,
                component=component,
                operation="SERIES",
                location=location,
                offset=offset,
                limit=_PAGE_SIZE,
            ),
        )
        page = response.get("series")
        paging = response.get("paging")
        if not isinstance(page, list) or not isinstance(paging, dict):
            raise FemCoreError(
                "ENGINEERING_RESPONSE_METRIC_SERIES_UNAVAILABLE",
                "Result Intelligence did not return paged SERIES evidence",
                details={"roleId": role["roleId"], "quantity": quantity},
            )
        page_identity = _page_identity(response)
        if identity is None:
            identity = page_identity
        elif page_identity != identity:
            raise FemCoreError(
                "ENGINEERING_RESPONSE_METRIC_PAGE_IDENTITY_MISMATCH",
                "Paged Result Intelligence response identity changed while assembling one metric series",
                details={"roleId": role["roleId"], "quantity": quantity},
            )

        page_total = paging.get("total")
        returned = paging.get("returned")
        page_offset = paging.get("offset")
        if (
            not isinstance(page_total, int)
            or isinstance(page_total, bool)
            or page_total <= 0
            or not isinstance(returned, int)
            or isinstance(returned, bool)
            or returned < 0
            or page_offset != offset
            or returned != len(page)
        ):
            raise FemCoreError(
                "ENGINEERING_RESPONSE_METRIC_PAGING_INVALID",
                "Result Intelligence returned an invalid paging contract",
                details={"roleId": role["roleId"], "paging": paging},
            )
        if total is None:
            total = page_total
        elif page_total != total:
            raise FemCoreError(
                "ENGINEERING_RESPONSE_METRIC_PAGING_INVALID",
                "Result Intelligence series total changed between pages",
                details={
                    "roleId": role["roleId"],
                    "expectedTotal": total,
                    "receivedTotal": page_total,
                },
            )
        if returned == 0 and offset < total:
            raise FemCoreError(
                "ENGINEERING_RESPONSE_METRIC_PAGING_INVALID",
                "Result Intelligence returned an empty page before the declared series end",
                details={"roleId": role["roleId"], "offset": offset},
            )

        for sample in page:
            if (
                not isinstance(sample, dict)
                or not isinstance(sample.get("abscissa"), (int, float))
                or isinstance(sample.get("abscissa"), bool)
                or not isinstance(sample.get("value"), (int, float))
                or isinstance(sample.get("value"), bool)
            ):
                raise FemCoreError(
                    "ENGINEERING_RESPONSE_METRIC_SERIES_INVALID",
                    "Metric series contains an invalid sample",
                    details={"roleId": role["roleId"]},
                )
            x = float(sample["abscissa"])
            y = float(sample["value"])
            if not math.isfinite(x) or not math.isfinite(y):
                raise FemCoreError(
                    "ENGINEERING_RESPONSE_METRIC_SERIES_INVALID",
                    "Metric series contains a non-finite sample",
                    details={"roleId": role["roleId"]},
                )
            abscissa.append(x)
            values.append(y)
        offset += returned

    if identity is None or total is None or len(values) != total:
        raise FemCoreError(
            "ENGINEERING_RESPONSE_METRIC_SERIES_INVALID",
            "Metric series did not reproduce the complete declared sample count",
            details={
                "roleId": role["roleId"],
                "declaredTotal": total,
                "received": len(values),
            },
        )
    return {
        **identity,
        "sampleCount": total,
        "abscissaValues": abscissa,
        "values": values,
    }


def _series_compatibility_key(series: dict[str, Any]) -> dict[str, Any]:
    return {
        "runId": series["runId"],
        "caseFingerprint": series["caseFingerprint"],
        "unit": series["unit"],
        "referenceFrame": series["referenceFrame"],
        "abscissa": copy.deepcopy(series["abscissa"]),
        "sampleCount": series["sampleCount"],
        "abscissaValues": list(series["abscissaValues"]),
    }


def _require_compatible_series(
    series: list[dict[str, Any]],
    *,
    metric_id: str,
) -> None:
    if not series:
        raise FemCoreError(
            "ENGINEERING_RESPONSE_METRIC_SERIES_INVALID",
            "Composite metric has no input series",
            details={"metricId": metric_id},
        )
    expected = _series_compatibility_key(series[0])
    for item in series[1:]:
        if _series_compatibility_key(item) != expected:
            raise FemCoreError(
                "ENGINEERING_RESPONSE_METRIC_SERIES_MISMATCH",
                "Composite engineering metric requires exactly aligned series with identical units and reference frame",
                details={
                    "metricId": metric_id,
                    "expected": {
                        key: value
                        for key, value in expected.items()
                        if key != "abscissaValues"
                    },
                    "received": {
                        key: value
                        for key, value in _series_compatibility_key(item).items()
                        if key != "abscissaValues"
                    },
                },
            )


def _signed_peak(
    abscissa: list[float],
    values: list[float],
) -> dict[str, Any]:
    peak_index = max(range(len(values)), key=lambda index: abs(values[index]))
    value = values[peak_index]
    return {
        "sampleCount": len(values),
        "min": min(values),
        "max": max(values),
        "valueAtAbsolutePeak": value,
        "absolutePeak": abs(value),
        "abscissaAtAbsolutePeak": abscissa[peak_index],
    }


def _relative_displacement_metric(
    workspace: Path,
    *,
    run_ref: str,
    metric: dict[str, Any],
    roles: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    target_role = _role(roles, metric["targetRoleId"])
    reference_role = _role(roles, metric["referenceRoleId"])
    for role in (target_role, reference_role):
        _validate_role_response_identity(role, quantity="DISPLACEMENT")
    if target_role["entity"] == reference_role["entity"]:
        raise FemCoreError(
            "ENGINEERING_RESPONSE_METRIC_ROLE_ENTITY_MISMATCH",
            "Relative displacement roles resolve to the same solver entity",
            details={
                "targetRoleId": target_role["roleId"],
                "referenceRoleId": reference_role["roleId"],
                "entity": target_role["entity"],
            },
        )

    target = _full_series(
        workspace,
        run_ref=run_ref,
        role=target_role,
        quantity="DISPLACEMENT",
        component=metric["component"],
    )
    reference = _full_series(
        workspace,
        run_ref=run_ref,
        role=reference_role,
        quantity="DISPLACEMENT",
        component=metric["component"],
    )
    _require_compatible_series(
        [target, reference],
        metric_id=metric["metricId"],
    )
    relative = [
        target_value - reference_value
        for target_value, reference_value in zip(
            target["values"],
            reference["values"],
            strict=True,
        )
    ]
    peak = _signed_peak(target["abscissaValues"], relative)
    return {
        "metricId": metric["metricId"],
        "type": metric["type"],
        "status": "COMPUTED",
        "targetRole": _role_provenance(target_role),
        "referenceRole": _role_provenance(reference_role),
        "quantity": "RELATIVE_DISPLACEMENT",
        "component": metric["component"],
        "formula": "target - reference",
        "unit": target["unit"],
        "referenceFrame": target["referenceFrame"],
        "abscissa": copy.deepcopy(target["abscissa"]),
        **peak,
        "sources": [
            copy.deepcopy(target["source"]),
            copy.deepcopy(reference["source"]),
        ],
    }


def _group_reaction_resultant_metric(
    workspace: Path,
    *,
    run_ref: str,
    metric: dict[str, Any],
    roles: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    resolved_roles = [_role(roles, role_id) for role_id in metric["roleIds"]]
    for role in resolved_roles:
        _validate_role_response_identity(role, quantity="REACTION_FORCE")
        if role["entity"]["type"] != "NODE":
            raise FemCoreError(
                "ENGINEERING_RESPONSE_METRIC_ROLE_ENTITY_MISMATCH",
                "Reaction resultant metrics require NODE roles",
                details={"roleId": role["roleId"], "entity": role["entity"]},
            )
    entity_keys = {
        (role["entity"]["type"], int(role["entity"]["id"]))
        for role in resolved_roles
    }
    if len(entity_keys) != len(resolved_roles):
        raise FemCoreError(
            "ENGINEERING_RESPONSE_METRIC_DUPLICATE_ENTITY",
            "Reaction resultant roleIds must resolve to distinct NODE entities",
            details={"roleIds": metric["roleIds"]},
        )

    series_by_role: dict[str, dict[str, dict[str, Any]]] = {}
    all_series: list[dict[str, Any]] = []
    for role in resolved_roles:
        component_series: dict[str, dict[str, Any]] = {}
        for component in ("X", "Y"):
            series = _full_series(
                workspace,
                run_ref=run_ref,
                role=role,
                quantity="REACTION_FORCE",
                component=component,
            )
            component_series[component] = series
            all_series.append(series)
        series_by_role[role["roleId"]] = component_series

    _require_compatible_series(
        all_series,
        metric_id=metric["metricId"],
    )
    sample_count = all_series[0]["sampleCount"]
    abscissa = all_series[0]["abscissaValues"]
    sum_x: list[float] = []
    sum_y: list[float] = []
    resultants: list[float] = []
    for index in range(sample_count):
        x_value = sum(
            series_by_role[role["roleId"]]["X"]["values"][index]
            for role in resolved_roles
        )
        y_value = sum(
            series_by_role[role["roleId"]]["Y"]["values"][index]
            for role in resolved_roles
        )
        resultant = math.hypot(x_value, y_value)
        if not (
            math.isfinite(x_value)
            and math.isfinite(y_value)
            and math.isfinite(resultant)
        ):
            raise FemCoreError(
                "ENGINEERING_RESPONSE_METRIC_NUMERIC_OVERFLOW",
                "Reaction resultant calculation produced a non-finite value",
                details={"metricId": metric["metricId"], "sampleIndex": index},
            )
        sum_x.append(x_value)
        sum_y.append(y_value)
        resultants.append(resultant)

    peak_index = max(
        range(sample_count),
        key=lambda index: resultants[index],
    )
    return {
        "metricId": metric["metricId"],
        "type": metric["type"],
        "status": "COMPUTED",
        "roles": [_role_provenance(role) for role in resolved_roles],
        "quantity": "REACTION_FORCE_RESULTANT",
        "components": ["X", "Y"],
        "formula": "sqrt((sum Rx)^2 + (sum Ry)^2)",
        "aggregation": "SIGNED_COMPONENT_SUM_THEN_VECTOR_MAGNITUDE",
        "unit": all_series[0]["unit"],
        "referenceFrame": all_series[0]["referenceFrame"],
        "abscissa": copy.deepcopy(all_series[0]["abscissa"]),
        "sampleCount": sample_count,
        "minResultant": min(resultants),
        "maxResultant": max(resultants),
        "absolutePeak": resultants[peak_index],
        "abscissaAtAbsolutePeak": abscissa[peak_index],
        "componentSumsAtAbsolutePeak": {
            "X": sum_x[peak_index],
            "Y": sum_y[peak_index],
        },
        "sources": [
            {
                "roleId": role["roleId"],
                "X": copy.deepcopy(
                    series_by_role[role["roleId"]]["X"]["source"]
                ),
                "Y": copy.deepcopy(
                    series_by_role[role["roleId"]]["Y"]["source"]
                ),
            }
            for role in resolved_roles
        ],
    }


def compute_engineering_response_metrics(
    workspace: Path,
    request: dict[str, Any],
) -> dict[str, Any]:
    normalized = _validate_request(request)
    semantic = inspect_semantic_roles(
        workspace,
        model_path=normalized["modelPath"],
        manifest_path=normalized["semanticManifestPath"],
    )
    inspection = inspect_result(workspace, normalized["runRef"])
    integrity = inspection.get("integrity")
    if (
        not isinstance(integrity, dict)
        or integrity.get("status") != "VALID"
    ):
        raise FemCoreError(
            "ENGINEERING_RESPONSE_METRIC_RESULT_NOT_VALID",
            "Engineering metrics require a Result Intelligence run with VALID artifact integrity",
            details={
                "runId": inspection.get("runId"),
                "integrityStatus": (
                    integrity.get("status")
                    if isinstance(integrity, dict)
                    else None
                ),
            },
        )

    semantic_fingerprint = semantic["model"]["bundleFingerprint"]
    recorded_model = inspection.get("model")
    run_fingerprint = (
        recorded_model.get("bundleFingerprint")
        if isinstance(recorded_model, dict)
        else None
    )
    if run_fingerprint != semantic_fingerprint:
        raise FemCoreError(
            "ENGINEERING_RESPONSE_METRIC_RUN_MODEL_MISMATCH",
            "Recorded solver run does not belong to the Model Bundle bound by the Semantic Role Manifest",
            details={
                "semanticModelBundleFingerprint": semantic_fingerprint,
                "runModelBundleFingerprint": run_fingerprint,
                "runId": inspection.get("runId"),
            },
        )

    roles = {
        str(role["roleId"]): role
        for role in semantic["roles"]
        if isinstance(role, dict)
    }
    results: list[dict[str, Any]] = []
    issues: list[dict[str, Any]] = []
    for metric in normalized["metrics"]:
        try:
            if metric["type"] == "ROLE_ABSOLUTE_PEAK":
                result = _absolute_peak_metric(
                    workspace,
                    run_ref=normalized["runRef"],
                    metric=metric,
                    roles=roles,
                )
            elif metric["type"] == "ROLE_RELATIVE_DISPLACEMENT_PEAK":
                result = _relative_displacement_metric(
                    workspace,
                    run_ref=normalized["runRef"],
                    metric=metric,
                    roles=roles,
                )
            else:
                result = _group_reaction_resultant_metric(
                    workspace,
                    run_ref=normalized["runRef"],
                    metric=metric,
                    roles=roles,
                )
        except FemCoreError as exc:
            issues.append(
                {
                    "metricId": metric["metricId"],
                    "code": exc.code,
                    "message": exc.message,
                    "details": copy.deepcopy(exc.details),
                }
            )
            continue
        results.append(result)

    solver = inspection.get("solver")
    manifest = semantic.get("manifest")
    return {
        "schema": REPORT_SCHEMA,
        "status": "COMPLETED" if not issues else "LIMITED",
        "requestFingerprint": _canonical_hash(normalized),
        "run": {
            "runId": inspection["runId"],
            "caseFingerprint": inspection["caseFingerprint"],
            "solver": copy.deepcopy(solver),
            "modelBundleFingerprint": run_fingerprint,
        },
        "semantic": {
            "modelPath": semantic["model"]["path"],
            "modelBundleFingerprint": semantic_fingerprint,
            "manifestPath": (
                manifest.get("path") if isinstance(manifest, dict) else None
            ),
            "manifestSha256": (
                manifest.get("sha256") if isinstance(manifest, dict) else None
            ),
        },
        "metrics": results,
        "issues": issues,
        "limitations": [
            {
                "code": "ENGINEERING_RESPONSE_METRICS_NO_ACCEPTANCE_JUDGMENT",
                "message": (
                    "PR34 reports deterministic response metrics only; it does not "
                    "apply design-code limits, acceptance thresholds, or PASS/FAIL judgments"
                ),
            }
        ],
    }


__all__ = [
    "REPORT_SCHEMA",
    "REQUEST_SCHEMA",
    "compute_engineering_response_metrics",
]
