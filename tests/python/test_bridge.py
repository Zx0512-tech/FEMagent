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


def test_solver_preflight_transports_solver_options(tmp_path: Path, monkeypatch) -> None:
    captured: dict = {}

    class StubAdapter:
        def preflight(
            self,
            workspace: Path,
            *,
            model_path: str,
            load_path: str | None = None,
            solver_options: dict | None = None,
        ) -> dict:
            captured["workspace"] = workspace
            captured["modelPath"] = model_path
            captured["loadPath"] = load_path
            captured["solverOptions"] = solver_options
            return {"kind": "stub_preflight", "solverOptions": solver_options}

    monkeypatch.setattr("fem_core.bridge.get_solver_adapter", lambda _solver: StubAdapter())
    response = handle_request(
        {
            "protocol": BRIDGE_PROTOCOL,
            "requestId": "req-solver-options",
            "command": "solver.preflight",
            "payload": {
                "solver": "ansys",
                "modelPath": "model.inp",
                "loadPath": "earthquake.csv",
                "solverOptions": {"modelUnits": {"length": "mm", "time": "s"}},
            },
        },
        workspace=tmp_path,
    )

    assert response["ok"] is True
    assert captured["modelPath"] == "model.inp"
    assert captured["loadPath"] == "earthquake.csv"
    assert captured["solverOptions"] == {"modelUnits": {"length": "mm", "time": "s"}}


def test_solver_options_must_be_object(tmp_path: Path) -> None:
    response = handle_request(
        {
            "protocol": BRIDGE_PROTOCOL,
            "requestId": "req-invalid-solver-options",
            "command": "solver.preflight",
            "payload": {
                "solver": "ansys",
                "modelPath": "model.inp",
                "solverOptions": "mm-s",
            },
        },
        workspace=tmp_path,
    )

    assert response["ok"] is False
    assert response["error"]["code"] == "INVALID_ARGUMENT"
