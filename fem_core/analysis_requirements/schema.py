from __future__ import annotations

import copy
import math
from typing import Any

DRAFT_SCHEMA = "FEMAGENT_ANALYSIS_REQUIREMENT_DRAFT_V1"
DRAFT_PROFILE = "TRANSIENT_UNIFORM_BASE_REQUIREMENT_V1"

_ROLE_TYPES = {
    "GIRDER_END",
    "TOWER_BASE",
    "MIDSPAN",
    "SUPPORT",
    "BEARING",
    "DAMPER_ATTACHMENT",
}
_COMPONENTS = {"X", "Y"}
_RESULT_QUANTITIES = {"DISPLACEMENT", "REACTION_FORCE"}


def _issue(code: str, path: str, message: str) -> dict[str, str]:
    return {"code": code, "path": path, "message": message}


def _exact_keys(
    value: Any,
    expected: set[str],
    path: str,
    issues: list[dict[str, str]],
) -> bool:
    if not isinstance(value, dict):
        issues.append(
            _issue(
                "ANALYSIS_REQUIREMENT_INVALID_SCHEMA",
                path,
                f"{path or 'draft'} must be a JSON object",
            )
        )
        return False
    for key in sorted(set(value) - expected):
        child = f"{path}.{key}" if path else key
        issues.append(
            _issue(
                "ANALYSIS_REQUIREMENT_UNKNOWN_FIELD",
                child,
                f"Unknown analysis requirement field: {child}",
            )
        )
    for key in sorted(expected - set(value)):
        child = f"{path}.{key}" if path else key
        issues.append(
            _issue(
                "ANALYSIS_REQUIREMENT_INVALID_SCHEMA",
                child,
                f"Required analysis requirement field is missing: {child}",
            )
        )
    return not any(issue["path"].startswith(path) for issue in issues if path)


def _evidence(
    value: Any,
    path: str,
    issues: list[dict[str, str]],
) -> None:
    if not _exact_keys(value, {"sourceId", "quote"}, path, issues):
        return
    if not isinstance(value.get("sourceId"), str) or not value["sourceId"].strip():
        issues.append(
            _issue(
                "ANALYSIS_REQUIREMENT_INVALID_EVIDENCE",
                f"{path}.sourceId",
                "evidence.sourceId must be a non-empty string",
            )
        )
    if not isinstance(value.get("quote"), str) or not value["quote"].strip():
        issues.append(
            _issue(
                "ANALYSIS_REQUIREMENT_INVALID_EVIDENCE",
                f"{path}.quote",
                "evidence.quote must be a non-empty string",
            )
        )


