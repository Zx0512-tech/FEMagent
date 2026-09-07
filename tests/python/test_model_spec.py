from __future__ import annotations

import copy
import json
import math
import re
from pathlib import Path

from fem_core.model_spec import validate_engineering_model_spec

FIXTURE = Path("tests/fixtures/model_spec/simple-portal-frame.json")


def load_spec() -> dict:
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


def codes(result: dict) -> set[str]:
    return {issue["code"] for issue in result["issues"]}


def assert_invalid(result: dict, code: str) -> None:
    assert result["schema"] == "FEMAGENT_MODEL_SPEC_VALIDATION_V1"
    assert result["status"] == "INVALID"
    assert code in codes(result)
    assert result["normalizedSpec"] is None
    assert result["modelSpecFingerprint"] is None


def test_valid_portal_frame_returns_normalized_spec_and_fingerprint() -> None:
    result = validate_engineering_model_spec(load_spec())

    assert result["schema"] == "FEMAGENT_MODEL_SPEC_VALIDATION_V1"
    assert result["status"] == "VALID"
    assert result["issues"] == []
    assert result["normalizedSpec"] is not None
    assert re.fullmatch(r"[0-9a-f]{64}", result["modelSpecFingerprint"])


def test_schema_and_unknown_fields_fail_closed() -> None:
    bad_schema = load_spec()
    bad_schema["schemaVersion"] = "2.0"
    assert_invalid(validate_engineering_model_spec(bad_schema), "MODEL_SPEC_INVALID_SCHEMA")

    extra = load_spec()
    extra["nodes"][0]["name"] = "base"
    assert_invalid(validate_engineering_model_spec(extra), "MODEL_SPEC_UNKNOWN_FIELD")


def test_required_collections_cannot_be_empty() -> None:
    for field in ("nodes", "materials", "sections", "elements"):
        spec = load_spec()
        spec[field] = []
        assert_invalid(validate_engineering_model_spec(spec), "MODEL_SPEC_EMPTY_COLLECTION")


def test_invalid_ids_and_numbers_are_rejected() -> None:
    bad_id = load_spec()
    bad_id["nodes"][0]["id"] = 0
    assert_invalid(validate_engineering_model_spec(bad_id), "MODEL_SPEC_INVALID_ID")

    bool_id = load_spec()
    bool_id["nodes"][0]["id"] = True
    assert_invalid(validate_engineering_model_spec(bool_id), "MODEL_SPEC_INVALID_ID")

    bad_number = load_spec()
    bad_number["nodes"][0]["x"] = math.inf
    assert_invalid(validate_engineering_model_spec(bad_number), "MODEL_SPEC_INVALID_NUMBER")


def test_scope_and_unit_values_are_rejected_explicitly() -> None:
    dimension = load_spec()
    dimension["dimension"] = "3D"
    assert_invalid(validate_engineering_model_spec(dimension), "MODEL_SPEC_UNSUPPORTED_DIMENSION")

    family = load_spec()
    family["family"] = "TRUSS"
    assert_invalid(validate_engineering_model_spec(family), "MODEL_SPEC_UNSUPPORTED_FAMILY")

    coordinate_system = load_spec()
    coordinate_system["coordinateSystem"] = "POLAR"
    assert_invalid(validate_engineering_model_spec(coordinate_system), "MODEL_SPEC_UNSUPPORTED_VALUE")

    units = load_spec()
    units["units"]["length"] = "inch"
    assert_invalid(validate_engineering_model_spec(units), "MODEL_SPEC_UNSUPPORTED_UNIT")


def test_duplicate_ids_are_rejected_per_namespace() -> None:
    spec = load_spec()
    spec["nodes"][1]["id"] = spec["nodes"][0]["id"]
    assert_invalid(validate_engineering_model_spec(spec), "MODEL_SPEC_DUPLICATE_ID")


def test_element_references_and_connectivity_are_validated() -> None:
    missing_node = load_spec()
    missing_node["elements"][0]["nodeJ"] = 99
    assert_invalid(validate_engineering_model_spec(missing_node), "MODEL_SPEC_ELEMENT_NODE_NOT_FOUND")

    missing_material = load_spec()
    missing_material["elements"][0]["materialId"] = 99
    assert_invalid(validate_engineering_model_spec(missing_material), "MODEL_SPEC_ELEMENT_MATERIAL_NOT_FOUND")

    missing_section = load_spec()
    missing_section["elements"][0]["sectionId"] = 99
    assert_invalid(validate_engineering_model_spec(missing_section), "MODEL_SPEC_ELEMENT_SECTION_NOT_FOUND")

    self_connection = load_spec()
    self_connection["elements"][0]["nodeJ"] = self_connection["elements"][0]["nodeI"]
    assert_invalid(validate_engineering_model_spec(self_connection), "MODEL_SPEC_ELEMENT_SELF_CONNECTION")

    zero_length = load_spec()
    zero_length["nodes"][3]["x"] = zero_length["nodes"][0]["x"]
    zero_length["nodes"][3]["y"] = zero_length["nodes"][0]["y"]
    assert_invalid(validate_engineering_model_spec(zero_length), "MODEL_SPEC_ZERO_LENGTH_ELEMENT")


