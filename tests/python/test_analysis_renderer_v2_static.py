from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from fem_core.analysis_spec import render_opensees_analysis
from fem_core.model_spec.validator import validate_engineering_model_spec

MODEL_FIXTURE = Path("tests/fixtures/model_spec/simple-portal-frame.json")
ANALYSIS_FIXTURE = Path("tests/fixtures/analysis_spec/simple-linear-static-v2.json")


def _model() -> dict[str, Any]:
    return json.loads(MODEL_FIXTURE.read_text(encoding="utf-8"))


def _analysis(model: dict[str, Any]) -> dict[str, Any]:
    spec = json.loads(ANALYSIS_FIXTURE.read_text(encoding="utf-8"))
    validation = validate_engineering_model_spec(model)
    assert validation["status"] == "VALID"
    spec["modelSpecFingerprint"] = validation["modelSpecFingerprint"]
    spec["units"]["force"] = model["units"]["force"]
    spec["definition"]["loadCases"][0]["nodalLoads"] = [
        {"nodeId": 3, "FX": 0.0, "FY": -10000.0, "MZ": 0.0}
    ]
    spec["resultRequests"][0]["target"]["id"] = 3
    return spec


def _artifact(workspace: Path, report: dict[str, Any], key: str) -> str:
    return (workspace / report["artifacts"][key]).read_text(encoding="utf-8")


def test_v2_static_renders_through_version_aware_entrypoint(tmp_path: Path) -> None:
    model = _model()
    analysis = _analysis(model)

    report = render_opensees_analysis(tmp_path, model, analysis)

    assert report["schema"] == "FEMAGENT_OPENSEES_ANALYSIS_RENDER_V2"
    assert report["status"] == "RENDERED"
    assert report["renderer"]["version"] == "2.0"
    assert report["input"]["readinessProfile"] == "OPENSEES_FRAME_2D_LINEAR_STATIC_V2"
    assert report["input"]["normalizedAnalysisSpec"]["schemaVersion"] == "2.0"
    source = _artifact(tmp_path, report, "analysisPath")
    assert 'ops.analysis("Static")' in source
    assert "ops.load(3, 0.0, -10000.0, 0.0)" in source
    assert source.count("ops.analyze(1)") == 1
    plan = json.loads(_artifact(tmp_path, report, "responsePlanPath"))
    assert plan["kind"] == "structural_response_plan"
    assert [item["channelId"] for item in plan["channels"]] == ["R1"]


def test_v2_static_renderer_is_content_deterministic(tmp_path: Path) -> None:
    model = _model()
    analysis = _analysis(model)

    first = render_opensees_analysis(tmp_path, model, analysis)
    second = render_opensees_analysis(tmp_path, model, analysis)

    assert first["analysisRenderId"] != second["analysisRenderId"]
    for key in ("analysisSha256", "responsePlanSha256", "readinessSha256"):
        assert first["artifacts"][key] == second["artifacts"][key]
    assert first["analysisRenderFingerprint"] == second["analysisRenderFingerprint"]


def test_v2_static_not_ready_is_blocked_without_writes(tmp_path: Path) -> None:
    model = _model()
    analysis = _analysis(model)
    analysis["modelSpecFingerprint"] = "0" * 64

    report = render_opensees_analysis(tmp_path, model, analysis)

    assert report["schema"] == "FEMAGENT_OPENSEES_ANALYSIS_RENDER_V2"
    assert report["status"] == "BLOCKED"
    assert report["artifacts"] is None
    assert not (tmp_path / ".femagent" / "generated-analyses").exists()


def test_legacy_v1_renderer_remains_available(tmp_path: Path) -> None:
    from fem_core.analysis_spec.opensees_renderer import render_opensees_linear_static_analysis

    model = _model()
    model_validation = validate_engineering_model_spec(model)
    v1 = {
        "schemaVersion": "1.0",
        "kind": "engineering_analysis_spec",
        "modelSpecFingerprint": model_validation["modelSpecFingerprint"],
        "analysisType": "LINEAR_STATIC",
        "units": {"force": model["units"]["force"]},
        "loadCases": [
            {"loadCaseId": "LC1", "nodalLoads": [{"nodeId": 3, "FX": 0.0, "FY": -1.0, "MZ": 0.0}]}
        ],
        "resultRequests": [
            {
                "requestId": "R1",
                "loadCaseId": "LC1",
                "quantity": "DISPLACEMENT",
                "target": {"type": "NODE", "id": 3},
                "component": "Y",
            }
        ],
    }
    report = render_opensees_linear_static_analysis(tmp_path, model, v1)
    assert report["schema"] == "FEMAGENT_OPENSEES_ANALYSIS_RENDER_V1"
    assert report["status"] == "RENDERED"
