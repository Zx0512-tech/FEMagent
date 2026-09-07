from __future__ import annotations

import re
import unicodedata
from decimal import Decimal, InvalidOperation
from typing import Any

_NUMBER = r"[-+]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][-+]?\d+)?"
_SPAN_RE = re.compile(rf"(?P<value>{_NUMBER})\s*(?P<unit>mm|cm|m)(?![A-Za-z0-9])")
_NODE_COORDINATE_RE = re.compile(
    rf"(?:节点|node\s*)(?P<node>\d+)\s*(?:在|at)\s*[（(]\s*(?P<x>{_NUMBER})\s*[,，]\s*(?P<y>{_NUMBER})\s*[)）]\s*(?P<unit>mm|cm|m)",
    re.IGNORECASE,
)
_ELEMENT_CONNECTIVITY_RE = re.compile(
    r"(?:单元|element\s*)(?P<element>\d+)\s*(?:连接|connects?\s*)(?:节点|node\s*)(?P<node_i>\d+)\s*(?:和|与|to|and)\s*(?:节点|node\s*)(?P<node_j>\d+)",
    re.IGNORECASE,
)
_ELEMENT_MATERIAL_RE = re.compile(
    r"(?:单元|element\s*)(?P<element>\d+)\s*(?:使用|uses?\s*)(?:材料|material\s*)(?P<material>\d+)",
    re.IGNORECASE,
)
_ELEMENT_SECTION_RE = re.compile(
    r"(?:单元|element\s*)(?P<element>\d+)\s*(?:使用|uses?\s*)(?:截面|section\s*)(?P<section>\d+)",
    re.IGNORECASE,
)
_FIXED_RE = re.compile(r"(?:(?:节点\s*(?P<cn_node>\d+)|(?P<cn_node_alt>\d+)\s*号节点)\s*固定|node\s*(?P<en_node>\d+)\s*fixed)", re.IGNORECASE)
_DOF_RE = re.compile(
    r"(?:节点\s*(?P<cn_node>\d+)|(?P<cn_node_alt>\d+)\s*号节点|node\s*(?P<en_node>\d+))\s*(?:约束|fix(?:es)?|constrain(?:s)?)\s*(?P<dofs>(?:(?:UX|UY|RZ)(?:\s*(?:和|与|,|，|/|\s)\s*)?)+)",
    re.IGNORECASE,
)


def _issue(code: str, path: str, message: str) -> dict[str, str]:
    return {"severity": "ERROR", "code": code, "path": path, "message": message}


def _same_number(left: Any, right_token: str) -> bool:
    try:
        return Decimal(str(left)) == Decimal(right_token)
    except (InvalidOperation, ValueError):
        return False


def _normalize(value: str) -> str:
    return re.sub(r"\s+", " ", unicodedata.normalize("NFKC", value).strip()).casefold()


def _relation_mismatch(path: str, message: str) -> dict[str, str]:
    return _issue("REQUIREMENT_EVIDENCE_RELATION_MISMATCH", path, message)


def _numeric_mismatch(path: str, message: str) -> dict[str, str]:
    return _issue("REQUIREMENT_EVIDENCE_NUMERIC_MISMATCH", path, message)


def _unit_mismatch(path: str, message: str) -> dict[str, str]:
    return _issue("REQUIREMENT_EVIDENCE_UNIT_MISMATCH", path, message)


def _ambiguous(path: str, message: str) -> dict[str, str]:
    return _issue("REQUIREMENT_EVIDENCE_RELATION_AMBIGUOUS", path, message)


