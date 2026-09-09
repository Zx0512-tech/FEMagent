from __future__ import annotations

import copy
import json
import math
import re
from pathlib import Path

from fem_core.analysis_spec import validate_engineering_analysis_spec

NODAL_FIXTURE = Path("tests/fixtures/analysis_spec/simple-transient-nodal-v2.json")
BASE_FIXTURE = Path("tests/fixtures/analysis_spec/simple-transient-base-v2.json")


def load_nodal() -> dict:
    return json.loads(NODAL_FIXTURE.read_text(encoding="utf-8"))


def load_base() -> dict:
    return json.loads(BASE_FIXTURE.read_text(encoding="utf-8"))


def codes(result: dict) -> set[str]:
    return {issue["code"] for issue in result["issues"]}


def assert_invalid(result: dict, code: str) -> None:
    assert result["schema"] == "FEMAGENT_ANALYSIS_SPEC_VALIDATION_V1"
    assert result["status"] == "INVALID"
    assert code in codes(result)
    assert result["normalizedSpec"] is None
    assert result["analysisSpecFingerprint"] is None


def fingerprint(spec: dict) -> str:
    result = validate_engineering_analysis_spec(spec)
    assert result["status"] == "VALID"
    return result["analysisSpecFingerprint"]


def test_transient_nodal_and_base_validate_and_normalize() -> None:
    nodal = validate_engineering_analysis_spec(load_nodal())
    base = validate_engineering_analysis_spec(load_base())

    assert nodal["status"] == "VALID"
    assert base["status"] == "VALID"
    assert re.fullmatch(r"[0-9a-f]{64}", nodal["analysisSpecFingerprint"])
    assert re.fullmatch(r"[0-9a-f]{64}", base["analysisSpecFingerprint"])
    assert nodal["normalizedSpec"]["definition"]["excitation"]["loadArtifact"]["path"] == "loads/force.csv"
    assert base["normalizedSpec"]["definition"]["excitation"]["loadArtifact"]["path"] == "loads/eq.csv"


def test_transient_time_step_and_duration_must_be_positive_finite_numbers() -> None:
    for field in ("timeStep", "duration"):
        for value in (0, -0.1, math.inf, True):
            spec = load_nodal()
            spec["definition"]["time"][field] = value
            assert_invalid(
                validate_engineering_analysis_spec(spec),
                "ANALYSIS_SPEC_INVALID_TIME",
            )


def test_transient_damping_none_is_exact_and_rayleigh_is_explicit() -> None:
    none_extra = load_nodal()
    none_extra["definition"]["damping"]["alphaM"] = 0.0
    assert_invalid(
        validate_engineering_analysis_spec(none_extra),
        "ANALYSIS_SPEC_UNKNOWN_FIELD",
    )

    unsupported = load_nodal()
    unsupported["definition"]["damping"] = {"type": "MODAL_RATIO", "ratio": 0.05}
    assert_invalid(
        validate_engineering_analysis_spec(unsupported),
        "ANALYSIS_SPEC_UNSUPPORTED_DAMPING",
    )

    for field in ("alphaM", "betaK"):
        for value in (-1.0, math.inf, True):
            spec = load_base()
            spec["definition"]["damping"][field] = value
            assert_invalid(
                validate_engineering_analysis_spec(spec),
                "ANALYSIS_SPEC_INVALID_DAMPING_COEFFICIENT",
            )

    zero = load_base()
    zero["definition"]["damping"] = {"type": "RAYLEIGH", "alphaM": 0.0, "betaK": 0.0}
    result = validate_engineering_analysis_spec(zero)
    assert result["status"] == "VALID"
    assert result["normalizedSpec"]["definition"]["damping"] == zero["definition"]["damping"]


