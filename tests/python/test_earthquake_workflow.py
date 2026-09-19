from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path
from typing import Any

import pytest

from fem_core.errors import FemCoreError
from fem_core.solvers import get_solver_adapter
from fem_core.workflows import (
    prepare_earthquake_workflow,
    summarize_earthquake_workflow,
)

MODEL_FIXTURE = Path("tests/fixtures/model_spec/simple-portal-frame.json")
_HEADER = (
    "time_s,load_kind,channel_id,application_type,target_type,target_id,"
    "component,quantity,value,unit\n"
)


def _model(*, mass: bool = True) -> dict[str, Any]:
    model = json.loads(MODEL_FIXTURE.read_text(encoding="utf-8"))
    model["nodalMasses"] = (
        [{"nodeId": 3, "mUX": 100.0, "mUY": 100.0}]
        if mass
        else []
    )
    return model


def _small_model() -> dict[str, Any]:
    return {
        "schemaVersion": "1.0",
        "kind": "engineering_model_spec",
        "dimension": "2D",
        "family": "FRAME",
        "coordinateSystem": "CARTESIAN_XY",
        "units": {"length": "m", "force": "N", "time": "s"},
        "nodes": [
            {"id": 1, "x": 0.0, "y": 0.0},
            {"id": 2, "x": 1.0, "y": 0.0},
        ],
        "materials": [
            {
                "id": 1,
                "type": "LINEAR_ELASTIC",
                "youngsModulus": 2.0e11,
            }
        ],
        "sections": [
            {"id": 1, "type": "FRAME_2D", "area": 0.02, "iz": 8.0e-5}
        ],
        "elements": [
            {
                "id": 1,
                "type": "ELASTIC_FRAME_2D",
                "formulation": "EULER_BERNOULLI",
                "nodeI": 1,
                "nodeJ": 2,
                "materialId": 1,
                "sectionId": 1,
            }
        ],
        "constraints": [
            {"nodeId": 1, "dofs": ["UX", "UY", "RZ"]},
        ],
        "nodalMasses": [{"nodeId": 2, "mUX": 1.0, "mUY": 1.0}],
    }


def _write_load(tmp_path: Path, *, component: str = "X") -> str:
    path = tmp_path / "loads" / "earthquake.csv"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        _HEADER
        + f"0,EARTHQUAKE,EQ,UNIFORM_EXCITATION,,,{component},ACCELERATION,0,m/s2\n"
        + f"0.01,EARTHQUAKE,EQ,UNIFORM_EXCITATION,,,{component},ACCELERATION,1,m/s2\n"
        + f"0.02,EARTHQUAKE,EQ,UNIFORM_EXCITATION,,,{component},ACCELERATION,0,m/s2\n",
        encoding="utf-8",
    )
    return "loads/earthquake.csv"


def _draft(*, displacement_node: int = 3, reaction_node: int = 1) -> dict[str, Any]:
    text = (
        "对模型做X向地震时程分析，使用这个地震波，不考虑阻尼，"
        f"查看节点{displacement_node}的X向位移和节点{reaction_node}的X向反力"
    )
    return {
        "schema": "FEMAGENT_ANALYSIS_REQUIREMENT_DRAFT_V1",
        "profile": "TRANSIENT_UNIFORM_BASE_REQUIREMENT_V1",
        "sources": [{"sourceId": "s1", "kind": "USER_MESSAGE", "text": text}],
        "intent": {
            "type": "TRANSIENT_UNIFORM_BASE",
            "evidence": {"sourceId": "s1", "quote": "X向地震时程分析"},
        },
        "facts": [
            {
                "kind": "EXCITATION_COMPONENT",
                "source": "USER_EXPLICIT",
                "component": "X",
                "evidence": {"sourceId": "s1", "quote": "X向地震时程分析"},
            },
            {
                "kind": "LOAD_SELECTION",
                "source": "USER_EXPLICIT",
                "evidence": {"sourceId": "s1", "quote": "这个地震波"},
            },
            {
                "kind": "DAMPING_NONE",
                "source": "USER_EXPLICIT",
                "evidence": {"sourceId": "s1", "quote": "不考虑阻尼"},
            },
            {
                "kind": "RESULT_REQUEST",
                "source": "USER_EXPLICIT",
                "quantity": "DISPLACEMENT",
                "target": {"type": "NODE", "id": displacement_node},
                "component": "X",
                "evidence": {
                    "sourceId": "s1",
                    "quote": f"节点{displacement_node}的X向位移",
                },
            },
            {
                "kind": "RESULT_REQUEST",
                "source": "USER_EXPLICIT",
                "quantity": "REACTION_FORCE",
                "target": {"type": "NODE", "id": reaction_node},
                "component": "X",
                "evidence": {
                    "sourceId": "s1",
                    "quote": f"节点{reaction_node}的X向反力",
                },
            },
        ],
    }


