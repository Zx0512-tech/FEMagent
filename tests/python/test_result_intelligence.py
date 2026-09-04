from __future__ import annotations

import csv
import json
from hashlib import sha256
from pathlib import Path

import pytest

from fem_core.errors import FemCoreError
from fem_core.result_intelligence import inspect_result


def _sha(path: Path) -> str:
    return sha256(path.read_bytes()).hexdigest()


def _write_open_sees_run(tmp_path: Path, *, run_id: str = "run_resulttest0001") -> Path:
    run_dir = tmp_path / ".femagent" / "runs" / run_id
    run_dir.mkdir(parents=True)
    response = run_dir / "response.csv"
    with response.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.writer(stream, lineterminator="\n")
        writer.writerow(
            [
                "time_s",
                "relative_displacement_m",
                "relative_velocity_m_s",
                "relative_acceleration_m_s2",
            ]
        )
        writer.writerows(
            [
                ["0", "0", "0", "0"],
                ["0.1", "0.02", "0.2", "1.0"],
                ["0.2", "-0.03", "-0.1", "-0.5"],
                ["0.3", "0.01", "0.0", "0.25"],
            ]
        )
    summary = run_dir / "result_summary.json"
    summary.write_text(
        json.dumps(
            {
                "responseNode": 2,
                "responseDof": 1,
                "sampleCount": 4,
                "minDisplacementM": -0.03,
                "maxDisplacementM": 0.02,
                "absolutePeakDisplacementM": 0.03,
                "timeAtAbsolutePeakS": 0.2,
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    solver_log = run_dir / "solver.log"
    solver_log.write_text("synthetic test log\n", encoding="utf-8")
    manifest = {
        "schemaVersion": "1.0",
        "kind": "solver_run",
        "runId": run_id,
        "caseFingerprint": "a" * 64,
        "status": "COMPLETED",
        "solver": {
            "name": "OPENSEESPY",
            "packageVersion": "3.8.0.0",
            "engineVersion": "3.8.0",
            "executionMode": "ISOLATED_WORKER_PROCESS",
        },
        "model": {"path": "model.json", "sha256": "b" * 64},
        "load": {"path": "load.csv", "sha256": "c" * 64},
        "analysis": {"type": "TRANSIENT_UNIFORM_EXCITATION"},
        "summary": json.loads(summary.read_text(encoding="utf-8")),
        "outputs": {
            "runManifest": f".femagent/runs/{run_id}/run_manifest.json",
            "responseCsv": f".femagent/runs/{run_id}/response.csv",
            "responseSha256": _sha(response),
            "resultSummary": f".femagent/runs/{run_id}/result_summary.json",
            "resultSummarySha256": _sha(summary),
            "solverLog": f".femagent/runs/{run_id}/solver.log",
            "solverLogSha256": _sha(solver_log),
        },
    }
    manifest_path = run_dir / "run_manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return run_dir


def test_inspect_result_resolves_run_id_directory_and_manifest_path(tmp_path: Path) -> None:
    run_dir = _write_open_sees_run(tmp_path)

    by_id = inspect_result(tmp_path, run_dir.name)
    by_dir = inspect_result(tmp_path, str(run_dir.relative_to(tmp_path)))
    by_manifest = inspect_result(tmp_path, str((run_dir / "run_manifest.json").relative_to(tmp_path)))

    assert by_id["runId"] == run_dir.name
    assert by_dir["runId"] == run_dir.name
    assert by_manifest["runId"] == run_dir.name
    assert by_id["integrity"]["status"] == "VALID"


def test_inspect_open_sees_controlled_response_exposes_three_nodal_quantities(tmp_path: Path) -> None:
    run_dir = _write_open_sees_run(tmp_path)

    report = inspect_result(tmp_path, run_dir.name)

    assert report["schemaVersion"] == "1.0"
    assert report["kind"] == "result_manifest"
    assert report["solver"]["name"] == "OPENSEESPY"
    assert report["abscissa"] == {
        "semantic": "TIME",
        "unit": "s",
        "sampleCount": 4,
        "start": 0.0,
        "end": 0.3,
    }
    capabilities = {(item["quantity"], item["component"]) for item in report["queryCapabilities"]}
    assert capabilities == {
        ("DISPLACEMENT", "X"),
        ("VELOCITY", "X"),
        ("ACCELERATION", "X"),
    }
    assert all(item["target"] == {"type": "NODE", "id": 2} for item in report["queryCapabilities"])


def test_inspect_result_rejects_declared_hash_mismatch(tmp_path: Path) -> None:
    run_dir = _write_open_sees_run(tmp_path)
    response = run_dir / "response.csv"
    response.write_text(response.read_text(encoding="utf-8") + "0.4,9,9,9\n", encoding="utf-8")

    with pytest.raises(FemCoreError) as exc_info:
        inspect_result(tmp_path, run_dir.name)

    assert exc_info.value.code == "RESULT_ARTIFACT_HASH_MISMATCH"


def test_inspect_result_rejects_path_escape_and_malformed_manifest(tmp_path: Path) -> None:
    with pytest.raises(FemCoreError) as escaped:
        inspect_result(tmp_path, "../outside/run_manifest.json")
    assert escaped.value.code == "PATH_OUTSIDE_WORKSPACE"

    run_dir = tmp_path / ".femagent" / "runs" / "run_badmanifest"
    run_dir.mkdir(parents=True)
    (run_dir / "run_manifest.json").write_text('{"kind":"not-a-run"}', encoding="utf-8")

    with pytest.raises(FemCoreError) as malformed:
        inspect_result(tmp_path, "run_badmanifest")
    assert malformed.value.code == "INVALID_RUN_MANIFEST"
