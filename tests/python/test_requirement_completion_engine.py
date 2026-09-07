from __future__ import annotations

from copy import deepcopy

from fem_core.requirements import complete_engineering_requirement


def _evidence(source_id: str, quote: str) -> dict[str, str]:
    return {"sourceId": source_id, "quote": quote}


def _explicit(kind: str, source_id: str, quote: str, **values: object) -> dict[str, object]:
    return {
        "kind": kind,
        "source": "USER_EXPLICIT",
        **values,
        "evidence": _evidence(source_id, quote),
    }


def _beam_draft(*, complete: bool = False) -> dict[str, object]:
    sources = [
        {
            "sourceId": "source_1",
            "kind": "USER_MESSAGE",
            "text": "建立一个15m简支梁",
        }
    ]
    facts: list[dict[str, object]] = [
        _explicit("SPAN", "source_1", "15m", value=15, unit="m")
    ]
    if complete:
        sources.append(
            {
                "sourceId": "source_2",
                "kind": "USER_MESSAGE",
                "text": "单位用m、N、s，E=2.06e11 Pa，A=0.02m²，Iz=8e-5m⁴",
            }
        )
        facts.extend(
            [
                _explicit(
                    "UNIT_DECLARATION",
                    "source_2",
                    "单位用m、N、s",
                    dimension="length",
                    value="m",
                ),
                _explicit(
                    "UNIT_DECLARATION",
                    "source_2",
                    "单位用m、N、s",
                    dimension="force",
                    value="N",
                ),
                _explicit(
                    "UNIT_DECLARATION",
                    "source_2",
                    "单位用m、N、s",
                    dimension="time",
                    value="s",
                ),
                _explicit(
                    "YOUNGS_MODULUS",
                    "source_2",
                    "E=2.06e11 Pa",
                    value=2.06e11,
                    unit="Pa",
                ),
                _explicit(
                    "SECTION_AREA",
                    "source_2",
                    "A=0.02m²",
                    value=0.02,
                    unit="m²",
                ),
                _explicit(
                    "SECTION_IZ",
                    "source_2",
                    "Iz=8e-5m⁴",
                    value=8e-5,
                    unit="m⁴",
                ),
            ]
        )
    return {
        "schema": "FEMAGENT_ENGINEERING_REQUIREMENT_DRAFT_V1",
        "profile": "FRAME_2D_REQUIREMENT_V1",
        "sources": sources,
        "templateIntent": {
            "templateId": "SIMPLY_SUPPORTED_BEAM_2D_V1",
            "evidence": _evidence("source_1", "简支梁"),
        },
        "facts": facts,
    }


def _explicit_frame_draft() -> dict[str, object]:
    text = (
        "节点1在(0,0)m；节点2在(5,0)m；单元1连接节点1和节点2；"
        "1号节点固定；单位用m、N、s；E=2.06e11 Pa；A=0.02m²；Iz=8e-5m⁴。"
    )
    return {
        "schema": "FEMAGENT_ENGINEERING_REQUIREMENT_DRAFT_V1",
        "profile": "FRAME_2D_REQUIREMENT_V1",
        "sources": [{"sourceId": "source_1", "kind": "USER_MESSAGE", "text": text}],
        "templateIntent": None,
        "facts": [
            _explicit(
                "NODE_COORDINATE",
                "source_1",
                "节点1在(0,0)m",
                nodeId=1,
                x=0,
                y=0,
                unit="m",
            ),
            _explicit(
                "NODE_COORDINATE",
                "source_1",
                "节点2在(5,0)m",
                nodeId=2,
                x=5,
                y=0,
                unit="m",
            ),
            _explicit(
                "ELEMENT_CONNECTIVITY",
                "source_1",
                "单元1连接节点1和节点2",
                elementId=1,
                nodeI=1,
                nodeJ=2,
            ),
            _explicit(
                "NODE_CONSTRAINT",
                "source_1",
                "1号节点固定",
                nodeId=1,
                dofs=["UX", "UY", "RZ"],
            ),
            _explicit(
                "UNIT_DECLARATION",
                "source_1",
                "单位用m、N、s",
                dimension="length",
                value="m",
            ),
            _explicit(
                "UNIT_DECLARATION",
                "source_1",
                "单位用m、N、s",
                dimension="force",
                value="N",
            ),
            _explicit(
                "UNIT_DECLARATION",
                "source_1",
                "单位用m、N、s",
                dimension="time",
                value="s",
            ),
            _explicit(
                "YOUNGS_MODULUS",
                "source_1",
                "E=2.06e11 Pa",
                value=2.06e11,
                unit="Pa",
            ),
            _explicit(
                "SECTION_AREA",
                "source_1",
                "A=0.02m²",
                value=0.02,
                unit="m²",
            ),
            _explicit(
                "SECTION_IZ",
                "source_1",
                "Iz=8e-5m⁴",
                value=8e-5,
                unit="m⁴",
            ),
        ],
    }


