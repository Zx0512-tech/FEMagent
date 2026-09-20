from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from fem_core.errors import FemCoreError
from fem_core.model_inspection import inspect_model
from fem_core.model_spec import (
    render_ansys_frame_2d,
    validate_engineering_model_spec,
    verify_ansys_model_render,
)
from fem_core.solvers.ansys_v2_analysis import build_ansys_v2_execution_plan

MODEL_FIXTURE = Path("tests/fixtures/model_spec/simple-portal-frame.json")
_HEADER = (
    "time_s,load_kind,channel_id,application_type,target_type,target_id,"
    "component,quantity,value,unit\n"
)


def _model(*, mass: bool = True) -> dict:
    model = json.loads(MODEL_FIXTURE.read_text(encoding="utf-8"))
    model["nodalMasses"] = (
        [{"nodeId": 3, "mUX": 100.0, "mUY": 80.0}]
        if mass
        else []
    )
    return model


def _load(tmp_path: Path) -> tuple[str, str]:
    path = tmp_path / "loads" / "earthquake.csv"
    path.parent.mkdir(parents=True, exist_ok=True)
    text = (
        _HEADER
        + "0,EARTHQUAKE,EQ,UNIFORM_EXCITATION,,,X,ACCELERATION,0,m/s2\n"
        + "0.01,EARTHQUAKE,EQ,UNIFORM_EXCITATION,,,X,ACCELERATION,1,m/s2\n"
        + "0.02,EARTHQUAKE,EQ,UNIFORM_EXCITATION,,,X,ACCELERATION,0,m/s2\n"
    )
    path.write_text(text, encoding="utf-8")
    return "loads/earthquake.csv", hashlib.sha256(text.encode("utf-8")).hexdigest()


