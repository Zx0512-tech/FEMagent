from __future__ import annotations

import copy
import json
import re
from pathlib import Path

from fem_core.analysis_spec import validate_engineering_analysis_spec

FIXTURE = Path("tests/fixtures/analysis_spec/simple-modal-v2.json")


def load_modal() -> dict:
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


def codes(result: dict) -> set[str]:
    return {item["code"] for item in result["issues"]}


def assert_invalid(result: dict, code: str) -> None:
    assert result["schema"] == "FEMAGENT_ANALYSIS_SPEC_VALIDATION_V1"
    assert result["status"] == "INVALID"
    assert code in codes(result)
    assert result["normalizedSpec"] is None
    assert result["analysisSpecFingerprint"] is None


def test_modal_v2_validates_and_fingerprints() -> None:
    result = validate_engineering_analysis_spec(load_modal())

    assert result["status"] == "VALID"
    assert result["issues"] == []
    assert result["normalizedSpec"]["analysisType"] == "MODAL"
    assert result["normalizedSpec"]["units"] == {}
    assert re.fullmatch(r"[0-9a-f]{64}", result["analysisSpecFingerprint"])


def test_modal_units_and_definition_are_exact() -> None:
    bad_units = load_modal()
    bad_units["units"]["force"] = "N"
    assert_invalid(
        validate_engineering_analysis_spec(bad_units),
        "ANALYSIS_SPEC_UNKNOWN_FIELD",
    )

    bad_definition = load_modal()
    bad_definition["definition"]["solver"] = "ARPACK"
    assert_invalid(
        validate_engineering_analysis_spec(bad_definition),
        "ANALYSIS_SPEC_UNKNOWN_FIELD",
    )


def test_modal_mode_count_must_be_positive_integer() -> None:
    for value in (0, -1, 1.5, True):
        spec = load_modal()
        spec["definition"]["modeCount"] = value
        assert_invalid(
            validate_engineering_analysis_spec(spec),
            "ANALYSIS_SPEC_INVALID_MODE_COUNT",
        )


def test_modal_scalar_quantities_are_supported() -> None:
    for quantity in ("EIGENVALUE", "NATURAL_FREQUENCY", "PERIOD"):
        spec = load_modal()
        spec["resultRequests"] = [
            {"requestId": "R1", "quantity": quantity, "mode": 1}
        ]
        assert validate_engineering_analysis_spec(spec)["status"] == "VALID"


def test_modal_scalar_request_rejects_target_component_location_and_load_case() -> None:
    for key, value in (
        ("target", {"type": "NODE", "id": 3}),
        ("component", "Y"),
        ("location", "END_I"),
        ("loadCaseId", "LC1"),
    ):
        spec = load_modal()
        request = spec["resultRequests"][0]
        request[key] = value
        assert_invalid(
            validate_engineering_analysis_spec(spec),
            "ANALYSIS_SPEC_UNKNOWN_FIELD",
        )


def test_modal_mode_index_must_be_positive_and_within_requested_count() -> None:
    for value in (0, -1, 1.5, True):
        spec = load_modal()
        spec["resultRequests"][0]["mode"] = value
        assert_invalid(
            validate_engineering_analysis_spec(spec),
            "ANALYSIS_SPEC_INVALID_MODE_INDEX",
        )

    exceeds = load_modal()
    exceeds["resultRequests"][0]["mode"] = 4
    assert_invalid(
        validate_engineering_analysis_spec(exceeds),
        "ANALYSIS_SPEC_MODE_EXCEEDS_REQUESTED_COUNT",
    )


def test_mode_shape_accepts_x_y_and_rz_node_components() -> None:
    for component in ("X", "Y", "RZ"):
        spec = load_modal()
        spec["resultRequests"] = [
            {
                "requestId": "MODE1",
                "quantity": "MODE_SHAPE",
                "mode": 1,
                "target": {"type": "NODE", "id": 3},
                "component": component,
            }
        ]
        assert validate_engineering_analysis_spec(spec)["status"] == "VALID"


def test_mode_shape_requires_node_target_and_supported_component() -> None:
    missing_target = load_modal()
    del missing_target["resultRequests"][1]["target"]
    assert_invalid(
        validate_engineering_analysis_spec(missing_target),
        "ANALYSIS_SPEC_INVALID_SCHEMA",
    )

    element_target = load_modal()
    element_target["resultRequests"][1]["target"] = {"type": "ELEMENT", "id": 1}
    assert_invalid(
        validate_engineering_analysis_spec(element_target),
        "ANALYSIS_SPEC_UNSUPPORTED_RESULT_REQUEST",
    )

    bad_target_id = load_modal()
    bad_target_id["resultRequests"][1]["target"]["id"] = 0
    assert_invalid(
        validate_engineering_analysis_spec(bad_target_id),
        "ANALYSIS_SPEC_INVALID_TARGET_ID",
    )

    bad_component = load_modal()
    bad_component["resultRequests"][1]["component"] = "Z"
    assert_invalid(
        validate_engineering_analysis_spec(bad_component),
        "ANALYSIS_SPEC_UNSUPPORTED_RESULT_REQUEST",
    )


def test_modal_rejects_unsupported_quantity() -> None:
    spec = load_modal()
    spec["resultRequests"][0]["quantity"] = "DISPLACEMENT"
    assert_invalid(
        validate_engineering_analysis_spec(spec),
        "ANALYSIS_SPEC_UNSUPPORTED_RESULT_REQUEST",
    )


def test_modal_result_requests_must_be_nonempty_and_have_unique_ids() -> None:
    empty = load_modal()
    empty["resultRequests"] = []
    assert_invalid(
        validate_engineering_analysis_spec(empty),
        "ANALYSIS_SPEC_INVALID_SCHEMA",
    )

    duplicate = load_modal()
    duplicate["resultRequests"].append(copy.deepcopy(duplicate["resultRequests"][0]))
    assert_invalid(
        validate_engineering_analysis_spec(duplicate),
        "ANALYSIS_SPEC_DUPLICATE_ID",
    )

    bad_id = load_modal()
    bad_id["resultRequests"][0]["requestId"] = "1R"
    assert_invalid(
        validate_engineering_analysis_spec(bad_id),
        "ANALYSIS_SPEC_INVALID_ID",
    )


def test_modal_validator_does_not_check_model_mass_or_target_existence() -> None:
    spec = load_modal()
    spec["resultRequests"][1]["target"]["id"] = 999999

    assert validate_engineering_analysis_spec(spec)["status"] == "VALID"


def test_modal_request_reordering_preserves_normalized_spec_and_fingerprint() -> None:
    first = load_modal()
    first["resultRequests"] = [
        {"requestId": "PER2", "quantity": "PERIOD", "mode": 2},
        {
            "requestId": "MODE1RZ",
            "quantity": "MODE_SHAPE",
            "mode": 1,
            "target": {"type": "NODE", "id": 3},
            "component": "RZ",
        },
        {"requestId": "EIG1", "quantity": "EIGENVALUE", "mode": 1},
    ]
    second = copy.deepcopy(first)
    second["resultRequests"].reverse()

    result_a = validate_engineering_analysis_spec(first)
    result_b = validate_engineering_analysis_spec(second)

    assert result_a["status"] == "VALID"
    assert result_b["status"] == "VALID"
    assert result_a["normalizedSpec"] == result_b["normalizedSpec"]
    assert result_a["analysisSpecFingerprint"] == result_b["analysisSpecFingerprint"]
