from __future__ import annotations

import math

import pytest

from fem_core.cross_solver.validation import compare_role_evidence_reports


def _report(
    *,
    node_id: int,
    peak: float = 0.031,
    role_id: str = "TOWER_BASE_LEFT",
    role_type: str = "TOWER_BASE",
    quantity: str = "DISPLACEMENT",
    component: str = "X",
    operation: str = "SUMMARY",
    unit: str | None = "m",
    reference_frame: str | None = "RELATIVE",
    status: str = "VERIFIED",
    solver: str = "OPENSEESPY",
    run_id: str = "run_left",
    fingerprint: str = "a" * 64,
) -> dict:
    evidence = {
        "evidenceId": f"EVID-{run_id}",
        "claim": "Recorded DISPLACEMENT engineering response",
        "status": status,
        "artifacts": [{"artifact": "response.csv", "sha256": "b" * 64, "entity": {}}],
        "metric": {
            "quantity": quantity,
            "target": {"type": "NODE", "id": node_id},
            "component": component,
            "operation": operation,
            "unit": unit,
            "referenceFrame": reference_frame,
            "summary": {"absolutePeak": peak},
        },
        "provenance": {
            "runId": run_id,
            "caseFingerprint": "c" * 64,
            "solver": solver,
            "semanticRole": {
                "roleId": role_id,
                "roleType": role_type,
                "entity": {"type": "NODE", "id": node_id},
                "entityValidation": "STATICALLY_CONFIRMED",
                "manifestSha256": "d" * 64,
                "modelBundleFingerprint": fingerprint,
            },
        },
    }
    return {
        "projectId": "bridge-demo",
        "solverRuns": [
            {"runId": run_id, "solver": solver, "caseFingerprint": "c" * 64}
        ],
        "verifiedEvidence": [evidence] if status == "VERIFIED" else [],
        "limitations": [] if status == "VERIFIED" else [
            {"evidenceId": evidence["evidenceId"], "status": status, "claim": evidence["claim"]}
        ],
        "semanticRole": evidence["provenance"]["semanticRole"],
    }


def _query() -> dict:
    return {"quantity": "DISPLACEMENT", "component": "X", "operation": "SUMMARY"}


def test_compatible_role_evidence_compares_absolute_peak_without_node_identity_equality() -> None:
    result = compare_role_evidence_reports(
        project_id="bridge-demo",
        left_report=_report(node_id=17, peak=0.031, run_id="run_left", fingerprint="1" * 64),
        right_report=_report(node_id=1024, peak=0.030, run_id="run_right", fingerprint="2" * 64),
        query=_query(),
    )

    assert result["status"] == "COMPARABLE"
    assert result["role"] == {"roleId": "TOWER_BASE_LEFT", "roleType": "TOWER_BASE"}
    assert result["sides"]["left"]["entity"] == {"type": "NODE", "id": 17}
    assert result["sides"]["right"]["entity"] == {"type": "NODE", "id": 1024}
    assert result["sides"]["left"]["modelBundleFingerprint"] == "1" * 64
    assert result["sides"]["right"]["modelBundleFingerprint"] == "2" * 64
    assert result["comparison"] == pytest.approx(
        {
            "metric": "absolutePeak",
            "left": 0.031,
            "right": 0.030,
            "absoluteDifference": 0.001,
            "relativeDifference": 0.001 / 0.031,
        }
    )
    assert result["limitations"] == []


def test_zero_peaks_have_zero_symmetric_relative_difference() -> None:
    result = compare_role_evidence_reports(
        project_id="bridge-demo",
        left_report=_report(node_id=1, peak=0.0),
        right_report=_report(node_id=2, peak=0.0),
        query=_query(),
    )

    assert result["status"] == "COMPARABLE"
    assert result["comparison"]["absoluteDifference"] == 0.0
    assert result["comparison"]["relativeDifference"] == 0.0


@pytest.mark.parametrize(
    ("left", "right", "expected_code"),
    [
        (_report(node_id=1, status="LIMITED"), _report(node_id=2), "CROSS_SOLVER_SIDE_NOT_VERIFIED"),
        (_report(node_id=1, role_id="TOWER_BASE_LEFT"), _report(node_id=2, role_id="TOWER_BASE_RIGHT"), "CROSS_SOLVER_ROLE_MISMATCH"),
        (_report(node_id=1, role_type="TOWER_BASE"), _report(node_id=2, role_type="SUPPORT"), "CROSS_SOLVER_ROLE_MISMATCH"),
        (_report(node_id=1, quantity="DISPLACEMENT"), _report(node_id=2, quantity="VELOCITY"), "CROSS_SOLVER_QUERY_MISMATCH"),
        (_report(node_id=1, unit=None), _report(node_id=2, unit="m"), "CROSS_SOLVER_UNIT_UNKNOWN"),
        (_report(node_id=1, unit="m"), _report(node_id=2, unit="mm"), "CROSS_SOLVER_UNIT_MISMATCH"),
        (_report(node_id=1, reference_frame="RELATIVE"), _report(node_id=2, reference_frame="SOLVER_NATIVE"), "CROSS_SOLVER_REFERENCE_FRAME_MISMATCH"),
        (_report(node_id=1, peak=math.nan), _report(node_id=2), "CROSS_SOLVER_METRIC_UNAVAILABLE"),
    ],
)
def test_incompatible_verified_evidence_returns_one_deterministic_limitation(
    left: dict,
    right: dict,
    expected_code: str,
) -> None:
    result = compare_role_evidence_reports(
        project_id="bridge-demo",
        left_report=left,
        right_report=right,
        query=_query(),
    )

    assert result["status"] == "NOT_COMPARABLE"
    assert result["comparison"] is None
    assert [item["code"] for item in result["limitations"]] == [expected_code]
