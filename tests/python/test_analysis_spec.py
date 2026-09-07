from __future__ import annotations

import copy
import json
import math
import re
from pathlib import Path

from fem_core.analysis_spec import validate_engineering_analysis_spec

FIXTURE = Path("tests/fixtures/analysis_spec/simple-linear-static.json")


def load_spec() -> dict:
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


def codes(result: dict) -> set[str]:
    return {issue["code"] for issue in result["issues"]}


def assert_invalid(result: dict, code: str) -> None:
    assert result["schema"] == "FEMAGENT_ANALYSIS_SPEC_VALIDATION_V1"
    assert result["status"] == "INVALID"
    assert code in codes(result)
    assert result["normalizedSpec"] is None
    assert result["analysisSpecFingerprint"] is None


def test_valid_spec_returns_normalized_spec_and_fingerprint() -> None:
    result = validate_engineering_analysis_spec(load_spec())

    assert result["status"] == "VALID"
    assert result["issues"] == []
    assert result["normalizedSpec"] is not None
    assert re.fullmatch(r"[0-9a-f]{64}", result["analysisSpecFingerprint"])


def test_schema_and_unknown_fields_fail_closed() -> None:
    bad_schema = load_spec()
    bad_schema["schemaVersion"] = "2.0"
    assert_invalid(validate_engineering_analysis_spec(bad_schema), "ANALYSIS_SPEC_INVALID_SCHEMA")

    for mutator in (
        lambda spec: spec.__setitem__("unexpected", True),
        lambda spec: spec["units"].__setitem__("length", "m"),
        lambda spec: spec["loadCases"][0].__setitem__("name", "dead"),
        lambda spec: spec["loadCases"][0]["nodalLoads"][0].__setitem__("label", "P"),
        lambda spec: spec["resultRequests"][0].__setitem__("operation", "SUMMARY"),
        lambda spec: spec["resultRequests"][0]["target"].__setitem__("role", "MIDSPAN"),
    ):
        spec = load_spec()
        mutator(spec)
        assert_invalid(
            validate_engineering_analysis_spec(spec),
            "ANALYSIS_SPEC_UNKNOWN_FIELD",
        )


def test_model_fingerprint_is_strict_lowercase_sha256_shape() -> None:
    malformed = load_spec()
    malformed["modelSpecFingerprint"] = "ABC"
    assert_invalid(
        validate_engineering_analysis_spec(malformed),
        "ANALYSIS_SPEC_INVALID_MODEL_FINGERPRINT",
    )

    uppercase = load_spec()
    uppercase["modelSpecFingerprint"] = "A" * 64
    assert_invalid(
        validate_engineering_analysis_spec(uppercase),
        "ANALYSIS_SPEC_INVALID_MODEL_FINGERPRINT",
    )


def test_analysis_type_and_force_unit_are_closed_v1_values() -> None:
    modal = load_spec()
    modal["analysisType"] = "MODAL"
    assert_invalid(
        validate_engineering_analysis_spec(modal),
        "ANALYSIS_SPEC_UNSUPPORTED_ANALYSIS_TYPE",
    )

    unit = load_spec()
    unit["units"]["force"] = "lbf"
    assert_invalid(
        validate_engineering_analysis_spec(unit),
        "ANALYSIS_SPEC_UNSUPPORTED_UNIT",
    )


def test_v1_requires_exactly_one_nonempty_load_case() -> None:
    empty = load_spec()
    empty["loadCases"] = []
    assert_invalid(
        validate_engineering_analysis_spec(empty),
        "ANALYSIS_SPEC_INVALID_LOAD_CASE_COUNT",
    )

    multiple = load_spec()
    second = copy.deepcopy(multiple["loadCases"][0])
    second["loadCaseId"] = "LC2"
    multiple["loadCases"].append(second)
    assert_invalid(
        validate_engineering_analysis_spec(multiple),
        "ANALYSIS_SPEC_INVALID_LOAD_CASE_COUNT",
    )

    no_loads = load_spec()
    no_loads["loadCases"][0]["nodalLoads"] = []
    assert_invalid(
        validate_engineering_analysis_spec(no_loads),
        "ANALYSIS_SPEC_INVALID_SCHEMA",
    )


