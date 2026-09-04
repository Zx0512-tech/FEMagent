from __future__ import annotations

import csv
import json
import shutil
from hashlib import sha256
from pathlib import Path

import pytest
from ansys.mapdl import reader as pymapdl_reader
from ansys.mapdl.reader import examples

from fem_core.errors import FemCoreError
from fem_core.result_intelligence import inspect_result, query_result


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


def _write_ansys_run(tmp_path: Path, *, with_binary: bool) -> Path:
    run_id = "run_ansysresult001"
    run_dir = tmp_path / ".femagent" / "runs" / run_id
    run_dir.mkdir(parents=True)
    outputs: dict[str, str] = {
        "runManifest": f".femagent/runs/{run_id}/run_manifest.json",
    }
    if with_binary:
        binary = run_dir / "fem_result.rst"
        shutil.copyfile(examples.rstfile, binary)
        outputs["binaryResult"] = f".femagent/runs/{run_id}/fem_result.rst"
        outputs["binaryResultSha256"] = _sha(binary)
    manifest = {
        "schemaVersion": "1.0",
        "kind": "solver_run",
        "runId": run_id,
        "caseFingerprint": "d" * 64,
        "status": "COMPLETED",
        "solver": {
            "name": "ANSYS",
            "runtime": "ANSYS_MAPDL",
            "executionMode": "ISOLATED_PROCESS",
        },
        "model": {"path": "main.inp", "sha256": "e" * 64},
        "load": {"mode": "MODEL_SCRIPT_MANAGED"},
        "analysis": {"type": "MODEL_SCRIPT"},
        "summary": {"processReturnCode": 0},
        "outputs": outputs,
    }
    (run_dir / "run_manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return run_dir


def _strip_standard_response(run_dir: Path) -> None:
    manifest_path = run_dir / "run_manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["analysis"] = {"type": "MODEL_SCRIPT"}
    manifest["summary"] = {"nodeCount": 2, "elementCount": 1, "analysisTime": 1.0}
    manifest["outputs"].pop("responseCsv", None)
    manifest["outputs"].pop("responseSha256", None)
    (run_dir / "response.csv").unlink()
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")


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


def test_inspect_result_rejects_symlinked_manifest_escape(tmp_path: Path) -> None:
    outside = tmp_path.parent / f"{tmp_path.name}-outside-run-manifest.json"
    outside.write_text('{"kind":"outside"}', encoding="utf-8")
    run_dir = tmp_path / "run_symlink_escape"
    run_dir.mkdir()
    (run_dir / "run_manifest.json").symlink_to(outside)

    with pytest.raises(FemCoreError) as escaped:
        inspect_result(tmp_path, run_dir.name)

    assert escaped.value.code == "PATH_OUTSIDE_WORKSPACE"


def test_query_open_sees_displacement_summary_returns_extrema_and_peak_time(tmp_path: Path) -> None:
    run_dir = _write_open_sees_run(tmp_path)

    result = query_result(
        tmp_path,
        run_dir.name,
        {
            "quantity": "DISPLACEMENT",
            "target": {"type": "NODE", "id": 2},
            "component": "UX",
            "operation": "SUMMARY",
        },
    )

    assert result["kind"] == "result_query"
    assert result["quantity"] == "DISPLACEMENT"
    assert result["component"] == "X"
    assert result["unit"] == "m"
    assert result["referenceFrame"] == "RELATIVE"
    assert result["abscissa"] == {"semantic": "TIME", "unit": "s"}
    assert result["summary"] == {
        "sampleCount": 4,
        "min": -0.03,
        "max": 0.02,
        "absolutePeak": 0.03,
        "abscissaAtAbsolutePeak": 0.2,
    }


def test_query_open_sees_series_supports_paging_and_component_aliases(tmp_path: Path) -> None:
    run_dir = _write_open_sees_run(tmp_path)

    for alias in ("X", "UX", "U1", "1"):
        result = query_result(
            tmp_path,
            run_dir.name,
            {
                "quantity": "ACCELERATION",
                "target": {"type": "NODE", "id": 2},
                "component": alias,
                "operation": "SERIES",
                "offset": 1,
                "limit": 2,
            },
        )
        assert result["component"] == "X"
        assert result["unit"] == "m/s2"
        assert result["series"] == [
            {"abscissa": 0.1, "value": 1.0},
            {"abscissa": 0.2, "value": -0.5},
        ]
        assert result["paging"] == {"offset": 1, "limit": 2, "returned": 2, "total": 4}


def test_query_rejects_unavailable_channel_and_invalid_page_request(tmp_path: Path) -> None:
    run_dir = _write_open_sees_run(tmp_path)

    with pytest.raises(FemCoreError) as missing_node:
        query_result(
            tmp_path,
            run_dir.name,
            {
                "quantity": "DISPLACEMENT",
                "target": {"type": "NODE", "id": 999},
                "component": "X",
                "operation": "SUMMARY",
            },
        )
    assert missing_node.value.code == "RESULT_SERIES_UNAVAILABLE"

    with pytest.raises(FemCoreError) as reaction:
        query_result(
            tmp_path,
            run_dir.name,
            {
                "quantity": "REACTION_FORCE",
                "target": {"type": "NODE", "id": 2},
                "component": "X",
                "operation": "SUMMARY",
            },
        )
    assert reaction.value.code == "RESULT_SERIES_UNAVAILABLE"

    with pytest.raises(FemCoreError) as invalid_limit:
        query_result(
            tmp_path,
            run_dir.name,
            {
                "quantity": "DISPLACEMENT",
                "target": {"type": "NODE", "id": 2},
                "component": "X",
                "operation": "SERIES",
                "limit": 5001,
            },
        )
    assert invalid_limit.value.code == "INVALID_RESULT_QUERY"


def test_query_arbitrary_open_sees_bundle_does_not_invent_response_series(tmp_path: Path) -> None:
    run_dir = _write_open_sees_run(tmp_path, run_id="run_scriptmanaged01")
    _strip_standard_response(run_dir)

    inspection = inspect_result(tmp_path, run_dir.name)
    assert inspection["integrity"]["status"] == "LIMITED"
    assert inspection["queryCapabilities"] == []

    with pytest.raises(FemCoreError) as unavailable:
        query_result(
            tmp_path,
            run_dir.name,
            {
                "quantity": "DISPLACEMENT",
                "target": {"type": "NODE", "id": 2},
                "component": "X",
                "operation": "SUMMARY",
            },
        )
    assert unavailable.value.code == "RESULT_SERIES_UNAVAILABLE"


def test_inspect_ansys_without_binary_result_is_limited_not_fabricated(tmp_path: Path) -> None:
    run_dir = _write_ansys_run(tmp_path, with_binary=False)

    report = inspect_result(tmp_path, run_dir.name)

    assert report["solver"]["name"] == "ANSYS"
    assert report["integrity"]["status"] == "LIMITED"
    assert report["queryCapabilities"] == []
    assert {warning["code"] for warning in report["warnings"]} == {
        "ANSYS_BINARY_RESULT_NOT_RECORDED"
    }


def test_inspect_and_query_ansys_real_binary_result_keep_units_unknown(tmp_path: Path) -> None:
    run_dir = _write_ansys_run(tmp_path, with_binary=True)
    binary_path = run_dir / "fem_result.rst"
    raw = pymapdl_reader.read_binary(binary_path, parse_vtk=False)
    nnum, _ = raw.nodal_solution(0)
    node_id = int(nnum[0])

    report = inspect_result(tmp_path, run_dir.name)
    assert report["integrity"]["status"] == "VALID"
    assert report["abscissa"]["unit"] is None
    assert any(capability["quantity"] == "DISPLACEMENT" for capability in report["queryCapabilities"])
    assert "ANSYS_RESULT_UNIT_SYSTEM_NOT_DECLARED" in {
        warning["code"] for warning in report["warnings"]
    }

    result = query_result(
        tmp_path,
        run_dir.name,
        {
            "quantity": "DISPLACEMENT",
            "target": {"type": "NODE", "id": node_id},
            "component": "X",
            "operation": "SUMMARY",
        },
    )
    assert result["unit"] is None
    assert result["referenceFrame"] == "SOLVER_NATIVE"
    assert result["summary"]["sampleCount"] >= 1
