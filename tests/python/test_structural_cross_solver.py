from __future__ import annotations

from fem_core.cross_solver.validation import compare_role_evidence_reports


def _report(
    *,
    run_id: str,
    location: str = "END_I",
    unit: str | None = "kN*m",
    reference_frame: str = "ELEMENT_LOCAL",
    stress_location: str | None = None,
) -> dict:
    metric = {
        "quantity": "GENERALIZED_FORCE",
        "target": {"type": "ELEMENT", "id": 41 if run_id == "left" else 99},
        "component": "MZ",
        "location": location,
        "operation": "SUMMARY",
        "unit": unit,
        "referenceFrame": reference_frame,
        "summary": {"absolutePeak": 10.0 if run_id == "left" else 9.5},
    }
    if stress_location is not None:
        metric["stressLocation"] = stress_location
    semantic = {
        "roleId": "GIRDER_MIDSPAN",
        "roleType": "MIDSPAN",
        "entity": metric["target"],
        "entityValidation": "STATICALLY_CONFIRMED",
        "manifestSha256": "d" * 64,
        "modelBundleFingerprint": ("1" if run_id == "left" else "2") * 64,
    }
    evidence = {
        "evidenceId": f"EVID-{run_id}",
        "claim": "Recorded GENERALIZED_FORCE engineering response",
        "status": "VERIFIED",
        "artifacts": [{"artifact": "structural_response.json", "sha256": "b" * 64, "entity": {}}],
        "metric": metric,
        "provenance": {
            "runId": f"run_{run_id}",
            "caseFingerprint": "c" * 64,
            "solver": "OPENSEESPY" if run_id == "left" else "ANSYS",
            "semanticRole": semantic,
        },
    }
    return {
        "projectId": "bridge-demo",
        "solverRuns": [],
        "verifiedEvidence": [evidence],
        "limitations": [],
        "semanticRole": semantic,
    }


def _compare(left: dict, right: dict) -> dict:
    return compare_role_evidence_reports(
        project_id="bridge-demo",
        left_report=left,
        right_report=right,
        query={
            "quantity": "GENERALIZED_FORCE",
            "component": "MZ",
            "location": "END_I",
            "operation": "SUMMARY",
        },
    )


def test_structural_location_mismatch_is_not_comparable() -> None:
    result = _compare(_report(run_id="left"), _report(run_id="right", location="END_J"))
    assert result["status"] == "NOT_COMPARABLE"
    assert [item["code"] for item in result["limitations"]] == ["CROSS_SOLVER_LOCATION_MISMATCH"]


def test_structural_reference_frame_mismatch_is_not_comparable() -> None:
    result = _compare(
        _report(run_id="left"),
        _report(run_id="right", reference_frame="SOLVER_NATIVE"),
    )
    assert result["status"] == "NOT_COMPARABLE"
    assert [item["code"] for item in result["limitations"]] == ["CROSS_SOLVER_REFERENCE_FRAME_MISMATCH"]


def test_structural_known_vs_unknown_unit_is_not_comparable() -> None:
    result = _compare(_report(run_id="left"), _report(run_id="right", unit=None))
    assert result["status"] == "NOT_COMPARABLE"
    assert [item["code"] for item in result["limitations"]] == ["CROSS_SOLVER_UNIT_UNKNOWN"]


def test_stress_semantics_mismatch_is_not_comparable() -> None:
    left = _report(run_id="left", stress_location="NODAL_AVERAGED")
    right = _report(run_id="right", stress_location="ELEMENT_NODAL")
    result = _compare(left, right)
    assert result["status"] == "NOT_COMPARABLE"
    assert [item["code"] for item in result["limitations"]] == ["CROSS_SOLVER_STRESS_SEMANTICS_MISMATCH"]


def test_matching_structural_identity_reuses_absolute_peak_comparison() -> None:
    result = _compare(_report(run_id="left"), _report(run_id="right"))
    assert result["status"] == "COMPARABLE"
    assert result["comparison"]["metric"] == "absolutePeak"
    assert result["comparison"]["absoluteDifference"] == 0.5
