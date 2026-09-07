from __future__ import annotations

import pytest

from fem_core.requirements.evidence import validate_explicit_evidence
from fem_core.requirements.schema import validate_requirement_draft_schema
from fem_core.requirements.templates import expand_beam_template, validate_template_intent


def _source(text: str = "建立一个15m简支梁") -> dict[str, str]:
    return {"sourceId": "source_1", "kind": "USER_MESSAGE", "text": text}


def _span_fact(*, value: float = 15, unit: str = "m", quote: str = "15m") -> dict[str, object]:
    return {
        "kind": "SPAN",
        "source": "USER_EXPLICIT",
        "value": value,
        "unit": unit,
        "evidence": {"sourceId": "source_1", "quote": quote},
    }


def _draft(*, facts: list[dict[str, object]] | None = None) -> dict[str, object]:
    return {
        "schema": "FEMAGENT_ENGINEERING_REQUIREMENT_DRAFT_V1",
        "profile": "FRAME_2D_REQUIREMENT_V1",
        "sources": [_source()],
        "templateIntent": None,
        "facts": facts or [],
    }


def test_draft_schema_accepts_minimal_v1_envelope() -> None:
    result = validate_requirement_draft_schema(_draft())

    assert result["status"] == "VALID"
    assert result["issues"] == []
    assert result["normalizedDraft"]["schema"] == "FEMAGENT_ENGINEERING_REQUIREMENT_DRAFT_V1"


def test_draft_schema_rejects_unknown_recursive_fields() -> None:
    draft = _draft(facts=[{**_span_fact(), "path": "geometry.span"}])

    result = validate_requirement_draft_schema(draft)

    assert result["status"] == "INVALID"
    assert any(
        issue["code"] == "REQUIREMENT_DRAFT_UNKNOWN_FIELD"
        and issue["path"] == "facts[0].path"
        for issue in result["issues"]
    )


def test_draft_schema_rejects_duplicate_source_ids() -> None:
    draft = _draft()
    draft["sources"] = [_source(), _source("第二条消息")]

    result = validate_requirement_draft_schema(draft)

    assert result["status"] == "INVALID"
    assert any(issue["code"] == "REQUIREMENT_DRAFT_INVALID_SOURCE" for issue in result["issues"])


def test_explicit_evidence_rejects_quote_not_in_source() -> None:
    fact = _span_fact(quote="20m")

    result = validate_explicit_evidence(
        sources={"source_1": "建立一个15m简支梁"},
        fact=fact,
    )

    assert any(issue["code"] == "REQUIREMENT_EVIDENCE_QUOTE_NOT_FOUND" for issue in result["issues"])


def test_span_evidence_rejects_numeric_mismatch() -> None:
    fact = _span_fact(value=12, quote="15m")

    result = validate_explicit_evidence(
        sources={"source_1": "建立一个15m简支梁"},
        fact=fact,
    )

    assert any(issue["code"] == "REQUIREMENT_EVIDENCE_NUMERIC_MISMATCH" for issue in result["issues"])


def test_span_evidence_rejects_unit_mismatch() -> None:
    fact = _span_fact(unit="mm", quote="15m")

    result = validate_explicit_evidence(
        sources={"source_1": "建立一个15m简支梁"},
        fact=fact,
    )

    assert any(issue["code"] == "REQUIREMENT_EVIDENCE_UNIT_MISMATCH" for issue in result["issues"])


@pytest.mark.parametrize(
    ("template_id", "quote"),
    [
        ("SIMPLY_SUPPORTED_BEAM_2D_V1", "简支梁"),
        ("SIMPLY_SUPPORTED_BEAM_2D_V1", "simply supported beam"),
        ("CANTILEVER_BEAM_2D_V1", "悬臂梁"),
        ("CANTILEVER_BEAM_2D_V1", "cantilever beam"),
        ("FIXED_FIXED_BEAM_2D_V1", "两端固支梁"),
        ("FIXED_FIXED_BEAM_2D_V1", "双端固支梁"),
        ("FIXED_FIXED_BEAM_2D_V1", "fixed-fixed beam"),
        ("FIXED_FIXED_BEAM_2D_V1", "fixed fixed beam"),
    ],
)
def test_template_intent_accepts_only_versioned_exact_aliases(template_id: str, quote: str) -> None:
    source_text = f"请建立一根15m的{quote}"
    result = validate_template_intent(
        sources={"source_1": source_text},
        template_intent={
            "templateId": template_id,
            "evidence": {"sourceId": "source_1", "quote": quote},
        },
    )

    assert result["status"] == "VALID"
    assert result["templateId"] == template_id
    assert result["issues"] == []


def test_template_intent_rejects_broad_fixed_beam_alias() -> None:
    result = validate_template_intent(
        sources={"source_1": "建立一个15m固支梁"},
        template_intent={
            "templateId": "FIXED_FIXED_BEAM_2D_V1",
            "evidence": {"sourceId": "source_1", "quote": "固支梁"},
        },
    )

    assert result["status"] == "INVALID"
    assert any(issue["code"] == "REQUIREMENT_TEMPLATE_EVIDENCE_MISMATCH" for issue in result["issues"])


def test_template_intent_rejects_wrong_template_for_exact_alias() -> None:
    result = validate_template_intent(
        sources={"source_1": "建立一个15m简支梁"},
        template_intent={
            "templateId": "CANTILEVER_BEAM_2D_V1",
            "evidence": {"sourceId": "source_1", "quote": "简支梁"},
        },
    )

    assert result["status"] == "INVALID"
    assert any(issue["code"] == "REQUIREMENT_TEMPLATE_EVIDENCE_MISMATCH" for issue in result["issues"])


@pytest.mark.parametrize(
    ("template_id", "expected_constraints"),
    [
        (
            "SIMPLY_SUPPORTED_BEAM_2D_V1",
            [{"nodeId": 1, "dofs": ["UX", "UY"]}, {"nodeId": 2, "dofs": ["UY"]}],
        ),
        (
            "CANTILEVER_BEAM_2D_V1",
            [{"nodeId": 1, "dofs": ["UX", "UY", "RZ"]}],
        ),
        (
            "FIXED_FIXED_BEAM_2D_V1",
            [
                {"nodeId": 1, "dofs": ["UX", "UY", "RZ"]},
                {"nodeId": 2, "dofs": ["UX", "UY", "RZ"]},
            ],
        ),
    ],
)
def test_beam_template_expansion_is_canonical_and_source_tracked(
    template_id: str,
    expected_constraints: list[dict[str, object]],
) -> None:
    result = expand_beam_template(template_id, span_value=15, span_unit="m")

    assert result["nodes"] == [{"id": 1, "x": 0, "y": 0}, {"id": 2, "x": 15, "y": 0}]
    assert result["elements"] == [{"id": 1, "nodeI": 1, "nodeJ": 2}]
    assert result["constraints"] == expected_constraints
    assert result["templateId"] == template_id
    assert {fact["source"] for fact in result["derivedFacts"]} <= {
        "TEMPLATE_DERIVED",
        "DETERMINISTIC_DERIVED",
    }
    assert any(fact.get("ruleId") == "BEAM_SPAN_COORDINATES_V1" for fact in result["derivedFacts"])
