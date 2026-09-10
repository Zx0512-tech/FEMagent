from __future__ import annotations

import json
from copy import deepcopy
from hashlib import sha256
from pathlib import Path
from typing import Any

from fem_core.analysis_spec.readiness import evaluate_engineering_analysis_readiness
from fem_core.model_spec.validator import validate_engineering_model_spec

MODEL_FIXTURE = Path("tests/fixtures/model_spec/simple-portal-frame.json")
HEADER = (
    "time_s,load_kind,channel_id,application_type,target_type,target_id,"
    "component,quantity,value,unit\n"
)


def _model() -> dict[str, Any]:
    return json.loads(MODEL_FIXTURE.read_text(encoding="utf-8"))


def _write_artifact(
    workspace: Path,
    *,
    rel: str,
    application: str,
    component: str,
    quantity: str,
    unit: str,
    target_type: str = "",
    target_id: str = "",
    times: tuple[float, ...] = (0.0, 0.01, 0.02),
) -> dict[str, str]:
    rows = []
    for index, time_s in enumerate(times):
        value = 0.0 if index in {0, len(times) - 1} else 1.0
        rows.append(
            f"{time_s},TRANSIENT,ch-1,{application},{target_type},{target_id},"
            f"{component},{quantity},{value},{unit}\n"
        )
    raw = (HEADER + "".join(rows)).encode("utf-8")
    path = workspace / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(raw)
    return {"path": rel, "sha256": sha256(raw).hexdigest()}


def _fingerprint(model: dict[str, Any]) -> str:
    report = validate_engineering_model_spec(model)
    assert report["status"] == "VALID"
    fingerprint = report["modelSpecFingerprint"]
    assert isinstance(fingerprint, str)
    return fingerprint


def _nodal_spec(
    model: dict[str, Any],
    ref: dict[str, str],
    *,
    time_step: float = 0.01,
    duration: float = 0.02,
    force_unit: str | None = None,
) -> dict[str, Any]:
    return {
        "schemaVersion": "2.0",
        "kind": "engineering_analysis_spec",
        "modelSpecFingerprint": _fingerprint(model),
        "analysisType": "TRANSIENT",
        "units": {"force": force_unit or model["units"]["force"]},
        "definition": {
            "time": {"timeStep": time_step, "duration": duration},
            "damping": {"type": "NONE"},
            "excitation": {
                "type": "NODAL_TIME_HISTORY",
                "nodeId": 3,
                "component": "Y",
                "quantity": "FORCE",
                "loadArtifact": ref,
            },
        },
        "resultRequests": [
            {
                "requestId": "U3Y",
                "quantity": "DISPLACEMENT",
                "target": {"type": "NODE", "id": 3},
                "component": "Y",
            },
            {
                "requestId": "V3Y",
                "quantity": "VELOCITY",
                "target": {"type": "NODE", "id": 3},
                "component": "Y",
            },
            {
                "requestId": "A3Y",
                "quantity": "ACCELERATION",
                "target": {"type": "NODE", "id": 3},
                "component": "Y",
            },
        ],
    }


def _base_spec(
    model: dict[str, Any],
    ref: dict[str, str],
    *,
    time_step: float = 0.01,
    duration: float = 0.02,
    absolute: bool = False,
) -> dict[str, Any]:
    accel_quantity = "ABSOLUTE_ACCELERATION" if absolute else "RELATIVE_ACCELERATION"
    return {
        "schemaVersion": "2.0",
        "kind": "engineering_analysis_spec",
        "modelSpecFingerprint": _fingerprint(model),
        "analysisType": "TRANSIENT",
        "units": {},
        "definition": {
            "time": {"timeStep": time_step, "duration": duration},
            "damping": {"type": "RAYLEIGH", "alphaM": 0.0, "betaK": 0.002},
            "excitation": {
                "type": "UNIFORM_BASE_EXCITATION",
                "component": "X",
                "quantity": "ACCELERATION",
                "loadArtifact": ref,
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
                "requestId": "V3X",
                "quantity": "VELOCITY",
                "target": {"type": "NODE", "id": 3},
                "component": "X",
            },
            {
                "requestId": "A3X",
                "quantity": accel_quantity,
                "target": {"type": "NODE", "id": 3},
                "component": "X",
            },
        ],
    }


def _codes(report: dict[str, Any]) -> set[str]:
    return {str(item["code"]) for item in report["issues"]}


