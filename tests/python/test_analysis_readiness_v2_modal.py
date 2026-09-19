from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path
from typing import Any

from fem_core.analysis_spec.readiness import evaluate_engineering_analysis_readiness
from fem_core.model_spec.validator import validate_engineering_model_spec

MODEL_FIXTURE = Path("tests/fixtures/model_spec/simple-portal-frame.json")


def _model() -> dict[str, Any]:
    model = json.loads(MODEL_FIXTURE.read_text(encoding="utf-8"))
    model["nodalMasses"] = [
        {"nodeId": 3, "mUX": 100.0, "mUY": 100.0},
    ]
    return model


def _analysis(model: dict[str, Any], *, mode_count: int = 2) -> dict[str, Any]:
    validation = validate_engineering_model_spec(model)
    assert validation["status"] == "VALID"
    return {
        "schemaVersion": "2.0",
        "kind": "engineering_analysis_spec",
        "modelSpecFingerprint": validation["modelSpecFingerprint"],
        "analysisType": "MODAL",
        "units": {},
        "definition": {"modeCount": mode_count},
        "resultRequests": [
            {"requestId": "EIG_1", "quantity": "EIGENVALUE", "mode": 1},
            {"requestId": "FREQ_1", "quantity": "NATURAL_FREQUENCY", "mode": 1},
            {"requestId": "PERIOD_1", "quantity": "PERIOD", "mode": 1},
            {
                "requestId": "MODE_X",
                "quantity": "MODE_SHAPE",
                "mode": 1,
                "target": {"type": "NODE", "id": 3},
                "component": "X",
            },
            {
                "requestId": "MODE_Y",
                "quantity": "MODE_SHAPE",
                "mode": 1,
                "target": {"type": "NODE", "id": 3},
                "component": "Y",
            },
            {
                "requestId": "MODE_RZ",
                "quantity": "MODE_SHAPE",
                "mode": 1,
                "target": {"type": "NODE", "id": 3},
                "component": "RZ",
            },
        ],
    }


def _codes(report: dict[str, Any]) -> set[str]:
    return {str(issue["code"]) for issue in report["issues"]}


def test_modal_ready_uses_positive_free_translational_mass_dof_bound() -> None:
    model = _model()
    analysis = _analysis(model)

    report = evaluate_engineering_analysis_readiness(model, analysis)

    assert report["schema"] == "FEMAGENT_ANALYSIS_READINESS_V2"
    assert report["status"] == "READY"
    assert report["profile"] == "OPENSEES_FRAME_2D_MODAL_V2"
    assert report["checks"]["modelReadiness"]["status"] == "PASS"
    assert report["checks"]["modelBinding"]["status"] == "PASS"
    assert report["checks"]["modalMass"]["status"] == "PASS"
    assert report["checks"]["modalMass"]["positiveTranslationalMassDofCount"] == 2
    assert report["checks"]["modalMass"]["positiveFreeTranslationalDofCount"] == 2
    assert report["checks"]["modeCount"]["status"] == "PASS"
    assert report["checks"]["modeCount"]["requested"] == 2
    assert report["checks"]["modeCount"]["upperBound"] == 2

    channels = {
        item["requestId"]: item
        for item in report["checks"]["responseMapping"]["channels"]
    }
    assert channels["EIG_1"] == {
        "requestId": "EIG_1",
        "quantity": "EIGENVALUE",
        "mode": 1,
        "access": "MODAL_EIGENVALUE",
        "unit": "1/s2",
    }
    assert channels["FREQ_1"]["access"] == "MODAL_EIGENVALUE"
    assert channels["FREQ_1"]["unit"] == "Hz"
    assert channels["PERIOD_1"]["access"] == "MODAL_EIGENVALUE"
    assert channels["PERIOD_1"]["unit"] == "s"
    assert "target" not in channels["EIG_1"]
    assert channels["MODE_X"]["access"] == "NODE_EIGENVECTOR"
    assert channels["MODE_X"]["dof"] == 1
    assert channels["MODE_Y"]["dof"] == 2
    assert channels["MODE_RZ"]["dof"] == 3
    assert channels["MODE_RZ"]["unit"] == "1"
    assert channels["MODE_RZ"]["normalization"] == "OPENSEES_NATIVE"


