from __future__ import annotations

from pathlib import Path

from fem_core.cross_solver.api import validate_cross_solver


def _verified_report(*, run_id: str, element_id: int, location: str) -> dict:
    evidence = {
        "evidenceId": f"EVID-{run_id}",
        "claim": "Recorded GENERALIZED_FORCE engineering response",
        "status": "VERIFIED",
        "artifacts": [{"artifact": "structural_response.json", "sha256": "a" * 64, "entity": {}}],
        "metric": {
            "quantity": "GENERALIZED_FORCE",
            "target": {"type": "ELEMENT", "id": element_id},
            "component": "MZ",
            "location": location,
            "operation": "SUMMARY",
            "unit": "N*m",
            "referenceFrame": "ELEMENT_LOCAL",
            "summary": {"absolutePeak": 10.0},
        },
        "provenance": {
            "runId": run_id,
            "caseFingerprint": "b" * 64,
            "solver": "OPENSEESPY",
            "semanticRole": {
                "roleId": "GIRDER_MIDSPAN",
                "roleType": "MIDSPAN",
                "entity": {"type": "ELEMENT", "id": element_id},
                "entityValidation": "STATICALLY_CONFIRMED",
                "manifestSha256": "c" * 64,
                "modelBundleFingerprint": "d" * 64,
            },
        },
    }
    return {
        "projectId": "bridge-demo",
        "solverRuns": [{"runId": run_id, "solver": "OPENSEESPY", "caseFingerprint": "b" * 64}],
        "verifiedEvidence": [evidence],
        "limitations": [],
        "semanticRole": evidence["provenance"]["semanticRole"],
    }


def test_cross_solver_api_forwards_structural_location_to_both_evidence_sides(
    tmp_path: Path,
    monkeypatch,
) -> None:
    calls: list[tuple[str, str | None]] = []

    def fake_project_role_evidence(*_args, **kwargs):
        run_ref = kwargs["run_ref"]
        location = kwargs.get("location")
        calls.append((run_ref, location))
        return _verified_report(
            run_id=run_ref,
            element_id=41 if run_ref == "run_left" else 99,
            location=location,
        )

    monkeypatch.setattr("fem_core.cross_solver.api.project_role_evidence", fake_project_role_evidence)

    report = validate_cross_solver(
        tmp_path,
        project_id="bridge-demo",
        left={
            "modelPath": "left.py",
            "manifestPath": "left-roles.json",
            "roleId": "GIRDER_MIDSPAN",
            "runRef": "run_left",
        },
        right={
            "modelPath": "right.py",
            "manifestPath": "right-roles.json",
            "roleId": "GIRDER_MIDSPAN",
            "runRef": "run_right",
        },
        query={
            "quantity": "GENERALIZED_FORCE",
            "component": "MZ",
            "location": "END_I",
            "operation": "SUMMARY",
        },
    )

    assert calls == [("run_left", "END_I"), ("run_right", "END_I")]
    assert report["status"] == "COMPARABLE"
    assert report["query"]["location"] == "END_I"
