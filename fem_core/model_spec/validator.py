from __future__ import annotations

import hashlib
import json
import math
from typing import Any

VALIDATION_SCHEMA = "FEMAGENT_MODEL_SPEC_VALIDATION_V1"
_ALLOWED_DOFS = ("UX", "UY", "RZ")
_ALLOWED_LENGTH_UNITS = {"m", "cm", "mm"}
_ALLOWED_FORCE_UNITS = {"N", "kN"}
_ALLOWED_TIME_UNITS = {"s", "ms"}

_TOP_LEVEL_KEYS = {
    "schemaVersion",
    "kind",
    "dimension",
    "family",
    "coordinateSystem",
    "units",
    "nodes",
    "materials",
    "sections",
    "elements",
    "constraints",
    "nodalMasses",
}


def _issue(
    issues: list[dict[str, Any]],
    severity: str,
    code: str,
    path: str,
    message: str,
) -> None:
    issues.append({"severity": severity, "code": code, "path": path, "message": message})


def _is_positive_int(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value > 0


def _is_finite_number(value: Any) -> bool:
    return (
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and math.isfinite(float(value))
    )


def _validate_exact_keys(
    value: Any,
    expected: set[str],
    path: str,
    issues: list[dict[str, Any]],
) -> bool:
    if not isinstance(value, dict):
        _issue(
            issues,
            "ERROR",
            "MODEL_SPEC_INVALID_SCHEMA",
            path,
            f"{path} must be a JSON object",
        )
        return False

    for key in sorted(set(value) - expected):
        child_path = f"{path}.{key}" if path else key
        _issue(
            issues,
            "ERROR",
            "MODEL_SPEC_UNKNOWN_FIELD",
            child_path,
            f"Unknown ModelSpec field: {child_path}",
        )
    for key in sorted(expected - set(value)):
        child_path = f"{path}.{key}" if path else key
        _issue(
            issues,
            "ERROR",
            "MODEL_SPEC_INVALID_SCHEMA",
            child_path,
            f"Required ModelSpec field is missing: {child_path}",
        )
    return True


def _validate_id(
    value: Any,
    path: str,
    issues: list[dict[str, Any]],
) -> int | None:
    if not _is_positive_int(value):
        _issue(
            issues,
            "ERROR",
            "MODEL_SPEC_INVALID_ID",
            path,
            f"{path} must be a positive integer",
        )
        return None
    return value


def _validate_number(
    value: Any,
    path: str,
    issues: list[dict[str, Any]],
) -> float | int | None:
    if not _is_finite_number(value):
        _issue(
            issues,
            "ERROR",
            "MODEL_SPEC_INVALID_NUMBER",
            path,
            f"{path} must be a finite JSON number",
        )
        return None
    return value


def _validate_collection(
    spec: dict[str, Any],
    field: str,
    minimum: int,
    issues: list[dict[str, Any]],
) -> list[Any]:
    value = spec.get(field)
    if not isinstance(value, list):
        _issue(
            issues,
            "ERROR",
            "MODEL_SPEC_INVALID_SCHEMA",
            field,
            f"{field} must be an array",
        )
        return []
    if len(value) < minimum:
        _issue(
            issues,
            "ERROR",
            "MODEL_SPEC_EMPTY_COLLECTION",
            field,
            f"{field} must contain at least {minimum} item(s)",
        )
    return value


def _record_duplicate_id(
    identifier: int | None,
    seen: set[int],
    path: str,
    namespace: str,
    issues: list[dict[str, Any]],
) -> None:
    if identifier is None:
        return
    if identifier in seen:
        _issue(
            issues,
            "ERROR",
            "MODEL_SPEC_DUPLICATE_ID",
            path,
            f"Duplicate {namespace} id {identifier}",
        )
    else:
        seen.add(identifier)


def _normalize_spec(spec: dict[str, Any]) -> dict[str, Any]:
    normalized = {
        "schemaVersion": spec["schemaVersion"],
        "kind": spec["kind"],
        "dimension": spec["dimension"],
        "family": spec["family"],
        "coordinateSystem": spec["coordinateSystem"],
        "units": {
            "length": spec["units"]["length"],
            "force": spec["units"]["force"],
            "time": spec["units"]["time"],
        },
        "nodes": sorted((dict(item) for item in spec["nodes"]), key=lambda item: item["id"]),
        "materials": sorted(
            (dict(item) for item in spec["materials"]), key=lambda item: item["id"]
        ),
        "sections": sorted(
            (dict(item) for item in spec["sections"]), key=lambda item: item["id"]
        ),
        "elements": sorted(
            (dict(item) for item in spec["elements"]), key=lambda item: item["id"]
        ),
        "constraints": [],
        "nodalMasses": sorted(
            (dict(item) for item in spec["nodalMasses"]), key=lambda item: item["nodeId"]
        ),
    }
    dof_order = {name: index for index, name in enumerate(_ALLOWED_DOFS)}
    normalized["constraints"] = sorted(
        (
            {
                "nodeId": item["nodeId"],
                "dofs": sorted(item["dofs"], key=lambda dof: dof_order[dof]),
            }
            for item in spec["constraints"]
        ),
        key=lambda item: item["nodeId"],
    )
    return normalized


def _fingerprint(normalized: dict[str, Any]) -> str:
    canonical = json.dumps(
        normalized,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()


def validate_engineering_model_spec(spec: dict[str, Any]) -> dict[str, Any]:
    issues: list[dict[str, Any]] = []
    _validate_exact_keys(spec, _TOP_LEVEL_KEYS, "", issues)

    if spec.get("schemaVersion") != "1.0" or spec.get("kind") != "engineering_model_spec":
        _issue(
            issues,
            "ERROR",
            "MODEL_SPEC_INVALID_SCHEMA",
            "schemaVersion",
            "V1 requires schemaVersion='1.0' and kind='engineering_model_spec'",
        )
    if spec.get("dimension") != "2D":
        _issue(
            issues,
            "ERROR",
            "MODEL_SPEC_UNSUPPORTED_DIMENSION",
            "dimension",
            "V1 supports dimension='2D' only",
        )
    if spec.get("family") != "FRAME":
        _issue(
            issues,
            "ERROR",
            "MODEL_SPEC_UNSUPPORTED_FAMILY",
            "family",
            "V1 supports family='FRAME' only",
        )
    if spec.get("coordinateSystem") != "CARTESIAN_XY":
        _issue(
            issues,
            "ERROR",
            "MODEL_SPEC_UNSUPPORTED_VALUE",
            "coordinateSystem",
            "V1 supports coordinateSystem='CARTESIAN_XY' only",
        )

    units = spec.get("units")
    if _validate_exact_keys(units, {"length", "force", "time"}, "units", issues):
        unit_rules = (
            ("length", _ALLOWED_LENGTH_UNITS),
            ("force", _ALLOWED_FORCE_UNITS),
            ("time", _ALLOWED_TIME_UNITS),
        )
        for name, allowed in unit_rules:
            if units.get(name) not in allowed:
                _issue(
                    issues,
                    "ERROR",
                    "MODEL_SPEC_UNSUPPORTED_UNIT",
                    f"units.{name}",
                    f"Unsupported {name} unit: {units.get(name)!r}",
                )

    nodes = _validate_collection(spec, "nodes", 2, issues)
    materials = _validate_collection(spec, "materials", 1, issues)
    sections = _validate_collection(spec, "sections", 1, issues)
    elements = _validate_collection(spec, "elements", 1, issues)
    constraints = _validate_collection(spec, "constraints", 0, issues)
    nodal_masses = _validate_collection(spec, "nodalMasses", 0, issues)

    node_ids: set[int] = set()
    node_coordinates: dict[int, tuple[float | int, float | int]] = {}
    for index, node in enumerate(nodes):
        path = f"nodes[{index}]"
        if not _validate_exact_keys(node, {"id", "x", "y"}, path, issues):
            continue
        node_id = _validate_id(node.get("id"), f"{path}.id", issues)
        _record_duplicate_id(node_id, node_ids, f"{path}.id", "node", issues)
        x = _validate_number(node.get("x"), f"{path}.x", issues)
        y = _validate_number(node.get("y"), f"{path}.y", issues)
        if node_id is not None and x is not None and y is not None and node_id not in node_coordinates:
            node_coordinates[node_id] = (x, y)

    material_ids: set[int] = set()
    for index, material in enumerate(materials):
        path = f"materials[{index}]"
        if not _validate_exact_keys(
            material, {"id", "type", "youngsModulus"}, path, issues
        ):
            continue
        material_id = _validate_id(material.get("id"), f"{path}.id", issues)
        _record_duplicate_id(material_id, material_ids, f"{path}.id", "material", issues)
        if material.get("type") != "LINEAR_ELASTIC":
            _issue(
                issues,
                "ERROR",
                "MODEL_SPEC_UNSUPPORTED_VALUE",
                f"{path}.type",
                "V1 supports LINEAR_ELASTIC materials only",
            )
        youngs_modulus = _validate_number(
            material.get("youngsModulus"), f"{path}.youngsModulus", issues
        )
        if youngs_modulus is not None and youngs_modulus <= 0:
            _issue(
                issues,
                "ERROR",
                "MODEL_SPEC_NONPOSITIVE_MATERIAL_PROPERTY",
                f"{path}.youngsModulus",
                "youngsModulus must be strictly positive",
            )

    section_ids: set[int] = set()
    for index, section in enumerate(sections):
        path = f"sections[{index}]"
        if not _validate_exact_keys(section, {"id", "type", "area", "iz"}, path, issues):
            continue
        section_id = _validate_id(section.get("id"), f"{path}.id", issues)
        _record_duplicate_id(section_id, section_ids, f"{path}.id", "section", issues)
        if section.get("type") != "FRAME_2D":
            _issue(
                issues,
                "ERROR",
                "MODEL_SPEC_UNSUPPORTED_VALUE",
                f"{path}.type",
                "V1 supports FRAME_2D sections only",
            )
        for field in ("area", "iz"):
            value = _validate_number(section.get(field), f"{path}.{field}", issues)
            if value is not None and value <= 0:
                _issue(
                    issues,
                    "ERROR",
                    "MODEL_SPEC_NONPOSITIVE_SECTION_PROPERTY",
                    f"{path}.{field}",
                    f"{field} must be strictly positive",
                )

    element_ids: set[int] = set()
    used_node_ids: set[int] = set()
    for index, element in enumerate(elements):
        path = f"elements[{index}]"
        expected = {
            "id",
            "type",
            "formulation",
            "nodeI",
            "nodeJ",
            "materialId",
            "sectionId",
        }
        if not _validate_exact_keys(element, expected, path, issues):
            continue
        element_id = _validate_id(element.get("id"), f"{path}.id", issues)
        _record_duplicate_id(element_id, element_ids, f"{path}.id", "element", issues)
        if element.get("type") != "ELASTIC_FRAME_2D":
            _issue(
                issues,
                "ERROR",
                "MODEL_SPEC_UNSUPPORTED_ELEMENT_TYPE",
                f"{path}.type",
                "V1 supports ELASTIC_FRAME_2D only",
            )
        if element.get("formulation") != "EULER_BERNOULLI":
            _issue(
                issues,
                "ERROR",
                "MODEL_SPEC_UNSUPPORTED_FORMULATION",
                f"{path}.formulation",
                "V1 supports EULER_BERNOULLI only",
            )

        node_i = _validate_id(element.get("nodeI"), f"{path}.nodeI", issues)
        node_j = _validate_id(element.get("nodeJ"), f"{path}.nodeJ", issues)
        material_id = _validate_id(element.get("materialId"), f"{path}.materialId", issues)
        section_id = _validate_id(element.get("sectionId"), f"{path}.sectionId", issues)

        if node_i is not None:
            used_node_ids.add(node_i)
            if node_i not in node_ids:
                _issue(
                    issues,
                    "ERROR",
                    "MODEL_SPEC_ELEMENT_NODE_NOT_FOUND",
                    f"{path}.nodeI",
                    f"Element references missing node {node_i}",
                )
        if node_j is not None:
            used_node_ids.add(node_j)
            if node_j not in node_ids:
                _issue(
                    issues,
                    "ERROR",
                    "MODEL_SPEC_ELEMENT_NODE_NOT_FOUND",
                    f"{path}.nodeJ",
                    f"Element references missing node {node_j}",
                )
        if material_id is not None and material_id not in material_ids:
            _issue(
                issues,
                "ERROR",
                "MODEL_SPEC_ELEMENT_MATERIAL_NOT_FOUND",
                f"{path}.materialId",
                f"Element references missing material {material_id}",
            )
        if section_id is not None and section_id not in section_ids:
            _issue(
                issues,
                "ERROR",
                "MODEL_SPEC_ELEMENT_SECTION_NOT_FOUND",
                f"{path}.sectionId",
                f"Element references missing section {section_id}",
            )
        if node_i is not None and node_j is not None and node_i == node_j:
            _issue(
                issues,
                "ERROR",
                "MODEL_SPEC_ELEMENT_SELF_CONNECTION",
                f"{path}.nodeJ",
                "Frame element endpoints must reference different node IDs",
            )
        if (
            node_i is not None
            and node_j is not None
            and node_i != node_j
            and node_i in node_coordinates
            and node_j in node_coordinates
            and node_coordinates[node_i] == node_coordinates[node_j]
        ):
            _issue(
                issues,
                "ERROR",
                "MODEL_SPEC_ZERO_LENGTH_ELEMENT",
                path,
                "Frame element endpoint coordinates are exactly coincident",
            )

    constrained_nodes: set[int] = set()
    for index, constraint in enumerate(constraints):
        path = f"constraints[{index}]"
        if not _validate_exact_keys(constraint, {"nodeId", "dofs"}, path, issues):
            continue
        node_id = _validate_id(constraint.get("nodeId"), f"{path}.nodeId", issues)
        if node_id is not None:
            if node_id in constrained_nodes:
                _issue(
                    issues,
                    "ERROR",
                    "MODEL_SPEC_DUPLICATE_CONSTRAINT",
                    f"{path}.nodeId",
                    f"Duplicate constraint record for node {node_id}",
                )
            else:
                constrained_nodes.add(node_id)
            if node_id not in node_ids:
                _issue(
                    issues,
                    "ERROR",
                    "MODEL_SPEC_CONSTRAINT_NODE_NOT_FOUND",
                    f"{path}.nodeId",
                    f"Constraint references missing node {node_id}",
                )
        dofs = constraint.get("dofs")
        if not isinstance(dofs, list) or len(dofs) == 0:
            _issue(
                issues,
                "ERROR",
                "MODEL_SPEC_INVALID_SCHEMA",
                f"{path}.dofs",
                "Constraint dofs must be a non-empty array",
            )
            continue
        seen_dofs: set[str] = set()
        for dof_index, dof in enumerate(dofs):
            dof_path = f"{path}.dofs[{dof_index}]"
            if dof not in _ALLOWED_DOFS:
                _issue(
                    issues,
                    "ERROR",
                    "MODEL_SPEC_UNSUPPORTED_VALUE",
                    dof_path,
                    f"Unsupported 2D frame DOF: {dof!r}",
                )
                continue
            if dof in seen_dofs:
                _issue(
                    issues,
                    "ERROR",
                    "MODEL_SPEC_DUPLICATE_DOF",
                    dof_path,
                    f"Duplicate constraint DOF {dof}",
                )
            else:
                seen_dofs.add(dof)

    mass_nodes: set[int] = set()
    for index, mass in enumerate(nodal_masses):
        path = f"nodalMasses[{index}]"
        if not _validate_exact_keys(mass, {"nodeId", "mUX", "mUY"}, path, issues):
            continue
        node_id = _validate_id(mass.get("nodeId"), f"{path}.nodeId", issues)
        if node_id is not None:
            if node_id in mass_nodes:
                _issue(
                    issues,
                    "ERROR",
                    "MODEL_SPEC_DUPLICATE_MASS",
                    f"{path}.nodeId",
                    f"Duplicate nodal mass record for node {node_id}",
                )
            else:
                mass_nodes.add(node_id)
            if node_id not in node_ids:
                _issue(
                    issues,
                    "ERROR",
                    "MODEL_SPEC_MASS_NODE_NOT_FOUND",
                    f"{path}.nodeId",
                    f"Nodal mass references missing node {node_id}",
                )
        m_ux = _validate_number(mass.get("mUX"), f"{path}.mUX", issues)
        m_uy = _validate_number(mass.get("mUY"), f"{path}.mUY", issues)
        if (
            m_ux is not None
            and m_uy is not None
            and (m_ux < 0 or m_uy < 0 or (m_ux == 0 and m_uy == 0))
        ):
            _issue(
                issues,
                "ERROR",
                "MODEL_SPEC_INVALID_MASS",
                path,
                "Nodal translational masses must be nonnegative with at least one positive component",
            )

    for index, node in enumerate(nodes):
        if not isinstance(node, dict):
            continue
        node_id = node.get("id")
        if _is_positive_int(node_id) and node_id not in used_node_ids:
            _issue(
                issues,
                "WARNING",
                "MODEL_SPEC_UNUSED_NODE",
                f"nodes[{index}].id",
                f"Node {node_id} is not referenced by any frame element",
            )

    has_error = any(issue["severity"] == "ERROR" for issue in issues)
    if has_error:
        return {
            "schema": VALIDATION_SCHEMA,
            "status": "INVALID",
            "issues": issues,
            "normalizedSpec": None,
            "modelSpecFingerprint": None,
        }

    normalized = _normalize_spec(spec)
    return {
        "schema": VALIDATION_SCHEMA,
        "status": "VALID",
        "issues": issues,
        "normalizedSpec": normalized,
        "modelSpecFingerprint": _fingerprint(normalized),
    }
