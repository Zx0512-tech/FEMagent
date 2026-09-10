from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from fem_core.errors import FemCoreError
from fem_core.result_intelligence import inspect_result, query_result


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write_modal_run(workspace: Path) -> str:
    run_id = "run_modal_result_intelligence"
    run_dir = workspace / ".femagent" / "runs" / run_id
    run_dir.mkdir(parents=True)
    modal = {
        "schemaVersion": "1.0",
        "kind": "modal_result_set",
        "modelTimeUnit": "s",
        "results": [
            {
                "requestId": "F1",
                "quantity": "NATURAL_FREQUENCY",
                "mode": 1,
                "value": 2.5,
                "unit": "Hz",
            },
            {
                "requestId": "S1",
                "quantity": "MODE_SHAPE",
                "mode": 1,
                "target": {"type": "NODE", "id": 2},
                "component": "Y",
                "value": 0.75,
                "unit": "1",
                "normalization": "OPENSEES_NATIVE",
            },
        ],
    }
    modal_path = run_dir / "modal_results.json"
    modal_path.write_text(json.dumps(modal, indent=2, sort_keys=True), encoding="utf-8")
    manifest = {
        "schemaVersion": "1.0",
        "kind": "solver_run",
        "runId": run_id,
        "caseFingerprint": "a" * 64,
        "status": "COMPLETED",
        "solver": {"name": "OPENSEESPY", "executionMode": "ISOLATED_WORKER_PROCESS"},
        "model": {"path": "generated/modal.py", "bundleFingerprint": "b" * 64},
        "summary": {"modeCount": 1, "resultCount": 2},
        "outputs": {
            "modalResults": str(modal_path.relative_to(workspace)),
            "modalResultsSha256": _sha(modal_path),
        },
    }
    (run_dir / "run_manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8"
    )
    return run_id


def test_inspect_modal_advertises_only_recorded_requested_capabilities(tmp_path: Path) -> None:
    run_id = _write_modal_run(tmp_path)

    result = inspect_result(tmp_path, run_id)

    assert result["integrity"]["status"] == "VALID"
    quantities = {item["quantity"] for item in result["queryCapabilities"]}
    assert quantities == {"NATURAL_FREQUENCY", "MODE_SHAPE"}
    freq = next(item for item in result["queryCapabilities"] if item["quantity"] == "NATURAL_FREQUENCY")
    assert freq["mode"] == 1
    assert freq["unit"] == "Hz"
    shape = next(item for item in result["queryCapabilities"] if item["quantity"] == "MODE_SHAPE")
    assert shape["mode"] == 1
    assert shape["target"] == {"type": "NODE", "id": 2}
    assert shape["component"] == "Y"
    assert shape["unit"] == "1"
    assert shape["normalization"] == "OPENSEES_NATIVE"


def test_query_modal_value_by_mode_and_mode_shape_identity(tmp_path: Path) -> None:
    run_id = _write_modal_run(tmp_path)

    freq = query_result(
        tmp_path,
        run_id,
        {"quantity": "NATURAL_FREQUENCY", "mode": 1, "operation": "VALUE"},
    )
    assert freq["value"] == pytest.approx(2.5)
    assert freq["unit"] == "Hz"
    assert freq["mode"] == 1

    shape = query_result(
        tmp_path,
        run_id,
        {
            "quantity": "MODE_SHAPE",
            "mode": 1,
            "target": {"type": "NODE", "id": 2},
            "component": "Y",
            "operation": "VALUE",
        },
    )
    assert shape["value"] == pytest.approx(0.75)
    assert shape["unit"] == "1"
    assert shape["normalization"] == "OPENSEES_NATIVE"
    assert shape["target"] == {"type": "NODE", "id": 2}
    assert shape["component"] == "Y"


def test_modal_result_hash_is_verified_before_inspection(tmp_path: Path) -> None:
    run_id = _write_modal_run(tmp_path)
    modal_path = tmp_path / ".femagent" / "runs" / run_id / "modal_results.json"
    modal_path.write_text(modal_path.read_text(encoding="utf-8") + "\n", encoding="utf-8")

    with pytest.raises(FemCoreError) as exc_info:
        inspect_result(tmp_path, run_id)
    assert exc_info.value.code == "RESULT_ARTIFACT_HASH_MISMATCH"
