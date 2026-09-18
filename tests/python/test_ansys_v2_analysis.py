from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from fem_core.errors import FemCoreError
from fem_core.model_inspection import inspect_model
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