def _write_ansys_model(tmp_path: Path) -> str:
    path = tmp_path / "model.inp"
    path.write_text(
        "/PREP7\n"
        "N,1,0,0,0\n"
        "N,2,1,0,0\n"
        "E,1,2\n"
        "D,1,ALL,0\n"
        "FINISH\n"
        "/SOLU\n"
        "ANTYPE,TRANS\n"
        "TRNOPT,FULL\n"
        "AUTOTS,OFF\n"
        "DELTIM,0.01\n"
        "TIME,0.02\n"
        "SOLVE\n"
        "FINISH\n"
        "/EXIT,NOSAVE\n",
        encoding="utf-8",
    )
    return "model.inp"


class _FakeReadyAnsysAdapter:
    def preflight(
        self,
        workspace: Path,
        *,
        model_path: str,
        load_path: str | None,
        solver_options: dict[str, Any],
    ) -> dict[str, Any]:
        del workspace
        assert model_path == "model.inp"
        assert load_path is None
        bundle = solver_options["ansysV2"]["confirmedBundleFingerprint"]
        return {
            "schemaVersion": "1.0",
            "kind": "solver_preflight",
            "solver": "ANSYS",
            "status": "READY",
            "checks": [
                {"code": "SOLVER_AVAILABLE", "status": "PASSED"},
                {"code": "ANSYS_V2_ANALYSIS_ADMISSION", "status": "PASSED"},
            ],
            "warnings": [],
            "model": {},
            "load": {},
            "executionEstimate": {"analysisSteps": 2},
            "analysisAdmission": {
                "schema": "FEMAGENT_ANSYS_V2_EXECUTION_ADMISSION_V1",
                "status": "ADMITTED",
                "profile": "ANSYS_APDL_TRANSIENT_UNIFORM_BASE_V2",
                "binding": {
                    "mode": "EXPLICIT_BUNDLE_CONFIRMATION",
                    "confirmedBundleFingerprint": bundle,
                    "currentBundleFingerprint": bundle,
                    "targetIdPolicy": "IDENTITY",
                    "semanticEquivalence": "NOT_MACHINE_PROVEN",
                },
                "executionIntentFingerprint": "e" * 64,
            },
        }


def _fake_ansys_factory(name: str) -> _FakeReadyAnsysAdapter:
    assert name == "ansys"
    return _FakeReadyAnsysAdapter()


def test_opensees_workflow_real_prepare_run_and_summary(tmp_path: Path) -> None:
    adapter = get_solver_adapter("opensees")
    if not adapter.status()["available"]:
        pytest.skip("OpenSeesPy optional dependency is unavailable")

    prepared = prepare_earthquake_workflow(
        tmp_path,
        solver="opensees",
        draft=_draft(),
        model_spec=_model(),
        load_artifact_path=_write_load(tmp_path),
    )

    assert prepared["status"] == "READY_FOR_CONFIRMATION"
    assert prepared["analysisCompletion"]["status"] == "COMPLETE"
    assert prepared["analysisReadiness"]["status"] == "READY"
    assert prepared["analysisReadiness"]["checks"]["workflowExcitedMass"] == {
        "status": "PASS",
        "component": "X",
        "massField": "mUX",
        "positiveMassNodeIds": [3],
    }
    assert prepared["render"]["status"] == "RENDERED"
    assert prepared["preflight"]["status"] == "READY"
    request = prepared["solverRunRequest"]
    assert request["solver"] == "opensees"
    assert "loadPath" not in request
    assert set(request["solverOptions"]) == {
        "responsePlanPath",
        "analysisManifestPath",
    }

    run = adapter.run(
        tmp_path,
        model_path=request["modelPath"],
        load_path=None,
        solver_options=request["solverOptions"],
    )
    assert run["status"] == "COMPLETED"

    summary = summarize_earthquake_workflow(
        tmp_path,
        workflow_manifest_path=prepared["workflowManifest"]["path"],
        workflow_manifest_sha256=prepared["workflowManifest"]["sha256"],
        run_ref=run["runId"],
    )

    assert summary["status"] == "COMPLETED"
    assert summary["run"]["runId"] == run["runId"]
    assert summary["resultInspection"]["integrity"]["status"] == "VALID"
    assert [item["requestId"] for item in summary["engineeringSummary"]] == [
        "R1",
        "R2",
    ]
    assert {item["quantity"] for item in summary["engineeringSummary"]} == {
        "DISPLACEMENT",
        "REACTION_FORCE",
    }
    for item in summary["engineeringSummary"]:
        assert item["sampleCount"] == 2
        assert math.isfinite(float(item["absolutePeak"]))
        assert item["abscissa"]["semantic"] == "TIME"


