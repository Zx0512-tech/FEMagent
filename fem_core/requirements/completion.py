from __future__ import annotations

import copy
import hashlib
import json
from collections import defaultdict
from typing import Any

from fem_core.errors import FemCoreError
from fem_core.model_spec import validate_engineering_model_spec
from fem_core.requirements.evidence import validate_explicit_evidence
from fem_core.requirements.schema import DRAFT_PROFILE, validate_requirement_draft_schema
from fem_core.requirements.templates import expand_beam_template, validate_template_intent

COMPLETION_SCHEMA = "FEMAGENT_ENGINEERING_REQUIREMENT_COMPLETION_V1"


def _canonical_hash(value: Any) -> str:
    canonical = json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()


def _missing(subject: str, message: str) -> dict[str, str]:
    return {
        "code": "REQUIREMENT_FACT_MISSING",
        "subject": subject,
        "message": message,
    }


def _ambiguous(subject: str, message: str, *, code: str = "REQUIREMENT_FACT_AMBIGUOUS") -> dict[str, str]:
    return {"code": code, "subject": subject, "message": message}


def _conflict(subject: str, message: str) -> dict[str, str]:
    return {
        "code": "REQUIREMENT_FACT_CONFLICT",
        "subject": subject,
        "message": message,
    }


def _base_report(*, requirement_fingerprint: str | None) -> dict[str, Any]:
    return {
        "schema": COMPLETION_SCHEMA,
        "profile": DRAFT_PROFILE,
        "status": "INCOMPLETE",
        "acceptedFacts": [],
        "derivedFacts": [],
        "template": None,
        "issues": [],
        "missing": [],
        "ambiguous": [],
        "conflicts": [],
        "candidateModelSpec": None,
        "modelSpecValidation": None,
        "modelSpecFingerprint": None,
        "requirementFingerprint": requirement_fingerprint,
    }


def _fact_key(fact: dict[str, Any]) -> tuple[Any, ...]:
    kind = fact["kind"]
    if kind == "SPAN":
        return kind,
    if kind == "UNIT_DECLARATION":
        return kind, fact["dimension"]
    if kind == "YOUNGS_MODULUS":
        return kind, fact.get("materialId")
    if kind in {"SECTION_AREA", "SECTION_IZ"}:
        return kind, fact.get("sectionId")
    if kind in {"NODE_COORDINATE", "NODE_CONSTRAINT", "NODAL_MASS"}:
        return kind, fact["nodeId"]
    if kind in {"ELEMENT_CONNECTIVITY", "ELEMENT_MATERIAL_REF", "ELEMENT_SECTION_REF"}:
        return kind, fact["elementId"]
    return kind,


def _fact_value(fact: dict[str, Any]) -> Any:
    ignored = {"kind", "source", "evidence"}
    return {key: fact[key] for key in sorted(fact) if key not in ignored}


def _dedupe_and_detect_fact_conflicts(
    facts: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, str]]]:
    grouped: dict[tuple[Any, ...], list[dict[str, Any]]] = defaultdict(list)
    for fact in facts:
        grouped[_fact_key(fact)].append(fact)

    accepted: list[dict[str, Any]] = []
    conflicts: list[dict[str, str]] = []
    for key in sorted(grouped, key=repr):
        records = grouped[key]
        values = {_canonical_hash(_fact_value(record)) for record in records}
        if len(values) > 1:
            conflicts.append(
                _conflict(
                    ".".join(str(part) for part in key),
                    f"Conflicting USER_EXPLICIT facts were supplied for {key!r}",
                )
            )
            continue
        accepted.append(copy.deepcopy(records[0]))
    accepted.sort(key=lambda item: (item["kind"], _canonical_hash(item)))
    return accepted, conflicts


def _single_fact(facts: list[dict[str, Any]], kind: str) -> dict[str, Any] | None:
    matches = [fact for fact in facts if fact["kind"] == kind]
    if len(matches) == 1:
        return matches[0]
    return None


def _unit_facts(facts: list[dict[str, Any]]) -> dict[str, str]:
    return {
        fact["dimension"]: fact["value"]
        for fact in facts
        if fact["kind"] == "UNIT_DECLARATION"
    }


def _base_length_units(facts: list[dict[str, Any]]) -> set[str]:
    result: set[str] = set()
    for fact in facts:
        if fact["kind"] in {"SPAN", "NODE_COORDINATE"}:
            result.add(fact["unit"])
    return result


def _property_records(facts: list[dict[str, Any]], kind: str) -> list[dict[str, Any]]:
    return [fact for fact in facts if fact["kind"] == kind]