def test_transient_artifact_reference_is_exact_and_syntax_only() -> None:
    bad_sha = load_base()
    bad_sha["definition"]["excitation"]["loadArtifact"]["sha256"] = "ABC"
    assert_invalid(
        validate_engineering_analysis_spec(bad_sha),
        "ANALYSIS_SPEC_INVALID_ARTIFACT_SHA",
    )

    for path in ("", "/tmp/eq.csv", "../eq.csv", "loads/../eq.csv", "C:/eq.csv", "C:\\eq.csv"):
        spec = load_base()
        spec["definition"]["excitation"]["loadArtifact"]["path"] = path
        assert_invalid(
            validate_engineering_analysis_spec(spec),
            "ANALYSIS_SPEC_INVALID_ARTIFACT_PATH",
        )

    backslash = load_base()
    backslash["definition"]["excitation"]["loadArtifact"]["path"] = "loads\\eq.csv"
    result = validate_engineering_analysis_spec(backslash)
    assert result["status"] == "VALID"
    assert result["normalizedSpec"]["definition"]["excitation"]["loadArtifact"]["path"] == "loads\\eq.csv"


def test_nodal_time_history_units_and_excitation_are_closed() -> None:
    bad_unit = load_nodal()
    bad_unit["units"]["force"] = "lbf"
    assert_invalid(
        validate_engineering_analysis_spec(bad_unit),
        "ANALYSIS_SPEC_UNSUPPORTED_UNIT",
    )

    extra_unit = load_nodal()
    extra_unit["units"]["time"] = "s"
    assert_invalid(
        validate_engineering_analysis_spec(extra_unit),
        "ANALYSIS_SPEC_UNKNOWN_FIELD",
    )

    bad_node = load_nodal()
    bad_node["definition"]["excitation"]["nodeId"] = 0
    assert_invalid(
        validate_engineering_analysis_spec(bad_node),
        "ANALYSIS_SPEC_INVALID_TARGET_ID",
    )

    for field, value in (("component", "RZ"), ("quantity", "ACCELERATION")):
        spec = load_nodal()
        spec["definition"]["excitation"][field] = value
        assert_invalid(
            validate_engineering_analysis_spec(spec),
            "ANALYSIS_SPEC_UNSUPPORTED_TRANSIENT_EXCITATION",
        )


def test_uniform_base_excitation_units_and_excitation_are_closed() -> None:
    bad_units = load_base()
    bad_units["units"]["force"] = "N"
    assert_invalid(
        validate_engineering_analysis_spec(bad_units),
        "ANALYSIS_SPEC_UNKNOWN_FIELD",
    )

    extra_node = load_base()
    extra_node["definition"]["excitation"]["nodeId"] = 3
    assert_invalid(
        validate_engineering_analysis_spec(extra_node),
        "ANALYSIS_SPEC_UNKNOWN_FIELD",
    )

    for field, value in (("component", "RZ"), ("quantity", "FORCE")):
        spec = load_base()
        spec["definition"]["excitation"][field] = value
        assert_invalid(
            validate_engineering_analysis_spec(spec),
            "ANALYSIS_SPEC_UNSUPPORTED_TRANSIENT_EXCITATION",
        )


def test_base_excitation_rejects_bare_acceleration() -> None:
    spec = load_base()
    spec["resultRequests"][0]["quantity"] = "ACCELERATION"
    assert_invalid(
        validate_engineering_analysis_spec(spec),
        "ANALYSIS_SPEC_UNSUPPORTED_TRANSIENT_RESPONSE",
    )


def test_nodal_excitation_acceleration_semantics_are_unambiguous() -> None:
    assert validate_engineering_analysis_spec(load_nodal())["status"] == "VALID"

    for quantity in ("RELATIVE_ACCELERATION", "ABSOLUTE_ACCELERATION"):
        spec = load_nodal()
        spec["resultRequests"][0]["quantity"] = quantity
        assert_invalid(
            validate_engineering_analysis_spec(spec),
            "ANALYSIS_SPEC_UNSUPPORTED_TRANSIENT_RESPONSE",
        )


def test_base_excitation_accepts_relative_and_absolute_acceleration() -> None:
    for quantity in ("RELATIVE_ACCELERATION", "ABSOLUTE_ACCELERATION"):
        spec = load_base()
        spec["resultRequests"][0]["quantity"] = quantity
        assert validate_engineering_analysis_spec(spec)["status"] == "VALID"


