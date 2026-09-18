from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

import pytest

from fem_core.bridge import handle_request
from fem_core.errors import FemCoreError
from fem_core.protocol import BRIDGE_PROTOCOL
from fem_core.model_inspection import inspect_model
from fem_core.solvers import get_solver_adapter
from fem_core.solvers.ansys_v2_analysis import (
    ANSYS_V2_PROFILE,
    build_ansys_v2_execution_plan,
    inject_ansys_v2_controls,
    write_ansys_v2_control_macro,
)

_HEADER = (
    "time_s,load_kind,channel_id,application_type,target_type,target_id,"
    "component,quantity,value,unit\n"
)


def _model(tmp_path: Path, *, restrained_x: bool = True, damping: str = "") -> str:
    path = tmp_path / "model.inp"
    support = "D,1,ALL,0" if restrained_x else "D,1,UY,0"
    path.write_text(
        "/PREP7\n"
        "N,1,0,0,0\n"
        "N,2,1,0,0\n"
        "E,1,2\n"
        f"{support}\n"
        "FINISH\n"
        "/SOLU\n"
        "ANTYPE,TRANS\n"
        "TRNOPT,FULL\n"
        f"{damping}"
        "AUTOTS,OFF\n"
        "DELTIM,0.01\n"
        "TIME,0.02\n"
        "SOLVE\n"
        "FINISH\n"
        "/EXIT,NOSAVE\n",
        encoding="utf-8",
    )
    return "model.inp"


def _load(tmp_path: Path, *, component: str = "X") -> tuple[str, str]:
    path = tmp_path / "earthquake.csv"
    text = _HEADER + (
        f"0,EARTHQUAKE,EQ,UNIFORM_EXCITATION,,,{component},ACCELERATION,0,m/s2\n"
        f"0.01,EARTHQUAKE,EQ,UNIFORM_EXCITATION,,,{component},ACCELERATION,1,m/s2\n"
        f"0.02,EARTHQUAKE,EQ,UNIFORM_EXCITATION,,,{component},ACCELERATION,0,m/s2\n"
    )
    path.write_text(text, encoding="utf-8")
    return "earthquake.csv", hashlib.sha256(text.encode("utf-8")).hexdigest()


def _analysis(load_path: str, load_sha: str) -> dict:
    return {
        "schemaVersion": "2.0",
        "kind": "engineering_analysis_spec",
        "modelSpecFingerprint": "a" * 64,
        "analysisType": "TRANSIENT",
        "units": {},
        "definition": {
            "time": {"timeStep": 0.01, "duration": 0.02},
            "damping": {"type": "RAYLEIGH", "alphaM": 0.1, "betaK": 0.002},
            "excitation": {
                "type": "UNIFORM_BASE_EXCITATION",
                "component": "X",
                "quantity": "ACCELERATION",
                "loadArtifact": {"path": load_path, "sha256": load_sha},
            },
        },
        "resultRequests": [
            {
                "requestId": "U2X",
                "quantity": "DISPLACEMENT",
                "target": {"type": "NODE", "id": 2},
                "component": "X",
            },
            {
                "requestId": "R1X",
                "quantity": "REACTION_FORCE",
                "target": {"type": "NODE", "id": 1},
                "component": "X",
            },
        ],
    }


def _confirmed_bundle(tmp_path: Path, model_path: str) -> str:
    return str(inspect_model(tmp_path, model_path)["bundle"]["bundleFingerprint"])


def test_ansys_v2_uniform_base_plan_is_admitted_from_exact_bundle_and_artifact(
    tmp_path: Path,
) -> None:
    model_path = _model(tmp_path)
    load_path, load_sha = _load(tmp_path)

    plan = build_ansys_v2_execution_plan(
        tmp_path,
        model_path=model_path,
        analysis_spec=_analysis(load_path, load_sha),
        model_units={"length": "m", "time": "s"},
        confirmed_bundle_fingerprint=_confirmed_bundle(tmp_path, model_path),
    )

    assert plan["schema"] == "FEMAGENT_ANSYS_V2_EXECUTION_ADMISSION_V1"
    assert plan["status"] == "ADMITTED"
    assert plan["profile"] == ANSYS_V2_PROFILE
    assert plan["binding"]["mode"] == "EXPLICIT_BUNDLE_CONFIRMATION"
    assert plan["binding"]["confirmedBundleFingerprint"] == plan["binding"]["currentBundleFingerprint"]
    assert plan["load"]["sha256"] == load_sha
    assert plan["time"] == {
        "timeStepModel": 0.01,
        "durationModel": 0.02,
        "analysisSteps": 2,
        "timeUnit": "s",
    }
    assert plan["damping"] == {"type": "RAYLEIGH", "alphaM": 0.1, "betaK": 0.002}
    assert [item["requestId"] for item in plan["resultRequests"]] == ["R1X", "U2X"]