def _merge_template(
    *,
    accepted: list[dict[str, Any]],
    template_id: str,
    span: dict[str, Any],
) -> tuple[dict[str, Any], list[dict[str, Any]], list[dict[str, str]]]:
    expansion = expand_beam_template(
        template_id,
        span_value=span["value"],
        span_unit=span["unit"],
    )
    conflicts: list[dict[str, str]] = []

    template_nodes = {item["id"]: item for item in expansion["nodes"]}
    for fact in accepted:
        if fact["kind"] != "NODE_COORDINATE" or fact["nodeId"] not in template_nodes:
            continue
        expected = template_nodes[fact["nodeId"]]
        if (
            fact["x"] != expected["x"]
            or fact["y"] != expected["y"]
            or fact["unit"] != span["unit"]
        ):
            conflicts.append(
                _conflict(
                    f"nodes.{fact['nodeId']}",
                    "Explicit node coordinates conflict with the controlled beam template",
                )
            )

    template_elements = {item["id"]: item for item in expansion["elements"]}
    for fact in accepted:
        if fact["kind"] != "ELEMENT_CONNECTIVITY" or fact["elementId"] not in template_elements:
            continue
        expected = template_elements[fact["elementId"]]
        if fact["nodeI"] != expected["nodeI"] or fact["nodeJ"] != expected["nodeJ"]:
            conflicts.append(
                _conflict(
                    f"elements.{fact['elementId']}",
                    "Explicit element connectivity conflicts with the controlled beam template",
                )
            )

    template_constraints = {item["nodeId"]: set(item["dofs"]) for item in expansion["constraints"]}
    for fact in accepted:
        if fact["kind"] != "NODE_CONSTRAINT" or fact["nodeId"] not in template_constraints:
            continue
        if set(fact["dofs"]) != template_constraints[fact["nodeId"]]:
            conflicts.append(
                _conflict(
                    f"constraints.{fact['nodeId']}",
                    "Explicit node constraints conflict with the controlled beam template",
                )
            )

    return expansion, copy.deepcopy(expansion["derivedFacts"]), conflicts


def _check_property_units(
    *,
    units: dict[str, str],
    accepted: list[dict[str, Any]],
) -> list[dict[str, str]]:
    conflicts: list[dict[str, str]] = []
    length = units.get("length")
    force = units.get("force")
    if length is None:
        return conflicts

    expected_area = f"{length}²"
    expected_iz = f"{length}⁴"
    for fact in accepted:
        if fact["kind"] == "SECTION_AREA" and fact["unit"] != expected_area:
            conflicts.append(_conflict("section.area.unit", "SECTION_AREA unit is not the square of the accepted model length unit"))
        elif fact["kind"] == "SECTION_IZ" and fact["unit"] != expected_iz:
            conflicts.append(_conflict("section.iz.unit", "SECTION_IZ unit is not the fourth power of the accepted model length unit"))

    if force is None:
        return conflicts
    compatible_modulus_units = {
        ("N", "m"): {"Pa", "N/m²"},
        ("N", "cm"): {"N/cm²"},
        ("N", "mm"): {"N/mm²"},
        ("kN", "m"): {"kN/m²"},
        ("kN", "cm"): {"kN/cm²"},
        ("kN", "mm"): {"kN/mm²"},
    }.get((force, length), set())
    for fact in accepted:
        if fact["kind"] == "YOUNGS_MODULUS" and fact["unit"] not in compatible_modulus_units:
            conflicts.append(_conflict("material.youngsModulus.unit", "YOUNGS_MODULUS unit is not identity-compatible with the accepted model force/length units"))
    return conflicts


def _assemble_materials(
    accepted: list[dict[str, Any]],
    derived: list[dict[str, Any]],
    ambiguous: list[dict[str, str]],
) -> list[dict[str, Any]]:
    records = _property_records(accepted, "YOUNGS_MODULUS")
    if not records:
        return []

    explicit_ids = {record["materialId"] for record in records if "materialId" in record}
    if len(records) == 1:
        record = records[0]
        material_id = record.get("materialId", 1)
        if "materialId" not in record:
            derived.append(
                {
                    "kind": "MATERIAL_ID",
                    "source": "DETERMINISTIC_DERIVED",
                    "ruleId": "SINGLETON_ENTITY_ID_V1",
                    "materialId": material_id,
                }
            )
        return [{"id": material_id, "type": "LINEAR_ELASTIC", "youngsModulus": record["value"]}]

    if len(explicit_ids) == len(records) and len(explicit_ids) == len(records):
        return sorted(
            [
                {"id": record["materialId"], "type": "LINEAR_ELASTIC", "youngsModulus": record["value"]}
                for record in records
            ],
            key=lambda item: item["id"],
        )

    ambiguous.append(
        _ambiguous(
            "materials",
            "Multiple material property records require explicitly evidenced material IDs",
        )
    )
    return []


