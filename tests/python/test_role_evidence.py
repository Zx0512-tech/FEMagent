from __future__ import annotations

import csv
import json
from hashlib import sha256
from pathlib import Path

import pytest

from fem_core.errors import FemCoreError
from fem_core.model_inspection import inspect_model
from fem_core.semantic_roles.evidence import project_role_evidence


def _sha(path: Path) -> str:
    return sha256(path.read_bytes()).hexdigest()


def _write_model_and_manifest(tmp_path: Path) -> str:
    model = tmp_path / "model.py"
    model.write_text(
        "import openseespy.opensees as ops\n"
        "ops.model('basic', '-ndm', 1, '-ndf', 1)\n"
        "ops.node(1, 0.0)\n"
        "ops.node(2, 1.0)\n"
        "ops.uniaxialMaterial('Elastic', 1, 100.0)\n"
        "ops.element('truss', 1, 1, 2, 1.0, 1)\n",
        encoding="utf-8",
    )
    fingerprint = inspect_model(tmp_path, "model.py")["bundle"]["bundleFingerprint"]
    (tmp_path / "semantic-roles.json").write_text(
        json.dumps(
            {
                "schemaVersion": "1.0",
                "kind": "engineering_semantic_roles",
                "model": {"bundleFingerprint": fingerprint},
                "roles": [
                    {
                        "roleId": "TOWER_BASE_LEFT",
                        "roleType": "TOWER_BASE",
                        "entity": {"type": "NODE", "id": 2},
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    return fingerprint


def _write_run(tmp_path: Path, *, bundle_fingerprint: str, run_id: str = "run_roleevidence01") -> str:
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
            ]
        )
    summary = run_dir / "result_summary.json"
    summary.write_text(
        json.dumps(
            {
                "responseNode": 2,
                "responseDof": 1,
                "sampleCount": 3,
                "absolutePeakDisplacementM": 0.03,
            }
        ),
        encoding="utf-8",
    )
    solver_log = run_dir / "solver.log"
    solver_log.write_text("role evidence test\n", encoding="utf-8")
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
        "model": {
            "path": "model.py",
            "sha256": "b" * 64,
            "bundleFingerprint": bundle_fingerprint,
        },
        "load": {"mode": "MODEL_SCRIPT_MANAGED"},
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
    return run_id


def test_role_based_evidence_resolves_node_and_preserves_semantic_provenance(tmp_path: Path) -> None:
    fingerprint = _write_model_and_manifest(tmp_path)
    run_id = _write_run(tmp_path, bundle_fingerprint=fingerprint)

    report = project_role_evidence(
        tmp_path,
        project_id="bridge-demo",
        model_path="model.py",
        manifest_path="semantic-roles.json",
        role_id="TOWER_BASE_LEFT",
        run_ref=run_id,
        evidence_id="EVID-ROLE-001",
        quantity="DISPLACEMENT",
        component="X",
        operation="SUMMARY",
    )

    assert report["limitations"] == []
    assert len(report["verifiedEvidence"]) == 1
    evidence = report["verifiedEvidence"][0]
    assert evidence["status"] == "VERIFIED"
    assert evidence["metric"]["target"] == {"type": "NODE", "id": 2}
    assert evidence["metric"]["summary"]["absolutePeak"] == 0.03
    semantic = evidence["provenance"]["semanticRole"]
    assert semantic["roleId"] == "TOWER_BASE_LEFT"
    assert semantic["roleType"] == "TOWER_BASE"
    assert semantic["entity"] == {"type": "NODE", "id": 2}
    assert semantic["entityValidation"] == "STATICALLY_CONFIRMED"
    assert semantic["modelBundleFingerprint"] == fingerprint
    assert len(semantic["manifestSha256"]) == 64


def test_role_based_evidence_rejects_run_from_different_model_bundle(tmp_path: Path) -> None:
    _write_model_and_manifest(tmp_path)
    run_id = _write_run(tmp_path, bundle_fingerprint="f" * 64)

    with pytest.raises(FemCoreError) as exc_info:
        project_role_evidence(
            tmp_path,
            project_id="bridge-demo",
            model_path="model.py",
            manifest_path="semantic-roles.json",
            role_id="TOWER_BASE_LEFT",
            run_ref=run_id,
            evidence_id="EVID-ROLE-002",
            quantity="DISPLACEMENT",
            component="X",
            operation="SUMMARY",
        )

    assert exc_info.value.code == "SEMANTIC_ROLE_RUN_MODEL_MISMATCH"
