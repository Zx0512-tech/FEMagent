from __future__ import annotations

import copy
import json
import math
import re
from pathlib import Path

from fem_core.analysis_spec import validate_engineering_analysis_spec

FIXTURE = Path("tests/fixtures/analysis_spec/simple-linear-static-v2.json")


def load_v2_static() -> dict:
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


def codes(result: dict) -> set[str]:
    return {issue["code"] for issue in result["issues"]}


def assert_invalid(result: dict, code: str) -> None:
    assert result["schema"] == "FEMAGENT_ANALYSIS_SPEC_VALIDATION_V1"
    assert result["status"] == "INVALID"
    assert code in codes(result)
    assert result["normalizedSpec"] is None
    assert result["analysisSpecFingerprint"] is None


def test_v2_static_validates_and_has_independent_fingerprint() -> None:
    result = validate_engineering_analysis_spec(load_v2_static())

    assert result["schema"] == "FEMAGENT_ANALYSIS_SPEC_VALIDATION_V1"
    assert result["status"] == "VALID"
    assert result["issues"] == []
    assert result["normalizedSpec"]["schemaVersion"] == "2.0"
    assert result["normalizedSpec"]["definition"]["loadCases"][0]["loadCaseId"] == "LC1"
    assert re.fullmatch(r"[0-9a-f]{64}", result["analysisSpecFingerprint"])


def test_v2_static_shared_envelope_fails_closed() -> None:
    malformed_fp = load_v2_static()
    malformed_fp["modelSpecFingerprint"] = "ABC"
    assert_invalid(
        validate_engineering_analysis_spec(malformed_fp),
        "ANALYSIS_SPEC_INVALID_MODEL_FINGERPRINT",
    )

    wrong_kind = load_v2_static()
    wrong_kind["kind"] = "solver_analysis_spec"
    assert_invalid(
        validate_engineering_analysis_spec(wrong_kind),
        "ANALYSIS_SPEC_INVALID_SCHEMA",
    )

    wrong_discriminator = load_v2_static()
    wrong_discriminator["analysisType"] = "TRANSIENT"
    assert_invalid(
        validate_engineering_analysis_spec(wrong_discriminator),
        "ANALYSIS_SPEC_UNSUPPORTED_ANALYSIS_TYPE",
    )


def test_v2_static_rejects_unknown_fields_at_each_static_layer() -> None:
    mutators = (
        lambda spec: spec.__setitem__("unexpected", True),
        lambda spec: spec["units"].__setitem__("length", "m"),
        lambda spec: spec["definition"].__setitem__("solver", "opensees"),
        lambda spec: spec["definition"]["loadCases"][0].__setitem__("name", "dead"),
        lambda spec: spec["definition"]["loadCases"][0]["nodalLoads"][0].__setitem__(
            "label", "P"
        ),
        lambda spec: spec["resultRequests"][0].__setitem__("operation", "SUMMARY"),
        lambda spec: spec["resultRequests"][0]["target"].__setitem__("role", "TIP"),
    )

    for mutator in mutators:
        spec = load_v2_static()
        mutator(spec)
        assert_invalid(
            validate_engineering_analysis_spec(spec),
            "ANALYSIS_SPEC_UNKNOWN_FIELD",
        )


def test_v2_static_force_unit_is_explicit_and_closed() -> None:
    spec = load_v2_static()
    spec["units"]["force"] = "lbf"
    assert_invalid(
        validate_engineering_analysis_spec(spec),
        "ANALYSIS_SPEC_UNSUPPORTED_UNIT",
    )


def test_v2_static_requires_exactly_one_load_case() -> None:
    empty = load_v2_static()
    empty["definition"]["loadCases"] = []
    assert_invalid(
        validate_engineering_analysis_spec(empty),
        "ANALYSIS_SPEC_INVALID_LOAD_CASE_COUNT",
    )

    multiple = load_v2_static()
    second = copy.deepcopy(multiple["definition"]["loadCases"][0])
    second["loadCaseId"] = "LC2"
    multiple["definition"]["loadCases"].append(second)
    assert_invalid(
        validate_engineering_analysis_spec(multiple),
        "ANALYSIS_SPEC_INVALID_LOAD_CASE_COUNT",
    )


def test_v2_static_requires_nonempty_explicit_nodal_loads() -> None:
    spec = load_v2_static()
    spec["definition"]["loadCases"][0]["nodalLoads"] = []
    assert_invalid(
        validate_engineering_analysis_spec(spec),
        "ANALYSIS_SPEC_INVALID_SCHEMA",
    )


def test_v2_static_rejects_zero_and_duplicate_nodal_load_targets() -> None:
    zero = load_v2_static()
    zero["definition"]["loadCases"][0]["nodalLoads"][0] = {
        "nodeId": 2,
        "FX": 0,
        "FY": 0,
        "MZ": 0,
    }
    assert_invalid(
        validate_engineering_analysis_spec(zero),
        "ANALYSIS_SPEC_ZERO_NODAL_LOAD",
    )

    duplicate = load_v2_static()
    duplicate["definition"]["loadCases"][0]["nodalLoads"].append(
        {"nodeId": 2, "FX": 1, "FY": 0, "MZ": 0}
    )
    assert_invalid(
        validate_engineering_analysis_spec(duplicate),
        "ANALYSIS_SPEC_DUPLICATE_NODAL_LOAD_TARGET",
    )


