from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from fem_core.analysis_spec import migrate_engineering_analysis_spec_v1_to_v2
from fem_core.bridge import handle_request
from fem_core.model_spec.validator import validate_engineering_model_spec
from fem_core.protocol import BRIDGE_PROTOCOL

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
                "requestId": "R1",
                "loadCaseId": "LC1",
                "quantity": "DISPLACEMENT",
                "target": {"type": "NODE", "id": 3},
                "component": "Y",
            }
        ],
    }


def _request(command: str, model_spec: object, analysis_spec: object) -> dict[str, Any]:
    return {
        "protocol": BRIDGE_PROTOCOL,
        "requestId": f"req-{command}",
        "command": command,
        "payload": {"modelSpec": model_spec, "analysisSpec": analysis_spec},
    }


def test_analysis_readiness_ready_and_not_ready_are_domain_results(tmp_path: Path) -> None:
    model = _model_spec()
    analysis = _analysis_spec(model)

    ready = handle_request(_request("analysis.readiness", model, analysis), workspace=tmp_path)
    assert ready["ok"] is True
    assert ready["result"]["status"] == "READY"

    analysis["modelSpecFingerprint"] = "0" * 64
    blocked = handle_request(_request("analysis.readiness", model, analysis), workspace=tmp_path)
    assert blocked["ok"] is True
    assert blocked["result"]["status"] == "NOT_READY"


def test_analysis_render_rendered_and_blocked_are_domain_results(tmp_path: Path) -> None:
    model = _model_spec()
    analysis = _analysis_spec(model)

    rendered = handle_request(
        _request("analysis.renderOpenSees", model, analysis),
        workspace=tmp_path,
    )
    assert rendered["ok"] is True
    assert rendered["result"]["status"] == "RENDERED"
    assert rendered["result"]["artifacts"]["analysisPath"].startswith(
        ".femagent/generated-analyses/"
    )

    analysis["modelSpecFingerprint"] = "0" * 64
    blocked = handle_request(
        _request("analysis.renderOpenSees", model, analysis),
        workspace=tmp_path,
    )
    assert blocked["ok"] is True
    assert blocked["result"]["status"] == "BLOCKED"


def test_valid_v2_render_is_blocked_without_generated_analysis_artifacts(tmp_path: Path) -> None:
    model = _model_spec()
    migration = migrate_engineering_analysis_spec_v1_to_v2(_analysis_spec(model))
    v2 = migration["candidateSpec"]
    assert isinstance(v2, dict)

    response = handle_request(
        _request("analysis.renderOpenSees", model, v2),
        workspace=tmp_path,
    )

    assert response["ok"] is True
    result = response["result"]
    assert result["status"] == "BLOCKED"
    assert result["artifacts"] is None
    assert result["readiness"]["status"] == "NOT_READY"
    assert "ANALYSIS_READINESS_UNSUPPORTED_ANALYSIS_SPEC_VERSION" in {
        issue["code"] for issue in result["readiness"]["issues"]
    }
    assert not (tmp_path / ".femagent" / "generated-analyses").exists()


def test_analysis_commands_require_object_specs(tmp_path: Path) -> None:
    model = _model_spec()
    analysis = _analysis_spec(model)

    bad_model = handle_request(
        _request("analysis.readiness", "not-an-object", analysis),
        workspace=tmp_path,
    )
    assert bad_model["ok"] is False
    assert bad_model["error"]["code"] == "INVALID_ARGUMENT"

    bad_analysis = handle_request(
        _request("analysis.renderOpenSees", model, "not-an-object"),
        workspace=tmp_path,
    )
    assert bad_analysis["ok"] is False
    assert bad_analysis["error"]["code"] == "INVALID_ARGUMENT"