def _assemble_sections(
    accepted: list[dict[str, Any]],
    derived: list[dict[str, Any]],
    ambiguous: list[dict[str, str]],
) -> list[dict[str, Any]]:
    areas = _property_records(accepted, "SECTION_AREA")
    izs = _property_records(accepted, "SECTION_IZ")
    if not areas or not izs:
        return []

    if len(areas) == 1 and len(izs) == 1:
        area = areas[0]
        iz = izs[0]
        ids = {record["sectionId"] for record in (area, iz) if "sectionId" in record}
        if len(ids) > 1:
            ambiguous.append(_ambiguous("sections", "SECTION_AREA and SECTION_IZ identify different section IDs"))
            return []
        section_id = next(iter(ids), 1)
        if not ids:
            derived.append(
                {
                    "kind": "SECTION_ID",
                    "source": "DETERMINISTIC_DERIVED",
                    "ruleId": "SINGLETON_ENTITY_ID_V1",
                    "sectionId": section_id,
                }
            )
        return [{"id": section_id, "type": "FRAME_2D", "area": area["value"], "iz": iz["value"]}]

    area_by_id = {record.get("sectionId"): record for record in areas if "sectionId" in record}
    iz_by_id = {record.get("sectionId"): record for record in izs if "sectionId" in record}
    common_ids = sorted(set(area_by_id) & set(iz_by_id))
    if len(common_ids) == len(areas) == len(izs):
        return [
            {
                "id": section_id,
                "type": "FRAME_2D",
                "area": area_by_id[section_id]["value"],
                "iz": iz_by_id[section_id]["value"],
            }
            for section_id in common_ids
        ]

    ambiguous.append(
        _ambiguous(
            "sections",
            "Multiple section property records require matching explicitly evidenced section IDs",
        )
    )
    return []


