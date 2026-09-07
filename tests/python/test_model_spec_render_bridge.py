from __future__ import annotations

import json
from pathlib import Path

from fem_core.bridge import handle_request
from fem_core.protocol import BRIDGE_PROTOCOL

FIXTURE = Path("tests/fixtures/model_spec/simple-portal-frame.json")


def _load_spec() -> dict:
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


def _request(spec: object) -> dict:
    return {
        "protocol": BRIDGE_PROTOCOL,
        "requestId": "req-model-render-opensees",
        "command": "modelSpec.renderOpenSees",
        "payload": {"spec": spec},
    }


def test_bridge_renders_ready_model_spec_into_controlled_workspace_artifact(tmp_path: Path) -> None:
    response = handle_request(_request(_load_spec()), workspace=tmp_path)

    assert response["ok"] is True
    result = response["result"]
    assert result["schema"] == "FEMAGENT_OPENSEES_RENDER_V1"
    assert result["status"] == "RENDERED"
    model_path = result["artifacts"]["modelPath"]
    manifest_path = result["artifacts"]["manifestPath"]
    assert model_path.startswith(".femagent/generated-models/render_")
    assert manifest_path.startswith(".femagent/generated-models/render_")
    assert (tmp_path / model_path).is_file()
    assert (tmp_path / manifest_path).is_file()


def test_bridge_returns_not_ready_as_normal_blocked_render_result(tmp_path: Path) -> None:
    spec = _load_spec()
    spec["constraints"] = []

    response = handle_request(_request(spec), workspace=tmp_path)

    assert response["ok"] is True
    assert response["result"]["status"] == "BLOCKED"
    assert response["result"]["reason"] == "MODEL_NOT_READY"
    assert response["result"]["readiness"]["status"] == "NOT_READY"
    assert response["result"]["artifacts"] is None


def test_bridge_returns_invalid_spec_as_normal_blocked_render_result(tmp_path: Path) -> None:
    spec = _load_spec()
    del spec["units"]

    response = handle_request(_request(spec), workspace=tmp_path)

    assert response["ok"] is True
    assert response["result"]["status"] == "BLOCKED"
    assert response["result"]["readiness"]["status"] == "INVALID_SPEC"
    assert response["result"]["artifacts"] is None


def test_bridge_rejects_non_object_render_spec_payload(tmp_path: Path) -> None:
    response = handle_request(_request("not-an-object"), workspace=tmp_path)

    assert response["ok"] is False
    assert response["error"]["code"] == "INVALID_ARGUMENT"
