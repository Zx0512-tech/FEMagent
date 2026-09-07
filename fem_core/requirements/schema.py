from __future__ import annotations

import copy
import json
import math
from typing import Any

DRAFT_SCHEMA = "FEMAGENT_ENGINEERING_REQUIREMENT_DRAFT_V1"
DRAFT_PROFILE = "FRAME_2D_REQUIREMENT_V1"

_ALLOWED_FACT_KINDS = {
    "SPAN",
    "UNIT_DECLARATION",
    "YOUNGS_MODULUS",
    "SECTION_AREA",
    "SECTION_IZ",
    "NODE_COORDINATE",
    "ELEMENT_CONNECTIVITY",
    "ELEMENT_MATERIAL_REF",
    "ELEMENT_SECTION_REF",
    "NODE_CONSTRAINT",
    "NODAL_MASS",
}

_FACT_KEYS: dict[str, tuple[set[str], set[str]]] = {
    "SPAN": (
        {"kind", "source", "value", "unit", "evidence"},
        {"kind", "source", "value", "unit", "evidence"},
    ),
    "UNIT_DECLARATION": (
        {"kind", "source", "dimension", "value", "evidence"},
        {"kind", "source", "dimension", "value", "evidence"},
    ),
    "YOUNGS_MODULUS": (
        {"kind", "source", "value", "unit", "evidence", "materialId"},
        {"kind", "source", "value", "unit", "evidence"},
    ),
    "SECTION_AREA": (
        {"kind", "source", "value", "unit", "evidence", "sectionId"},
        {"kind", "source", "value", "unit", "evidence"},
    ),
    "SECTION_IZ": (
        {"kind", "source", "value", "unit", "evidence", "sectionId"},
        {"kind", "source", "value", "unit", "evidence"},
    ),
    "NODE_COORDINATE": (
        {"kind", "source", "nodeId", "x", "y", "unit", "evidence"},
        {"kind", "source", "nodeId", "x", "y", "unit", "evidence"},
    ),
    "ELEMENT_CONNECTIVITY": (
        {"kind", "source", "elementId", "nodeI", "nodeJ", "evidence"},
        {"kind", "source", "elementId", "nodeI", "nodeJ", "evidence"},
    ),
    "ELEMENT_MATERIAL_REF": (
        {"kind", "source", "elementId", "materialId", "evidence"},
        {"kind", "source", "elementId", "materialId", "evidence"},
    ),
    "ELEMENT_SECTION_REF": (
        {"kind", "source", "elementId", "sectionId", "evidence"},
        {"kind", "source", "elementId", "sectionId", "evidence"},
    ),
    "NODE_CONSTRAINT": (
        {"kind", "source", "nodeId", "dofs", "evidence"},
        {"kind", "source", "nodeId", "dofs", "evidence"},
    ),
    "NODAL_MASS": (
        {"kind", "source", "nodeId", "mUX", "mUY", "evidence"},
        {"kind", "source", "nodeId", "mUX", "mUY", "evidence"},
    ),
}


def _issue(code: str, path: str, message: str) -> dict[str, str]:
    return {"severity": "ERROR", "code": code, "path": path, "message": message}


