from __future__ import annotations

import copy
import hashlib
import json
import math
import re
from pathlib import Path
from typing import Any

from fem_core.errors import FemCoreError
from fem_core.response_metrics import compute_engineering_response_metrics

REQUEST_SCHEMA = "FEMAGENT_ENGINEERING_PERFORMANCE_REQUEST_V1"
REPORT_SCHEMA = "FEMAGENT_ENGINEERING_PERFORMANCE_EVALUATION_V1"

_CONSTRAINT_ID = re.compile(r"^[A-Za-z][A-Za-z0-9_-]{0,63}$")
_METRIC_ID = re.compile(r"^[A-Za-z][A-Za-z0-9_-]{0,63}$")


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
        "INVALID_ENGINEERING_PERFORMANCE_REQUEST",
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
            f"{subject} fields do not match the PR35 contract",
            subject=subject,
            missing=sorted(expected - received),
            unknown=sorted(received - expected),
        )
    return value


def _identifier(
    value: Any,
    *,
    pattern: re.Pattern[str],
    subject: str,
) -> str:
    if not isinstance(value, str) or pattern.fullmatch(value) is None:
        raise _invalid(
            f"{subject} has an invalid identifier",
            subject=subject,
            value=value,
        )
    return value


def _normalize_constraint(
    raw: Any,
    *,
    index: int,
) -> dict[str, Any]:
    if not isinstance(raw, dict):
        raise _invalid(
            "Each engineering performance constraint must be a JSON object",
            constraintIndex=index,
        )
    expected = {
        "constraintId",
        "metricId",
        "operator",
        "limit",
        "unit",
    }
    if "label" in raw:
        expected.add("label")
    _exact_keys(raw, expected, subject=f"constraints[{index}]")

    constraint_id = _identifier(
        raw.get("constraintId"),
        pattern=_CONSTRAINT_ID,
        subject=f"constraints[{index}].constraintId",
    )
    metric_id = _identifier(
        raw.get("metricId"),
        pattern=_METRIC_ID,
        subject=f"constraints[{index}].metricId",
    )
    if raw.get("operator") != "MAXIMUM":
        raise _invalid(
            "PR35 V1 supports operator=MAXIMUM only",
            constraintIndex=index,
            operator=raw.get("operator"),
        )

    limit = raw.get("limit")
    if (
        not isinstance(limit, (int, float))
        or isinstance(limit, bool)
        or not math.isfinite(float(limit))
        or float(limit) < 0.0
    ):
        raise _invalid(
            "Constraint limit must be a finite non-negative number",
            constraintIndex=index,
            limit=limit,
        )
    unit = raw.get("unit")
    if not isinstance(unit, str) or not unit.strip():
        raise _invalid(
            "Constraint unit must be a non-empty explicit string",
            constraintIndex=index,
        )

    normalized: dict[str, Any] = {
        "constraintId": constraint_id,
        "metricId": metric_id,
        "operator": "MAXIMUM",
        "limit": float(limit),
        "unit": unit.strip(),
    }
    if "label" in raw:
        label = raw.get("label")
        if not isinstance(label, str) or not label.strip():
            raise _invalid(
                "Constraint label must be non-empty when provided",
                constraintIndex=index,
            )
        normalized["label"] = label.strip()
    return normalized


def _normalize_request(request: Any) -> dict[str, Any]:
    request = _exact_keys(
        request,
        {"schema", "metricsRequest", "constraints"},
        subject="request",
    )
    if request.get("schema") != REQUEST_SCHEMA:
        raise _invalid(
            f"request.schema must equal {REQUEST_SCHEMA}",
            schema=request.get("schema"),
        )
    metrics_request = request.get("metricsRequest")
    if not isinstance(metrics_request, dict):
        raise _invalid("metricsRequest must be a PR34 request JSON object")

    raw_constraints = request.get("constraints")
    if not isinstance(raw_constraints, list) or not raw_constraints:
        raise _invalid("constraints must be a non-empty array")
    if len(raw_constraints) > 100:
        raise _invalid("PR35 accepts at most 100 constraints per request")

    constraints = [
        _normalize_constraint(raw, index=index)
        for index, raw in enumerate(raw_constraints)
    ]
    constraint_ids = [item["constraintId"] for item in constraints]
    if len(set(constraint_ids)) != len(constraint_ids):
        raise _invalid(
            "constraintId values must be unique",
            constraintIds=constraint_ids,
        )
    constraints.sort(key=lambda item: str(item["constraintId"]))
    return {
        "schema": REQUEST_SCHEMA,
        "metricsRequest": copy.deepcopy(metrics_request),
        "constraints": constraints,
    }