def test_transient_common_result_whitelist_is_shared_by_both_excitation_profiles() -> None:
    requests = [
        {
            "requestId": "D3X",
            "quantity": "DISPLACEMENT",
            "target": {"type": "NODE", "id": 3},
            "component": "X",
        },
        {
            "requestId": "V3Y",
            "quantity": "VELOCITY",
            "target": {"type": "NODE", "id": 3},
            "component": "Y",
        },
        {
            "requestId": "RF1X",
            "quantity": "REACTION_FORCE",
            "target": {"type": "NODE", "id": 1},
            "component": "X",
        },
        {
            "requestId": "RM1Z",
            "quantity": "REACTION_MOMENT",
            "target": {"type": "NODE", "id": 1},
            "component": "Z",
        },
        {
            "requestId": "M1I",
            "quantity": "GENERALIZED_FORCE",
            "target": {"type": "ELEMENT", "id": 1},
            "component": "MZ",
            "location": "END_I",
        },
    ]

    for loader in (load_nodal, load_base):
        spec = loader()
        spec["resultRequests"] = copy.deepcopy(requests)
        assert validate_engineering_analysis_spec(spec)["status"] == "VALID"


def test_transient_result_request_shape_ids_and_whitelist_fail_closed() -> None:
    load_case = load_nodal()
    load_case["resultRequests"][0]["loadCaseId"] = "LC1"
    assert_invalid(
        validate_engineering_analysis_spec(load_case),
        "ANALYSIS_SPEC_UNKNOWN_FIELD",
    )

    bad_target = load_nodal()
    bad_target["resultRequests"][0]["target"]["id"] = True
    assert_invalid(
        validate_engineering_analysis_spec(bad_target),
        "ANALYSIS_SPEC_INVALID_TARGET_ID",
    )

    unsupported = load_nodal()
    unsupported["resultRequests"][0]["quantity"] = "PERIOD"
    assert_invalid(
        validate_engineering_analysis_spec(unsupported),
        "ANALYSIS_SPEC_UNSUPPORTED_TRANSIENT_RESPONSE",
    )

    empty = load_nodal()
    empty["resultRequests"] = []
    assert_invalid(
        validate_engineering_analysis_spec(empty),
        "ANALYSIS_SPEC_INVALID_SCHEMA",
    )

    duplicate = load_nodal()
    duplicate["resultRequests"].append(copy.deepcopy(duplicate["resultRequests"][0]))
    assert_invalid(
        validate_engineering_analysis_spec(duplicate),
        "ANALYSIS_SPEC_DUPLICATE_ID",
    )


def test_transient_artifact_path_is_not_semantic_identity() -> None:
    first = load_base()
    second = copy.deepcopy(first)
    second["definition"]["excitation"]["loadArtifact"]["path"] = "copies/eq.csv"

    assert fingerprint(first) == fingerprint(second)


def test_transient_artifact_sha_is_semantic_identity() -> None:
    first = load_base()
    second = copy.deepcopy(first)
    second["definition"]["excitation"]["loadArtifact"]["sha256"] = "b" * 64

    assert fingerprint(first) != fingerprint(second)


def test_transient_request_reordering_preserves_normalized_spec_and_fingerprint() -> None:
    first = load_base()
    first["resultRequests"] = [
        {
            "requestId": "V3Y",
            "quantity": "VELOCITY",
            "target": {"type": "NODE", "id": 3},
            "component": "Y",
        },
        {
            "requestId": "A3X",
            "quantity": "ABSOLUTE_ACCELERATION",
            "target": {"type": "NODE", "id": 3},
            "component": "X",
        },
        {
            "requestId": "M1J",
            "quantity": "GENERALIZED_FORCE",
            "target": {"type": "ELEMENT", "id": 1},
            "component": "MZ",
            "location": "END_J",
        },
    ]
    second = copy.deepcopy(first)
    second["resultRequests"].reverse()

    result_a = validate_engineering_analysis_spec(first)
    result_b = validate_engineering_analysis_spec(second)

    assert result_a["status"] == "VALID"
    assert result_b["status"] == "VALID"
    assert result_a["normalizedSpec"] == result_b["normalizedSpec"]
    assert result_a["analysisSpecFingerprint"] == result_b["analysisSpecFingerprint"]


def test_transient_intrinsic_validation_does_not_read_artifact_or_model_targets() -> None:
    spec = load_nodal()
    spec["definition"]["excitation"]["nodeId"] = 999999
    spec["definition"]["excitation"]["loadArtifact"]["path"] = "missing/not-real.csv"
    spec["resultRequests"][0]["target"]["id"] = 999999

    assert validate_engineering_analysis_spec(spec)["status"] == "VALID"
