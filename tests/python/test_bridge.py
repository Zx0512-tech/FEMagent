from pathlib import Path

from fem_core.bridge import handle_request
from fem_core.protocol import BRIDGE_PROTOCOL


def test_health_bridge_success_envelope(tmp_path: Path) -> None:
    response = handle_request(
        {"protocol": BRIDGE_PROTOCOL, "requestId": "req-1", "command": "health", "payload": {}},
        workspace=tmp_path,
    )
    assert response["ok"] is True
    assert response["requestId"] == "req-1"
    assert response["result"]["core"] == "fem_core"


def test_bridge_rejects_protocol_mismatch(tmp_path: Path) -> None:
    response = handle_request(
        {"protocol": "old", "requestId": "req-2", "command": "health", "payload": {}},
        workspace=tmp_path,
    )
    assert response["ok"] is False
    assert response["error"]["code"] == "PROTOCOL_MISMATCH"