def _assemble_topology(
    *,
    accepted: list[dict[str, Any]],
    template_expansion: dict[str, Any] | None,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    if template_expansion is not None:
        nodes = copy.deepcopy(template_expansion["nodes"])
        connectivity = copy.deepcopy(template_expansion["elements"])
        constraints = copy.deepcopy(template_expansion["constraints"])
        return nodes, connectivity, constraints

    nodes = sorted(
        [
            {"id": fact["nodeId"], "x": fact["x"], "y": fact["y"]}
            for fact in accepted
            if fact["kind"] == "NODE_COORDINATE"
        ],
        key=lambda item: item["id"],
    )
    connectivity = sorted(
        [
            {"id": fact["elementId"], "nodeI": fact["nodeI"], "nodeJ": fact["nodeJ"]}
            for fact in accepted
            if fact["kind"] == "ELEMENT_CONNECTIVITY"
        ],
        key=lambda item: item["id"],
    )
    constraints = sorted(
        [
            {"nodeId": fact["nodeId"], "dofs": list(fact["dofs"])}
            for fact in accepted
            if fact["kind"] == "NODE_CONSTRAINT"
        ],
        key=lambda item: item["nodeId"],
    )
    return nodes, connectivity, constraints


def _bind_elements(
    *,
    connectivity: list[dict[str, Any]],
    accepted: list[dict[str, Any]],
    materials: list[dict[str, Any]],
    sections: list[dict[str, Any]],
    derived: list[dict[str, Any]],
    ambiguous: list[dict[str, str]],
) -> list[dict[str, Any]]:
    material_refs = {
        fact["elementId"]: fact["materialId"]
        for fact in accepted
        if fact["kind"] == "ELEMENT_MATERIAL_REF"
    }
    section_refs = {
        fact["elementId"]: fact["sectionId"]
        for fact in accepted
        if fact["kind"] == "ELEMENT_SECTION_REF"
    }
    material_ids = {item["id"] for item in materials}
    section_ids = {item["id"] for item in sections}
    result: list[dict[str, Any]] = []

    for item in connectivity:
        element_id = item["id"]
        material_id = material_refs.get(element_id)
        section_id = section_refs.get(element_id)
        if material_id is None and len(materials) == 1:
            material_id = materials[0]["id"]
            derived.append(
                {
                    "kind": "ELEMENT_MATERIAL_REF",
                    "source": "DETERMINISTIC_DERIVED",
                    "ruleId": "SINGLETON_ELEMENT_BINDING_V1",
                    "elementId": element_id,
                    "materialId": material_id,
                }
            )
        if section_id is None and len(sections) == 1:
            section_id = sections[0]["id"]
            derived.append(
                {
                    "kind": "ELEMENT_SECTION_REF",
                    "source": "DETERMINISTIC_DERIVED",
                    "ruleId": "SINGLETON_ELEMENT_BINDING_V1",
                    "elementId": element_id,
                    "sectionId": section_id,
                }
            )
        if material_id is None:
            ambiguous.append(_ambiguous(f"elements.{element_id}.materialId", "Element material binding cannot be resolved deterministically"))
            continue
        if section_id is None:
            ambiguous.append(_ambiguous(f"elements.{element_id}.sectionId", "Element section binding cannot be resolved deterministically"))
            continue
        if material_id not in material_ids:
            ambiguous.append(_ambiguous(f"elements.{element_id}.materialId", f"Element references unavailable material {material_id}"))
            continue
        if section_id not in section_ids:
            ambiguous.append(_ambiguous(f"elements.{element_id}.sectionId", f"Element references unavailable section {section_id}"))
            continue
        result.append(
            {
                "id": element_id,
                "type": "ELASTIC_FRAME_2D",
                "formulation": "EULER_BERNOULLI",
                "nodeI": item["nodeI"],
                "nodeJ": item["nodeJ"],
                "materialId": material_id,
                "sectionId": section_id,
            }
        )
    return sorted(result, key=lambda item: item["id"])


def complete_engineering_requirement(draft: dict[str, Any]) -> dict[str, Any]:
    schema_result = validate_requirement_draft_schema(draft)
    if schema_result["status"] != "VALID":
        report = _base_report(requirement_fingerprint=None)
        report["status"] = "INVALID_DRAFT"
        report["issues"] = schema_result["issues"]
        return report

    normalized = schema_result["normalizedDraft"]
    requirement_fingerprint = _canonical_hash(normalized)
    report = _base_report(requirement_fingerprint=requirement_fingerprint)
    sources = {source["sourceId"]: source["text"] for source in normalized["sources"]}

    admitted: list[dict[str, Any]] = []
    evidence_ambiguous: list[dict[str, str]] = []
    evidence_issues: list[dict[str, str]] = []
    for fact in normalized["facts"]:
        evidence_result = validate_explicit_evidence(sources=sources, fact=fact)
        if evidence_result["issues"]:
            evidence_issues.extend(evidence_result["issues"])
            continue
        if evidence_result["ambiguous"]:
            evidence_ambiguous.extend(evidence_result["ambiguous"])
            continue
        admitted.append(copy.deepcopy(fact))

    if evidence_issues:
        report["status"] = "INVALID_DRAFT"
        report["issues"] = evidence_issues
        return report

    template_intent = normalized["templateIntent"]
    template_id: str | None = None
    if template_intent is not None:
        template_result = validate_template_intent(
            sources=sources,
            template_intent=template_intent,
        )
        if template_result["status"] != "VALID":
            report["status"] = "INVALID_DRAFT"
            report["issues"] = template_result["issues"]
            return report
        template_id = template_result["templateId"]
        report["template"] = {
            "templateId": template_id,
            "evidence": copy.deepcopy(template_intent["evidence"]),
        }

    accepted, explicit_conflicts = _dedupe_and_detect_fact_conflicts(admitted)
    report["acceptedFacts"] = copy.deepcopy(accepted)
    if explicit_conflicts:
        report["status"] = "CONFLICT"
        report["conflicts"] = explicit_conflicts
        return report

    ambiguous = copy.deepcopy(evidence_ambiguous)
    missing: list[dict[str, str]] = []
    conflicts: list[dict[str, str]] = []
    derived: list[dict[str, Any]] = [
        {
            "kind": "PROFILE_FIELDS",
            "source": "DETERMINISTIC_DERIVED",
            "ruleId": "FRAME_2D_PROFILE_FIELDS_V1",
            "schemaVersion": "1.0",
            "modelKind": "engineering_model_spec",
            "dimension": "2D",
            "family": "FRAME",
            "coordinateSystem": "CARTESIAN_XY",
        }
    ]

    units = _unit_facts(accepted)
    base_length_units = _base_length_units(accepted)
    if "length" not in units:
        if len(base_length_units) == 1:
            units["length"] = next(iter(base_length_units))
            derived.append(
                {
                    "kind": "UNIT_DECLARATION",
                    "source": "DETERMINISTIC_DERIVED",
                    "ruleId": "CONSISTENT_LENGTH_UNIT_V1",
                    "dimension": "length",
                    "value": units["length"],
                }
            )
        elif len(base_length_units) > 1:
            conflicts.append(_conflict("units.length", "Accepted length-bearing facts use mixed units and V1 performs no conversion"))
    elif base_length_units and base_length_units != {units["length"]}:
        conflicts.append(_conflict("units.length", "Explicit model length unit conflicts with accepted length-bearing facts"))

    for dimension in ("length", "force", "time"):
        if dimension not in units:
            missing.append(_missing(f"units.{dimension}", f"Model {dimension} unit is required"))

    span = _single_fact(accepted, "SPAN")
    template_expansion: dict[str, Any] | None = None
    if template_id is not None:
        if span is None:
            missing.append(_missing("span", "Controlled beam templates require an explicit SPAN fact"))
        else:
            template_expansion, template_derived, template_conflicts = _merge_template(
                accepted=accepted,
                template_id=template_id,
                span=span,
            )
            derived.extend(template_derived)
            conflicts.extend(template_conflicts)

    conflicts.extend(_check_property_units(units=units, accepted=accepted))

    youngs = _property_records(accepted, "YOUNGS_MODULUS")
    areas = _property_records(accepted, "SECTION_AREA")
    izs = _property_records(accepted, "SECTION_IZ")
    if not youngs:
        missing.append(_missing("material.youngsModulus", "At least one explicit Young's modulus is required"))
    if not areas:
        missing.append(_missing("section.area", "At least one explicit section area is required"))
    if not izs:
        missing.append(_missing("section.iz", "At least one explicit section Iz is required"))

    materials = _assemble_materials(accepted, derived, ambiguous)
    sections = _assemble_sections(accepted, derived, ambiguous)
    nodes, connectivity, constraints = _assemble_topology(
        accepted=accepted,
        template_expansion=template_expansion,
    )

    if template_id is None:
        if len(nodes) < 2:
            missing.append(_missing("nodes", "Explicit no-template FRAME authoring requires at least two evidenced nodes"))
        if not connectivity:
            missing.append(_missing("elements", "Explicit no-template FRAME authoring requires evidenced element connectivity"))

    elements = _bind_elements(
        connectivity=connectivity,
        accepted=accepted,
        materials=materials,
        sections=sections,
        derived=derived,
        ambiguous=ambiguous,
    )

    nodal_masses = sorted(
        [
            {"nodeId": fact["nodeId"], "mUX": fact["mUX"], "mUY": fact["mUY"]}
            for fact in accepted
            if fact["kind"] == "NODAL_MASS"
        ],
        key=lambda item: item["nodeId"],
    )
    if not nodal_masses:
        derived.append(
            {
                "kind": "NODAL_MASS_COLLECTION",
                "source": "DETERMINISTIC_DERIVED",
                "ruleId": "EMPTY_NODAL_MASS_COLLECTION_V1",
                "value": [],
            }
        )

    derived.sort(key=lambda item: (item.get("source", ""), item.get("kind", ""), _canonical_hash(item)))
    report["derivedFacts"] = copy.deepcopy(derived)
    report["missing"] = sorted(missing, key=lambda item: (item["subject"], item["code"]))
    report["ambiguous"] = sorted(ambiguous, key=lambda item: (item.get("subject", "evidence"), item["code"]))
    report["conflicts"] = sorted(conflicts, key=lambda item: (item["subject"], item["code"]))

    if conflicts:
        report["status"] = "CONFLICT"
        return report
    if missing or ambiguous:
        report["status"] = "INCOMPLETE"
        return report

    candidate = {
        "schemaVersion": "1.0",
        "kind": "engineering_model_spec",
        "dimension": "2D",
        "family": "FRAME",
        "coordinateSystem": "CARTESIAN_XY",
        "units": {"length": units["length"], "force": units["force"], "time": units["time"]},
        "nodes": nodes,
        "materials": materials,
        "sections": sections,
        "elements": elements,
        "constraints": constraints,
        "nodalMasses": nodal_masses,
    }
    validation = validate_engineering_model_spec(candidate)
    if validation["status"] != "VALID":
        raise FemCoreError(
            "REQUIREMENT_COMPLETION_INTERNAL_INVARIANT",
            "Controlled completion assembled a candidate that violates the PR21 ModelSpec invariant",
            details={"modelSpecValidation": validation},
        )

    report["status"] = "COMPLETE"
    report["candidateModelSpec"] = validation["normalizedSpec"]
    report["modelSpecValidation"] = validation
    report["modelSpecFingerprint"] = validation["modelSpecFingerprint"]
    return report
