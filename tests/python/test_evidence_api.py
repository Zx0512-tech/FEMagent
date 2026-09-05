from __future__ import annotations

import csv
import json
from hashlib import sha256
from pathlib import Path

import pytest

from fem_core.errors import FemCoreError
from fem_core.evidence.api import project_run_evidence


def _sha(path: Path) -> str:
    return sha256(path.read_bytes()).hexdigest()


def _write_open_sees_run(tmp_path: Path, *, run_id: str = "run_evidenceapi001") -> Path:
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
                "absolutePeakDisplacementM": 0.03,
            }
        ),
        encoding="utf-8",
    )
    solver_log = run_dir / "solver.log"
    solver_log.write_text("evidence api test\n", encoding="utf-8")
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
    (run_dir / "run_manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    return run_dir


def test_project_run_evidence_promotes_only_hash_verified_result_query(tmp_path: Path) -> None:
    run_dir = _write_open_sees_run(tmp_path)

    report = project_run_evidence(
        tmp_path,
        project_id="bridge-demo",
        run_ref=run_dir.name,
        evidence_id="EVID-RUN-001",
        query={
            "quantity": "DISPLACEMENT",
            "target": {"type": "NODE", "id": 2},
            "component": "UX",
            "operation": "SUMMARY",
        },
    )

    assert report["projectId"] == "bridge-demo"
    assert report["solverRuns"] == [
        {
            "runId": run_dir.name,
            "solver": "OPENSEESPY",
            "caseFingerprint": "a" * 64,
        }
    ]
    assert report["limitations"] == []
    assert len(report["verifiedEvidence"]) == 1
    evidence = report["verifiedEvidence"][0]
    assert evidence["evidenceId"] == "EVID-RUN-001"
    assert evidence["status"] == "VERIFIED"
    assert evidence["artifacts"][0]["artifact"].endswith("response.csv")
    assert len(evidence["artifacts"][0]["sha256"]) == 64
    assert evidence["artifacts"][0]["entity"] == {
        "type": "NODE",
        "id": 2,
        "component": "X",
    }
    assert evidence["metric"]["quantity"] == "DISPLACEMENT"
    assert evidence["metric"]["summary"]["absolutePeak"] == 0.03
    assert evidence["provenance"] == {
        "runId": run_dir.name,
        "caseFingerprint": "a" * 64,
        "solver": "OPENSEESPY",
    }


def test_project_run_evidence_rejects_tampered_result_artifact(tmp_path: Path) -> None:
    run_dir = _write_open_sees_run(tmp_path)
    response = run_dir / "response.csv"
    response.write_text(response.read_text(encoding="utf-8") + "0.4,9,9,9\n", encoding="utf-8")

    with pytest.raises(FemCoreError) as exc_info:
        project_run_evidence(
            tmp_path,
            project_id="bridge-demo",
            run_ref=run_dir.name,
            evidence_id="EVID-RUN-002",
            query={
                "quantity": "DISPLACEMENT",
                "target": {"type": "NODE", "id": 2},
                "component": "X",
                "operation": "SUMMARY",
            },
        )

    assert exc_info.value.code == "RESULT_ARTIFACT_HASH_MISMATCH"