def test_ids_and_nodal_load_numbers_are_strict() -> None:
    bad_case_id = load_spec()
    bad_case_id["loadCases"][0]["loadCaseId"] = "1LC"
    assert_invalid(
        validate_engineering_analysis_spec(bad_case_id),
        "ANALYSIS_SPEC_INVALID_ID",
    )

    bad_node_id = load_spec()
    bad_node_id["loadCases"][0]["nodalLoads"][0]["nodeId"] = 0
    assert_invalid(
        validate_engineering_analysis_spec(bad_node_id),
        "ANALYSIS_SPEC_INVALID_TARGET_ID",
    )

    bool_node_id = load_spec()
    bool_node_id["loadCases"][0]["nodalLoads"][0]["nodeId"] = True
    assert_invalid(
        validate_engineering_analysis_spec(bool_node_id),
        "ANALYSIS_SPEC_INVALID_TARGET_ID",
    )

    missing_component = load_spec()
    del missing_component["loadCases"][0]["nodalLoads"][0]["FX"]
    assert_invalid(
        validate_engineering_analysis_spec(missing_component),
        "ANALYSIS_SPEC_INVALID_SCHEMA",
    )

    nonfinite = load_spec()
    nonfinite["loadCases"][0]["nodalLoads"][0]["FY"] = math.inf
    assert_invalid(
        validate_engineering_analysis_spec(nonfinite),
        "ANALYSIS_SPEC_INVALID_NUMBER",
    )

    bool_number = load_spec()
    bool_number["loadCases"][0]["nodalLoads"][0]["FY"] = True
    assert_invalid(
        validate_engineering_analysis_spec(bool_number),
        "ANALYSIS_SPEC_INVALID_NUMBER",
    )


def test_zero_and_duplicate_nodal_load_targets_are_rejected() -> None:
    zero = load_spec()
    zero["loadCases"][0]["nodalLoads"][0] = {
        "nodeId": 2,
        "FX": 0,
        "FY": 0,
        "MZ": 0,
    }
    assert_invalid(
        validate_engineering_analysis_spec(zero),
        "ANALYSIS_SPEC_ZERO_NODAL_LOAD",
    )

    duplicate = load_spec()
    duplicate["loadCases"][0]["nodalLoads"].append(
        {"nodeId": 2, "FX": 1, "FY": 0, "MZ": 0}
    )
    assert_invalid(
        validate_engineering_analysis_spec(duplicate),
        "ANALYSIS_SPEC_DUPLICATE_NODAL_LOAD_TARGET",
    )


def test_result_request_v1_whitelist_accepts_supported_forms() -> None:
    spec = load_spec()
    spec["resultRequests"] = [
        {
            "requestId": "R1",
            "loadCaseId": "LC1",
            "quantity": "DISPLACEMENT",
            "target": {"type": "NODE", "id": 2},
            "component": "X",
        },
        {
            "requestId": "R2",
            "loadCaseId": "LC1",
            "quantity": "REACTION_FORCE",
            "target": {"type": "NODE", "id": 1},
            "component": "Y",
        },
        {
            "requestId": "R3",
            "loadCaseId": "LC1",
            "quantity": "REACTION_MOMENT",
            "target": {"type": "NODE", "id": 1},
            "component": "Z",
        },
        {
            "requestId": "R4",
            "loadCaseId": "LC1",
            "quantity": "GENERALIZED_FORCE",
            "target": {"type": "ELEMENT", "id": 1},
            "component": "MZ",
            "location": "END_I",
        },
    ]

    result = validate_engineering_analysis_spec(spec)
    assert result["status"] == "VALID"