def _metric_ids_from_report(
    report: dict[str, Any],
) -> set[str]:
    result: set[str] = set()
    for metric in report.get("metrics", []):
        if isinstance(metric, dict) and isinstance(metric.get("metricId"), str):
            result.add(metric["metricId"])
    for issue in report.get("issues", []):
        if isinstance(issue, dict) and isinstance(issue.get("metricId"), str):
            result.add(issue["metricId"])
    return result


def _metric_issue_map(
    report: dict[str, Any],
) -> dict[str, list[dict[str, Any]]]:
    result: dict[str, list[dict[str, Any]]] = {}
    for issue in report.get("issues", []):
        if not isinstance(issue, dict):
            continue
        metric_id = issue.get("metricId")
        if not isinstance(metric_id, str):
            continue
        result.setdefault(metric_id, []).append(copy.deepcopy(issue))
    return result


def _metric_context(metric: dict[str, Any]) -> dict[str, Any]:
    result = {
        "metricId": metric.get("metricId"),
        "metricType": metric.get("type"),
        "quantity": metric.get("quantity"),
        "component": metric.get("component"),
        "components": copy.deepcopy(metric.get("components")),
        "location": metric.get("location"),
        "referenceFrame": metric.get("referenceFrame"),
        "abscissa": copy.deepcopy(metric.get("abscissa")),
        "abscissaAtAbsolutePeak": metric.get("abscissaAtAbsolutePeak"),
    }
    for key in ("role", "roles", "targetRole", "referenceRole"):
        if key in metric:
            result[key] = copy.deepcopy(metric[key])
    return result


def _not_evaluable(
    constraint: dict[str, Any],
    *,
    code: str,
    message: str,
    details: dict[str, Any] | None = None,
) -> dict[str, Any]:
    result: dict[str, Any] = {
        "constraintId": constraint["constraintId"],
        "metricId": constraint["metricId"],
        "operator": "MAXIMUM",
        "status": "NOT_EVALUABLE",
        "observed": None,
        "limit": constraint["limit"],
        "unit": constraint["unit"],
        "utilization": None,
        "reserve": None,
        "issue": {
            "code": code,
            "message": message,
            "details": copy.deepcopy(details or {}),
        },
    }
    if "label" in constraint:
        result["label"] = constraint["label"]
    return result


def _evaluate_constraint(
    constraint: dict[str, Any],
    *,
    metric: dict[str, Any] | None,
    metric_issues: list[dict[str, Any]],
) -> dict[str, Any]:
    if metric is None:
        return _not_evaluable(
            constraint,
            code="ENGINEERING_CONSTRAINT_METRIC_NOT_COMPUTED",
            message=(
                "The referenced PR34 metric was not computed from recorded result "
                "evidence"
            ),
            details={"metricIssues": copy.deepcopy(metric_issues)},
        )

    observed = metric.get("absolutePeak")
    if (
        not isinstance(observed, (int, float))
        or isinstance(observed, bool)
        or not math.isfinite(float(observed))
        or float(observed) < 0.0
    ):
        return _not_evaluable(
            constraint,
            code="ENGINEERING_CONSTRAINT_METRIC_VALUE_INVALID",
            message="The referenced metric does not expose a finite non-negative absolutePeak",
            details={"metric": _metric_context(metric)},
        )

    metric_unit = metric.get("unit")
    if not isinstance(metric_unit, str) or not metric_unit:
        return _not_evaluable(
            constraint,
            code="ENGINEERING_CONSTRAINT_UNIT_UNPROVEN",
            message=(
                "The referenced metric unit is unknown, so an explicit physical "
                "limit cannot be compared safely"
            ),
            details={"metricUnit": metric_unit},
        )
    if metric_unit != constraint["unit"]:
        return _not_evaluable(
            constraint,
            code="ENGINEERING_CONSTRAINT_UNIT_MISMATCH",
            message=(
                "PR35 performs no unit conversion; metric and constraint units "
                "must match exactly"
            ),
            details={
                "metricUnit": metric_unit,
                "constraintUnit": constraint["unit"],
            },
        )

    observed_value = float(observed)
    limit = float(constraint["limit"])
    status = "SATISFIED" if observed_value <= limit else "VIOLATED"
    if limit > 0.0:
        utilization: float | None = observed_value / limit
    elif observed_value == 0.0:
        utilization = 0.0
    else:
        utilization = None

    result: dict[str, Any] = {
        "constraintId": constraint["constraintId"],
        "metricId": constraint["metricId"],
        "operator": "MAXIMUM",
        "status": status,
        "observed": observed_value,
        "limit": limit,
        "unit": metric_unit,
        "utilization": utilization,
        "reserve": limit - observed_value,
        "metric": _metric_context(metric),
        "issue": None,
    }
    if "label" in constraint:
        result["label"] = constraint["label"]
    return result


