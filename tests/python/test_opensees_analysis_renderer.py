from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path
from typing import Any

import pytest

from fem_core.analysis_spec.opensees_renderer import render_opensees_linear_static_analysis
from fem_core.errors import FemCoreError
from fem_core.model_spec.validator import validate_engineering_model_spec

FIXTURE = Path("tests/fixtures/model_spec/simple-portal-frame.json")


def _model_spec() -> dict[str, Any]:
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


def _analysis_spec(model: dict[str, Any]) -> dict[str, Any]:
    validation = validate_engineering_model_spec(model)
    assert validation["status"] == "VALID"
    return {
        "schemaVersion": "1.0",
        "kind": "engineering_analysis_spec",
        "modelSpecFingerprint": validation["modelSpecFingerprint"],
        "analysisType": "LINEAR_STATIC",
        "units": {"force": model["units"]["force"]},
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


def _artifact(workspace: Path, report: dict[str, Any], key: str) -> Path:
    return workspace / Path(report["artifacts"][key])


def test_ready_pair_renders_standalone_four_file_bundle(tmp_path: Path) -> None:
    model = _model_spec()
    analysis = _analysis_spec(model)

    report = render_opensees_linear_static_analysis(tmp_path, model, analysis)

    assert report["schema"] == "FEMAGENT_OPENSEES_ANALYSIS_RENDER_V1"
    assert report["status"] == "RENDERED"
    assert report["renderer"] == {
        "name": "OPENSEES_FRAME_2D_LINEAR_STATIC_V1",
        "version": "1.0",
    }
    assert report["analysisRenderId"].startswith("analysis_render_")
    assert len(report["analysisRenderFingerprint"]) == 64
    for key in (
        "analysisPath",
        "responsePlanPath",
        "readinessPath",
        "manifestPath",
    ):
        assert _artifact(tmp_path, report, key).is_file()

    source = _artifact(tmp_path, report, "analysisPath").read_text(encoding="utf-8")
    assert 'ops.timeSeries("Linear", 1)' in source
    assert 'ops.pattern("Plain", 1, 1)' in source
    assert 'ops.load(3, 0.0, -10000.0, 0.0)' in source
    assert 'ops.constraints("Plain")' in source
    assert 'ops.numberer("Plain")' in source
    assert 'ops.system("BandGeneral")' in source
    assert 'ops.algorithm("Linear")' in source
    assert 'ops.integrator("LoadControl", 1.0)' in source
    assert 'ops.analysis("Static")' in source
    assert source.count("ops.analyze(") == 1
    assert "nodeDisp" not in source
    assert "nodeReaction" not in source
    assert "eleResponse" not in source
    assert "subprocess" not in source


def test_response_plan_contains_identity_only_sorted_by_request_id(tmp_path: Path) -> None:
    model = _model_spec()
    analysis = _analysis_spec(model)
    analysis["resultRequests"] = list(reversed(analysis["resultRequests"]))

    report = render_opensees_linear_static_analysis(tmp_path, model, analysis)
    plan = json.loads(_artifact(tmp_path, report, "responsePlanPath").read_text(encoding="utf-8"))

    assert plan["schemaVersion"] == "1.0"
    assert plan["kind"] == "structural_response_plan"
    assert [channel["channelId"] for channel in plan["channels"]] == sorted(
        channel["channelId"] for channel in plan["channels"]
    )
    forbidden = {"unit", "access", "dof", "index", "response", "vectorLength"}
    for channel in plan["channels"]:
        assert not forbidden.intersection(channel)


def test_manifest_embeds_normalized_specs_and_trusted_identity(tmp_path: Path) -> None:
    model = _model_spec()
    analysis = _analysis_spec(model)

    report = render_opensees_linear_static_analysis(tmp_path, model, analysis)
    manifest = json.loads(_artifact(tmp_path, report, "manifestPath").read_text(encoding="utf-8"))

    assert manifest == report
    assert manifest["input"]["normalizedModelSpec"]["kind"] == "engineering_model_spec"
    assert manifest["input"]["normalizedAnalysisSpec"]["kind"] == "engineering_analysis_spec"
    assert manifest["input"]["modelSpecFingerprint"] == analysis["modelSpecFingerprint"]
    assert len(manifest["input"]["analysisSpecFingerprint"]) == 64
    assert manifest["input"]["readinessProfile"] == "OPENSEES_FRAME_2D_LINEAR_STATIC_V1"
    assert manifest["loadCaseId"] == "LC1"
    assert manifest["responseMappings"]
    assert len(manifest["artifacts"]["analysisSha256"]) == 64
    assert len(manifest["artifacts"]["responsePlanSha256"]) == 64
    assert len(manifest["artifacts"]["readinessSha256"]) == 64


def test_not_ready_pair_is_blocked_without_partial_bundle(tmp_path: Path) -> None:
    model = _model_spec()
    analysis = _analysis_spec(model)
    analysis["modelSpecFingerprint"] = "0" * 64

    report = render_opensees_linear_static_analysis(tmp_path, model, analysis)

    assert report["status"] == "BLOCKED"
    assert report["reason"] == "ANALYSIS_NOT_READY"
    assert report["readiness"]["status"] == "NOT_READY"
    assert report["analysisRenderId"] is None
    assert report["artifacts"] is None
    assert report["analysisRenderFingerprint"] is None
    assert not (tmp_path / ".femagent" / "generated-analyses").exists()


def test_semantic_reordering_preserves_rendered_content_identity(tmp_path: Path) -> None:
    model = _model_spec()
    analysis = _analysis_spec(model)
    reordered_model = deepcopy(model)
    for key in ("nodes", "materials", "sections", "elements", "constraints", "nodalMasses"):
        reordered_model[key] = list(reversed(reordered_model[key]))
    reordered_analysis = deepcopy(analysis)
    reordered_analysis["resultRequests"] = list(reversed(reordered_analysis["resultRequests"]))

    first = render_opensees_linear_static_analysis(tmp_path, model, analysis)
    second = render_opensees_linear_static_analysis(tmp_path, reordered_model, reordered_analysis)

    assert first["analysisRenderId"] != second["analysisRenderId"]
    assert first["analysisRenderFingerprint"] == second["analysisRenderFingerprint"]
    for hash_key in ("analysisSha256", "responsePlanSha256", "readinessSha256"):
        assert first["artifacts"][hash_key] == second["artifacts"][hash_key]


def test_failed_publication_removes_fresh_analysis_directory(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from fem_core.analysis_spec import opensees_renderer as renderer_module

    model = _model_spec()
    analysis = _analysis_spec(model)
    original = renderer_module._write_text
    writes = 0

    def fail_second_write(path: Path, content: str) -> None:
        nonlocal writes
        writes += 1
        if writes == 2:
            raise OSError("synthetic response-plan write failure")
        original(path, content)

    monkeypatch.setattr(renderer_module, "_write_text", fail_second_write)

    with pytest.raises(FemCoreError) as raised:
        render_opensees_linear_static_analysis(tmp_path, model, analysis)

    assert raised.value.code == "OPENSEES_ANALYSIS_RENDER_WRITE_FAILED"
    root = tmp_path / ".femagent" / "generated-analyses"
    assert root.is_dir()
    assert list(root.iterdir()) == []
