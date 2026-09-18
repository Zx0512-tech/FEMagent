from __future__ import annotations

import math
import re
import unicodedata
from typing import Any

_INTENT_ALIASES = (
    "地震时程分析",
    "地震时程",
    "地震波",
    "earthquake time history",
    "uniform base excitation",
)
_LOAD_ALIASES = (
    "地震波",
    "地震记录",
    "这个地震波",
    "该地震波",
    "earthquake record",
    "accelerogram",
    "wave",
)
_NONE_DAMPING_ALIASES = (
    "无阻尼",
    "不考虑阻尼",
    "不计阻尼",
    "no damping",
)
_QUANTITY_ALIASES = {
    "DISPLACEMENT": ("位移", "displacement"),
    "REACTION_FORCE": ("反力", "reaction force"),
}
_ROLE_ALIASES = {
    "GIRDER_END": ("梁端", "girder end"),
    "TOWER_BASE": ("塔底", "tower base"),
    "MIDSPAN": ("跨中", "midspan"),
    "SUPPORT": ("支座", "support"),
    "BEARING": ("支承", "bearing"),
    "DAMPER_ATTACHMENT": ("阻尼器连接点", "damper attachment"),
}

_NUMBER = r"[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?"


def _normalize(text: str) -> str:
    return " ".join(unicodedata.normalize("NFKC", text).strip().casefold().split())


def _contains_alias(text: str, aliases: tuple[str, ...]) -> bool:
    normalized = _normalize(text)
    return any(_normalize(alias) in normalized for alias in aliases)


def _issue(code: str, subject: str, message: str) -> dict[str, str]:
    return {"code": code, "subject": subject, "message": message}


def _source_quote(
    sources: dict[str, str],
    evidence: dict[str, Any],
    *,
    subject: str,
) -> tuple[str | None, list[dict[str, str]]]:
    source_id = evidence.get("sourceId") if isinstance(evidence, dict) else None
    quote = evidence.get("quote") if isinstance(evidence, dict) else None
    if not isinstance(source_id, str) or source_id not in sources:
        return None, [
            _issue(
                "ANALYSIS_REQUIREMENT_EVIDENCE_SOURCE_NOT_FOUND",
                subject,
                "Evidence sourceId does not resolve to exactly one submitted source",
            )
        ]
    if not isinstance(quote, str) or not quote.strip():
        return None, [
            _issue(
                "ANALYSIS_REQUIREMENT_EVIDENCE_QUOTE_EMPTY",
                subject,
                "Evidence quote must be non-empty",
            )
        ]
    if quote not in sources[source_id]:
        return None, [
            _issue(
                "ANALYSIS_REQUIREMENT_EVIDENCE_QUOTE_NOT_FOUND",
                subject,
                "Evidence quote must be an exact substring of the referenced source",
            )
        ]
    return quote, []


def _component_is_evidenced(quote: str, component: str) -> bool:
    normalized = _normalize(quote)
    if component == "X":
        patterns = (
            r"(?<![a-z0-9])x\s*向",
            r"(?<![a-z0-9])x\s*方向",
            r"(?<![a-z0-9])x[- ]?direction",
            r"(?<![a-z0-9])x[- ]?dir",
        )
    else:
        patterns = (
            r"(?<![a-z0-9])y\s*向",
            r"(?<![a-z0-9])y\s*方向",
            r"(?<![a-z0-9])y[- ]?direction",
            r"(?<![a-z0-9])y[- ]?dir",
        )
    return any(re.search(pattern, normalized) for pattern in patterns)


def _rayleigh_value(quote: str, label: str) -> float | None:
    normalized = unicodedata.normalize("NFKC", quote).casefold()
    aliases = ("alpham", "αm") if label == "alphaM" else ("betak", "βk")
    for alias in aliases:
        match = re.search(rf"{re.escape(alias)}\s*=\s*({_NUMBER})", normalized)
        if match is not None:
            return float(match.group(1))
    return None


def validate_intent_evidence(
    *,
    sources: dict[str, str],
    intent: dict[str, Any],
) -> dict[str, Any]:
    quote, issues = _source_quote(
        sources,
        intent["evidence"],
        subject="intent",
    )
    if issues:
        return {"issues": issues}
    assert quote is not None
    if not _contains_alias(quote, _INTENT_ALIASES):
        issues.append(
            _issue(
                "ANALYSIS_REQUIREMENT_INTENT_EVIDENCE_MISMATCH",
                "intent",
                "Intent evidence does not explicitly identify a supported earthquake time-history/base-excitation request",
            )
        )
    return {"issues": issues}


