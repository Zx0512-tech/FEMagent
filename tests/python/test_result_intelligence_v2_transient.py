from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from fem_core.result_intelligence import inspect_result, query_result


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write_transient_run(workspace: Path) -> str:
    run_id = "run_v2_transient_result_intelligence"
    run_dir = workspace / ".femagent" / "runs" / run_id
    run_dir.mkdir(parents=True)
    response = {
        "schemaVersion": "1.0",
        "kind": "structural_response_series",
        "channels": [
            {
                "channelId": "U3X",
                "quantity": "DISPLACEMENT",
                "target": {"type": "NODE", "id": 3},
                "component": "X",
                "unit": "mm",
                "referenceFrame": "RELATIVE",
                "abscissaSemantic": "TIME",
                "abscissaUnit": "ms",
                "abscissaValues": [10.0, 20.0, 30.0],
                "values": [0.1, 0.2, 0.15],
            },
            {
                "channelId": "V3X",
                "quantity": "VELOCITY",
                "target": {"type": "NODE", "id": 3},
                "component": "X",
                "unit": "mm/ms",
                "referenceFrame": "RELATIVE",
                "abscissaSemantic": "TIME",
                "abscissaUnit": "ms",
                "abscissaValues": [10.0, 20.0, 30.0],
                "values": [0.01, 0.02, 0.0],
            },
            {
                "channelId": "AR3X",
                "quantity": "RELATIVE_ACCELERATION",
                "target": {"type": "NODE", "id": 3},
                "component": "X",
                "unit": "mm/ms2",
                "referenceFrame": "RELATIVE",
                "abscissaSemantic": "TIME",
                "abscissaUnit": "ms",
                "abscissaValues": [10.0, 20.0, 30.0],
                "values": [0.001, -0.002, 0.001],
            },
        ],
    }
    response_path = run_dir / "structural_response.json"
    response_path.write_text(json.dumps(response, indent=2, sort_keys=True), encoding="utf-8")
    manifest = {
        "schemaVersion": "1.0",
        "kind": "solver_run",
        "runId": run_id,
        "caseFingerprint": "c" * 64,
        "status": "COMPLETED",
        "solver": {"name": "OPENSEESPY", "executionMode": "ISOLATED_WORKER_PROCESS"},
        "model": {"path": "generated/transient.py", "bundleFingerprint": "d" * 64},
        "summary": {"analysisTime": 30.0},
        "outputs": {
            "structuralResponse": str(response_path.relative_to(workspace)),
            "structuralResponseSha256": _sha(response_path),
        },
    }
    (run_dir / "run_manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8"
    )
    return run_id


def test_v2_transient_inspection_preserves_time_unit_and_relative_reference_frame(tmp_path: Path) -> None:
    run_id = _write_transient_run(tmp_path)

    result = inspect_result(tmp_path, run_id)

    assert result["integrity"]["status"] == "VALID"
    assert result["abscissa"] == {
        "semantic": "TIME",
        "unit": "ms",
        "sampleCount": 3,
        "start": 10.0,
        "end": 30.0,
    }
    capabilities = result["queryCapabilities"]
    assert {item["quantity"] for item in capabilities} == {
        "DISPLACEMENT",
        "VELOCITY",
        "RELATIVE_ACCELERATION",
    }
    assert all(item["referenceFrame"] == "RELATIVE" for item in capabilities)
    assert "ABSOLUTE_ACCELERATION" not in {item["quantity"] for item in capabilities}


def test_v2_transient_series_and_summary_keep_model_time_and_response_units(tmp_path: Path) -> None:
    run_id = _write_transient_run(tmp_path)

    series = query_result(
        tmp_path,
        run_id,
        {
            "quantity": "DISPLACEMENT",
            "target": {"type": "NODE", "id": 3},
            "component": "X",
            "operation": "SERIES",
        },
    )
    assert series["unit"] == "mm"
    assert series["referenceFrame"] == "RELATIVE"
    assert series["abscissa"] == {"semantic": "TIME", "unit": "ms"}
    assert [item["abscissa"] for item in series["series"]] == pytest.approx([10.0, 20.0, 30.0])

    summary = query_result(
        tmp_path,
        run_id,
        {
            "quantity": "RELATIVE_ACCELERATION",
            "target": {"type": "NODE", "id": 3},
            "component": "X",
            "operation": "SUMMARY",
        },
    )
    assert summary["unit"] == "mm/ms2"
    assert summary["referenceFrame"] == "RELATIVE"
    assert summary["abscissa"] == {"semantic": "TIME", "unit": "ms"}
    assert summary["summary"]["sampleCount"] == 3
