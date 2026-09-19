from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path
from typing import Any

from fem_core.analysis_spec.readiness import evaluate_engineering_analysis_readiness
from fem_core.analysis_spec.validator import validate_engineering_analysis_spec
from fem_core.model_spec.validator import validate_engineering_model_spec

MODEL_FIXTURE = Path("tests/fixtures/model_spec/simple-portal-frame.json")


def _model() -> dict[str, Any]:
    return json.loads(MODEL_FIXTURE.read_text(encoding="utf-8"))


def _analysis(model: dict[str, Any]) -> dict[str, Any]:
    model_validation = validate_engineering_model_spec(model)
    assert model_validation["status"] == "VALID"
    return {
        "schemaVersion": "2.0",
        "kind": "engineering_analysis_spec",
        "modelSpecFingerprint": model_validation["modelSpecFingerprint"],
        "analysisType": "LINEAR_STATIC",
        "units": {"force": "N"},
        "definition": {
            "loadCases": [
                {
                    "loadCaseId": "LC1",
                    "nodalLoads": [
                        {"nodeId": 3, "FX": 0.0, "FY": -10000.0, "MZ": 0.0}
                    ],
                }
            ]
        },
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


def _codes(report: dict[str, Any]) -> set[str]:
    return {str(issue["code"]) for issue in report["issues"]}


def test_v2_static_is_ready_without_v1_identity_conversion() -> None:
    model = _model()
    analysis = _analysis(model)
    validation = validate_engineering_analysis_spec(analysis)
    assert validation["status"] == "VALID"

    report = evaluate_engineering_analysis_readiness(model, analysis)

    assert report["schema"] == "FEMAGENT_ANALYSIS_READINESS_V2"
    assert report["status"] == "READY"
    assert report["profile"] == "OPENSEES_FRAME_2D_LINEAR_STATIC_V2"
    assert report["analysisSpecFingerprint"] == validation["analysisSpecFingerprint"]
    assert validation["normalizedSpec"]["schemaVersion"] == "2.0"
    assert "definition" in validation["normalizedSpec"]
    assert "loadCases" not in validation["normalizedSpec"]
    assert report["checks"]["modelReadiness"]["status"] == "PASS"
    assert report["checks"]["modelBinding"]["status"] == "PASS"
    assert report["checks"]["unitCompatibility"]["status"] == "PASS"
    assert report["checks"]["loadTargets"]["status"] == "PASS"
    assert report["checks"]["resultTargets"]["status"] == "PASS"
    assert report["checks"]["reactionSemantics"]["status"] == "PASS"
    channels = {
        channel["requestId"]: channel
        for channel in report["checks"]["responseMapping"]["channels"]
    }
    assert channels["R_DISP"]["access"] == "NODE_DISP"
    assert channels["R_DISP"]["dof"] == 2
    assert channels["R_RY"]["access"] == "NODE_REACTION"
    assert channels["R_MZ"]["dof"] == 3
    assert channels["R_ELE_MZ"]["access"] == "ELEMENT_LOCAL_FORCE"
    assert channels["R_ELE_MZ"]["index"] == 5


def test_v2_static_model_fingerprint_mismatch_is_not_ready() -> None:
    model = _model()
    analysis = _analysis(model)
    analysis["modelSpecFingerprint"] = "0" * 64
    report = evaluate_engineering_analysis_readiness(model, analysis)
    assert report["status"] == "NOT_READY"
    assert "ANALYSIS_READINESS_MODEL_FINGERPRINT_MISMATCH" in _codes(report)


def test_v2_static_force_unit_mismatch_is_not_ready() -> None:
    model = _model()
    analysis = _analysis(model)
    analysis["units"]["force"] = "kN"
    report = evaluate_engineering_analysis_readiness(model, analysis)
    assert report["status"] == "NOT_READY"
    assert "ANALYSIS_READINESS_FORCE_UNIT_MISMATCH" in _codes(report)


def test_v2_static_missing_load_node_is_not_ready() -> None:
    model = _model()
    analysis = _analysis(model)
    analysis["definition"]["loadCases"][0]["nodalLoads"][0]["nodeId"] = 999999
    report = evaluate_engineering_analysis_readiness(model, analysis)
    assert report["status"] == "NOT_READY"
    assert "ANALYSIS_READINESS_LOAD_NODE_NOT_FOUND" in _codes(report)


def test_v2_static_missing_result_targets_are_not_ready() -> None:
    model = _model()
    analysis = _analysis(model)
    analysis["resultRequests"][0]["target"]["id"] = 999998
    analysis["resultRequests"][-1]["target"]["id"] = 999999
    report = evaluate_engineering_analysis_readiness(model, analysis)
    assert report["status"] == "NOT_READY"
    assert "ANALYSIS_READINESS_RESULT_NODE_NOT_FOUND" in _codes(report)
    assert "ANALYSIS_READINESS_RESULT_ELEMENT_NOT_FOUND" in _codes(report)


def test_v2_static_reaction_requires_restrained_dof() -> None:
    model = _model()
    analysis = _analysis(model)
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
    assert "ANALYSIS_READINESS_REACTION_DOF_UNRESTRAINED" in _codes(report)


def test_v2_static_readiness_is_invariant_to_semantic_collection_order() -> None:
    model_a = _model()
    analysis_a = _analysis(model_a)
    model_b = deepcopy(model_a)
    for key in ("nodes", "materials", "sections", "elements", "constraints", "nodalMasses"):
        model_b[key] = list(reversed(model_b[key]))
    model_b_validation = validate_engineering_model_spec(model_b)
    assert model_b_validation["status"] == "VALID"
    analysis_b = deepcopy(analysis_a)
    analysis_b["modelSpecFingerprint"] = model_b_validation["modelSpecFingerprint"]
    analysis_b["resultRequests"] = list(reversed(analysis_b["resultRequests"]))

    first = evaluate_engineering_analysis_readiness(model_a, analysis_a)
    second = evaluate_engineering_analysis_readiness(model_b, analysis_b)

    assert first["status"] == second["status"] == "READY"
    assert first["modelSpecFingerprint"] == second["modelSpecFingerprint"]
    assert first["analysisSpecFingerprint"] == second["analysisSpecFingerprint"]
    assert first["checks"]["responseMapping"]["channels"] == second["checks"]["responseMapping"]["channels"]