def _validate_unit_declaration(fact: dict[str, Any], quote: str) -> tuple[list[dict[str, str]], list[dict[str, str]]]:
    issues: list[dict[str, str]] = []
    ambiguous: list[dict[str, str]] = []
    dimension = fact.get("dimension")
    value = fact.get("value")
    normalized = _normalize(quote)

    triple = re.search(
        r"(?:单位用|units?\s*(?:are|use|=|:)?\s*)(m|cm|mm)\s*[,、，/]\s*(n|kn)\s*[,、，/]\s*(s|ms)",
        normalized,
        re.IGNORECASE,
    )
    if triple is not None:
        recovered = {
            "length": triple.group(1),
            "force": "kN" if triple.group(2).casefold() == "kn" else "N",
            "time": triple.group(3),
        }
        recovered["length"] = recovered["length"].casefold()
        recovered["time"] = recovered["time"].casefold()
        if value != recovered.get(dimension):
            issues.append(_unit_mismatch("value", f"{dimension} unit does not match the canonical unit triple in evidence"))
        return issues, ambiguous

    labels = {
        "length": (r"(?:长度单位|length\s*unit)\s*(?:为|是|=|:)?\s*(m|cm|mm)\b", {"m", "cm", "mm"}),
        "force": (r"(?:力单位|force\s*unit)\s*(?:为|是|=|:)?\s*(n|kn)\b", {"N", "kN"}),
        "time": (r"(?:时间单位|time\s*unit)\s*(?:为|是|=|:)?\s*(s|ms)\b", {"s", "ms"}),
    }
    if dimension not in labels:
        ambiguous.append(_ambiguous("evidence.quote", "Unsupported unit-declaration dimension"))
        return issues, ambiguous
    pattern, _ = labels[dimension]
    match = re.search(pattern, normalized, re.IGNORECASE)
    if match is None:
        ambiguous.append(_ambiguous("evidence.quote", "Unit evidence must use a deterministic labeled declaration or canonical length/force/time triple"))
        return issues, ambiguous
    token = match.group(1)
    if dimension == "force":
        token = "kN" if token.casefold() == "kn" else "N"
    else:
        token = token.casefold()
    if value != token:
        issues.append(_unit_mismatch("value", f"{dimension} unit does not match the labeled unit in evidence"))
    return issues, ambiguous


def _validate_property(
    fact: dict[str, Any],
    quote: str,
    *,
    label_pattern: str,
    allowed_units: tuple[str, ...],
    id_field: str | None = None,
    id_pattern: str | None = None,
) -> tuple[list[dict[str, str]], list[dict[str, str]]]:
    issues: list[dict[str, str]] = []
    ambiguous: list[dict[str, str]] = []
    unit_alt = "|".join(re.escape(unit) for unit in sorted(allowed_units, key=len, reverse=True))
    match = re.search(
        rf"(?:{label_pattern})\s*(?:=|:|为|是)?\s*(?P<value>{_NUMBER})\s*(?P<unit>{unit_alt})",
        unicodedata.normalize("NFKC", quote),
        re.IGNORECASE,
    )
    if match is None:
        ambiguous.append(_ambiguous("evidence.quote", "Property evidence does not match a deterministic V1 labeled value grammar"))
        return issues, ambiguous
    if not _same_number(fact.get("value"), match.group("value")):
        issues.append(_numeric_mismatch("value", "Property value does not match the numeric token in evidence"))
    if fact.get("unit") != match.group("unit"):
        issues.append(_unit_mismatch("unit", "Property unit does not match the unit token in evidence"))

    if id_field is not None and id_field in fact:
        if id_pattern is None:
            issues.append(_relation_mismatch(id_field, f"{id_field} cannot be evidenced for this fact kind"))
        else:
            id_match = re.search(id_pattern, unicodedata.normalize("NFKC", quote), re.IGNORECASE)
            if id_match is None:
                issues.append(_relation_mismatch(id_field, f"{id_field} was supplied but is not identified by the evidence quote"))
            elif int(id_match.group("id")) != fact[id_field]:
                issues.append(_relation_mismatch(id_field, f"{id_field} does not match the identifier in evidence"))
    return issues, ambiguous


def _validate_node_coordinate(fact: dict[str, Any], quote: str) -> tuple[list[dict[str, str]], list[dict[str, str]]]:
    match = _NODE_COORDINATE_RE.search(unicodedata.normalize("NFKC", quote))
    if match is None:
        return [], [_ambiguous("evidence.quote", "NODE_COORDINATE evidence must identify node ID, coordinate pair, and length unit")]
    issues: list[dict[str, str]] = []
    if int(match.group("node")) != fact.get("nodeId"):
        issues.append(_relation_mismatch("nodeId", "nodeId does not match NODE_COORDINATE evidence"))
    if not _same_number(fact.get("x"), match.group("x")) or not _same_number(fact.get("y"), match.group("y")):
        issues.append(_numeric_mismatch("evidence.quote", "NODE_COORDINATE values do not match evidence"))
    if fact.get("unit") != match.group("unit"):
        issues.append(_unit_mismatch("unit", "NODE_COORDINATE unit does not match evidence"))
    return issues, []