def test_modal_requires_at_least_one_positive_translational_mass() -> None:
    model = _model()
    model["nodalMasses"] = []
    analysis = _analysis(model)

    report = evaluate_engineering_analysis_readiness(model, analysis)

    assert report["status"] == "NOT_READY"
    assert "ANALYSIS_READINESS_MODAL_MASS_REQUIRED" in _codes(report)
    assert report["checks"]["modalMass"]["positiveTranslationalMassDofCount"] == 0


def test_modal_requires_positive_mass_on_a_free_translational_dof() -> None:
    model = _model()
    model["nodalMasses"] = [{"nodeId": 1, "mUX": 100.0, "mUY": 100.0}]
    analysis = _analysis(model)

    report = evaluate_engineering_analysis_readiness(model, analysis)

    assert report["status"] == "NOT_READY"
    assert "ANALYSIS_READINESS_MODAL_FREE_MASS_DOF_REQUIRED" in _codes(report)
    assert report["checks"]["modalMass"]["positiveTranslationalMassDofCount"] == 2
    assert report["checks"]["modalMass"]["positiveFreeTranslationalDofCount"] == 0


def test_modal_mode_count_cannot_exceed_positive_free_mass_dof_bound() -> None:
    model = _model()
    analysis = _analysis(model, mode_count=3)

    report = evaluate_engineering_analysis_readiness(model, analysis)

    assert report["status"] == "NOT_READY"
    assert "ANALYSIS_READINESS_MODAL_MODE_COUNT_EXCEEDS_DOF_BOUND" in _codes(report)
    assert report["checks"]["modeCount"]["requested"] == 3
    assert report["checks"]["modeCount"]["upperBound"] == 2


def test_modal_mode_shape_target_node_must_exist() -> None:
    model = _model()
    analysis = _analysis(model)
    request = next(item for item in analysis["resultRequests"] if item["quantity"] == "MODE_SHAPE")
    request["target"]["id"] = 999999

    report = evaluate_engineering_analysis_readiness(model, analysis)

    assert report["status"] == "NOT_READY"
    assert "ANALYSIS_READINESS_RESULT_NODE_NOT_FOUND" in _codes(report)


def test_modal_mass_bound_ignores_zero_mass_and_restrained_dofs() -> None:
    model = _model()
    model["nodalMasses"] = [
        {"nodeId": 1, "mUX": 50.0, "mUY": 50.0},
        {"nodeId": 3, "mUX": 100.0, "mUY": 0.0},
        {"nodeId": 4, "mUX": 0.0, "mUY": 25.0},
    ]
    analysis = _analysis(model, mode_count=2)

    report = evaluate_engineering_analysis_readiness(model, analysis)

    assert report["status"] == "READY"
    assert report["checks"]["modalMass"]["positiveTranslationalMassDofCount"] == 4
    assert report["checks"]["modalMass"]["positiveFreeTranslationalDofCount"] == 2
    assert report["checks"]["modalMass"]["positiveFreeDofs"] == [
        {"nodeId": 3, "component": "X"},
        {"nodeId": 4, "component": "Y"},
    ]


def test_modal_readiness_is_deterministic_under_model_collection_reordering() -> None:
    model_a = _model()
    analysis_a = _analysis(model_a)
    model_b = deepcopy(model_a)
    for key in ("nodes", "materials", "sections", "elements", "constraints", "nodalMasses"):
        model_b[key] = list(reversed(model_b[key]))
    validation_b = validate_engineering_model_spec(model_b)
    assert validation_b["status"] == "VALID"
    analysis_b = deepcopy(analysis_a)
    analysis_b["modelSpecFingerprint"] = validation_b["modelSpecFingerprint"]
    analysis_b["resultRequests"] = list(reversed(analysis_b["resultRequests"]))

    first = evaluate_engineering_analysis_readiness(model_a, analysis_a)
    second = evaluate_engineering_analysis_readiness(model_b, analysis_b)

    assert first["status"] == second["status"] == "READY"
    assert first["modelSpecFingerprint"] == second["modelSpecFingerprint"]
    assert first["analysisSpecFingerprint"] == second["analysisSpecFingerprint"]
    assert first["checks"]["responseMapping"]["channels"] == second["checks"]["responseMapping"]["channels"]
