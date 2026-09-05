from __future__ import annotations

import csv
import json
from hashlib import sha256
from pathlib import Path

import pytest

from fem_core.cross_solver.api import validate_cross_solver
from fem_core.errors import FemCoreError
from fem_core.model_inspection import inspect_model


def _sha(path: Path) -> str:
    return sha256(path.read_bytes()).hexdigest()


def _write_side(
    workspace: Path,
    *,
    prefix: str,
    response_node: int,
    peak: float,
    stale_manifest: bool = False,
    wrong_run_fingerprint: bool = False,
    tamper_response: bool = False,
) -> dict[str, str]:
    model_name = f"{prefix}_model.py"
    model = workspace / model_name
    model.write_text(
        "import openseespy.opensees as ops\n"
        "ops.model('basic', '-ndm', 1, '-ndf', 1)\n"
        "ops.node(1, 0.0)\n"
        f"ops.node({response_node}, 1.0)\n"
        "ops.uniaxialMaterial('Elastic', 1, 100.0)\n"
        f"ops.element('truss', 1, 1, {response_node}, 1.0, 1)\n",
        encoding="utf-8",
    )
    fingerprint = inspect_model(workspace, model_name)["bundle"]["bundleFingerprint"]

    manifest_name = f"{prefix}_semantic-roles.json"
    manifest_fingerprint = "0" * 64 if stale_manifest else fingerprint
    (workspace / manifest_name).write_text(
        json.dumps(
            {
                "schemaVersion": "1.0",
                "kind": "engineering_semantic_roles",
                "model": {"bundleFingerprint": manifest_fingerprint},
                "roles": [
                    {
                        "roleId": "TOWER_BASE_LEFT",
                        "roleType": "TOWER_BASE",
                        "entity": {"type": "NODE", "id": response_node},
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    run_id = f"run_{prefix}01"
    run_dir = workspace / ".femagent" / "runs" / run_id
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
                ["0.1", str(peak), "0.2", "1.0"],
                ["0.2", str(-peak / 2), "-0.1", "-0.5"],
            ]
        )
    summary = run_dir / "result_summary.json"
    summary.write_text(
        json.dumps(
            {
                "responseNode": response_node,
                "responseDof": 1,
                "sampleCount": 3,
                "absolutePeakDisplacementM": peak,
            }
        ),
        encoding="utf-8",
    )
    solver_log = run_dir / "solver.log"
    solver_log.write_text("cross solver api test\n", encoding="utf-8")
    recorded_fingerprint = "f" * 64 if wrong_run_fingerprint else fingerprint
    run_manifest = {
        "schemaVersion": "1.0",
        "kind": "solver_run",
        "runId": run_id,
        "caseFingerprint": ("a" if prefix == "left" else "b") * 64,
        "status": "COMPLETED",
        "solver": {
            "name": "OPENSEESPY",
            "packageVersion": "3.8.0.0",
            "engineVersion": "3.8.0",
            "executionMode": "ISOLATED_WORKER_PROCESS",
        },
        "model": {
            "path": model_name,
            "sha256": "c" * 64,
            "bundleFingerprint": recorded_fingerprint,
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
    (run_dir / "run_manifest.json").write_text(json.dumps(run_manifest), encoding="utf-8")
    if tamper_response:
        response.write_text(response.read_text(encoding="utf-8") + "0.3,9,9,9\n", encoding="utf-8")

    return {
        "modelPath": model_name,
        "manifestPath": manifest_name,
        "roleId": "TOWER_BASE_LEFT",
        "runRef": run_id,
    }


def _summary_query() -> dict[str, str]:
    return {"quantity": "DISPLACEMENT", "component": "X", "operation": "SUMMARY"}


def test_validate_cross_solver_compares_two_independently_verified_role_runs(tmp_path: Path) -> None:
    left = _write_side(tmp_path, prefix="left", response_node=2, peak=0.031)
    right = _write_side(tmp_path, prefix="right", response_node=3, peak=0.030)

    report = validate_cross_solver(
        tmp_path,
        project_id="bridge-demo",
        left=left,
        right=right,
        query=_summary_query(),
    )

    assert report["status"] == "COMPARABLE"
    assert report["role"] == {"roleId": "TOWER_BASE_LEFT", "roleType": "TOWER_BASE"}
    assert report["sides"]["left"]["entity"] == {"type": "NODE", "id": 2}
    assert report["sides"]["right"]["entity"] == {"type": "NODE", "id": 3}
    assert report["comparison"]["left"] == pytest.approx(0.031)
    assert report["comparison"]["right"] == pytest.approx(0.030)
    assert report["comparison"]["absoluteDifference"] == pytest.approx(0.001)
    assert report["comparison"]["relativeDifference"] == pytest.approx(0.001 / 0.031)


def test_series_request_returns_not_comparable_before_accessing_side_paths(tmp_path: Path) -> None:
    report = validate_cross_solver(
        tmp_path,
        project_id="bridge-demo",
        left={
            "modelPath": "missing-left.py",
            "manifestPath": "missing-left.json",
            "roleId": "TOWER_BASE_LEFT",
            "runRef": "run_missing_left",
        },
        right={
            "modelPath": "missing-right.py",
            "manifestPath": "missing-right.json",
            "roleId": "TOWER_BASE_LEFT",
            "runRef": "run_missing_right",
        },
        query={"quantity": "DISPLACEMENT", "component": "X", "operation": "SERIES"},
    )

    assert report["status"] == "NOT_COMPARABLE"
    assert report["comparison"] is None
    assert [item["code"] for item in report["limitations"]] == [
        "CROSS_SOLVER_OPERATION_NOT_SUPPORTED"
    ]


def test_stale_semantic_manifest_remains_a_hard_error(tmp_path: Path) -> None:
    left = _write_side(
        tmp_path,
        prefix="left",
        response_node=2,
        peak=0.031,
        stale_manifest=True,
    )
    right = _write_side(tmp_path, prefix="right", response_node=3, peak=0.030)

    with pytest.raises(FemCoreError) as exc_info:
        validate_cross_solver(
            tmp_path,
            project_id="bridge-demo",
            left=left,
            right=right,
            query=_summary_query(),
        )

    assert exc_info.value.code == "SEMANTIC_ROLE_MODEL_MISMATCH"


def test_recorded_run_model_mismatch_remains_a_hard_error(tmp_path: Path) -> None:
    left = _write_side(
        tmp_path,
        prefix="left",
        response_node=2,
        peak=0.031,
        wrong_run_fingerprint=True,
    )
    right = _write_side(tmp_path, prefix="right", response_node=3, peak=0.030)

    with pytest.raises(FemCoreError) as exc_info:
        validate_cross_solver(
            tmp_path,
            project_id="bridge-demo",
            left=left,
            right=right,
            query=_summary_query(),
        )

    assert exc_info.value.code == "SEMANTIC_ROLE_RUN_MODEL_MISMATCH"


def test_tampered_result_artifact_remains_a_hard_error(tmp_path: Path) -> None:
    left = _write_side(
        tmp_path,
        prefix="left",
        response_node=2,
        peak=0.031,
        tamper_response=True,
    )
    right = _write_side(tmp_path, prefix="right", response_node=3, peak=0.030)

    with pytest.raises(FemCoreError) as exc_info:
        validate_cross_solver(
            tmp_path,
            project_id="bridge-demo",
            left=left,
            right=right,
            query=_summary_query(),
        )

    assert exc_info.value.code == "RESULT_ARTIFACT_HASH_MISMATCH"