def _positive_node_id(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value > 0


def _finite_nonnegative(value: Any) -> bool:
    return (
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and math.isfinite(float(value))
        and float(value) >= 0.0
    )


def _validate_target(
    value: Any,
    path: str,
    issues: list[dict[str, str]],
) -> None:
    if not isinstance(value, dict):
        issues.append(
            _issue(
                "ANALYSIS_REQUIREMENT_INVALID_TARGET",
                path,
                "Result target must be a JSON object",
            )
        )
        return
    target_type = value.get("type")
    if target_type == "NODE":
        _exact_keys(value, {"type", "id"}, path, issues)
        if not _positive_node_id(value.get("id")):
            issues.append(
                _issue(
                    "ANALYSIS_REQUIREMENT_INVALID_TARGET",
                    f"{path}.id",
                    "NODE target id must be a positive integer",
                )
            )
        return
    if target_type == "SEMANTIC_ROLE_TYPE":
        _exact_keys(value, {"type", "roleType"}, path, issues)
        if value.get("roleType") not in _ROLE_TYPES:
            issues.append(
                _issue(
                    "ANALYSIS_REQUIREMENT_INVALID_TARGET",
                    f"{path}.roleType",
                    "Unsupported semantic role type",
                )
            )
        return
    issues.append(
        _issue(
            "ANALYSIS_REQUIREMENT_INVALID_TARGET",
            f"{path}.type",
            "Result target type must be NODE or SEMANTIC_ROLE_TYPE",
        )
    )


def _validate_fact(
    fact: Any,
    index: int,
    issues: list[dict[str, str]],
) -> None:
    path = f"facts[{index}]"
    if not isinstance(fact, dict):
        issues.append(
            _issue(
                "ANALYSIS_REQUIREMENT_INVALID_SCHEMA",
                path,
                "Each analysis requirement fact must be a JSON object",
            )
        )
        return
    kind = fact.get("kind")
    base = {"kind", "source", "evidence"}
    if fact.get("source") != "USER_EXPLICIT":
        issues.append(
            _issue(
                "ANALYSIS_REQUIREMENT_INVALID_SOURCE",
                f"{path}.source",
                "Input analysis requirement facts must use source=USER_EXPLICIT",
            )
        )

    if kind == "EXCITATION_COMPONENT":
        _exact_keys(fact, base | {"component"}, path, issues)
        if fact.get("component") not in _COMPONENTS:
            issues.append(
                _issue(
                    "ANALYSIS_REQUIREMENT_INVALID_COMPONENT",
                    f"{path}.component",
                    "Excitation component must be X or Y",
                )
            )
    elif kind in {"LOAD_SELECTION", "DAMPING_NONE"}:
        _exact_keys(fact, base, path, issues)
    elif kind == "RAYLEIGH_DAMPING":
        _exact_keys(fact, base | {"alphaM", "betaK"}, path, issues)
        for field in ("alphaM", "betaK"):
            if not _finite_nonnegative(fact.get(field)):
                issues.append(
                    _issue(
                        "ANALYSIS_REQUIREMENT_INVALID_DAMPING",
                        f"{path}.{field}",
                        f"{field} must be a non-negative finite number",
                    )
                )
    elif kind == "RESULT_REQUEST":
        _exact_keys(
            fact,
            base | {"quantity", "target", "component"},
            path,
            issues,
        )
        if fact.get("quantity") not in _RESULT_QUANTITIES:
            issues.append(
                _issue(
                    "ANALYSIS_REQUIREMENT_INVALID_RESULT",
                    f"{path}.quantity",
                    "V1 supports DISPLACEMENT or REACTION_FORCE only",
                )
            )
        component = fact.get("component")
        if component is not None and component not in _COMPONENTS:
            issues.append(
                _issue(
                    "ANALYSIS_REQUIREMENT_INVALID_COMPONENT",
                    f"{path}.component",
                    "Result component must be X or Y when provided",
                )
            )
        _validate_target(fact.get("target"), f"{path}.target", issues)
    else:
        issues.append(
            _issue(
                "ANALYSIS_REQUIREMENT_UNSUPPORTED_FACT",
                f"{path}.kind",
                f"Unsupported analysis requirement fact kind: {kind!r}",
            )
        )

    _evidence(fact.get("evidence"), f"{path}.evidence", issues)


def validate_analysis_requirement_draft(draft: Any) -> dict[str, Any]:
    issues: list[dict[str, str]] = []
    if not _exact_keys(
        draft,
        {"schema", "profile", "sources", "intent", "facts"},
        "",
        issues,
    ):
        return {
            "status": "INVALID",
            "issues": issues,
            "normalizedDraft": None,
        }

    if draft.get("schema") != DRAFT_SCHEMA:
        issues.append(
            _issue(
                "ANALYSIS_REQUIREMENT_INVALID_SCHEMA",
                "schema",
                f"schema must equal {DRAFT_SCHEMA}",
            )
        )
    if draft.get("profile") != DRAFT_PROFILE:
        issues.append(
            _issue(
                "ANALYSIS_REQUIREMENT_UNSUPPORTED_PROFILE",
                "profile",
                f"profile must equal {DRAFT_PROFILE}",
            )
        )

    raw_sources = draft.get("sources")
    if not isinstance(raw_sources, list) or not raw_sources:
        issues.append(
            _issue(
                "ANALYSIS_REQUIREMENT_INVALID_SOURCE",
                "sources",
                "sources must contain at least one USER_MESSAGE",
            )
        )
        raw_sources = []
    source_ids: set[str] = set()
    for index, source in enumerate(raw_sources):
        path = f"sources[{index}]"
        if not _exact_keys(source, {"sourceId", "kind", "text"}, path, issues):
            continue
        source_id = source.get("sourceId")
        if not isinstance(source_id, str) or not source_id.strip() or source_id in source_ids:
            issues.append(
                _issue(
                    "ANALYSIS_REQUIREMENT_INVALID_SOURCE",
                    f"{path}.sourceId",
                    "sourceId must be non-empty and unique",
                )
            )
        else:
            source_ids.add(source_id)
        if source.get("kind") != "USER_MESSAGE":
            issues.append(
                _issue(
                    "ANALYSIS_REQUIREMENT_INVALID_SOURCE",
                    f"{path}.kind",
                    "V1 accepts USER_MESSAGE sources only",
                )
            )
        if not isinstance(source.get("text"), str) or not source["text"].strip():
            issues.append(
                _issue(
                    "ANALYSIS_REQUIREMENT_INVALID_SOURCE",
                    f"{path}.text",
                    "source text must be non-empty",
                )
            )

    intent = draft.get("intent")
    if _exact_keys(intent, {"type", "evidence"}, "intent", issues):
        if intent.get("type") != "TRANSIENT_UNIFORM_BASE":
            issues.append(
                _issue(
                    "ANALYSIS_REQUIREMENT_UNSUPPORTED_PROFILE",
                    "intent.type",
                    "V1 supports TRANSIENT_UNIFORM_BASE intent only",
                )
            )
        _evidence(intent.get("evidence"), "intent.evidence", issues)

    facts = draft.get("facts")
    if not isinstance(facts, list):
        issues.append(
            _issue(
                "ANALYSIS_REQUIREMENT_INVALID_SCHEMA",
                "facts",
                "facts must be an array",
            )
        )
        facts = []
    for index, fact in enumerate(facts):
        _validate_fact(fact, index, issues)

    if issues:
        return {
            "status": "INVALID",
            "issues": issues,
            "normalizedDraft": None,
        }
    return {
        "status": "VALID",
        "issues": [],
        "normalizedDraft": copy.deepcopy(draft),
    }


__all__ = [
    "DRAFT_PROFILE",
    "DRAFT_SCHEMA",
    "validate_analysis_requirement_draft",
]
