from __future__ import annotations

import math
from typing import Any

from .models import (
    COMPARABLE,
    CROSS_SOLVER_LOCATION_MISMATCH,
    CROSS_SOLVER_METRIC_UNAVAILABLE,
    CROSS_SOLVER_QUERY_MISMATCH,
    CROSS_SOLVER_REFERENCE_FRAME_MISMATCH,
    CROSS_SOLVER_ROLE_MISMATCH,
    CROSS_SOLVER_SIDE_NOT_VERIFIED,
    CROSS_SOLVER_STRESS_SEMANTICS_MISMATCH,
    CROSS_SOLVER_UNIT_MISMATCH,
    CROSS_SOLVER_UNIT_UNKNOWN,
    NOT_COMPARABLE,
)


def _limitation(code: str, message: str) -> dict[str, str]:
    return {"code": code, "message": message}


def _verified_evidence(report: dict[str, Any]) -> dict[str, Any] | None:
    evidences = report.get("verifiedEvidence")
    if not isinstance(evidences, list) or len(evidences) != 1:
        return None
    evidence = evidences[0]
    if not isinstance(evidence, dict) or evidence.get("status") != "VERIFIED":
        return None
    return evidence


def _semantic_role(evidence: dict[str, Any]) -> dict[str, Any]:
    provenance = evidence.get("provenance")
    semantic = provenance.get("semanticRole") if isinstance(provenance, dict) else None
    return semantic if isinstance(semantic, dict) else {}


def _metric(evidence: dict[str, Any]) -> dict[str, Any]:
    metric = evidence.get("metric")
    return metric if isinstance(metric, dict) else {}


def _side_projection(evidence: dict[str, Any] | None) -> dict[str, Any]:
    if evidence is None:
        return {
            "solver": None,
            "runId": None,
            "modelBundleFingerprint": None,
            "entity": None,
            "unit": None,
            "referenceFrame": None,
            "location": None,
            "stressLocation": None,
            "absolutePeak": None,
        }

    provenance = evidence.get("provenance")
    provenance = provenance if isinstance(provenance, dict) else {}
    semantic = _semantic_role(evidence)
    metric = _metric(evidence)
    summary = metric.get("summary")
    summary = summary if isinstance(summary, dict) else {}
    entity = semantic.get("entity")
    if not isinstance(entity, dict):
        entity = metric.get("target") if isinstance(metric.get("target"), dict) else None
    return {
        "solver": provenance.get("solver") if isinstance(provenance.get("solver"), str) else None,
        "runId": provenance.get("runId") if isinstance(provenance.get("runId"), str) else None,
        "modelBundleFingerprint": (
            semantic.get("modelBundleFingerprint")
            if isinstance(semantic.get("modelBundleFingerprint"), str)
            else None
        ),
        "entity": dict(entity) if isinstance(entity, dict) else None,
        "unit": metric.get("unit") if isinstance(metric.get("unit"), str) else None,
        "referenceFrame": (
            metric.get("referenceFrame") if isinstance(metric.get("referenceFrame"), str) else None
        ),
        "location": metric.get("location") if isinstance(metric.get("location"), str) else None,
        "stressLocation": (
            metric.get("stressLocation") if isinstance(metric.get("stressLocation"), str) else None
        ),
        "absolutePeak": summary.get("absolutePeak"),
    }


def _not_comparable(
    *,
    project_id: str,
    query: dict[str, Any],
    left: dict[str, Any],
    right: dict[str, Any],
    role: dict[str, Any] | None,
    limitation: dict[str, str],
) -> dict[str, Any]:
    return {
        "schemaVersion": "1.0",
        "kind": "cross_solver_validation",
        "status": NOT_COMPARABLE,
        "projectId": project_id,
        "role": role,
        "query": dict(query),
        "sides": {"left": left, "right": right},
        "comparison": None,
        "limitations": [limitation],
    }