def _governing_constraint(
    evaluations: list[dict[str, Any]],
) -> dict[str, Any] | None:
    if not evaluations or any(
        item["status"] == "NOT_EVALUABLE" for item in evaluations
    ):
        return None

    if all(item["utilization"] is not None for item in evaluations):
        governing = max(
            evaluations,
            key=lambda item: (
                float(item["utilization"]),
                str(item["constraintId"]),
            ),
        )
        basis = "MAXIMUM_UTILIZATION"
    else:
        governing = min(
            evaluations,
            key=lambda item: (
                float(item["reserve"]),
                str(item["constraintId"]),
            ),
        )
        basis = "MINIMUM_RESERVE"

    return {
        "constraintId": governing["constraintId"],
        "metricId": governing["metricId"],
        "status": governing["status"],
        "basis": basis,
        "utilization": governing["utilization"],
        "reserve": governing["reserve"],
    }


def evaluate_engineering_performance(
    workspace: Path,
    request: dict[str, Any],
) -> dict[str, Any]:
    normalized = _normalize_request(request)
    metrics_report = compute_engineering_response_metrics(
        workspace,
        normalized["metricsRequest"],
    )

    requested_metric_ids = _metric_ids_from_report(metrics_report)
    referenced_metric_ids = {
        str(item["metricId"]) for item in normalized["constraints"]
    }
    unknown = sorted(referenced_metric_ids - requested_metric_ids)
    if unknown:
        raise _invalid(
            "Every constraint metricId must reference one requested PR34 metric",
            unknownMetricIds=unknown,
            requestedMetricIds=sorted(requested_metric_ids),
        )

    metrics = {
        str(metric["metricId"]): metric
        for metric in metrics_report.get("metrics", [])
        if isinstance(metric, dict) and isinstance(metric.get("metricId"), str)
    }
    issue_map = _metric_issue_map(metrics_report)
    evaluations = [
        _evaluate_constraint(
            constraint,
            metric=metrics.get(str(constraint["metricId"])),
            metric_issues=issue_map.get(str(constraint["metricId"]), []),
        )
        for constraint in normalized["constraints"]
    ]

    violated = sum(
        item["status"] == "VIOLATED" for item in evaluations
    )
    not_evaluable = sum(
        item["status"] == "NOT_EVALUABLE" for item in evaluations
    )
    satisfied = sum(
        item["status"] == "SATISFIED" for item in evaluations
    )
    if violated:
        status = "INFEASIBLE"
    elif not_evaluable:
        status = "LIMITED"
    else:
        status = "FEASIBLE"

    constraint_set_fingerprint = _canonical_hash(
        normalized["constraints"]
    )
    evaluation_fingerprint = _canonical_hash(
        {
            "metricsRequestFingerprint": metrics_report["requestFingerprint"],
            "constraintSetFingerprint": constraint_set_fingerprint,
            "runId": metrics_report["run"]["runId"],
            "caseFingerprint": metrics_report["run"]["caseFingerprint"],
            "modelBundleFingerprint": metrics_report["run"][
                "modelBundleFingerprint"
            ],
        }
    )

    return {
        "schema": REPORT_SCHEMA,
        "status": status,
        "metricsRequestFingerprint": metrics_report["requestFingerprint"],
        "constraintSetFingerprint": constraint_set_fingerprint,
        "evaluationFingerprint": evaluation_fingerprint,
        "run": copy.deepcopy(metrics_report["run"]),
        "semantic": copy.deepcopy(metrics_report["semantic"]),
        "metricsStatus": metrics_report["status"],
        "constraints": evaluations,
        "summary": {
            "constraintCount": len(evaluations),
            "satisfied": satisfied,
            "violated": violated,
            "notEvaluable": not_evaluable,
        },
        "governingConstraint": _governing_constraint(evaluations),
        "metricsReport": metrics_report,
        "limitations": [
            {
                "code": "ENGINEERING_PERFORMANCE_EXPLICIT_CONSTRAINTS_ONLY",
                "message": (
                    "FEASIBLE/INFEASIBLE applies only to the explicit PR35 "
                    "numerical constraints supplied in this request; it is not a "
                    "general structural-safety or design-code compliance verdict"
                ),
            },
            {
                "code": "ENGINEERING_PERFORMANCE_NO_UNIT_CONVERSION",
                "message": (
                    "Constraint evaluation requires exact known unit equality; "
                    "PR35 does not convert or infer units"
                ),
            },
        ],
    }


__all__ = [
    "REPORT_SCHEMA",
    "REQUEST_SCHEMA",
    "evaluate_engineering_performance",
]