def _validate_three_ids(
    fact: dict[str, Any],
    quote: str,
    *,
    pattern: re.Pattern[str],
    fields: tuple[str, ...],
    groups: tuple[str, ...],
) -> tuple[list[dict[str, str]], list[dict[str, str]]]:
    match = pattern.search(unicodedata.normalize("NFKC", quote))
    if match is None:
        return [], [_ambiguous("evidence.quote", f"{fact.get('kind')} evidence does not match a deterministic V1 relation grammar")]
    issues: list[dict[str, str]] = []
    for field, group in zip(fields, groups, strict=True):
        if int(match.group(group)) != fact.get(field):
            issues.append(_relation_mismatch(field, f"{field} does not match the identifier in evidence"))
    return issues, []


def _validate_constraint(fact: dict[str, Any], quote: str) -> tuple[list[dict[str, str]], list[dict[str, str]]]:
    normalized = unicodedata.normalize("NFKC", quote)
    fixed = _FIXED_RE.search(normalized)
    if fixed is not None:
        node_token = fixed.group("cn_node") or fixed.group("cn_node_alt") or fixed.group("en_node")
        issues = []
        if int(node_token) != fact.get("nodeId"):
            issues.append(_relation_mismatch("nodeId", "Constraint nodeId does not match evidence"))
        if set(fact.get("dofs", [])) != {"UX", "UY", "RZ"}:
            issues.append(_relation_mismatch("dofs", "The exact fixed alias maps to UX, UY, and RZ"))
        return issues, []

    match = _DOF_RE.search(normalized)
    if match is None:
        return [], [_ambiguous("evidence.quote", "Constraint evidence must use explicit DOF labels or the exact fixed alias")]
    node_token = match.group("cn_node") or match.group("cn_node_alt") or match.group("en_node")
    recovered_dofs = set(re.findall(r"UX|UY|RZ", match.group("dofs"), re.IGNORECASE))
    recovered_dofs = {dof.upper() for dof in recovered_dofs}
    issues: list[dict[str, str]] = []
    if int(node_token) != fact.get("nodeId"):
        issues.append(_relation_mismatch("nodeId", "Constraint nodeId does not match evidence"))
    if recovered_dofs != set(fact.get("dofs", [])):
        issues.append(_relation_mismatch("dofs", "Constraint DOFs do not match explicit evidence labels"))
    return issues, []