def compare_role_evidence_reports(
    *,
    project_id: str,
    left_report: dict[str, Any],
    right_report: dict[str, Any],
    query: dict[str, Any],
) -> dict[str, Any]:
    """Compare two already-projected role-backed evidence reports.

    This function is intentionally pure: it does not read model/result files,
    resolve semantic roles, verify artifacts, convert units, or invoke solvers.
    """

    left_evidence = _verified_evidence(left_report)
    right_evidence = _verified_evidence(right_report)
    left = _side_projection(left_evidence)
    right = _side_projection(right_evidence)

    if left_evidence is None or right_evidence is None:
        return _not_comparable(
            project_id=project_id,
            query=query,
            left=left,
            right=right,
            role=None,
            limitation=_limitation(
                CROSS_SOLVER_SIDE_NOT_VERIFIED,
                "Both sides require exactly one VERIFIED Engineering Evidence record",
            ),
        )

    left_semantic = _semantic_role(left_evidence)
    right_semantic = _semantic_role(right_evidence)
    left_role_id = left_semantic.get("roleId")
    right_role_id = right_semantic.get("roleId")
    left_role_type = left_semantic.get("roleType")
    right_role_type = right_semantic.get("roleType")
    role = {
        "roleId": left_role_id if isinstance(left_role_id, str) else None,
        "roleType": left_role_type if isinstance(left_role_type, str) else None,
    }
    if (
        not isinstance(left_role_id, str)
        or not isinstance(right_role_id, str)
        or not isinstance(left_role_type, str)
        or not isinstance(right_role_type, str)
        or left_role_id != right_role_id
        or left_role_type != right_role_type
    ):
        return _not_comparable(
            project_id=project_id,
            query=query,
            left=left,
            right=right,
            role=role,
            limitation=_limitation(
                CROSS_SOLVER_ROLE_MISMATCH,
                "Both sides must resolve to the same explicit semantic roleId and roleType",
            ),
        )

    left_metric = _metric(left_evidence)
    right_metric = _metric(right_evidence)
    expected = (query.get("quantity"), query.get("component"), query.get("operation"))
    left_contract = (
        left_metric.get("quantity"),
        left_metric.get("component"),
        left_metric.get("operation"),
    )
    right_contract = (
        right_metric.get("quantity"),
        right_metric.get("component"),
        right_metric.get("operation"),
    )
    if left_contract != right_contract or left_contract != expected:
        return _not_comparable(
            project_id=project_id,
            query=query,
            left=left,
            right=right,
            role=role,
            limitation=_limitation(
                CROSS_SOLVER_QUERY_MISMATCH,
                "Both evidence records must match the requested quantity, component, and operation",
            ),
        )

    left_location = left_metric.get("location")
    right_location = right_metric.get("location")
    expected_location = query.get("location")
    if (
        left_location != right_location
        or (expected_location is not None and left_location != expected_location)
    ):
        return _not_comparable(
            project_id=project_id,
            query=query,
            left=left,
            right=right,
            role=role,
            limitation=_limitation(
                CROSS_SOLVER_LOCATION_MISMATCH,
                "Both structural evidence records must refer to the same explicit response location",
            ),
        )

    left_stress_location = left_metric.get("stressLocation")
    right_stress_location = right_metric.get("stressLocation")
    if left_stress_location != right_stress_location:
        return _not_comparable(
            project_id=project_id,
            query=query,
            left=left,
            right=right,
            role=role,
            limitation=_limitation(
                CROSS_SOLVER_STRESS_SEMANTICS_MISMATCH,
                "Both structural evidence records require identical stress location/averaging semantics",
            ),
        )

    left_unit = left_metric.get("unit")
    right_unit = right_metric.get("unit")
    if not isinstance(left_unit, str) or not left_unit or not isinstance(right_unit, str) or not right_unit:
        return _not_comparable(
            project_id=project_id,
            query=query,
            left=left,
            right=right,
            role=role,
            limitation=_limitation(
                CROSS_SOLVER_UNIT_UNKNOWN,
                "Both sides require proven non-null result units before numerical comparison",
            ),
        )
    if left_unit != right_unit:
        return _not_comparable(
            project_id=project_id,
            query=query,
            left=left,
            right=right,
            role=role,
            limitation=_limitation(
                CROSS_SOLVER_UNIT_MISMATCH,
                "PR15 V1 does not convert between different result units",
            ),
        )

    left_frame = left_metric.get("referenceFrame")
    right_frame = right_metric.get("referenceFrame")
    if (
        not isinstance(left_frame, str)
        or not left_frame
        or not isinstance(right_frame, str)
        or not right_frame
        or left_frame != right_frame
    ):
        return _not_comparable(
            project_id=project_id,
            query=query,
            left=left,
            right=right,
            role=role,
            limitation=_limitation(
                CROSS_SOLVER_REFERENCE_FRAME_MISMATCH,
                "Both sides require the same explicit reference frame; PR15 V1 performs no frame transformation",
            ),
        )

    left_peak = left["absolutePeak"]
    right_peak = right["absolutePeak"]
    if (
        isinstance(left_peak, bool)
        or not isinstance(left_peak, (int, float))
        or not math.isfinite(float(left_peak))
        or isinstance(right_peak, bool)
        or not isinstance(right_peak, (int, float))
        or not math.isfinite(float(right_peak))
    ):
        return _not_comparable(
            project_id=project_id,
            query=query,
            left=left,
            right=right,
            role=role,
            limitation=_limitation(
                CROSS_SOLVER_METRIC_UNAVAILABLE,
                "Both sides require a finite metric.summary.absolutePeak value",
            ),
        )

    left_value = float(left_peak)
    right_value = float(right_peak)
    absolute_difference = abs(left_value - right_value)
    scale = max(abs(left_value), abs(right_value))
    relative_difference = 0.0 if scale == 0.0 else absolute_difference / scale

    return {
        "schemaVersion": "1.0",
        "kind": "cross_solver_validation",
        "status": COMPARABLE,
        "projectId": project_id,
        "role": role,
        "query": dict(query),
        "sides": {"left": left, "right": right},
        "comparison": {
            "metric": "absolutePeak",
            "left": left_value,
            "right": right_value,
            "absoluteDifference": absolute_difference,
            "relativeDifference": relative_difference,
        },
        "limitations": [],
    }