def test_v2_static_nodal_load_shape_and_numbers_are_strict() -> None:
    missing_component = load_v2_static()
    del missing_component["definition"]["loadCases"][0]["nodalLoads"][0]["FX"]
    assert_invalid(
        validate_engineering_analysis_spec(missing_component),
        "ANALYSIS_SPEC_INVALID_SCHEMA",
    )

    nonfinite = load_v2_static()
    nonfinite["definition"]["loadCases"][0]["nodalLoads"][0]["FY"] = math.inf
    assert_invalid(
        validate_engineering_analysis_spec(nonfinite),
        "ANALYSIS_SPEC_INVALID_NUMBER",
    )

    bool_number = load_v2_static()
    bool_number["definition"]["loadCases"][0]["nodalLoads"][0]["MZ"] = True
    assert_invalid(
        validate_engineering_analysis_spec(bool_number),
        "ANALYSIS_SPEC_INVALID_NUMBER",
    )


def test_v2_static_ids_and_target_ids_are_strict() -> None:
    bad_case_id = load_v2_static()
    bad_case_id["definition"]["loadCases"][0]["loadCaseId"] = "1LC"
    assert_invalid(
        validate_engineering_analysis_spec(bad_case_id),
        "ANALYSIS_SPEC_INVALID_ID",
    )

    bad_load_target = load_v2_static()
    bad_load_target["definition"]["loadCases"][0]["nodalLoads"][0]["nodeId"] = 0
    assert_invalid(
        validate_engineering_analysis_spec(bad_load_target),
        "ANALYSIS_SPEC_INVALID_TARGET_ID",
    )

    bad_result_target = load_v2_static()
    bad_result_target["resultRequests"][0]["target"]["id"] = True
    assert_invalid(
        validate_engineering_analysis_spec(bad_result_target),
        "ANALYSIS_SPEC_INVALID_TARGET_ID",
    )


def test_v2_static_whitelist_accepts_all_pr25_static_request_forms() -> None:
    spec = load_v2_static()
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
            "location": "END_J",
        },
    ]

    assert validate_engineering_analysis_spec(spec)["status"] == "VALID"


def test_v2_static_rejects_unsupported_static_request() -> None:
    spec = load_v2_static()
    spec["resultRequests"][0]["component"] = "Z"
    assert_invalid(
        validate_engineering_analysis_spec(spec),
        "ANALYSIS_SPEC_UNSUPPORTED_RESULT_REQUEST",
    )


def test_v2_static_result_requests_are_nonempty_unique_and_bound_to_load_case() -> None:
    empty = load_v2_static()
    empty["resultRequests"] = []
    assert_invalid(
        validate_engineering_analysis_spec(empty),
        "ANALYSIS_SPEC_INVALID_SCHEMA",
    )

    duplicate = load_v2_static()
    duplicate["resultRequests"].append(copy.deepcopy(duplicate["resultRequests"][0]))
    assert_invalid(
        validate_engineering_analysis_spec(duplicate),
        "ANALYSIS_SPEC_DUPLICATE_ID",
    )

    missing_case = load_v2_static()
    missing_case["resultRequests"][0]["loadCaseId"] = "LC2"
    assert_invalid(
        validate_engineering_analysis_spec(missing_case),
        "ANALYSIS_SPEC_RESULT_LOAD_CASE_NOT_FOUND",
    )

    bad_request_id = load_v2_static()
    bad_request_id["resultRequests"][0]["requestId"] = "1R"
    assert_invalid(
        validate_engineering_analysis_spec(bad_request_id),
        "ANALYSIS_SPEC_INVALID_ID",
    )


def test_v2_static_does_not_check_model_target_existence() -> None:
    spec = load_v2_static()
    spec["definition"]["loadCases"][0]["nodalLoads"][0]["nodeId"] = 999999
    spec["resultRequests"][0]["target"]["id"] = 999999

    assert validate_engineering_analysis_spec(spec)["status"] == "VALID"


def test_v2_static_reordering_preserves_normalized_spec_and_fingerprint() -> None:
    first = load_v2_static()
    first["definition"]["loadCases"][0]["nodalLoads"] = [
        {"nodeId": 3, "FX": 1, "FY": 0, "MZ": 0},
        {"nodeId": 2, "FX": 0, "FY": -10, "MZ": 0},
    ]
    first["resultRequests"] = [
        {
            "requestId": "R2",
            "loadCaseId": "LC1",
            "quantity": "GENERALIZED_FORCE",
            "target": {"type": "ELEMENT", "id": 1},
            "component": "MZ",
            "location": "END_I",
        },
        {
            "requestId": "R1",
            "loadCaseId": "LC1",
            "quantity": "DISPLACEMENT",
            "target": {"type": "NODE", "id": 2},
            "component": "Y",
        },
    ]

    second = copy.deepcopy(first)
    second["definition"]["loadCases"][0]["nodalLoads"].reverse()
    second["resultRequests"].reverse()

    result_a = validate_engineering_analysis_spec(first)
    result_b = validate_engineering_analysis_spec(second)

    assert result_a["status"] == "VALID"
    assert result_b["status"] == "VALID"
    assert result_a["normalizedSpec"] == result_b["normalizedSpec"]
    assert result_a["analysisSpecFingerprint"] == result_b["analysisSpecFingerprint"]
