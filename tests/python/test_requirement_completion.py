from __future__ import annotations

from fem_core.requirements.evidence import validate_explicit_evidence
from fem_core.requirements.schema import validate_requirement_draft_schema


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
