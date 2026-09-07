from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path
from typing import Any

from fem_core.analysis_spec import validate_engineering_analysis_spec
from fem_core.analysis_spec.readiness import evaluate_engineering_analysis_readiness
from fem_core.model_spec.validator import validate_engineering_model_spec

FIXTURE = Path("tests/fixtures/model_spec/simple-portal-frame.json")


def _model_spec() -> dict[str, Any]:
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


def _bound_analysis_spec(model_spec: dict[str, Any]) -> dict[str, Any]:
    validation = validate_engineering_model_spec(model_spec)
    assert validation["status"] == "VALID"
    fingerprint = validation["modelSpecFingerprint"]
    assert isinstance(fingerprint, str)
    return {
        "schemaVersion": "1.0",
        "kind": "engineering_analysis_spec",
        "modelSpecFingerprint": fingerprint,
        "analysisType": "LINEAR_STATIC",
        "units": {"force": model_spec["units"]["force"]},
        "loadCases": [
            {
                "loadCaseId": "LC1",
                "nodalLoads": [
                    {"nodeId": 3, "FX": 0.0, "FY": -10000.0, "MZ": 0.0}
                ],
            }
        ],
        "resultRequests": [
            {
                "requestId": "R_DISP",
                "loadCaseId": "LC1",
                "quantity": "DISPLACEMENT",
                "target": {"type": "NODE", "id": 3},
                "component": "Y",
            },
            {
                "requestId": "R_RY",
                "loadCaseId": "LC1",
                "quantity": "REACTION_FORCE",
                "target": {"type": "NODE", "id": 1},
                "component": "Y",
            },
            {
                "requestId": "R_MZ",
                "loadCaseId": "LC1",
                "quantity": "REACTION_MOMENT",
                "target": {"type": "NODE", "id": 1},
                "component": "Z",
            },
            {
                "requestId": "R_ELE_MZ",
                "loadCaseId": "LC1",
                "quantity": "GENERALIZED_FORCE",
                "target": {"type": "ELEMENT", "id": 2},
                "component": "MZ",
                "location": "END_J",
            },
        ],
    }


def _issue_codes(report: dict[str, Any]) -> set[str]:
    return {str(issue["code"]) for issue in report["issues"]}


def test_bound_valid_specs_are_ready_with_proven_response_mappings() -> None:
    model = _model_spec()
    analysis = _bound_analysis_spec(model)

    report = evaluate_engineering_analysis_readiness(model, analysis)

    assert report["schema"] == "FEMAGENT_ANALYSIS_READINESS_V1"
    assert report["status"] == "READY"
    assert report["profile"] == "OPENSEES_FRAME_2D_LINEAR_STATIC_V1"
    assert report["modelSpecFingerprint"] == analysis["modelSpecFingerprint"]
    assert isinstance(report["analysisSpecFingerprint"], str)
    assert report["checks"]["modelReadiness"]["status"] == "PASS"
    assert report["checks"]["modelBinding"]["status"] == "PASS"
    assert report["checks"]["unitCompatibility"]["status"] == "PASS"
    assert report["checks"]["loadTargets"]["status"] == "PASS"
    assert report["checks"]["resultTargets"]["status"] == "PASS"
    assert report["checks"]["reactionSemantics"]["status"] == "PASS"
    response_mapping = report["checks"]["responseMapping"]
    assert response_mapping["status"] == "PASS"
    mappings = {item["requestId"]: item for item in response_mapping["channels"]}
    assert mappings["R_DISP"]["access"] == "NODE_DISP"
    assert mappings["R_DISP"]["dof"] == 2
    assert mappings["R_DISP"]["unit"] == "m"
    assert mappings["R_RY"]["access"] == "NODE_REACTION"
    assert mappings["R_RY"]["dof"] == 2
    assert mappings["R_RY"]["unit"] == "N"
    assert mappings["R_MZ"]["dof"] == 3
    assert mappings["R_MZ"]["unit"] == "N*m"
    assert mappings["R_ELE_MZ"]["access"] == "ELEMENT_LOCAL_FORCE"
    assert mappings["R_ELE_MZ"]["index"] == 5
    assert mappings["R_ELE_MZ"]["unit"] == "N*m"


def test_invalid_model_spec_produces_invalid_spec_and_skips_joint_checks() -> None:
    model = _model_spec()
    analysis = _bound_analysis_spec(model)
    model["elements"][0]["nodeJ"] = 999999

    report = evaluate_engineering_analysis_readiness(model, analysis)

    assert report["status"] == "INVALID_SPEC"
    assert "ANALYSIS_READINESS_INVALID_MODEL_SPEC" in _issue_codes(report)
    assert all(check["status"] == "SKIPPED" for check in report["checks"].values())


def test_invalid_analysis_spec_produces_invalid_spec_and_skips_joint_checks() -> None:
    model = _model_spec()
    analysis = _bound_analysis_spec(model)
    del analysis["analysisType"]

    report = evaluate_engineering_analysis_readiness(model, analysis)

    assert report["status"] == "INVALID_SPEC"
    assert "ANALYSIS_READINESS_INVALID_ANALYSIS_SPEC" in _issue_codes(report)
    assert all(check["status"] == "SKIPPED" for check in report["checks"].values())


def test_model_not_ready_blocks_analysis_without_repair() -> None:
    model = _model_spec()
    model["constraints"] = []
    analysis = _bound_analysis_spec(model)

    report = evaluate_engineering_analysis_readiness(model, analysis)

    assert report["status"] == "NOT_READY"
    assert "ANALYSIS_READINESS_MODEL_NOT_READY" in _issue_codes(report)