def validate_fact_evidence(
    *,
    sources: dict[str, str],
    fact: dict[str, Any],
) -> dict[str, Any]:
    subject = str(fact["kind"])
    quote, issues = _source_quote(
        sources,
        fact["evidence"],
        subject=subject,
    )
    if issues:
        return {"issues": issues}
    assert quote is not None
    kind = fact["kind"]

    if kind == "EXCITATION_COMPONENT":
        if not _component_is_evidenced(quote, fact["component"]):
            issues.append(
                _issue(
                    "ANALYSIS_REQUIREMENT_COMPONENT_EVIDENCE_MISMATCH",
                    subject,
                    "Excitation component is not explicitly evidenced by the quote",
                )
            )
    elif kind == "LOAD_SELECTION":
        normalized = _normalize(quote)
        has_file_token = bool(re.search(r"\.(?:csv|xlsx|xls|txt)\b", normalized))
        if not _contains_alias(quote, _LOAD_ALIASES) and not has_file_token:
            issues.append(
                _issue(
                    "ANALYSIS_REQUIREMENT_LOAD_EVIDENCE_MISMATCH",
                    subject,
                    "Load-selection evidence must explicitly refer to an earthquake record/wave or named load file",
                )
            )
    elif kind == "DAMPING_NONE":
        if not _contains_alias(quote, _NONE_DAMPING_ALIASES):
            issues.append(
                _issue(
                    "ANALYSIS_REQUIREMENT_DAMPING_EVIDENCE_MISMATCH",
                    subject,
                    "NONE damping requires explicit no-damping wording",
                )
            )
    elif kind == "RAYLEIGH_DAMPING":
        alpha = _rayleigh_value(quote, "alphaM")
        beta = _rayleigh_value(quote, "betaK")
        if (
            alpha is None
            or beta is None
            or not math.isclose(alpha, float(fact["alphaM"]), rel_tol=1e-12, abs_tol=1e-15)
            or not math.isclose(beta, float(fact["betaK"]), rel_tol=1e-12, abs_tol=1e-15)
        ):
            issues.append(
                _issue(
                    "ANALYSIS_REQUIREMENT_DAMPING_EVIDENCE_MISMATCH",
                    subject,
                    "Rayleigh evidence must explicitly label alphaM and betaK with the submitted numeric values",
                )
            )
    elif kind == "RESULT_REQUEST":
        quantity = str(fact["quantity"])
        if not _contains_alias(quote, _QUANTITY_ALIASES[quantity]):
            issues.append(
                _issue(
                    "ANALYSIS_REQUIREMENT_RESULT_EVIDENCE_MISMATCH",
                    subject,
                    "Result quantity is not explicitly evidenced by the quote",
                )
            )
        component = fact.get("component")
        if isinstance(component, str) and not _component_is_evidenced(quote, component):
            issues.append(
                _issue(
                    "ANALYSIS_REQUIREMENT_COMPONENT_EVIDENCE_MISMATCH",
                    subject,
                    "Result component is not explicitly evidenced by the quote",
                )
            )
        target = fact["target"]
        if target["type"] == "NODE":
            normalized = _normalize(quote)
            node_id = int(target["id"])
            patterns = (
                rf"节点\s*{node_id}(?!\d)",
                rf"node\s*{node_id}(?!\d)",
            )
            if not any(re.search(pattern, normalized) for pattern in patterns):
                issues.append(
                    _issue(
                        "ANALYSIS_REQUIREMENT_TARGET_EVIDENCE_MISMATCH",
                        subject,
                        "NODE target id is not explicitly evidenced by the quote",
                    )
                )
        else:
            role_type = str(target["roleType"])
            if not _contains_alias(quote, _ROLE_ALIASES[role_type]):
                issues.append(
                    _issue(
                        "ANALYSIS_REQUIREMENT_TARGET_EVIDENCE_MISMATCH",
                        subject,
                        "Semantic role type is not explicitly evidenced by the quote",
                    )
                )
    return {"issues": issues}


__all__ = [
    "validate_fact_evidence",
    "validate_intent_evidence",
]
