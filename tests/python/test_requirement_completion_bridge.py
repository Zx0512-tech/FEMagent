from __future__ import annotations

from pathlib import Path

from fem_core.bridge import handle_request
from fem_core.protocol import BRIDGE_PROTOCOL


def _draft() -> dict[str, object]:
    return {
        "schema": "FEMAGENT_ENGINEERING_REQUIREMENT_DRAFT_V1",
        "profile": "FRAME_2D_REQUIREMENT_V1",
        "sources": [
            {
                "sourceId": "source_1",
                "kind": "USER_MESSAGE",
                "text": "建立一个15m简支梁",
            }
        ],
        "templateIntent": {
            "templateId": "SIMPLY_SUPPORTED_BEAM_2D_V1",
            "evidence": {"sourceId": "source_1", "quote": "简支梁"},
        },
        "facts": [
            {
                "kind": "SPAN",
                "source": "USER_EXPLICIT",
                "value": 15,
                "unit": "m",
                "evidence": {"sourceId": "source_1", "quote": "15m"},
            }
        ],
    }


def _request(payload: dict[str, object]) -> dict[str, object]:
    return {
        "protocol": BRIDGE_PROTOCOL,
        "requestId": "req-requirement-complete",
        "command": "requirement.complete",
        "payload": payload,
    }


def test_requirement_completion_crosses_bridge_as_typed_result(tmp_path: Path) -> None:
    response = handle_request(_request({"draft": _draft()}), workspace=tmp_path)

    assert response["ok"] is True
    assert response["result"]["schema"] == "FEMAGENT_ENGINEERING_REQUIREMENT_COMPLETION_V1"
    assert response["result"]["status"] == "INCOMPLETE"
    assert response["result"]["candidateModelSpec"] is None


def test_requirement_completion_bridge_rejects_missing_draft(tmp_path: Path) -> None:
    response = handle_request(_request({}), workspace=tmp_path)

    assert response["ok"] is False
    assert response["error"]["code"] == "INVALID_ARGUMENT"
    assert response["error"]["details"]["field"] == "draft"


def test_requirement_completion_bridge_rejects_non_object_draft(tmp_path: Path) -> None:
    response = handle_request(_request({"draft": "not-an-object"}), workspace=tmp_path)

    assert response["ok"] is False
    assert response["error"]["code"] == "INVALID_ARGUMENT"
    assert response["error"]["details"]["field"] == "draft"