def test_simple_beam_without_properties_is_incomplete() -> None:
    result = complete_engineering_requirement(_beam_draft())

    assert result["status"] == "INCOMPLETE"
    assert result["candidateModelSpec"] is None
    missing_subjects = {item["subject"] for item in result["missing"]}
    assert {
        "units.force",
        "units.time",
        "material.youngsModulus",
        "section.area",
        "section.iz",
    } <= missing_subjects
    assert "units.length" not in missing_subjects


def test_fully_specified_simple_beam_completes_to_pr21_candidate() -> None:
    result = complete_engineering_requirement(_beam_draft(complete=True))

    assert result["status"] == "COMPLETE"
    spec = result["candidateModelSpec"]
    assert spec is not None
    assert spec["units"] == {"length": "m", "force": "N", "time": "s"}
    assert spec["nodes"] == [{"id": 1, "x": 0, "y": 0}, {"id": 2, "x": 15, "y": 0}]
    assert spec["materials"] == [
        {"id": 1, "type": "LINEAR_ELASTIC", "youngsModulus": 2.06e11}
    ]
    assert spec["sections"] == [
        {"id": 1, "type": "FRAME_2D", "area": 0.02, "iz": 8e-5}
    ]
    assert spec["elements"] == [
        {
            "id": 1,
            "type": "ELASTIC_FRAME_2D",
            "formulation": "EULER_BERNOULLI",
            "nodeI": 1,
            "nodeJ": 2,
            "materialId": 1,
            "sectionId": 1,
        }
    ]
    assert spec["constraints"] == [
        {"nodeId": 1, "dofs": ["UX", "UY"]},
        {"nodeId": 2, "dofs": ["UY"]},
    ]
    assert spec["nodalMasses"] == []
    assert result["modelSpecValidation"]["status"] == "VALID"
    assert result["modelSpecFingerprint"] == result["modelSpecValidation"]["modelSpecFingerprint"]


def test_numeric_evidence_mismatch_is_invalid_draft() -> None:
    draft = _beam_draft()
    draft["facts"][0]["value"] = 12

    result = complete_engineering_requirement(draft)

    assert result["status"] == "INVALID_DRAFT"
    assert result["candidateModelSpec"] is None
    assert any(
        issue["code"] == "REQUIREMENT_EVIDENCE_NUMERIC_MISMATCH"
        for issue in result["issues"]
    )


def test_template_support_conflict_blocks_completion() -> None:
    draft = _beam_draft(complete=True)
    draft["sources"].append(
        {
            "sourceId": "source_3",
            "kind": "USER_MESSAGE",
            "text": "节点2约束UX和UY",
        }
    )
    draft["facts"].append(
        _explicit(
            "NODE_CONSTRAINT",
            "source_3",
            "节点2约束UX和UY",
            nodeId=2,
            dofs=["UX", "UY"],
        )
    )

    result = complete_engineering_requirement(draft)

    assert result["status"] == "CONFLICT"
    assert result["candidateModelSpec"] is None
    assert any(item["code"] == "REQUIREMENT_FACT_CONFLICT" for item in result["conflicts"])


def test_explicit_length_unit_conflicting_with_span_unit_blocks() -> None:
    draft = _beam_draft(complete=True)
    for fact in draft["facts"]:
        if fact["kind"] == "UNIT_DECLARATION" and fact["dimension"] == "length":
            fact["value"] = "mm"
            fact["evidence"] = _evidence("source_2", "单位用m、N、s")
            break

    result = complete_engineering_requirement(draft)

    assert result["status"] in {"INVALID_DRAFT", "CONFLICT"}
    assert result["candidateModelSpec"] is None


def test_complete_no_template_explicit_frame_is_supported() -> None:
    result = complete_engineering_requirement(_explicit_frame_draft())

    assert result["status"] == "COMPLETE"
    assert result["template"] is None
    spec = result["candidateModelSpec"]
    assert spec is not None
    assert len(spec["nodes"]) == 2
    assert len(spec["elements"]) == 1
    assert spec["elements"][0]["materialId"] == 1
    assert spec["elements"][0]["sectionId"] == 1


def test_missing_explicit_topology_is_not_invented_without_template() -> None:
    draft = _explicit_frame_draft()
    draft["facts"] = [fact for fact in draft["facts"] if fact["kind"] != "ELEMENT_CONNECTIVITY"]

    result = complete_engineering_requirement(draft)

    assert result["status"] == "INCOMPLETE"
    assert result["candidateModelSpec"] is None
    assert any(item["subject"] == "elements" for item in result["missing"])


def test_completion_is_deterministic_under_fact_and_source_ordering() -> None:
    first = _beam_draft(complete=True)
    second = deepcopy(first)
    second["facts"] = list(reversed(second["facts"]))
    second["sources"] = list(reversed(second["sources"]))

    result_a = complete_engineering_requirement(first)
    result_b = complete_engineering_requirement(second)

    assert result_a["status"] == result_b["status"] == "COMPLETE"
    assert result_a["requirementFingerprint"] == result_b["requirementFingerprint"]
    assert result_a["modelSpecFingerprint"] == result_b["modelSpecFingerprint"]
    assert result_a["candidateModelSpec"] == result_b["candidateModelSpec"]
