from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from fem_core.analysis_spec import render_opensees_analysis
from fem_core.model_spec.validator import validate_engineering_model_spec

MODEL_FIXTURE = Path("tests/fixtures/model_spec/simple-portal-frame.json")


def _model() -> dict[str, Any]:
    model = json.loads(MODEL_FIXTURE.read_text(encoding="utf-8"))
    model["nodalMasses"] = [{"nodeId": 3, "mUX": 100.0, "mUY": 100.0}]
    return model


def _analysis(model: dict[str, Any]) -> dict[str, Any]:
    validation = validate_engineering_model_spec(model)
    assert validation["status"] == "VALID"
    return {
        "schemaVersion": "2.0",
        "kind": "engineering_analysis_spec",
        "modelSpecFingerprint": validation["modelSpecFingerprint"],
        "analysisType": "MODAL",
        "units": {},
        "definition": {"modeCount": 2},
        "resultRequests": [
            {"requestId": "FREQ_1", "quantity": "NATURAL_FREQUENCY", "mode": 1},
            {"requestId": "PERIOD_2", "quantity": "PERIOD", "mode": 2},
            {
                "requestId": "MODE_1_Y",
                "quantity": "MODE_SHAPE",
                "mode": 1,
                "target": {"type": "NODE", "id": 3},
                "component": "Y",
            },
        ],
    }


def test_modal_renderer_emits_one_native_eigen_call_and_modal_plan(tmp_path: Path) -> None:
    model = _model()
    analysis = _analysis(model)

    rendered = render_opensees_analysis(tmp_path, model, analysis)

    assert rendered["schema"] == "FEMAGENT_OPENSEES_ANALYSIS_RENDER_V2"
    assert rendered["status"] == "RENDERED"
    assert rendered["input"]["readinessProfile"] == "OPENSEES_FRAME_2D_MODAL_V2"
    analysis_path = tmp_path / rendered["artifacts"]["analysisPath"]
    source = analysis_path.read_text(encoding="utf-8")
    assert source.count("ops.eigen(") == 1
    assert "_femagent_eigenvalues = ops.eigen(2)" in source
    assert "sqrt(" not in source
    assert "nodeEigenvector" not in source

    plan = json.loads((tmp_path / rendered["artifacts"]["responsePlanPath"]).read_text(encoding="utf-8"))
    assert plan == {
        "schemaVersion": "1.0",
        "kind": "modal_response_plan",
        "modeCount": 2,
        "requests": [
            {"requestId": "FREQ_1", "quantity": "NATURAL_FREQUENCY", "mode": 1},
            {
                "requestId": "MODE_1_Y",
                "quantity": "MODE_SHAPE",
                "mode": 1,
                "target": {"type": "NODE", "id": 3},
                "component": "Y",
            },
            {"requestId": "PERIOD_2", "quantity": "PERIOD", "mode": 2},
        ],
    }


def test_modal_renderer_is_deterministic_except_for_render_id(tmp_path: Path) -> None:
    model = _model()
    analysis = _analysis(model)

    first = render_opensees_analysis(tmp_path, model, analysis)
    second = render_opensees_analysis(tmp_path, model, analysis)

    assert first["analysisRenderId"] != second["analysisRenderId"]
    assert first["analysisRenderFingerprint"] == second["analysisRenderFingerprint"]
    for key in ("analysisSha256", "responsePlanSha256", "readinessSha256"):
        assert first["artifacts"][key] == second["artifacts"][key]