def test_result_request_v1_whitelist_rejects_unsupported_forms() -> None:
    invalid_requests = [
        {
            "requestId": "R1",
            "loadCaseId": "LC1",
            "quantity": "DISPLACEMENT",
            "target": {"type": "NODE", "id": 2},
            "component": "Z",
        },
        {
            "requestId": "R1",
            "loadCaseId": "LC1",
            "quantity": "REACTION_MOMENT",
            "target": {"type": "NODE", "id": 1},
            "component": "X",
        },
        {
            "requestId": "R1",
            "loadCaseId": "LC1",
            "quantity": "GENERALIZED_FORCE",
            "target": {"type": "ELEMENT", "id": 1},
            "component": "MZ",
        },
        {
            "requestId": "R1",
            "loadCaseId": "LC1",
            "quantity": "GENERALIZED_FORCE",
            "target": {"type": "ELEMENT", "id": 1},
            "component": "MZ",
            "location": "SECTION",
        },
        {
            "requestId": "R1",
            "loadCaseId": "LC1",
            "quantity": "DISPLACEMENT",
            "target": {"type": "NODE", "id": 2},
            "component": "Y",
            "location": "END_I",
        },
        {
            "requestId": "R1",
            "loadCaseId": "LC1",
            "quantity": "STRESS",
            "target": {"type": "ELEMENT", "id": 1},
            "component": "XX",
        },
        {
            "requestId": "R1",
            "loadCaseId": "LC1",
            "quantity": "VELOCITY",
            "target": {"type": "NODE", "id": 2},
            "component": "Y",
        },
        {
            "requestId": "R1",
            "loadCaseId": "LC1",
            "quantity": "ACCELERATION",
            "target": {"type": "NODE", "id": 2},
            "component": "Y",
        },
        {
            "requestId": "R1",
            "loadCaseId": "LC1",
            "quantity": "DAMPER_RESPONSE",
            "target": {"type": "ELEMENT", "id": 1},
            "component": "FORCE",
        },
    ]

    for request in invalid_requests:
        spec = load_spec()
        spec["resultRequests"] = [request]
        assert_invalid(
            validate_engineering_analysis_spec(spec),
            "ANALYSIS_SPEC_UNSUPPORTED_RESULT_REQUEST",
        )


def test_result_request_ids_and_internal_load_case_reference_are_strict() -> None:
    bad_request_id = load_spec()
    bad_request_id["resultRequests"][0]["requestId"] = "1R"
    assert_invalid(
        validate_engineering_analysis_spec(bad_request_id),
        "ANALYSIS_SPEC_INVALID_ID",
    )

    duplicate = load_spec()
    duplicate["resultRequests"].append(copy.deepcopy(duplicate["resultRequests"][0]))
    assert_invalid(
        validate_engineering_analysis_spec(duplicate),
        "ANALYSIS_SPEC_DUPLICATE_ID",
    )

    missing_case = load_spec()
    missing_case["resultRequests"][0]["loadCaseId"] = "LC2"
    assert_invalid(
        validate_engineering_analysis_spec(missing_case),
        "ANALYSIS_SPEC_RESULT_LOAD_CASE_NOT_FOUND",
    )

    bad_target = load_spec()
    bad_target["resultRequests"][0]["target"]["id"] = 0
    assert_invalid(
        validate_engineering_analysis_spec(bad_target),
        "ANALYSIS_SPEC_INVALID_TARGET_ID",
    )

    empty = load_spec()
    empty["resultRequests"] = []
    assert_invalid(
        validate_engineering_analysis_spec(empty),
        "ANALYSIS_SPEC_INVALID_SCHEMA",
    )


def test_validator_does_not_check_model_target_existence() -> None:
    spec = load_spec()
    spec["loadCases"][0]["nodalLoads"][0]["nodeId"] = 999999
    spec["resultRequests"][0]["target"]["id"] = 999999

    result = validate_engineering_analysis_spec(spec)

    assert result["status"] == "VALID"
