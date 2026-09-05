from __future__ import annotations

import json
from pathlib import Path

import pytest

from fem_core.errors import FemCoreError
from fem_core.opensees_response_plan import load_opensees_response_plan


def _write_plan(tmp_path: Path, payload: dict) -> Path:
    path = tmp_path / "response-plan.json"
    path.write_text(json.dumps(payload, separators=(",", ":")), encoding="utf-8")
    return path


def _valid_payload() -> dict:
    return {
        "schemaVersion": "1.0",
        "kind": "structural_response_plan",
        "channels": [
            {
                "channelId": "girder_mz_i",
                "quantity": "GENERALIZED_FORCE",
                "target": {"type": "ELEMENT", "id": 41},
                "component": "MZ",
                "location": "END_I",
            }
        ],
    }


def test_loads_strict_structural_response_plan_with_hash_provenance(tmp_path: Path) -> None:
    path = _write_plan(tmp_path, _valid_payload())

    result = load_opensees_response_plan(tmp_path, "response-plan.json")

    assert result["schemaVersion"] == "1.0"
    assert result["kind"] == "structural_response_plan"
    assert result["plan"]["path"] == "response-plan.json"
    assert len(result["plan"]["sha256"]) == 64
    assert result["channels"] == [
        {
            "channelId": "girder_mz_i",
            "quantity": "GENERALIZED_FORCE",
            "target": {"type": "ELEMENT", "id": 41},
            "component": "MZ",
            "location": "END_I",
        }
    ]
    assert result["plan"]["sha256"]
    assert path.is_file()


@pytest.mark.parametrize(
    "mutate",
    [
        lambda payload: payload.update({"schemaVersion": "2.0"}),
        lambda payload: payload.update({"kind": "native_recorders"}),
        lambda payload: payload.update({"recorder": "Element -ele 41 force"}),
        lambda payload: payload["channels"][0].update({"command": "eleResponse"}),
        lambda payload: payload["channels"][0].update({"args": ["localForce"]}),
        lambda payload: payload["channels"][0].update({"operation": "SERIES"}),
    ],
)
def test_rejects_free_form_or_unknown_response_plan_fields(tmp_path: Path, mutate) -> None:
    payload = _valid_payload()
    mutate(payload)
    _write_plan(tmp_path, payload)

    with pytest.raises(FemCoreError) as exc_info:
        load_opensees_response_plan(tmp_path, "response-plan.json")

    assert exc_info.value.code == "INVALID_STRUCTURAL_RESPONSE_PLAN"


def test_rejects_duplicate_channel_ids(tmp_path: Path) -> None:
    payload = _valid_payload()
    payload["channels"].append(dict(payload["channels"][0]))
    _write_plan(tmp_path, payload)

    with pytest.raises(FemCoreError) as exc_info:
        load_opensees_response_plan(tmp_path, "response-plan.json")

    assert exc_info.value.code == "INVALID_STRUCTURAL_RESPONSE_PLAN"


def test_rejects_invalid_channel_identity(tmp_path: Path) -> None:
    payload = _valid_payload()
    payload["channels"][0] = {
        "channelId": "bad",
        "quantity": "GENERALIZED_FORCE",
        "target": {"type": "NODE", "id": 41},
        "component": "MZ",
        "location": "END_I",
    }
    _write_plan(tmp_path, payload)

    with pytest.raises(FemCoreError) as exc_info:
        load_opensees_response_plan(tmp_path, "response-plan.json")

    assert exc_info.value.code == "INVALID_STRUCTURAL_RESPONSE_PLAN"