def test_ansys_v2_plan_fails_closed_on_bundle_confirmation_mismatch(tmp_path: Path) -> None:
    model_path = _model(tmp_path)
    load_path, load_sha = _load(tmp_path)

    with pytest.raises(FemCoreError) as exc_info:
        build_ansys_v2_execution_plan(
            tmp_path,
            model_path=model_path,
            analysis_spec=_analysis(load_path, load_sha),
            model_units={"length": "m", "time": "s"},
            confirmed_bundle_fingerprint="f" * 64,
        )

    assert exc_info.value.code == "ANSYS_V2_BUNDLE_CONFIRMATION_MISMATCH"


def test_ansys_v2_plan_rereads_external_artifact_and_detects_tamper(tmp_path: Path) -> None:
    model_path = _model(tmp_path)
    load_path, load_sha = _load(tmp_path)
    analysis = _analysis(load_path, load_sha)
    (tmp_path / load_path).write_text((tmp_path / load_path).read_text() + "\n", encoding="utf-8")

    with pytest.raises(FemCoreError) as exc_info:
        build_ansys_v2_execution_plan(
            tmp_path,
            model_path=model_path,
            analysis_spec=analysis,
            model_units={"length": "m", "time": "s"},
            confirmed_bundle_fingerprint=_confirmed_bundle(tmp_path, model_path),
        )

    assert exc_info.value.code == "TRANSIENT_ARTIFACT_HASH_MISMATCH"


def test_ansys_v2_plan_rejects_unproven_result_quantity(tmp_path: Path) -> None:
    model_path = _model(tmp_path)
    load_path, load_sha = _load(tmp_path)
    analysis = _analysis(load_path, load_sha)
    analysis["resultRequests"] = [
        {
            "requestId": "A2X",
            "quantity": "RELATIVE_ACCELERATION",
            "target": {"type": "NODE", "id": 2},
            "component": "X",
        }
    ]

    with pytest.raises(FemCoreError) as exc_info:
        build_ansys_v2_execution_plan(
            tmp_path,
            model_path=model_path,
            analysis_spec=analysis,
            model_units={"length": "m", "time": "s"},
            confirmed_bundle_fingerprint=_confirmed_bundle(tmp_path, model_path),
        )

    assert exc_info.value.code == "ANSYS_V2_RESULT_MAPPING_UNSUPPORTED"


def test_ansys_v2_plan_rejects_unrestrained_reaction_request(tmp_path: Path) -> None:
    model_path = _model(tmp_path, restrained_x=False)
    load_path, load_sha = _load(tmp_path)

    with pytest.raises(FemCoreError) as exc_info:
        build_ansys_v2_execution_plan(
            tmp_path,
            model_path=model_path,
            analysis_spec=_analysis(load_path, load_sha),
            model_units={"length": "m", "time": "s"},
            confirmed_bundle_fingerprint=_confirmed_bundle(tmp_path, model_path),
        )

    assert exc_info.value.code == "ANSYS_V2_REACTION_DOF_UNRESTRAINED"


def test_ansys_v2_plan_rejects_existing_damping_commands(tmp_path: Path) -> None:
    model_path = _model(tmp_path, damping="ALPHAD,0.2\n")
    load_path, load_sha = _load(tmp_path)

    with pytest.raises(FemCoreError) as exc_info:
        build_ansys_v2_execution_plan(
            tmp_path,
            model_path=model_path,
            analysis_spec=_analysis(load_path, load_sha),
            model_units={"length": "m", "time": "s"},
            confirmed_bundle_fingerprint=_confirmed_bundle(tmp_path, model_path),
        )

    assert exc_info.value.code == "ANSYS_V2_DAMPING_CONFLICT"


