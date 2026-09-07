from __future__ import annotations

import json
from pathlib import Path

from fem_core.bridge import handle_request
from fem_core.protocol import BRIDGE_PROTOCOL

FIXTURE = Path("tests/fixtures/model_spec/simple-portal-frame.json")


def load_spec() -> dict:
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


def request(spec: object) -> dict:
    return {
        "protocol": BRIDGE_PROTOCOL,
        "requestId": "req-model-spec",
        "command": "modelSpec.validate",
        "payload": {"spec": spec},
    }


def test_bridge_validates_model_spec_without_solver_execution(tmp_path: Path) -> None:
    response = handle_request(request(load_spec()), workspace=tmp_path)

    assert response["ok"] is True
    assert response["result"]["status"] == "VALID"
    assert response["result"]["modelSpecFingerprint"] is not None


def test_bridge_returns_invalid_model_content_as_normal_result(tmp_path: Path) -> None:
    spec = load_spec()
    spec["elements"][0]["nodeJ"] = 99

    response = handle_request(request(spec), workspace=tmp_path)

    assert response["ok"] is True
    assert response["result"]["status"] == "INVALID"
    assert "MODEL_SPEC_ELEMENT_NODE_NOT_FOUND" in {
        issue["code"] for issue in response["result"]["issues"]
    }


def test_bridge_rejects_non_object_model_spec_payload(tmp_path: Path) -> None:
    response = handle_request(request("not-an-object"), workspace=tmp_path)

    assert response["ok"] is False
    assert response["error"]["code"] == "INVALID_ARGUMENT"