def _validate_nodal_mass(fact: dict[str, Any], quote: str) -> tuple[list[dict[str, str]], list[dict[str, str]]]:
    normalized = unicodedata.normalize("NFKC", quote)
    equal_match = re.search(
        rf"(?:节点|node\s*)(?P<node>\d+).*?mUX.*?mUY.*?(?:均为|both\s*(?:are|=))\s*(?P<value>{_NUMBER})",
        normalized,
        re.IGNORECASE,
    )
    if equal_match is not None:
        issues: list[dict[str, str]] = []
        if int(equal_match.group("node")) != fact.get("nodeId"):
            issues.append(_relation_mismatch("nodeId", "NODAL_MASS nodeId does not match evidence"))
        if not _same_number(fact.get("mUX"), equal_match.group("value")) or not _same_number(fact.get("mUY"), equal_match.group("value")):
            issues.append(_numeric_mismatch("evidence.quote", "NODAL_MASS values do not match evidence"))
        return issues, []

    separate = re.search(
        rf"(?:节点|node\s*)(?P<node>\d+).*?mUX\s*(?:=|:|为)\s*(?P<mux>{_NUMBER}).*?mUY\s*(?:=|:|为)\s*(?P<muy>{_NUMBER})",
        normalized,
        re.IGNORECASE,
    )
    if separate is None:
        return [], [_ambiguous("evidence.quote", "NODAL_MASS evidence must identify nodeId, mUX, and mUY deterministically")]
    issues = []
    if int(separate.group("node")) != fact.get("nodeId"):
        issues.append(_relation_mismatch("nodeId", "NODAL_MASS nodeId does not match evidence"))
    if not _same_number(fact.get("mUX"), separate.group("mux")) or not _same_number(fact.get("mUY"), separate.group("muy")):
        issues.append(_numeric_mismatch("evidence.quote", "NODAL_MASS values do not match evidence"))
    return issues, []


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
            ambiguous.append(_ambiguous("evidence.quote", "SPAN evidence must contain a deterministic number+length-unit form"))
        else:
            if not _same_number(fact.get("value"), match.group("value")):
                issues.append(_numeric_mismatch("value", "SPAN value does not match the numeric token in evidence"))
            if fact.get("unit") != match.group("unit"):
                issues.append(_unit_mismatch("unit", "SPAN unit does not match the unit token in evidence"))
    elif kind == "UNIT_DECLARATION":
        more_issues, more_ambiguous = _validate_unit_declaration(fact, quote)
        issues.extend(more_issues)
        ambiguous.extend(more_ambiguous)
    elif kind == "YOUNGS_MODULUS":
        more_issues, more_ambiguous = _validate_property(
            fact,
            quote,
            label_pattern=r"(?:E|Young'?s?\s+modulus|杨氏模量|弹性模量)",
            allowed_units=("Pa", "N/m²", "N/mm²", "kN/m²", "kN/mm²"),
            id_field="materialId",
            id_pattern=r"(?:材料|material\s*)(?P<id>\d+)",
        )
        issues.extend(more_issues)
        ambiguous.extend(more_ambiguous)
    elif kind == "SECTION_AREA":
        more_issues, more_ambiguous = _validate_property(
            fact,
            quote,
            label_pattern=r"(?:A|截面面积|section\s+area|area)",
            allowed_units=("m²", "cm²", "mm²"),
            id_field="sectionId",
            id_pattern=r"(?:截面|section\s*)(?P<id>\d+)",
        )
        issues.extend(more_issues)
        ambiguous.extend(more_ambiguous)
    elif kind == "SECTION_IZ":
        more_issues, more_ambiguous = _validate_property(
            fact,
            quote,
            label_pattern=r"(?:Iz|I_z|截面惯性矩|moment\s+of\s+inertia)",
            allowed_units=("m⁴", "cm⁴", "mm⁴"),
            id_field="sectionId",
            id_pattern=r"(?:截面|section\s*)(?P<id>\d+)",
        )
        issues.extend(more_issues)
        ambiguous.extend(more_ambiguous)
    elif kind == "NODE_COORDINATE":
        more_issues, more_ambiguous = _validate_node_coordinate(fact, quote)
        issues.extend(more_issues)
        ambiguous.extend(more_ambiguous)
    elif kind == "ELEMENT_CONNECTIVITY":
        more_issues, more_ambiguous = _validate_three_ids(
            fact,
            quote,
            pattern=_ELEMENT_CONNECTIVITY_RE,
            fields=("elementId", "nodeI", "nodeJ"),
            groups=("element", "node_i", "node_j"),
        )
        issues.extend(more_issues)
        ambiguous.extend(more_ambiguous)
    elif kind == "ELEMENT_MATERIAL_REF":
        more_issues, more_ambiguous = _validate_three_ids(
            fact,
            quote,
            pattern=_ELEMENT_MATERIAL_RE,
            fields=("elementId", "materialId"),
            groups=("element", "material"),
        )
        issues.extend(more_issues)
        ambiguous.extend(more_ambiguous)
    elif kind == "ELEMENT_SECTION_REF":
        more_issues, more_ambiguous = _validate_three_ids(
            fact,
            quote,
            pattern=_ELEMENT_SECTION_RE,
            fields=("elementId", "sectionId"),
            groups=("element", "section"),
        )
        issues.extend(more_issues)
        ambiguous.extend(more_ambiguous)
    elif kind == "NODE_CONSTRAINT":
        more_issues, more_ambiguous = _validate_constraint(fact, quote)
        issues.extend(more_issues)
        ambiguous.extend(more_ambiguous)
    elif kind == "NODAL_MASS":
        more_issues, more_ambiguous = _validate_nodal_mass(fact, quote)
        issues.extend(more_issues)
        ambiguous.extend(more_ambiguous)

    return {"issues": issues, "ambiguous": ambiguous}
