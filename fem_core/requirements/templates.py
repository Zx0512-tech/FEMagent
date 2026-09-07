from __future__ import annotations

import math
import re
import unicodedata
from typing import Any

TEMPLATE_ALIASES: dict[str, tuple[str, ...]] = {
    "SIMPLY_SUPPORTED_BEAM_2D_V1": (
        "简支梁",
        "simply supported beam",
    ),
    "CANTILEVER_BEAM_2D_V1": (
        "悬臂梁",
        "cantilever beam",
    ),
    "FIXED_FIXED_BEAM_2D_V1": (
        "两端固支梁",
        "双端固支梁",
        "fixed-fixed beam",
        "fixed fixed beam",
    ),
}


def _issue(code: str, path: str, message: str) -> dict[str, str]:
    return {"severity": "ERROR", "code": code, "path": path, "message": message}


def _normalize_alias(value: str) -> str:
    value = unicodedata.normalize("NFKC", value).strip()
    return re.sub(r"\s+", " ", value).casefold()


def validate_template_intent(
    *,
    sources: dict[str, str],
    template_intent: dict[str, Any],
) -> dict[str, Any]:
    issues: list[dict[str, str]] = []
    template_id = template_intent.get("templateId")
    if template_id not in TEMPLATE_ALIASES:
        issues.append(
            _issue(
                "REQUIREMENT_TEMPLATE_UNSUPPORTED",
                "templateIntent.templateId",
                f"Unsupported controlled requirement template: {template_id!r}",
            )
        )
        return {"status": "INVALID", "templateId": None, "issues": issues}

    evidence = template_intent.get("evidence")
    if not isinstance(evidence, dict):
        issues.append(
            _issue(
                "REQUIREMENT_TEMPLATE_EVIDENCE_MISMATCH",
                "templateIntent.evidence",
                "Template intent requires an evidence object",
            )
        )
        return {"status": "INVALID", "templateId": None, "issues": issues}

    source_id = evidence.get("sourceId")
    quote = evidence.get("quote")
    if not isinstance(source_id, str) or source_id not in sources:
        issues.append(
            _issue(
                "REQUIREMENT_EVIDENCE_SOURCE_NOT_FOUND",
                "templateIntent.evidence.sourceId",
                "Template evidence sourceId does not resolve to a submitted source",
            )
        )
        return {"status": "INVALID", "templateId": None, "issues": issues}
    if not isinstance(quote, str) or not quote or quote not in sources[source_id]:
        issues.append(
            _issue(
                "REQUIREMENT_EVIDENCE_QUOTE_NOT_FOUND",
                "templateIntent.evidence.quote",
                "Template evidence quote must be an exact substring of its source",
            )
        )
        return {"status": "INVALID", "templateId": None, "issues": issues}

    normalized_quote = _normalize_alias(quote)
    allowed_aliases = {_normalize_alias(alias) for alias in TEMPLATE_ALIASES[template_id]}
    if normalized_quote not in allowed_aliases:
        issues.append(
            _issue(
                "REQUIREMENT_TEMPLATE_EVIDENCE_MISMATCH",
                "templateIntent.evidence.quote",
                f"Evidence does not select template {template_id}",
            )
        )

    return {
        "status": "VALID" if not issues else "INVALID",
        "templateId": template_id if not issues else None,
        "issues": issues,
    }


def _derived_fact(
    kind: str,
    *,
    source: str,
    template_id: str | None = None,
    rule_id: str | None = None,
    **values: Any,
) -> dict[str, Any]:
    fact: dict[str, Any] = {"kind": kind, "source": source, **values}
    if template_id is not None:
        fact["templateId"] = template_id
    if rule_id is not None:
        fact["ruleId"] = rule_id
    return fact


def expand_beam_template(
    template_id: str,
    *,
    span_value: float | int,
    span_unit: str,
) -> dict[str, Any]:
    if template_id not in TEMPLATE_ALIASES:
        raise ValueError(f"Unsupported controlled requirement template: {template_id}")
    if (
        not isinstance(span_value, (int, float))
        or isinstance(span_value, bool)
        or not math.isfinite(float(span_value))
        or float(span_value) <= 0
    ):
        raise ValueError("Beam span must be a positive finite number")
    if span_unit not in {"m", "cm", "mm"}:
        raise ValueError("Beam span unit must be m, cm, or mm")

    nodes = [{"id": 1, "x": 0, "y": 0}, {"id": 2, "x": span_value, "y": 0}]
    elements = [{"id": 1, "nodeI": 1, "nodeJ": 2}]
    constraints_by_template = {
        "SIMPLY_SUPPORTED_BEAM_2D_V1": [
            {"nodeId": 1, "dofs": ["UX", "UY"]},
            {"nodeId": 2, "dofs": ["UY"]},
        ],
        "CANTILEVER_BEAM_2D_V1": [
            {"nodeId": 1, "dofs": ["UX", "UY", "RZ"]},
        ],
        "FIXED_FIXED_BEAM_2D_V1": [
            {"nodeId": 1, "dofs": ["UX", "UY", "RZ"]},
            {"nodeId": 2, "dofs": ["UX", "UY", "RZ"]},
        ],
    }
    constraints = constraints_by_template[template_id]

    derived_facts: list[dict[str, Any]] = [
        _derived_fact(
            "NODE_COORDINATE",
            source="DETERMINISTIC_DERIVED",
            rule_id="BEAM_SPAN_COORDINATES_V1",
            nodeId=1,
            x=0,
            y=0,
            unit=span_unit,
        ),
        _derived_fact(
            "NODE_COORDINATE",
            source="DETERMINISTIC_DERIVED",
            rule_id="BEAM_SPAN_COORDINATES_V1",
            nodeId=2,
            x=span_value,
            y=0,
            unit=span_unit,
        ),
        _derived_fact(
            "ELEMENT_CONNECTIVITY",
            source="TEMPLATE_DERIVED",
            template_id=template_id,
            elementId=1,
            nodeI=1,
            nodeJ=2,
        ),
    ]
    derived_facts.extend(
        _derived_fact(
            "NODE_CONSTRAINT",
            source="TEMPLATE_DERIVED",
            template_id=template_id,
            nodeId=constraint["nodeId"],
            dofs=list(constraint["dofs"]),
        )
        for constraint in constraints
    )

    return {
        "templateId": template_id,
        "nodes": nodes,
        "elements": elements,
        "constraints": constraints,
        "derivedFacts": derived_facts,
    }
