from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from fem_core.errors import FemCoreError
from fem_core.repair import plan_controlled_repair, retry_controlled_repair
from fem_core.solvers import get_solver_adapter
from fem_core.workflows import prepare_earthquake_workflow

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


def _write_load(tmp_path: Path, component: str = "X") -> str:
    path = tmp_path / "loads" / f"earthquake_{component}.csv"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        _HEADER
        + f"0,EARTHQUAKE,EQ,UNIFORM_EXCITATION,,,{component},ACCELERATION,0,m/s2\n"
        + f"0.01,EARTHQUAKE,EQ,UNIFORM_EXCITATION,,,{component},ACCELERATION,1,m/s2\n"
        + f"0.02,EARTHQUAKE,EQ,UNIFORM_EXCITATION,,,{component},ACCELERATION,0,m/s2\n",
        encoding="utf-8",
    )
    return f"loads/earthquake_{component}.csv"


def _draft(
    *,
    damping: bool = True,
    excitation_component: bool = True,
    result_component: bool = True,
) -> dict[str, Any]:
    text = (
        "做地震时程分析，使用这个地震波，不考虑阻尼，"
        "查看节点3的X向位移和节点1的X向反力"
    )
    facts: list[dict[str, Any]] = [
        {
            "kind": "LOAD_SELECTION",
            "source": "USER_EXPLICIT",
            "evidence": {"sourceId": "s1", "quote": "这个地震波"},
        },
        {
            "kind": "RESULT_REQUEST",
            "source": "USER_EXPLICIT",
            "quantity": "DISPLACEMENT",
            "target": {"type": "NODE", "id": 3},
            **({"component": "X"} if result_component else {}),
            "evidence": {
                "sourceId": "s1",
                "quote": "节点3的X向位移" if result_component else "节点3的位移",
            },
        },
        {
            "kind": "RESULT_REQUEST",
            "source": "USER_EXPLICIT",
            "quantity": "REACTION_FORCE",
            "target": {"type": "NODE", "id": 1},
            "component": "X",
            "evidence": {"sourceId": "s1", "quote": "节点1的X向反力"},
        },
    ]
    if damping:
        facts.insert(
            1,
            {
                "kind": "DAMPING_NONE",
                "source": "USER_EXPLICIT",
                "evidence": {"sourceId": "s1", "quote": "不考虑阻尼"},
            },
        )
    if excitation_component:
        facts.insert(
            0,
            {
                "kind": "EXCITATION_COMPONENT",
                "source": "USER_EXPLICIT",
                "component": "X",
                "evidence": {"sourceId": "s1", "quote": "X向"},
            },
        )
        text = "做X向地震时程分析，使用这个地震波，不考虑阻尼，查看节点3的X向位移和节点1的X向反力"
    if not result_component:
        text = text.replace("节点3的X向位移", "节点3的位移")
    return {
        "schema": "FEMAGENT_ANALYSIS_REQUIREMENT_DRAFT_V1",
        "profile": "TRANSIENT_UNIFORM_BASE_REQUIREMENT_V1",
        "sources": [{"sourceId": "s1", "kind": "USER_MESSAGE", "text": text}],
        "intent": {
            "type": "TRANSIENT_UNIFORM_BASE",
            "evidence": {"sourceId": "s1", "quote": "地震时程分析"},
        },
        "facts": facts,
    }


def _workflow_input(
    tmp_path: Path,
    *,
    model: dict[str, Any] | None = None,
    draft: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "solver": "opensees",
        "draft": draft or _draft(),
        "modelSpec": model or _model(),
        "loadArtifactPath": _write_load(tmp_path),
    }


def _prepare(tmp_path: Path, workflow_input: dict[str, Any]) -> dict[str, Any]:
    return prepare_earthquake_workflow(
        tmp_path,
        solver=workflow_input["solver"],
        draft=workflow_input["draft"],
        model_spec=workflow_input["modelSpec"],
        load_artifact_path=workflow_input["loadArtifactPath"],
        semantic_context=workflow_input.get("semanticContext"),
        solver_model_path=workflow_input.get("solverModelPath"),
    )