def test_element_type_and_formulation_are_fixed_in_v1() -> None:
    element_type = load_spec()
    element_type["elements"][0]["type"] = "TRUSS_2D"
    assert_invalid(validate_engineering_model_spec(element_type), "MODEL_SPEC_UNSUPPORTED_ELEMENT_TYPE")

    formulation = load_spec()
    formulation["elements"][0]["formulation"] = "TIMOSHENKO"
    assert_invalid(validate_engineering_model_spec(formulation), "MODEL_SPEC_UNSUPPORTED_FORMULATION")


def test_material_and_section_properties_must_be_positive() -> None:
    material = load_spec()
    material["materials"][0]["youngsModulus"] = 0.0
    assert_invalid(
        validate_engineering_model_spec(material),
        "MODEL_SPEC_NONPOSITIVE_MATERIAL_PROPERTY",
    )

    section = load_spec()
    section["sections"][0]["iz"] = -1.0
    assert_invalid(
        validate_engineering_model_spec(section),
        "MODEL_SPEC_NONPOSITIVE_SECTION_PROPERTY",
    )


def test_constraint_contract_is_strict() -> None:
    missing_node = load_spec()
    missing_node["constraints"][0]["nodeId"] = 99
    assert_invalid(validate_engineering_model_spec(missing_node), "MODEL_SPEC_CONSTRAINT_NODE_NOT_FOUND")

    duplicate_record = load_spec()
    duplicate_record["constraints"].append(copy.deepcopy(duplicate_record["constraints"][0]))
    assert_invalid(validate_engineering_model_spec(duplicate_record), "MODEL_SPEC_DUPLICATE_CONSTRAINT")

    duplicate_dof = load_spec()
    duplicate_dof["constraints"][0]["dofs"] = ["UX", "UX"]
    assert_invalid(validate_engineering_model_spec(duplicate_dof), "MODEL_SPEC_DUPLICATE_DOF")

    unsupported_dof = load_spec()
    unsupported_dof["constraints"][0]["dofs"] = ["UZ"]
    assert_invalid(validate_engineering_model_spec(unsupported_dof), "MODEL_SPEC_UNSUPPORTED_VALUE")


def test_nodal_mass_contract_is_strict() -> None:
    missing_node = load_spec()
    missing_node["nodalMasses"] = [{"nodeId": 99, "mUX": 1.0, "mUY": 1.0}]
    assert_invalid(validate_engineering_model_spec(missing_node), "MODEL_SPEC_MASS_NODE_NOT_FOUND")

    duplicate_mass = load_spec()
    duplicate_mass["nodalMasses"] = [
        {"nodeId": 3, "mUX": 1.0, "mUY": 1.0},
        {"nodeId": 3, "mUX": 2.0, "mUY": 2.0},
    ]
    assert_invalid(validate_engineering_model_spec(duplicate_mass), "MODEL_SPEC_DUPLICATE_MASS")

    negative_mass = load_spec()
    negative_mass["nodalMasses"] = [{"nodeId": 3, "mUX": -1.0, "mUY": 0.0}]
    assert_invalid(validate_engineering_model_spec(negative_mass), "MODEL_SPEC_INVALID_MASS")

    zero_mass = load_spec()
    zero_mass["nodalMasses"] = [{"nodeId": 3, "mUX": 0.0, "mUY": 0.0}]
    assert_invalid(validate_engineering_model_spec(zero_mass), "MODEL_SPEC_INVALID_MASS")


def test_unused_node_is_warning_only() -> None:
    spec = load_spec()
    spec["nodes"].append({"id": 5, "x": 12.0, "y": 12.0})

    result = validate_engineering_model_spec(spec)

    assert result["status"] == "VALID"
    assert "MODEL_SPEC_UNUSED_NODE" in codes(result)
    warning = next(issue for issue in result["issues"] if issue["code"] == "MODEL_SPEC_UNUSED_NODE")
    assert warning["severity"] == "WARNING"
    assert result["normalizedSpec"] is not None
    assert result["modelSpecFingerprint"] is not None


def test_validation_collects_multiple_independent_errors() -> None:
    spec = load_spec()
    spec["materials"][0]["youngsModulus"] = 0.0
    spec["sections"][0]["area"] = 0.0
    spec["elements"][0]["materialId"] = 99

    result = validate_engineering_model_spec(spec)

    assert result["status"] == "INVALID"
    assert {
        "MODEL_SPEC_NONPOSITIVE_MATERIAL_PROPERTY",
        "MODEL_SPEC_NONPOSITIVE_SECTION_PROPERTY",
        "MODEL_SPEC_ELEMENT_MATERIAL_NOT_FOUND",
    }.issubset(codes(result))