def test_ansys_v2_control_injection_is_staged_only_and_deterministic(tmp_path: Path) -> None:
    model_path = _model(tmp_path)
    load_path, load_sha = _load(tmp_path)
    plan = build_ansys_v2_execution_plan(
        tmp_path,
        model_path=model_path,
        analysis_spec=_analysis(load_path, load_sha),
        model_units={"length": "m", "time": "s"},
        confirmed_bundle_fingerprint=_confirmed_bundle(tmp_path, model_path),
    )
    source_before = (tmp_path / model_path).read_bytes()
    stage = tmp_path / "stage"
    stage.mkdir()
    staged_model = stage / "model.inp"
    staged_model.write_bytes(source_before)

    control = write_ansys_v2_control_macro(stage, plan)
    injection = inject_ansys_v2_controls(stage, plan["solveHook"])

    assert (tmp_path / model_path).read_bytes() == source_before
    macro = Path(control["macroPath"]).read_text(encoding="utf-8")
    assert "TRNOPT,FULL" in macro
    assert "AUTOTS,OFF" in macro
    assert "DELTIM,0.01" in macro
    assert "TIME,0.02" in macro
    assert "ALPHAD,0.1" in macro
    assert "BETAD,0.002" in macro
    assert "OUTRES,NSOL,ALL" in macro
    assert "OUTRES,RSOL,ALL" in macro
    staged = staged_model.read_text(encoding="utf-8").splitlines()
    solve_index = staged.index("SOLVE")
    assert staged[solve_index - 1] == "/INPUT,'femagent_analysis_v2','mac'"
    assert injection["injected"] is True
    assert len(control["macroSha256"]) == 64


def _fake_ansys_runtime(tmp_path: Path) -> Path:
    executable = tmp_path / "ansys_pr29_fake"
    executable.write_text(
        "#!/usr/bin/env python3\n"
        "import sys\n"
        "from pathlib import Path\n"
        "args = sys.argv[1:]\n"
        "input_path = Path(args[args.index('-i') + 1]).resolve()\n"
        "output_path = Path(args[args.index('-o') + 1]).resolve()\n"
        "job_name = args[args.index('-j') + 1]\n"
        "output_path.write_text('FAKE ANSYS PR29 OK\\n', encoding='utf-8')\n"
        "if input_path.name != 'build_only.inp':\n"
        "    text = input_path.read_text(encoding='utf-8')\n"
        "    assert \"/INPUT,'femagent_load','mac'\" in text\n"
        "    assert \"/INPUT,'femagent_analysis_v2','mac'\" in text\n"
        "    assert (Path.cwd() / 'femagent_load.mac').is_file()\n"
        "    assert (Path.cwd() / 'femagent_analysis_v2.mac').is_file()\n"
        "    (Path.cwd() / f'{job_name}.rst').write_bytes(b'FEMagent PR29 fake RST')\n",
        encoding="utf-8",
    )
    executable.chmod(executable.stat().st_mode | 0o111)
    return executable


def _solver_options(
    tmp_path: Path,
    model_path: str,
    analysis: dict,
) -> dict:
    return {
        "modelUnits": {"length": "m", "time": "s"},
        "ansysV2": {
            "analysisSpec": analysis,
            "confirmedBundleFingerprint": _confirmed_bundle(tmp_path, model_path),
        },
    }


def test_ansys_adapter_preflight_admits_v2_uniform_base_without_external_load_path(
    tmp_path: Path,
    monkeypatch,
) -> None:
    executable = _fake_ansys_runtime(tmp_path)
    monkeypatch.setenv("FEM_ANSYS_EXECUTABLE", str(executable))
    model_path = _model(tmp_path)
    load_path, load_sha = _load(tmp_path)
    analysis = _analysis(load_path, load_sha)

    report = get_solver_adapter("ansys").preflight(
        tmp_path,
        model_path=model_path,
        load_path=None,
        solver_options=_solver_options(tmp_path, model_path, analysis),
    )

    assert report["status"] == "READY"
    checks = {item["code"]: item["status"] for item in report["checks"]}
    assert checks["ANSYS_V2_ANALYSIS_ADMISSION"] == "PASSED"
    assert checks["CANONICAL_LOAD_INJECTION"] == "PASSED"
    assert checks["BUILD_ONLY_INSPECTION"] == "PASSED"
    assert report["executionEstimate"] == {
        "mode": "ANSYS_APDL_V2_UNIFORM_BASE",
        "analysisSteps": 2,
    }
    admission = report["analysisAdmission"]
    assert admission["status"] == "ADMITTED"
    assert admission["profile"] == ANSYS_V2_PROFILE
    assert "canonicalLoad" not in admission
    assert "loadHook" not in admission
    assert "solveHook" not in admission