def _is_positive_int(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value > 0


def _is_finite_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(float(value))


def _check_exact_keys(
    value: dict[str, Any],
    *,
    allowed: set[str],
    required: set[str],
    path: str,
    issues: list[dict[str, str]],
) -> None:
    for key in sorted(set(value) - allowed):
        issues.append(_issue("REQUIREMENT_DRAFT_UNKNOWN_FIELD", f"{path}.{key}" if path else key, f"Unknown requirement draft field: {key}"))
    for key in sorted(required - set(value)):
        issues.append(_issue("REQUIREMENT_DRAFT_INVALID_SCHEMA", f"{path}.{key}" if path else key, f"Required requirement draft field is missing: {key}"))


def _validate_evidence_shape(value: Any, path: str, issues: list[dict[str, str]]) -> None:
    if not isinstance(value, dict):
        issues.append(_issue("REQUIREMENT_DRAFT_INVALID_SCHEMA", path, f"{path} must be an object"))
        return
    _check_exact_keys(value, allowed={"sourceId", "quote"}, required={"sourceId", "quote"}, path=path, issues=issues)
    if "sourceId" in value and (not isinstance(value["sourceId"], str) or not value["sourceId"].strip()):
        issues.append(_issue("REQUIREMENT_DRAFT_INVALID_SOURCE", f"{path}.sourceId", "Evidence sourceId must be a non-empty string"))
    if "quote" in value and (not isinstance(value["quote"], str) or not value["quote"]):
        issues.append(_issue("REQUIREMENT_DRAFT_INVALID_SCHEMA", f"{path}.quote", "Evidence quote must be a non-empty string"))


def _validate_fact(fact: Any, index: int, issues: list[dict[str, str]]) -> None:
    path = f"facts[{index}]"
    if not isinstance(fact, dict):
        issues.append(_issue("REQUIREMENT_DRAFT_INVALID_SCHEMA", path, "Requirement fact must be an object"))
        return
    kind = fact.get("kind")
    if kind not in _ALLOWED_FACT_KINDS:
        issues.append(_issue("REQUIREMENT_DRAFT_INVALID_SCHEMA", f"{path}.kind", f"Unsupported requirement fact kind: {kind!r}"))
        return
    allowed, required = _FACT_KEYS[kind]
    _check_exact_keys(fact, allowed=allowed, required=required, path=path, issues=issues)
    if fact.get("source") != "USER_EXPLICIT":
        issues.append(_issue("REQUIREMENT_DRAFT_INVALID_SCHEMA", f"{path}.source", "Input facts must use source='USER_EXPLICIT'"))
    if "evidence" in fact:
        _validate_evidence_shape(fact["evidence"], f"{path}.evidence", issues)

    positive_number_kinds = {"SPAN", "YOUNGS_MODULUS", "SECTION_AREA", "SECTION_IZ"}
    if kind in positive_number_kinds and "value" in fact:
        if not _is_finite_number(fact["value"]) or float(fact["value"]) <= 0:
            issues.append(_issue("REQUIREMENT_DRAFT_INVALID_SCHEMA", f"{path}.value", f"{kind} value must be a positive finite number"))

    if kind == "SPAN" and fact.get("unit") not in {"m", "cm", "mm"}:
        issues.append(_issue("REQUIREMENT_DRAFT_INVALID_SCHEMA", f"{path}.unit", "SPAN unit must be m, cm, or mm"))
    if kind == "UNIT_DECLARATION":
        allowed_units = {
            "length": {"m", "cm", "mm"},
            "force": {"N", "kN"},
            "time": {"s", "ms"},
        }
        dimension = fact.get("dimension")
        if dimension not in allowed_units or fact.get("value") not in allowed_units.get(dimension, set()):
            issues.append(_issue("REQUIREMENT_DRAFT_INVALID_SCHEMA", path, "UNIT_DECLARATION dimension/value is unsupported"))
    if kind in {"NODE_COORDINATE", "NODE_CONSTRAINT", "NODAL_MASS"} and "nodeId" in fact and not _is_positive_int(fact["nodeId"]):
        issues.append(_issue("REQUIREMENT_DRAFT_INVALID_SCHEMA", f"{path}.nodeId", "nodeId must be a positive integer"))
    if kind in {"ELEMENT_CONNECTIVITY", "ELEMENT_MATERIAL_REF", "ELEMENT_SECTION_REF"} and "elementId" in fact and not _is_positive_int(fact["elementId"]):
        issues.append(_issue("REQUIREMENT_DRAFT_INVALID_SCHEMA", f"{path}.elementId", "elementId must be a positive integer"))
    if kind == "ELEMENT_CONNECTIVITY":
        for field in ("nodeI", "nodeJ"):
            if field in fact and not _is_positive_int(fact[field]):
                issues.append(_issue("REQUIREMENT_DRAFT_INVALID_SCHEMA", f"{path}.{field}", f"{field} must be a positive integer"))
        if fact.get("nodeI") == fact.get("nodeJ") and _is_positive_int(fact.get("nodeI")):
            issues.append(_issue("REQUIREMENT_DRAFT_INVALID_SCHEMA", path, "ELEMENT_CONNECTIVITY requires nodeI != nodeJ"))
    if kind == "NODE_CONSTRAINT" and "dofs" in fact:
        dofs = fact["dofs"]
        if not isinstance(dofs, list) or not dofs or any(dof not in {"UX", "UY", "RZ"} for dof in dofs) or len(dofs) != len(set(dofs)):
            issues.append(_issue("REQUIREMENT_DRAFT_INVALID_SCHEMA", f"{path}.dofs", "dofs must be a non-empty unique subset of UX, UY, RZ"))
    if kind == "NODAL_MASS":
        for field in ("mUX", "mUY"):
            if field in fact and (not _is_finite_number(fact[field]) or float(fact[field]) < 0):
                issues.append(_issue("REQUIREMENT_DRAFT_INVALID_SCHEMA", f"{path}.{field}", f"{field} must be a finite non-negative number"))
    for field in ("materialId", "sectionId"):
        if field in fact and not _is_positive_int(fact[field]):
            issues.append(_issue("REQUIREMENT_DRAFT_INVALID_SCHEMA", f"{path}.{field}", f"{field} must be a positive integer"))


def validate_requirement_draft_schema(draft: Any) -> dict[str, Any]:
    issues: list[dict[str, str]] = []
    if not isinstance(draft, dict):
        return {
            "status": "INVALID",
            "issues": [_issue("REQUIREMENT_DRAFT_INVALID_SCHEMA", "", "Requirement draft must be an object")],
            "normalizedDraft": None,
        }

    _check_exact_keys(
        draft,
        allowed={"schema", "profile", "sources", "templateIntent", "facts"},
        required={"schema", "profile", "sources", "templateIntent", "facts"},
        path="",
        issues=issues,
    )
    if draft.get("schema") != DRAFT_SCHEMA:
        issues.append(_issue("REQUIREMENT_DRAFT_INVALID_SCHEMA", "schema", f"schema must equal {DRAFT_SCHEMA}"))
    if draft.get("profile") != DRAFT_PROFILE:
        issues.append(_issue("REQUIREMENT_DRAFT_INVALID_SCHEMA", "profile", f"profile must equal {DRAFT_PROFILE}"))

    sources = draft.get("sources")
    seen_source_ids: set[str] = set()
    if not isinstance(sources, list) or not sources:
        issues.append(_issue("REQUIREMENT_DRAFT_INVALID_SOURCE", "sources", "sources must be a non-empty array"))
    else:
        for index, source in enumerate(sources):
            path = f"sources[{index}]"
            if not isinstance(source, dict):
                issues.append(_issue("REQUIREMENT_DRAFT_INVALID_SOURCE", path, "Source must be an object"))
                continue
            _check_exact_keys(source, allowed={"sourceId", "kind", "text"}, required={"sourceId", "kind", "text"}, path=path, issues=issues)
            source_id = source.get("sourceId")
            if not isinstance(source_id, str) or not source_id.strip():
                issues.append(_issue("REQUIREMENT_DRAFT_INVALID_SOURCE", f"{path}.sourceId", "sourceId must be a non-empty string"))
            elif source_id in seen_source_ids:
                issues.append(_issue("REQUIREMENT_DRAFT_INVALID_SOURCE", f"{path}.sourceId", f"Duplicate sourceId: {source_id}"))
            else:
                seen_source_ids.add(source_id)
            if source.get("kind") != "USER_MESSAGE":
                issues.append(_issue("REQUIREMENT_DRAFT_INVALID_SOURCE", f"{path}.kind", "V1 source kind must be USER_MESSAGE"))
            if not isinstance(source.get("text"), str) or not source.get("text"):
                issues.append(_issue("REQUIREMENT_DRAFT_INVALID_SOURCE", f"{path}.text", "Source text must be a non-empty string"))

    template_intent = draft.get("templateIntent")
    if template_intent is not None:
        if not isinstance(template_intent, dict):
            issues.append(_issue("REQUIREMENT_DRAFT_INVALID_SCHEMA", "templateIntent", "templateIntent must be null or an object"))
        else:
            _check_exact_keys(template_intent, allowed={"templateId", "evidence"}, required={"templateId", "evidence"}, path="templateIntent", issues=issues)
            if not isinstance(template_intent.get("templateId"), str) or not template_intent.get("templateId"):
                issues.append(_issue("REQUIREMENT_DRAFT_INVALID_SCHEMA", "templateIntent.templateId", "templateId must be a non-empty string"))
            if "evidence" in template_intent:
                _validate_evidence_shape(template_intent["evidence"], "templateIntent.evidence", issues)

    facts = draft.get("facts")
    if not isinstance(facts, list):
        issues.append(_issue("REQUIREMENT_DRAFT_INVALID_SCHEMA", "facts", "facts must be an array"))
    else:
        for index, fact in enumerate(facts):
            _validate_fact(fact, index, issues)

    if issues:
        return {"status": "INVALID", "issues": issues, "normalizedDraft": None}

    normalized = copy.deepcopy(draft)
    normalized["sources"] = sorted(normalized["sources"], key=lambda item: item["sourceId"])
    normalized["facts"] = sorted(
        normalized["facts"],
        key=lambda item: (item["kind"], json.dumps(item, sort_keys=True, ensure_ascii=False, separators=(",", ":"))),
    )
    return {"status": "VALID", "issues": [], "normalizedDraft": normalized}