def test_model_fingerprint_mismatch_is_not_ready() -> None:
    model = _model_spec()
    analysis = _bound_analysis_spec(model)
    analysis["modelSpecFingerprint"] = "0" * 64

    report = evaluate_engineering_analysis_readiness(model, analysis)

    assert report["status"] == "NOT_READY"
    assert "ANALYSIS_READINESS_MODEL_FINGERPRINT_MISMATCH" in _issue_codes(report)


def test_force_unit_mismatch_is_not_ready_without_conversion() -> None:
    model = _model_spec()
    analysis = _bound_analysis_spec(model)
    analysis["units"]["force"] = "kN"

    report = evaluate_engineering_analysis_readiness(model, analysis)

    assert report["status"] == "NOT_READY"
    assert "ANALYSIS_READINESS_FORCE_UNIT_MISMATCH" in _issue_codes(report)


def test_missing_load_node_is_not_ready() -> None:
    model = _model_spec()
    analysis = _bound_analysis_spec(model)
    analysis["loadCases"][0]["nodalLoads"][0]["nodeId"] = 999999

    report = evaluate_engineering_analysis_readiness(model, analysis)

    assert report["status"] == "NOT_READY"
    assert "ANALYSIS_READINESS_LOAD_NODE_NOT_FOUND" in _issue_codes(report)


def test_pr25_valid_missing_node_result_target_becomes_pr26_not_ready() -> None:
    model = _model_spec()
    analysis = _bound_analysis_spec(model)
    analysis["resultRequests"][0]["target"]["id"] = 999999

    intrinsic = validate_engineering_analysis_spec(analysis)
    report = evaluate_engineering_analysis_readiness(model, analysis)

    assert intrinsic["status"] == "VALID"
    assert report["status"] == "NOT_READY"
    assert "ANALYSIS_READINESS_RESULT_NODE_NOT_FOUND" in _issue_codes(report)


def test_missing_element_result_target_is_not_ready() -> None:
    model = _model_spec()
    analysis = _bound_analysis_spec(model)
    analysis["resultRequests"][-1]["target"]["id"] = 999999

    report = evaluate_engineering_analysis_readiness(model, analysis)

    assert report["status"] == "NOT_READY"
    assert "ANALYSIS_READINESS_RESULT_ELEMENT_NOT_FOUND" in _issue_codes(report)


def test_reaction_force_x_requires_ux_restraint() -> None:
    model = _model_spec()
    analysis = _bound_analysis_spec(model)
    analysis["resultRequests"] = [
        {
            "requestId": "R_FREE_X",
            "loadCaseId": "LC1",
            "quantity": "REACTION_FORCE",
            "target": {"type": "NODE", "id": 3},
            "component": "X",
        }
    ]

    report = evaluate_engineering_analysis_readiness(model, analysis)

    assert report["status"] == "NOT_READY"
    assert "ANALYSIS_READINESS_REACTION_DOF_UNRESTRAINED" in _issue_codes(report)


def test_reaction_force_y_requires_uy_restraint() -> None:
    model = _model_spec()
    analysis = _bound_analysis_spec(model)
    analysis["resultRequests"] = [
        {
            "requestId": "R_FREE_Y",
            "loadCaseId": "LC1",
            "quantity": "REACTION_FORCE",
            "target": {"type": "NODE", "id": 3},
            "component": "Y",
        }
    ]

    report = evaluate_engineering_analysis_readiness(model, analysis)

    assert report["status"] == "NOT_READY"
    assert "ANALYSIS_READINESS_REACTION_DOF_UNRESTRAINED" in _issue_codes(report)


def test_reaction_moment_z_requires_rz_restraint() -> None:
    model = _model_spec()
    analysis = _bound_analysis_spec(model)
    analysis["resultRequests"] = [
        {
            "requestId": "R_FREE_MZ",
            "loadCaseId": "LC1",
            "quantity": "REACTION_MOMENT",
            "target": {"type": "NODE", "id": 3},
            "component": "Z",
        }
    ]

    report = evaluate_engineering_analysis_readiness(model, analysis)

    assert report["status"] == "NOT_READY"
    assert "ANALYSIS_READINESS_REACTION_DOF_UNRESTRAINED" in _issue_codes(report)


def test_semantic_reordering_preserves_analysis_readiness_fingerprints_and_mappings() -> None:
    model = _model_spec()
    analysis = _bound_analysis_spec(model)
    reordered_model = deepcopy(model)
    for key in ("nodes", "materials", "sections", "elements", "constraints", "nodalMasses"):
        reordered_model[key] = list(reversed(reordered_model[key]))
    reordered_analysis = deepcopy(analysis)
    reordered_analysis["loadCases"][0]["nodalLoads"] = list(
        reversed(reordered_analysis["loadCases"][0]["nodalLoads"])
    )
    reordered_analysis["resultRequests"] = list(reversed(reordered_analysis["resultRequests"]))

    first = evaluate_engineering_analysis_readiness(model, analysis)
    second = evaluate_engineering_analysis_readiness(reordered_model, reordered_analysis)

    assert first["status"] == second["status"] == "READY"
    assert first["modelSpecFingerprint"] == second["modelSpecFingerprint"]
    assert first["analysisSpecFingerprint"] == second["analysisSpecFingerprint"]
    assert first["checks"]["responseMapping"]["channels"] == second["checks"]["responseMapping"]["channels"]