def test_opensees_uniform_base_workflow_requires_excited_direction_mass(
    tmp_path: Path,
) -> None:
    prepared = prepare_earthquake_workflow(
        tmp_path,
        solver="opensees",
        draft=_draft(),
        model_spec=_model(mass=False),
        load_artifact_path=_write_load(tmp_path),
    )

    assert prepared["status"] == "ANALYSIS_NOT_READY"
    assert prepared["render"] is None
    assert prepared["preflight"] is None
    assert prepared["solverRunRequest"] is None
    assert (
        prepared["analysisReadiness"]["checks"]["workflowExcitedMass"]["status"]
        == "FAIL"
    )
    assert any(
        issue["code"] == "EARTHQUAKE_WORKFLOW_OPENSEES_EXCITED_MASS_UNPROVEN"
        for issue in prepared["analysisReadiness"]["issues"]
    )


def test_ansys_workflow_freezes_exact_bundle_and_pr29_options(tmp_path: Path) -> None:
    model_path = _write_ansys_model(tmp_path)
    prepared = prepare_earthquake_workflow(
        tmp_path,
        solver="ansys",
        draft=_draft(displacement_node=2, reaction_node=1),
        model_spec=_small_model(),
        load_artifact_path=_write_load(tmp_path),
        solver_model_path=model_path,
        solver_adapter_factory=_fake_ansys_factory,
    )

    assert prepared["status"] == "READY_FOR_CONFIRMATION"
    assert prepared["analysisReadiness"] is None
    assert prepared["modelInspection"]["format"] == "ANSYS_APDL_TEXT"
    request = prepared["solverRunRequest"]
    assert request["solver"] == "ansys"
    assert request["modelPath"] == model_path
    assert "loadPath" not in request
    assert request["solverOptions"]["modelUnits"] == {
        "length": "m",
        "time": "s",
    }
    bundle = prepared["modelInspection"]["bundle"]["bundleFingerprint"]
    assert request["solverOptions"]["ansysV2"]["confirmedBundleFingerprint"] == bundle
    assert (
        prepared["preflight"]["analysisAdmission"]["binding"]["semanticEquivalence"]
        == "NOT_MACHINE_PROVEN"
    )
    assert any(
        item["code"]
        == "EARTHQUAKE_WORKFLOW_ANSYS_SEMANTIC_EQUIVALENCE_NOT_PROVEN"
        for item in prepared["warnings"]
    )


def test_ansys_workflow_requires_model_path(tmp_path: Path) -> None:
    prepared = prepare_earthquake_workflow(
        tmp_path,
        solver="ansys",
        draft=_draft(displacement_node=2, reaction_node=1),
        model_spec=_small_model(),
        load_artifact_path=_write_load(tmp_path),
        solver_adapter_factory=_fake_ansys_factory,
    )

    assert prepared["status"] == "NEEDS_INPUT"
    assert prepared["solverRunRequest"] is None
    assert any(
        item["code"] == "EARTHQUAKE_WORKFLOW_ANSYS_MODEL_PATH_REQUIRED"
        for item in prepared["warnings"]
    )


def test_workflow_manifest_hash_tamper_fails_closed(tmp_path: Path) -> None:
    adapter = get_solver_adapter("opensees")
    if not adapter.status()["available"]:
        pytest.skip("OpenSeesPy optional dependency is unavailable")

    prepared = prepare_earthquake_workflow(
        tmp_path,
        solver="opensees",
        draft=_draft(),
        model_spec=_model(),
        load_artifact_path=_write_load(tmp_path),
    )
    manifest = tmp_path / prepared["workflowManifest"]["path"]
    manifest.write_text(manifest.read_text(encoding="utf-8") + "\n", encoding="utf-8")

    with pytest.raises(FemCoreError) as exc_info:
        summarize_earthquake_workflow(
            tmp_path,
            workflow_manifest_path=prepared["workflowManifest"]["path"],
            workflow_manifest_sha256=prepared["workflowManifest"]["sha256"],
            run_ref="run_missing",
        )

    assert exc_info.value.code == "EARTHQUAKE_WORKFLOW_MANIFEST_HASH_MISMATCH"


def test_ready_manifest_binds_exact_frozen_run_request(tmp_path: Path) -> None:
    prepared = prepare_earthquake_workflow(
        tmp_path,
        solver="ansys",
        draft=_draft(displacement_node=2, reaction_node=1),
        model_spec=_small_model(),
        load_artifact_path=_write_load(tmp_path),
        solver_model_path=_write_ansys_model(tmp_path),
        solver_adapter_factory=_fake_ansys_factory,
    )
    manifest_path = tmp_path / prepared["workflowManifest"]["path"]
    raw = manifest_path.read_bytes()
    assert hashlib.sha256(raw).hexdigest() == prepared["workflowManifest"]["sha256"]
    manifest = json.loads(raw.decode("utf-8"))

    assert manifest["status"] == "READY_FOR_CONFIRMATION"
    assert manifest["solverRunRequest"] == prepared["solverRunRequest"]
    assert manifest["analysisSpecFingerprint"] == prepared["analysisCompletion"][
        "analysisSpecFingerprint"
    ]
    assert [item["requestId"] for item in manifest["postprocessPlan"]] == [
        "R1",
        "R2",
    ]
