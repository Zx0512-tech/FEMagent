from __future__ import annotations

import json
from pathlib import Path

from fem_core.analysis_requirements import complete_engineering_analysis_requirement
from fem_core.model_inspection import inspect_model
from fem_core.model_spec import render_opensees_frame_2d

MODEL_FIXTURE = Path("tests/fixtures/model_spec/simple-portal-frame.json")
_HEADER = (
    "time_s,load_kind,channel_id,application_type,target_type,target_id,"
    "component,quantity,value,unit\n"
)


def _model() -> dict:
    return json.loads(MODEL_FIXTURE.read_text(encoding="utf-8"))


def _write_load(tmp_path: Path, component: str = "X") -> str:
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


def _draft(*, damping: bool = True, component: str | None = "X") -> dict:
    text = (
        "对模型做X向地震时程分析，使用这个地震波，不考虑阻尼，"
        "查看节点3的X向位移和节点1的X向反力"
    )
    facts: list[dict] = [
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
            "kind": "RESULT_REQUEST",
            "source": "USER_EXPLICIT",
            "quantity": "DISPLACEMENT",
            "target": {"type": "NODE", "id": 3},
            **({} if component is None else {"component": component}),
            "evidence": {"sourceId": "s1", "quote": "节点3的X向位移"},
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
            2,
            {
                "kind": "DAMPING_NONE",
                "source": "USER_EXPLICIT",
                "evidence": {"sourceId": "s1", "quote": "不考虑阻尼"},
            },
        )
    return {
        "schema": "FEMAGENT_ANALYSIS_REQUIREMENT_DRAFT_V1",
        "profile": "TRANSIENT_UNIFORM_BASE_REQUIREMENT_V1",
        "sources": [{"sourceId": "s1", "kind": "USER_MESSAGE", "text": text}],
        "intent": {
            "type": "TRANSIENT_UNIFORM_BASE",
            "evidence": {"sourceId": "s1", "quote": "X向地震时程分析"},
        },
        "facts": facts,
    }


def _semantic_draft() -> dict:
    text = (
        "对模型做X向地震时程分析，使用这个地震波，不考虑阻尼，"
        "查看梁端的X向位移和塔底的X向反力"
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
                "target": {"type": "SEMANTIC_ROLE_TYPE", "roleType": "GIRDER_END"},
                "component": "X",
                "evidence": {"sourceId": "s1", "quote": "梁端的X向位移"},
            },
            {
                "kind": "RESULT_REQUEST",
                "source": "USER_EXPLICIT",
                "quantity": "REACTION_FORCE",
                "target": {"type": "SEMANTIC_ROLE_TYPE", "roleType": "TOWER_BASE"},
                "component": "X",
                "evidence": {"sourceId": "s1", "quote": "塔底的X向反力"},
            },
        ],
    }


def _semantic_context(tmp_path: Path, model: dict, *, duplicate_girder: bool = False) -> dict:
    rendered = render_opensees_frame_2d(tmp_path, model)
    assert rendered["status"] == "RENDERED"
    model_path = rendered["artifacts"]["modelPath"]
    inspected = inspect_model(tmp_path, model_path)
    fingerprint = inspected["bundle"]["bundleFingerprint"]
    roles = [
        {
            "roleId": "GIRDER_END_RIGHT",
            "roleType": "GIRDER_END",
            "entity": {"type": "NODE", "id": 3},
        },
        {
            "roleId": "TOWER_BASE_LEFT",
            "roleType": "TOWER_BASE",
            "entity": {"type": "NODE", "id": 1},
        },
    ]
    if duplicate_girder:
        roles.append(
            {
                "roleId": "GIRDER_END_LEFT",
                "roleType": "GIRDER_END",
                "entity": {"type": "NODE", "id": 4},
            }
        )
    manifest = tmp_path / "semantic_roles.json"
    manifest.write_text(
        json.dumps(
            {
                "schemaVersion": "1.0",
                "kind": "engineering_semantic_roles",
                "model": {"bundleFingerprint": fingerprint},
                "roles": roles,
            }
        ),
        encoding="utf-8",
    )
    return {
        "modelPath": model_path,
        "manifestPath": "semantic_roles.json",
    }


def test_complete_direct_node_requirement_builds_valid_analysis_spec(tmp_path: Path) -> None:
    model = _model()
    load_path = _write_load(tmp_path)

    result = complete_engineering_analysis_requirement(
        tmp_path,
        draft=_draft(),
        model_spec=model,
        load_artifact_path=load_path,
    )

    assert result["status"] == "COMPLETE"
    candidate = result["candidateAnalysisSpec"]
    assert candidate["schemaVersion"] == "2.0"
    assert candidate["analysisType"] == "TRANSIENT"
    assert candidate["definition"]["time"] == {"timeStep": 0.01, "duration": 0.02}
    assert candidate["definition"]["damping"] == {"type": "NONE"}
    assert candidate["definition"]["excitation"]["component"] == "X"
    assert candidate["definition"]["excitation"]["loadArtifact"]["path"] == load_path
    assert len(candidate["definition"]["excitation"]["loadArtifact"]["sha256"]) == 64
    assert candidate["resultRequests"] == [
        {
            "requestId": "R1",
            "quantity": "DISPLACEMENT",
            "target": {"type": "NODE", "id": 3},
            "component": "X",
        },
        {
            "requestId": "R2",
            "quantity": "REACTION_FORCE",
            "target": {"type": "NODE", "id": 1},
            "component": "X",
        },
    ]
    assert result["analysisSpecValidation"]["status"] == "VALID"
    assert len(result["analysisSpecFingerprint"]) == 64