def test_missing_damping_plan_never_defaults_and_confirmed_none_recovers(
    tmp_path: Path,
) -> None:
    if not get_solver_adapter("opensees").status()["available"]:
        pytest.skip("OpenSeesPy optional dependency is unavailable")
    workflow_input = _workflow_input(tmp_path, draft=_draft(damping=False))
    failed = _prepare(tmp_path, workflow_input)
    assert failed["status"] == "NEEDS_INPUT"

    plan = plan_controlled_repair(
        workflow_input=workflow_input,
        failed_preparation=failed,
    )

    assert plan["status"] == "USER_ACTION_REQUIRED"
    action = next(item for item in plan["actions"] if item["subject"] == "damping")
    assert action["resolutionTypes"] == [
        "ADD_DAMPING_NONE",
        "ADD_RAYLEIGH_DAMPING",
    ]
    assert plan["rules"]["engineeringFactInferenceAllowed"] is False
    assert plan["rules"]["solverExecutionAllowed"] is False

    retry = retry_controlled_repair(
        tmp_path,
        workflow_input=workflow_input,
        failed_preparation=failed,
        plan_fingerprint=plan["planFingerprint"],
        resolutions=[
            {
                "actionId": action["actionId"],
                "type": "ADD_DAMPING_NONE",
                "sourceText": "本次分析不考虑阻尼",
                "quote": "不考虑阻尼",
            }
        ],
    )

    assert retry["status"] == "RECOVERED_TO_READY"
    assert retry["preparation"]["status"] == "READY_FOR_CONFIRMATION"
    damping = retry["preparation"]["analysisCompletion"]["candidateAnalysisSpec"][
        "definition"
    ]["damping"]
    assert damping == {"type": "NONE"}


def test_missing_result_component_can_only_be_repaired_with_new_explicit_evidence(
    tmp_path: Path,
) -> None:
    if not get_solver_adapter("opensees").status()["available"]:
        pytest.skip("OpenSeesPy optional dependency is unavailable")
    workflow_input = _workflow_input(
        tmp_path,
        draft=_draft(result_component=False),
    )
    failed = _prepare(tmp_path, workflow_input)
    assert failed["status"] == "NEEDS_INPUT"

    plan = plan_controlled_repair(
        workflow_input=workflow_input,
        failed_preparation=failed,
    )
    action = next(
        item
        for item in plan["actions"]
        if item["subject"] == "resultRequests[0].component"
    )
    retry = retry_controlled_repair(
        tmp_path,
        workflow_input=workflow_input,
        failed_preparation=failed,
        plan_fingerprint=plan["planFingerprint"],
        resolutions=[
            {
                "actionId": action["actionId"],
                "type": "SET_RESULT_COMPONENT",
                "component": "X",
                "sourceText": "查看节点3的X向位移",
                "quote": "节点3的X向位移",
            }
        ],
    )

    assert retry["status"] == "RECOVERED_TO_READY"
    request = retry["preparation"]["analysisCompletion"]["candidateAnalysisSpec"][
        "resultRequests"
    ][0]
    assert request["component"] == "X"


def test_missing_excitation_component_repair_is_evidence_backed(tmp_path: Path) -> None:
    if not get_solver_adapter("opensees").status()["available"]:
        pytest.skip("OpenSeesPy optional dependency is unavailable")
    workflow_input = _workflow_input(
        tmp_path,
        draft=_draft(excitation_component=False),
    )
    failed = _prepare(tmp_path, workflow_input)
    assert failed["status"] == "NEEDS_INPUT"
    plan = plan_controlled_repair(
        workflow_input=workflow_input,
        failed_preparation=failed,
    )
    action = next(
        item
        for item in plan["actions"]
        if item["subject"] == "excitation.component"
    )

    retry = retry_controlled_repair(
        tmp_path,
        workflow_input=workflow_input,
        failed_preparation=failed,
        plan_fingerprint=plan["planFingerprint"],
        resolutions=[
            {
                "actionId": action["actionId"],
                "type": "SET_EXCITATION_COMPONENT",
                "component": "X",
                "sourceText": "本次采用X向地震输入",
                "quote": "X向",
            }
        ],
    )

    assert retry["status"] == "RECOVERED_TO_READY"
    assert (
        retry["preparation"]["analysisCompletion"]["candidateAnalysisSpec"][
            "definition"
        ]["excitation"]["component"]
        == "X"
    )