def _analysis(model_fingerprint: str, load_path: str, load_sha: str) -> dict:
    return {
        "schemaVersion": "2.0",
        "kind": "engineering_analysis_spec",
        "modelSpecFingerprint": model_fingerprint,
        "analysisType": "TRANSIENT",
        "units": {},
        "definition": {
            "time": {"timeStep": 0.01, "duration": 0.02},
            "damping": {"type": "NONE"},
            "excitation": {
                "type": "UNIFORM_BASE_EXCITATION",
                "component": "X",
                "quantity": "ACCELERATION",
                "loadArtifact": {"path": load_path, "sha256": load_sha},
            },
        },
        "resultRequests": [
            {
                "requestId": "U3X",
                "quantity": "DISPLACEMENT",
                "target": {"type": "NODE", "id": 3},
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


def test_ansys_renderer_is_deterministic_and_preserves_v1_identity(tmp_path: Path) -> None:
    model = _model()
    first = render_ansys_frame_2d(tmp_path, model)
    second = render_ansys_frame_2d(tmp_path, model)

    assert first["status"] == "RENDERED"
    assert second["status"] == "RENDERED"
    assert first["renderId"] != second["renderId"]
    assert first["renderFingerprint"] == second["renderFingerprint"]
    assert first["artifacts"]["modelSha256"] == second["artifacts"]["modelSha256"]
    assert (
        first["artifacts"]["bundleFingerprint"]
        == second["artifacts"]["bundleFingerprint"]
    )

    first_source = (tmp_path / first["artifacts"]["modelPath"]).read_text(
        encoding="utf-8"
    )
    second_source = (tmp_path / second["artifacts"]["modelPath"]).read_text(
        encoding="utf-8"
    )
    assert first_source == second_source
    assert "ET,1,BEAM3" in first_source
    assert "ET,2,MASS21" in first_source
    assert "KEYOPT,2,3,0" in first_source
    assert "MP,EX,1,206000000000" in first_source
    assert "R,1,0.02,8e-05" in first_source
    assert "D,1,ROTZ,0" in first_source
    assert "D,3,UZ,0" in first_source
    assert "D,3,ROTX,0" in first_source
    assert "D,3,ROTY,0" in first_source
    assert first_source.splitlines().count("ANTYPE,TRANS") == 1
    assert first_source.splitlines().count("SOLVE") == 1
    for forbidden in ("ACEL,", "ALPHAD,", "BETAD,", "DELTIM,", "TIME,"):
        assert forbidden not in first_source

    validation = validate_engineering_model_spec(model)
    assert first["input"]["modelSpecFingerprint"] == validation[
        "modelSpecFingerprint"
    ]
    assert first["mapping"]["nodeTagPolicy"] == "IDENTITY"
    assert first["mapping"]["frameElementTagPolicy"] == "IDENTITY"
    assert first["mapping"]["auxiliaryMassElements"] == [
        {"nodeId": 3, "elementId": 4, "realConstantId": 2}
    ]

    inspection = inspect_model(tmp_path, first["artifacts"]["modelPath"])
    assert inspection["validation"]["executionEligibility"] == "STATICALLY_ELIGIBLE"
    assert inspection["manifest"]["topology"]["nodeTags"] == [1, 2, 3, 4]


def test_ansys_renderer_verification_fails_closed_after_source_tamper(
    tmp_path: Path,
) -> None:
    rendered = render_ansys_frame_2d(tmp_path, _model())
    model_path = tmp_path / rendered["artifacts"]["modelPath"]

    verified = verify_ansys_model_render(
        tmp_path,
        model_path=rendered["artifacts"]["modelPath"],
        manifest_path=rendered["artifacts"]["manifestPath"],
        expected_model_spec_fingerprint=rendered["input"][
            "modelSpecFingerprint"
        ],
    )
    assert verified["status"] == "VERIFIED"
    assert verified["renderFingerprint"] == rendered["renderFingerprint"]

    model_path.write_text(
        model_path.read_text(encoding="utf-8") + "! tampered\n",
        encoding="utf-8",
    )
    with pytest.raises(FemCoreError) as exc_info:
        verify_ansys_model_render(
            tmp_path,
            model_path=rendered["artifacts"]["modelPath"],
            manifest_path=rendered["artifacts"]["manifestPath"],
        )

    assert exc_info.value.code == "ANSYS_MODEL_RENDER_SOURCE_HASH_MISMATCH"


def test_ansys_renderer_blocks_nonready_model(tmp_path: Path) -> None:
    model = _model()
    model["constraints"] = []

    rendered = render_ansys_frame_2d(tmp_path, model)

    assert rendered["status"] == "BLOCKED"
    assert rendered["reason"] == "MODEL_NOT_READY"
    assert rendered["artifacts"] is None


def test_pr29_machine_proves_generated_ansys_modelspec_binding(tmp_path: Path) -> None:
    model = _model()
    validation = validate_engineering_model_spec(model)
    model_fingerprint = validation["modelSpecFingerprint"]
    assert isinstance(model_fingerprint, str)
    rendered = render_ansys_frame_2d(tmp_path, model)
    load_path, load_sha = _load(tmp_path)
    analysis = _analysis(model_fingerprint, load_path, load_sha)

    plan = build_ansys_v2_execution_plan(
        tmp_path,
        model_path=rendered["artifacts"]["modelPath"],
        analysis_spec=analysis,
        model_units={"length": "m", "time": "s"},
        confirmed_bundle_fingerprint=rendered["artifacts"][
            "bundleFingerprint"
        ],
        render_manifest_path=rendered["artifacts"]["manifestPath"],
    )

    assert plan["binding"]["mode"] == "DETERMINISTIC_MODEL_SPEC_RENDER"
    assert (
        plan["binding"]["semanticEquivalence"]
        == "MACHINE_PROVEN_RENDER_BINDING"
    )
    assert plan["binding"]["renderFingerprint"] == rendered["renderFingerprint"]
    assert plan["binding"]["renderManifestPath"] == rendered["artifacts"][
        "manifestPath"
    ]
    assert plan["declaredModelSpecFingerprint"] == model_fingerprint


def test_pr29_legacy_apdl_binding_remains_not_machine_proven(tmp_path: Path) -> None:
    model = _model()
    validation = validate_engineering_model_spec(model)
    model_fingerprint = validation["modelSpecFingerprint"]
    assert isinstance(model_fingerprint, str)
    rendered = render_ansys_frame_2d(tmp_path, model)
    load_path, load_sha = _load(tmp_path)

    plan = build_ansys_v2_execution_plan(
        tmp_path,
        model_path=rendered["artifacts"]["modelPath"],
        analysis_spec=_analysis(model_fingerprint, load_path, load_sha),
        model_units={"length": "m", "time": "s"},
        confirmed_bundle_fingerprint=rendered["artifacts"][
            "bundleFingerprint"
        ],
    )

    assert plan["binding"]["mode"] == "EXPLICIT_BUNDLE_CONFIRMATION"
    assert plan["binding"]["semanticEquivalence"] == "NOT_MACHINE_PROVEN"


def test_pr29_render_binding_rejects_different_modelspec_identity(
    tmp_path: Path,
) -> None:
    model = _model()
    rendered = render_ansys_frame_2d(tmp_path, model)
    load_path, load_sha = _load(tmp_path)
    analysis = _analysis("f" * 64, load_path, load_sha)

    with pytest.raises(FemCoreError) as exc_info:
        build_ansys_v2_execution_plan(
            tmp_path,
            model_path=rendered["artifacts"]["modelPath"],
            analysis_spec=analysis,
            model_units={"length": "m", "time": "s"},
            confirmed_bundle_fingerprint=rendered["artifacts"][
                "bundleFingerprint"
            ],
            render_manifest_path=rendered["artifacts"]["manifestPath"],
        )

    assert exc_info.value.code == "ANSYS_MODEL_RENDER_MODEL_SPEC_MISMATCH"


def test_ansys_adapter_preflight_carries_machine_proven_render_binding(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.delenv("FEM_ANSYS_EXECUTABLE", raising=False)
    model = _model()
    validation = validate_engineering_model_spec(model)
    model_fingerprint = validation["modelSpecFingerprint"]
    assert isinstance(model_fingerprint, str)
    rendered = render_ansys_frame_2d(tmp_path, model)
    load_path, load_sha = _load(tmp_path)

    report = __import__(
        "fem_core.solvers",
        fromlist=["get_solver_adapter"],
    ).get_solver_adapter("ansys").preflight(
        tmp_path,
        model_path=rendered["artifacts"]["modelPath"],
        load_path=None,
        solver_options={
            "modelUnits": {"length": "m", "time": "s"},
            "ansysV2": {
                "analysisSpec": _analysis(
                    model_fingerprint,
                    load_path,
                    load_sha,
                ),
                "confirmedBundleFingerprint": rendered["artifacts"][
                    "bundleFingerprint"
                ],
                "renderManifestPath": rendered["artifacts"]["manifestPath"],
            },
        },
    )

    assert report["status"] == "BLOCKED"
    checks = {item["code"]: item["status"] for item in report["checks"]}
    assert checks["SOLVER_AVAILABLE"] == "FAILED"
    assert checks["ANSYS_V2_ANALYSIS_ADMISSION"] == "PASSED"
    binding = report["analysisAdmission"]["binding"]
    assert binding["mode"] == "DETERMINISTIC_MODEL_SPEC_RENDER"
    assert binding["semanticEquivalence"] == "MACHINE_PROVEN_RENDER_BINDING"
