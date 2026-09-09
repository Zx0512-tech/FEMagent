from __future__ import annotations

import json
from pathlib import Path

from fem_core.bridge import handle_request
from fem_core.protocol import BRIDGE_PROTOCOL

FIXTURE = Path("tests/fixtures/analysis_spec/simple-linear-static.json")


def load_spec() -> dict:
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


def request(spec: object) -> dict:
    return {
        "protocol": BRIDGE_PROTOCOL,
        "requestId": "req-analysis-spec",
        "command": "analysisSpec.validate",
        "payload": {"spec": spec},
    }


def migration_request(spec: object) -> dict:
    return {
        "protocol": BRIDGE_PROTOCOL,
        "requestId": "req-analysis-spec-migration",
        "command": "analysisSpec.migrateV1ToV2",
        "payload": {"spec": spec},
    }


def test_bridge_validates_analysis_spec_without_solver_execution(tmp_path: Path) -> None:
    response = handle_request(request(load_spec()), workspace=tmp_path)

    assert response["ok"] is True
    assert response["result"]["schema"] == "FEMAGENT_ANALYSIS_SPEC_VALIDATION_V1"
    assert response["result"]["status"] == "VALID"
    assert response["result"]["analysisSpecFingerprint"] is not None


def test_invalid_analysis_content_is_normal_bridge_result(tmp_path: Path) -> None:
    spec = load_spec()
    spec["analysisType"] = "MODAL"

    response = handle_request(request(spec), workspace=tmp_path)

    assert response["ok"] is True
    assert response["result"]["status"] == "INVALID"
    assert "ANALYSIS_SPEC_UNSUPPORTED_ANALYSIS_TYPE" in {
        issue["code"] for issue in response["result"]["issues"]
    }


def test_bridge_rejects_non_object_analysis_spec_payload(tmp_path: Path) -> None:
    response = handle_request(request("not-an-object"), workspace=tmp_path)

    assert response["ok"] is False
    assert response["error"]["code"] == "INVALID_ARGUMENT"


def test_bridge_migrates_v1_to_v2_without_workspace_writes(tmp_path: Path) -> None:
    response = handle_request(migration_request(load_spec()), workspace=tmp_path)

    assert response["ok"] is True
    assert response["result"]["schema"] == "FEMAGENT_ANALYSIS_SPEC_MIGRATION_V1_TO_V2"
    assert response["result"]["status"] == "MIGRATED"
    assert response["result"]["candidateSpec"]["schemaVersion"] == "2.0"
    assert list(tmp_path.iterdir()) == []


def test_bridge_rejects_non_object_migration_spec_payload(tmp_path: Path) -> None:
    response = handle_request(migration_request("not-an-object"), workspace=tmp_path)

    assert response["ok"] is False
    assert response["error"]["code"] == "INVALID_ARGUMENT"
    assert list(tmp_path.iterdir()) == []
