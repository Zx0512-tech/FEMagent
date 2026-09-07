from __future__ import annotations

from pathlib import Path

from fem_core.model_spec import (
    evaluate_engineering_model_readiness,
    render_opensees_frame_2d,
    validate_engineering_model_spec,
)
from fem_core.opensees_python_inspection import inspect_opensees_python
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


def _simple_support_draft(*, complete: bool) -> dict[str, object]:
    sources: list[dict[str, str]] = [
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


def test_complete_requirement_reaches_pr21_pr22_pr23_and_static_model_intelligence(
    tmp_path: Path,
) -> None:
    completion = complete_engineering_requirement(_simple_support_draft(complete=True))

    assert completion["status"] == "COMPLETE"
    spec = completion["candidateModelSpec"]
    assert spec is not None

    validation = validate_engineering_model_spec(spec)
    assert validation["status"] == "VALID"
    assert validation["modelSpecFingerprint"] == completion["modelSpecFingerprint"]

    readiness = evaluate_engineering_model_readiness(spec)
    assert readiness["status"] == "READY"
    assert readiness["modelSpecFingerprint"] == completion["modelSpecFingerprint"]

    render = render_opensees_frame_2d(tmp_path, spec)
    assert render["status"] == "RENDERED"
    assert render["input"]["modelSpecFingerprint"] == completion["modelSpecFingerprint"]

    inspection = inspect_opensees_python(tmp_path, render["artifacts"]["modelPath"])
    assert inspection["classification"] == "MODEL_CONFIRMED"
    assert inspection["dynamicGeneration"] is False
    assert inspection["safetyFindings"] == []
    assert inspection["staticTopology"] == {
        "nodeCount": 2,
        "elementCount": 1,
        "nodeTags": [1, 2],
        "elementTags": [1],
        "basis": "LITERAL_AST_CALLS",
    }

    model_text = (tmp_path / render["artifacts"]["modelPath"]).read_text(encoding="utf-8")
    for forbidden in (
        "ops.timeSeries(",
        "ops.pattern(",
        "ops.integrator(",
        "ops.algorithm(",
        "ops.analysis(",
        "ops.analyze(",
        "ops.eigen(",
    ):
        assert forbidden not in model_text


def test_incomplete_requirement_never_produces_a_renderable_candidate(tmp_path: Path) -> None:
    completion = complete_engineering_requirement(_simple_support_draft(complete=False))

    assert completion["status"] == "INCOMPLETE"
    assert completion["candidateModelSpec"] is None
    assert completion["modelSpecFingerprint"] is None
    assert not (tmp_path / ".femagent" / "generated-models").exists()
