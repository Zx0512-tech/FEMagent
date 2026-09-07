from __future__ import annotations

import re
from decimal import Decimal, InvalidOperation
from typing import Any

_NUMBER = r"[-+]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][-+]?\d+)?"
_SPAN_RE = re.compile(rf"(?P<value>{_NUMBER})\s*(?P<unit>mm|cm|m)(?![A-Za-z0-9])")


def _issue(code: str, path: str, message: str) -> dict[str, str]:
    return {"severity": "ERROR", "code": code, "path": path, "message": message}


def _same_number(left: Any, right_token: str) -> bool:
    try:
        return Decimal(str(left)) == Decimal(right_token)
    except (InvalidOperation, ValueError):
        return False


def validate_explicit_evidence(
    *,
    sources: dict[str, str],
    fact: dict[str, Any],
) -> dict[str, list[dict[str, str]]]:
    issues: list[dict[str, str]] = []
    ambiguous: list[dict[str, str]] = []
    evidence = fact.get("evidence")
    if not isinstance(evidence, dict):
        issues.append(_issue("REQUIREMENT_DRAFT_INVALID_SCHEMA", "evidence", "Fact evidence must be an object"))
        return {"issues": issues, "ambiguous": ambiguous}

    source_id = evidence.get("sourceId")
    quote = evidence.get("quote")
    if not isinstance(source_id, str) or source_id not in sources:
        issues.append(_issue("REQUIREMENT_EVIDENCE_SOURCE_NOT_FOUND", "evidence.sourceId", "Evidence sourceId does not resolve to a submitted source"))
        return {"issues": issues, "ambiguous": ambiguous}
    if not isinstance(quote, str) or not quote or quote not in sources[source_id]:
        issues.append(_issue("REQUIREMENT_EVIDENCE_QUOTE_NOT_FOUND", "evidence.quote", "Evidence quote must be an exact substring of its source"))
        return {"issues": issues, "ambiguous": ambiguous}

    kind = fact.get("kind")
    if kind == "SPAN":
        match = _SPAN_RE.search(quote)
        if match is None:
            ambiguous.append(_issue("REQUIREMENT_EVIDENCE_RELATION_AMBIGUOUS", "evidence.quote", "SPAN evidence must contain a deterministic number+length-unit form"))
            return {"issues": issues, "ambiguous": ambiguous}
        if not _same_number(fact.get("value"), match.group("value")):
            issues.append(_issue("REQUIREMENT_EVIDENCE_NUMERIC_MISMATCH", "value", "SPAN value does not match the numeric token in evidence"))
        if fact.get("unit") != match.group("unit"):
            issues.append(_issue("REQUIREMENT_EVIDENCE_UNIT_MISMATCH", "unit", "SPAN unit does not match the unit token in evidence"))

    return {"issues": issues, "ambiguous": ambiguous}