def _mapping(report: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {
        str(item["requestId"]): item
        for item in report["checks"]["responseMapping"]["channels"]
    }


def test_nodal_force_transient_is_ready_with_global_response_mappings(tmp_path: Path) -> None:
    model = _model()
    ref = _write_artifact(
        tmp_path,
        rel="loads/force.csv",
        application="NODAL_FORCE",
        component="Y",
        quantity="FORCE",
        unit="N",
        target_type="NODE",
        target_id="3",
    )
    report = evaluate_engineering_analysis_readiness(model, _nodal_spec(model, ref), workspace=tmp_path)

    assert report["schema"] == "FEMAGENT_ANALYSIS_READINESS_V2"
    assert report["status"] == "READY"
    assert report["profile"] == "OPENSEES_FRAME_2D_TRANSIENT_NODAL_FORCE_V2"
    assert report["checks"]["loadArtifact"]["status"] == "PASS"
    assert report["checks"]["timeCompatibility"]["status"] == "PASS"
    mappings = _mapping(report)
    assert mappings["U3Y"]["access"] == "NODE_DISP"
    assert mappings["U3Y"]["referenceFrame"] == "GLOBAL"
    assert mappings["V3Y"]["access"] == "NODE_VEL"
    assert mappings["V3Y"]["unit"] == "m/s"
    assert mappings["A3Y"]["access"] == "NODE_ACCEL"
    assert mappings["A3Y"]["unit"] == "m/s2"
    conversions = report["checks"]["unitConversions"]["conversions"]
    assert {item["quantity"] for item in conversions} == {"TIME", "FORCE"}


def test_uniform_base_transient_is_ready_with_relative_kinematic_frame(tmp_path: Path) -> None:
    model = _model()
    ref = _write_artifact(
        tmp_path,
        rel="loads/base.csv",
        application="UNIFORM_EXCITATION",
        component="X",
        quantity="ACCELERATION",
        unit="m/s2",
    )
    report = evaluate_engineering_analysis_readiness(model, _base_spec(model, ref), workspace=tmp_path)

    assert report["status"] == "READY"
    assert report["profile"] == "OPENSEES_FRAME_2D_TRANSIENT_UNIFORM_BASE_V2"
    mappings = _mapping(report)
    assert mappings["U3X"]["referenceFrame"] == "RELATIVE"
    assert mappings["V3X"]["referenceFrame"] == "RELATIVE"
    assert mappings["A3X"]["referenceFrame"] == "RELATIVE"
    assert mappings["A3X"]["access"] == "NODE_ACCEL"


def test_transient_requires_workspace_for_external_artifact(tmp_path: Path) -> None:
    model = _model()
    ref = _write_artifact(
        tmp_path,
        rel="loads/force.csv",
        application="NODAL_FORCE",
        component="Y",
        quantity="FORCE",
        unit="N",
        target_type="NODE",
        target_id="3",
    )
    report = evaluate_engineering_analysis_readiness(model, _nodal_spec(model, ref))
    assert report["status"] == "NOT_READY"
    assert "ANALYSIS_READINESS_WORKSPACE_REQUIRED" in _codes(report)


def test_transient_artifact_hash_mismatch_is_not_ready(tmp_path: Path) -> None:
    model = _model()
    ref = _write_artifact(
        tmp_path,
        rel="loads/force.csv",
        application="NODAL_FORCE",
        component="Y",
        quantity="FORCE",
        unit="N",
        target_type="NODE",
        target_id="3",
    )
    spec = _nodal_spec(model, {**ref, "sha256": "0" * 64})
    report = evaluate_engineering_analysis_readiness(model, spec, workspace=tmp_path)
    assert report["status"] == "NOT_READY"
    assert "ANALYSIS_READINESS_LOAD_ARTIFACT_HASH_MISMATCH" in _codes(report)


def test_transient_channel_semantics_must_match_analysis_spec(tmp_path: Path) -> None:
    model = _model()
    ref = _write_artifact(
        tmp_path,
        rel="loads/force.csv",
        application="NODAL_FORCE",
        component="X",
        quantity="FORCE",
        unit="N",
        target_type="NODE",
        target_id="3",
    )
    report = evaluate_engineering_analysis_readiness(model, _nodal_spec(model, ref), workspace=tmp_path)
    assert report["status"] == "NOT_READY"
    assert "ANALYSIS_READINESS_LOAD_CHANNEL_MISMATCH" in _codes(report)


def test_transient_time_origin_step_and_duration_are_verified_separately(tmp_path: Path) -> None:
    model = _model()

    origin_ref = _write_artifact(
        tmp_path,
        rel="loads/origin.csv",
        application="NODAL_FORCE",
        component="Y",
        quantity="FORCE",
        unit="N",
        target_type="NODE",
        target_id="3",
        times=(0.01, 0.02),
    )
    origin = evaluate_engineering_analysis_readiness(
        model, _nodal_spec(model, origin_ref), workspace=tmp_path
    )
    assert "ANALYSIS_READINESS_TIME_ORIGIN_MISMATCH" in _codes(origin)

    step_ref = _write_artifact(
        tmp_path,
        rel="loads/step.csv",
        application="NODAL_FORCE",
        component="Y",
        quantity="FORCE",
        unit="N",
        target_type="NODE",
        target_id="3",
        times=(0.0, 0.02, 0.04),
    )
    step = evaluate_engineering_analysis_readiness(
        model, _nodal_spec(model, step_ref, duration=0.04), workspace=tmp_path
    )
    assert "ANALYSIS_READINESS_TIME_STEP_MISMATCH" in _codes(step)

    duration_ref = _write_artifact(
        tmp_path,
        rel="loads/duration.csv",
        application="NODAL_FORCE",
        component="Y",
        quantity="FORCE",
        unit="N",
        target_type="NODE",
        target_id="3",
    )
    duration = evaluate_engineering_analysis_readiness(
        model, _nodal_spec(model, duration_ref, duration=0.03), workspace=tmp_path
    )
    assert "ANALYSIS_READINESS_DURATION_MISMATCH" in _codes(duration)


def test_base_absolute_acceleration_remains_not_ready(tmp_path: Path) -> None:
    model = _model()
    ref = _write_artifact(
        tmp_path,
        rel="loads/base.csv",
        application="UNIFORM_EXCITATION",
        component="X",
        quantity="ACCELERATION",
        unit="m/s2",
    )
    report = evaluate_engineering_analysis_readiness(
        model, _base_spec(model, ref, absolute=True), workspace=tmp_path
    )
    assert report["status"] == "NOT_READY"
    assert "ANALYSIS_READINESS_ABSOLUTE_ACCELERATION_MAPPING_UNPROVEN" in _codes(report)


def test_nodal_force_unit_must_match_bound_model_unit(tmp_path: Path) -> None:
    model = _model()
    ref = _write_artifact(
        tmp_path,
        rel="loads/force.csv",
        application="NODAL_FORCE",
        component="Y",
        quantity="FORCE",
        unit="N",
        target_type="NODE",
        target_id="3",
    )
    report = evaluate_engineering_analysis_readiness(
        model, _nodal_spec(model, ref, force_unit="kN"), workspace=tmp_path
    )
    assert report["status"] == "NOT_READY"
    assert "ANALYSIS_READINESS_FORCE_UNIT_MISMATCH" in _codes(report)


def test_transient_conversion_evidence_uses_model_native_mm_ms_units(tmp_path: Path) -> None:
    model = deepcopy(_model())
    model["units"]["length"] = "mm"
    model["units"]["time"] = "ms"
    ref = _write_artifact(
        tmp_path,
        rel="loads/base.csv",
        application="UNIFORM_EXCITATION",
        component="X",
        quantity="ACCELERATION",
        unit="m/s2",
    )
    spec = _base_spec(model, ref, time_step=10.0, duration=20.0)
    report = evaluate_engineering_analysis_readiness(model, spec, workspace=tmp_path)

    assert report["status"] == "READY"
    conversions = {
        item["quantity"]: item
        for item in report["checks"]["unitConversions"]["conversions"]
    }
    assert conversions["TIME"] == {
        "quantity": "TIME",
        "sourceUnit": "s",
        "targetUnit": "ms",
        "factor": 1000.0,
    }
    assert conversions["ACCELERATION"] == {
        "quantity": "ACCELERATION",
        "sourceUnit": "m/s2",
        "targetUnit": "mm/ms2",
        "factor": 0.001,
    }
    mappings = _mapping(report)
    assert mappings["V3X"]["unit"] == "mm/ms"
    assert mappings["A3X"]["unit"] == "mm/ms2"
