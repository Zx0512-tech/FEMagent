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
        "requestId": "req-model-readiness",
        "command": "modelSpec.readiness",
        "payload": {"spec": spec},
    }


def test_bridge_returns_typed_model_readiness_result(tmp_path: Path) -> None:
    response = handle_request(_request(_load_spec()), workspace=tmp_path)

    assert response["ok"] is True
    assert response["result"]["schema"] == "FEMAGENT_MODEL_SPEC_READINESS_V1"
    assert response["result"]["status"] == "READY"
    assert response["result"]["checks"]["rigidBodyRestraint"]["components"][0][
        "constraintRank"
    ] == 3


def test_bridge_returns_invalid_spec_as_normal_readiness_result(tmp_path: Path) -> None:
    spec = _load_spec()
    del spec["units"]

    response = handle_request(_request(spec), workspace=tmp_path)

    assert response["ok"] is True
    assert response["result"]["status"] == "INVALID_SPEC"
    assert response["result"]["checks"]["connectivity"]["status"] == "SKIPPED"


def test_bridge_returns_not_ready_as_normal_result(tmp_path: Path) -> None:
    spec = _load_spec()
    spec["constraints"] = []

    response = handle_request(_request(spec), workspace=tmp_path)

    assert response["ok"] is True
    assert response["result"]["status"] == "NOT_READY"


def test_bridge_rejects_non_object_readiness_spec_payload(tmp_path: Path) -> None:
    response = handle_request(_request("not-an-object"), workspace=tmp_path)

    assert response["ok"] is False
    assert response["error"]["code"] == "INVALID_ARGUMENT"