def test_missing_excited_mass_requires_revised_model_and_never_invents_mass(
    tmp_path: Path,
) -> None:
    if not get_solver_adapter("opensees").status()["available"]:
        pytest.skip("OpenSeesPy optional dependency is unavailable")
    workflow_input = _workflow_input(tmp_path, model=_model(mass=False))
    failed = _prepare(tmp_path, workflow_input)
    assert failed["status"] == "ANALYSIS_NOT_READY"

    plan = plan_controlled_repair(
        workflow_input=workflow_input,
        failed_preparation=failed,
    )
    assert plan["status"] == "MANUAL_ENGINEERING_CHANGE_REQUIRED"
    action = next(
        item for item in plan["actions"] if item["actionId"] == "repair_model_mass"
    )
    assert action["resolutionTypes"] == ["REPLACE_MODEL_SPEC"]

    retry = retry_controlled_repair(
        tmp_path,
        workflow_input=workflow_input,
        failed_preparation=failed,
        plan_fingerprint=plan["planFingerprint"],
        resolutions=[
            {
                "actionId": action["actionId"],
                "type": "REPLACE_MODEL_SPEC",
                "modelSpec": _model(mass=True),
            }
        ],
    )

    assert retry["status"] == "RECOVERED_TO_READY"
    assert retry["workflowInput"]["modelSpec"]["nodalMasses"] == [
        {"nodeId": 3, "mUX": 100.0, "mUY": 100.0}
    ]


def test_stale_repair_plan_fingerprint_fails_closed(tmp_path: Path) -> None:
    workflow_input = _workflow_input(tmp_path, draft=_draft(damping=False))
    failed = _prepare(tmp_path, workflow_input)
    plan = plan_controlled_repair(
        workflow_input=workflow_input,
        failed_preparation=failed,
    )

    with pytest.raises(FemCoreError) as exc_info:
        retry_controlled_repair(
            tmp_path,
            workflow_input=workflow_input,
            failed_preparation=failed,
            plan_fingerprint="0" * 64,
            resolutions=[],
        )

    assert exc_info.value.code == "CONTROLLED_REPAIR_STALE_PLAN"
    assert plan["planFingerprint"] != "0" * 64


def test_semantic_ambiguity_is_manual_and_has_no_auto_resolution() -> None:
    workflow_input = {
        "solver": "opensees",
        "draft": {"facts": []},
        "modelSpec": {},
        "loadArtifactPath": "loads/eq.csv",
    }
    failed = {
        "status": "NEEDS_INPUT",
        "analysisCompletion": {
            "status": "INCOMPLETE",
            "missing": [],
            "ambiguous": [
                {
                    "code": "ANALYSIS_REQUIREMENT_ROLE_AMBIGUOUS",
                    "subject": "semanticRole.GIRDER_END",
                    "message": "multiple",
                    "candidates": ["GIRDER_END_LEFT", "GIRDER_END_RIGHT"],
                }
            ],
            "conflicts": [],
            "issues": [],
        },
        "analysisReadiness": None,
        "preflight": None,
        "warnings": [],
    }

    plan = plan_controlled_repair(
        workflow_input=workflow_input,
        failed_preparation=failed,
    )

    assert plan["status"] == "MANUAL_ENGINEERING_CHANGE_REQUIRED"
    action = plan["actions"][0]
    assert action["subject"] == "semanticRole.GIRDER_END"
    assert action["resolutionTypes"] == []
    assert action["details"]["candidates"] == [
        "GIRDER_END_LEFT",
        "GIRDER_END_RIGHT",
    ]


def test_ansys_missing_model_path_is_user_input_not_guessed() -> None:
    workflow_input = {
        "solver": "ansys",
        "draft": {},
        "modelSpec": {},
        "loadArtifactPath": "loads/eq.csv",
    }
    failed = {
        "status": "NEEDS_INPUT",
        "analysisCompletion": {"status": "COMPLETE"},
        "analysisReadiness": None,
        "preflight": None,
        "warnings": [
            {
                "code": "EARTHQUAKE_WORKFLOW_ANSYS_MODEL_PATH_REQUIRED",
                "message": "path required",
            }
        ],
    }

    plan = plan_controlled_repair(
        workflow_input=workflow_input,
        failed_preparation=failed,
    )

    action = next(
        item
        for item in plan["actions"]
        if item["actionId"] == "repair_ansys_model_path"
    )
    assert plan["status"] == "USER_ACTION_REQUIRED"
    assert action["resolutionTypes"] == ["SET_ANSYS_MODEL_PATH"]
