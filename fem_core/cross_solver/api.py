from __future__ import annotations

from pathlib import Path
from typing import Any

from fem_core.errors import FemCoreError
from fem_core.semantic_roles.evidence import project_role_evidence

from .models import CROSS_SOLVER_OPERATION_NOT_SUPPORTED, NOT_COMPARABLE
from .validation import compare_role_evidence_reports

_REQUIRED_SIDE_FIELDS = ("modelPath", "manifestPath", "roleId", "runRef")
_REQUIRED_QUERY_FIELDS = ("quantity", "component", "operation")


def _required_text(mapping: dict[str, Any], field: str, *, scope: str) -> str:
    value = mapping.get(field)
    if not isinstance(value, str) or not value.strip():
        raise FemCoreError(
            "INVALID_CROSS_SOLVER_VALIDATION_REQUEST",
            f"Cross-solver validation requires non-empty {scope}.{field}",
            details={"scope": scope, "field": field},
        )
    return value.strip()


def _validated_side(side: dict[str, Any], *, scope: str) -> dict[str, str]:
    if not isinstance(side, dict):
        raise FemCoreError(
            "INVALID_CROSS_SOLVER_VALIDATION_REQUEST",
            f"Cross-solver validation {scope} must be an object",
            details={"scope": scope},
        )
    return {field: _required_text(side, field, scope=scope) for field in _REQUIRED_SIDE_FIELDS}


def _validated_query(query: dict[str, Any]) -> dict[str, str]:
    if not isinstance(query, dict):
        raise FemCoreError(
            "INVALID_CROSS_SOLVER_VALIDATION_REQUEST",
            "Cross-solver validation query must be an object",
        )
    normalized = {
        field: _required_text(query, field, scope="query").upper()
        for field in _REQUIRED_QUERY_FIELDS
    }
    location = query.get("location")
    if location is not None:
        if not isinstance(location, str) or not location.strip():
            raise FemCoreError(
                "INVALID_CROSS_SOLVER_VALIDATION_REQUEST",
                "Cross-solver validation query.location must be a non-empty string when provided",
                details={"scope": "query", "field": "location"},
            )
        normalized["location"] = location.strip().upper()
    return normalized


def _unsupported_operation(project_id: str, query: dict[str, str]) -> dict[str, Any]:
    return {
        "schemaVersion": "1.0",
        "kind": "cross_solver_validation",
        "status": NOT_COMPARABLE,
        "projectId": project_id,
        "role": None,
        "query": dict(query),
        "sides": {"left": None, "right": None},
        "comparison": None,
        "limitations": [
            {
                "code": CROSS_SOLVER_OPERATION_NOT_SUPPORTED,
                "message": "Cross-Solver Validation V1 supports SUMMARY comparison only",
            }
        ],
    }


def validate_cross_solver(
    workspace: Path,
    *,
    project_id: str,
    left: dict[str, str],
    right: dict[str, str],
    query: dict[str, Any],
) -> dict[str, Any]:
    """Compare two independently verified role-backed recorded responses.

    The function delegates semantic identity, run/model binding, result artifact
    integrity, and evidence promotion to the existing PR13/PR12 production path.
    It never executes a solver or accepts caller-provided numerical evidence.
    """

    if not isinstance(project_id, str) or not project_id.strip():
        raise FemCoreError(
            "INVALID_CROSS_SOLVER_VALIDATION_REQUEST",
            "Cross-solver validation requires a non-empty projectId",
        )
    normalized_query = _validated_query(query)

    # V1 rejects unsupported comparison modes before touching either side's
    # model, semantic manifest, or recorded result artifacts.
    if normalized_query["operation"] != "SUMMARY":
        return _unsupported_operation(project_id.strip(), normalized_query)

    normalized_left = _validated_side(left, scope="left")
    normalized_right = _validated_side(right, scope="right")
    location = normalized_query.get("location")

    left_report = project_role_evidence(
        workspace,
        project_id=project_id.strip(),
        model_path=normalized_left["modelPath"],
        manifest_path=normalized_left["manifestPath"],
        role_id=normalized_left["roleId"],
        run_ref=normalized_left["runRef"],
        evidence_id=f"{project_id.strip()}:cross-solver:left",
        quantity=normalized_query["quantity"],
        component=normalized_query["component"],
        location=location,
        operation=normalized_query["operation"],
    )
    right_report = project_role_evidence(
        workspace,
        project_id=project_id.strip(),
        model_path=normalized_right["modelPath"],
        manifest_path=normalized_right["manifestPath"],
        role_id=normalized_right["roleId"],
        run_ref=normalized_right["runRef"],
        evidence_id=f"{project_id.strip()}:cross-solver:right",
        quantity=normalized_query["quantity"],
        component=normalized_query["component"],
        location=location,
        operation=normalized_query["operation"],
    )

    return compare_role_evidence_reports(
        project_id=project_id.strip(),
        left_report=left_report,
        right_report=right_report,
        query=normalized_query,
    )