def test_missing_damping_never_defaults_to_none(tmp_path: Path) -> None:
    result = complete_engineering_analysis_requirement(
        tmp_path,
        draft=_draft(damping=False),
        model_spec=_model(),
        load_artifact_path=_write_load(tmp_path),
    )

    assert result["status"] == "INCOMPLETE"
    assert result["candidateAnalysisSpec"] is None
    assert any(item["subject"] == "damping" for item in result["missing"])


def test_missing_result_component_remains_incomplete(tmp_path: Path) -> None:
    result = complete_engineering_analysis_requirement(
        tmp_path,
        draft=_draft(component=None),
        model_spec=_model(),
        load_artifact_path=_write_load(tmp_path),
    )

    assert result["status"] == "INCOMPLETE"
    assert any(
        item["subject"] == "resultRequests[0].component"
        for item in result["missing"]
    )


def test_context_load_component_mismatch_is_conflict(tmp_path: Path) -> None:
    result = complete_engineering_analysis_requirement(
        tmp_path,
        draft=_draft(),
        model_spec=_model(),
        load_artifact_path=_write_load(tmp_path, "Y"),
    )

    assert result["status"] == "CONFLICT"
    assert any(
        item["subject"] == "loadArtifact.component"
        for item in result["conflicts"]
    )


def test_rayleigh_coefficients_must_be_explicit_and_are_preserved(tmp_path: Path) -> None:
    draft = _draft(damping=False)
    draft["sources"][0]["text"] = draft["sources"][0]["text"].replace(
        "不考虑阻尼",
        "Rayleigh阻尼 alphaM=0.1 betaK=0.002",
    )
    draft["facts"].insert(
        2,
        {
            "kind": "RAYLEIGH_DAMPING",
            "source": "USER_EXPLICIT",
            "alphaM": 0.1,
            "betaK": 0.002,
            "evidence": {
                "sourceId": "s1",
                "quote": "Rayleigh阻尼 alphaM=0.1 betaK=0.002",
            },
        },
    )

    result = complete_engineering_analysis_requirement(
        tmp_path,
        draft=draft,
        model_spec=_model(),
        load_artifact_path=_write_load(tmp_path),
    )

    assert result["status"] == "COMPLETE"
    assert result["candidateAnalysisSpec"]["definition"]["damping"] == {
        "type": "RAYLEIGH",
        "alphaM": 0.1,
        "betaK": 0.002,
    }


def test_semantic_role_types_resolve_deterministically_to_nodes(tmp_path: Path) -> None:
    model = _model()
    context = _semantic_context(tmp_path, model)

    result = complete_engineering_analysis_requirement(
        tmp_path,
        draft=_semantic_draft(),
        model_spec=model,
        load_artifact_path=_write_load(tmp_path),
        semantic_context=context,
    )

    assert result["status"] == "COMPLETE"
    requests = result["candidateAnalysisSpec"]["resultRequests"]
    assert requests[0]["target"] == {"type": "NODE", "id": 3}
    assert requests[1]["target"] == {"type": "NODE", "id": 1}
    role_facts = [
        fact
        for fact in result["derivedFacts"]
        if fact.get("ruleId") == "SEMANTIC_ROLE_TYPE_RESOLUTION_V1"
    ]
    assert {fact["roleId"] for fact in role_facts} == {
        "GIRDER_END_RIGHT",
        "TOWER_BASE_LEFT",
    }


def test_multiple_roles_of_same_type_are_reported_as_ambiguous(tmp_path: Path) -> None:
    model = _model()
    context = _semantic_context(tmp_path, model, duplicate_girder=True)

    result = complete_engineering_analysis_requirement(
        tmp_path,
        draft=_semantic_draft(),
        model_spec=model,
        load_artifact_path=_write_load(tmp_path),
        semantic_context=context,
    )

    assert result["status"] == "INCOMPLETE"
    assert result["candidateAnalysisSpec"] is None
    ambiguity = next(
        item for item in result["ambiguous"]
        if item["subject"] == "semanticRole.GIRDER_END"
    )
    assert ambiguity["candidates"] == ["GIRDER_END_LEFT", "GIRDER_END_RIGHT"]


def test_semantic_target_without_context_is_incomplete(tmp_path: Path) -> None:
    result = complete_engineering_analysis_requirement(
        tmp_path,
        draft=_semantic_draft(),
        model_spec=_model(),
        load_artifact_path=_write_load(tmp_path),
    )

    assert result["status"] == "INCOMPLETE"
    assert any(
        item["code"] == "ANALYSIS_REQUIREMENT_CONTEXT_MISSING"
        for item in result["missing"]
    )


def test_reaction_request_on_unrestrained_dof_conflicts_with_model(tmp_path: Path) -> None:
    model = _model()
    model["constraints"] = [{"nodeId": 1, "dofs": ["UY", "RZ"]}]
    result = complete_engineering_analysis_requirement(
        tmp_path,
        draft=_draft(),
        model_spec=model,
        load_artifact_path=_write_load(tmp_path),
    )

    assert result["status"] == "CONFLICT"
    assert any(
        "REACTION_FORCE" in item["message"]
        for item in result["conflicts"]
    )


def test_unknown_draft_field_is_invalid_draft(tmp_path: Path) -> None:
    draft = _draft()
    draft["facts"][0]["guess"] = "do not admit"

    result = complete_engineering_analysis_requirement(
        tmp_path,
        draft=draft,
        model_spec=_model(),
        load_artifact_path=_write_load(tmp_path),
    )

    assert result["status"] == "INVALID_DRAFT"
    assert any(
        item["code"] == "ANALYSIS_REQUIREMENT_UNKNOWN_FIELD"
        for item in result["issues"]
    )