def test_ansys_adapter_v2_forbids_parallel_external_load_path(
    tmp_path: Path,
    monkeypatch,
) -> None:
    executable = _fake_ansys_runtime(tmp_path)
    monkeypatch.setenv("FEM_ANSYS_EXECUTABLE", str(executable))
    model_path = _model(tmp_path)
    load_path, load_sha = _load(tmp_path)
    analysis = _analysis(load_path, load_sha)

    with pytest.raises(FemCoreError) as exc_info:
        get_solver_adapter("ansys").preflight(
            tmp_path,
            model_path=model_path,
            load_path=load_path,
            solver_options=_solver_options(tmp_path, model_path, analysis),
        )

    assert exc_info.value.code == "ANSYS_V2_EXTERNAL_LOAD_PATH_FORBIDDEN"


def test_ansys_adapter_v2_run_records_admission_controls_and_preserves_source(
    tmp_path: Path,
    monkeypatch,
) -> None:
    executable = _fake_ansys_runtime(tmp_path)
    monkeypatch.setenv("FEM_ANSYS_EXECUTABLE", str(executable))
    model_path = _model(tmp_path)
    load_path, load_sha = _load(tmp_path)
    analysis = _analysis(load_path, load_sha)
    source = tmp_path / model_path
    before = source.read_bytes()
    options = _solver_options(tmp_path, model_path, analysis)

    run = get_solver_adapter("ansys").run(
        tmp_path,
        model_path=model_path,
        load_path=None,
        solver_options=options,
    )

    assert source.read_bytes() == before
    assert run["status"] == "COMPLETED"
    assert run["analysis"]["type"] == "TRANSIENT_UNIFORM_EXCITATION_V2"
    assert run["analysis"]["profile"] == ANSYS_V2_PROFILE
    assert run["analysis"]["analysisSpecFingerprint"] == run["analysisAdmission"][
        "analysisSpecFingerprint"
    ]
    assert run["analysisAdmission"]["binding"]["mode"] == "EXPLICIT_BUNDLE_CONFIRMATION"
    assert len(run["executionInputFingerprint"]) == 64
    assert len(run["outputs"]["generatedAnalysisControlSha256"]) == 64
    assert len(run["outputs"]["generatedLoadMacroSha256"]) == 64
    assert len(run["outputs"]["binaryResultSha256"]) == 64

    staged_root = tmp_path / run["outputs"]["stagedBundleRoot"]
    staged_model = staged_root / "model.inp"
    lines = staged_model.read_text(encoding="utf-8").splitlines()
    antype_index = lines.index("ANTYPE,TRANS")
    solve_index = lines.index("SOLVE")
    assert lines[antype_index + 1] == "/INPUT,'femagent_load','mac'"
    assert lines[solve_index - 1] == "/INPUT,'femagent_analysis_v2','mac'"
    assert (tmp_path / run["outputs"]["generatedAnalysisControl"]).is_file()


def test_pr29_fake_runtime_is_executable_on_posix(tmp_path: Path) -> None:
    executable = _fake_ansys_runtime(tmp_path)
    if os.name != "nt":
        assert os.access(executable, os.X_OK)


def test_solver_bridge_transports_ansys_v2_context_without_new_command(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.delenv("FEM_ANSYS_EXECUTABLE", raising=False)
    model_path = _model(tmp_path)
    load_path, load_sha = _load(tmp_path)
    analysis = _analysis(load_path, load_sha)

    response = handle_request(
        {
            "protocol": BRIDGE_PROTOCOL,
            "requestId": "pr29-bridge",
            "command": "solver.preflight",
            "payload": {
                "solver": "ansys",
                "modelPath": model_path,
                "solverOptions": _solver_options(tmp_path, model_path, analysis),
            },
        },
        workspace=tmp_path,
    )

    assert response["ok"] is True
    report = response["result"]
    assert report["status"] == "BLOCKED"
    checks = {item["code"]: item["status"] for item in report["checks"]}
    assert checks["SOLVER_AVAILABLE"] == "FAILED"
    assert checks["ANSYS_V2_ANALYSIS_ADMISSION"] == "PASSED"
    assert report["analysisAdmission"]["profile"] == ANSYS_V2_PROFILE
