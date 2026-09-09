from __future__ import annotations

import copy
import json
from pathlib import Path

from fem_core.analysis_spec import validate_engineering_analysis_spec
from fem_core.analysis_spec.v2.migration import migrate_engineering_analysis_spec_v1_to_v2

V1_FIXTURE = Path("tests/fixtures/analysis_spec/simple-linear-static.json")
V2_FIXTURE = Path("tests/fixtures/analysis_spec/simple-linear-static-v2.json")


def load_v1() -> dict:
    return json.loads(V1_FIXTURE.read_text(encoding="utf-8"))


def load_v2_static() -> dict:
    return json.loads(V2_FIXTURE.read_text(encoding="utf-8"))


def test_valid_v1_static_migrates_deterministically() -> None:
    source = load_v1()

    first = migrate_engineering_analysis_spec_v1_to_v2(source)
    second = migrate_engineering_analysis_spec_v1_to_v2(source)

    assert first == second
    assert first["schema"] == "FEMAGENT_ANALYSIS_SPEC_MIGRATION_V1_TO_V2"
    assert first["status"] == "MIGRATED"
    assert first["candidateSpec"]["schemaVersion"] == "2.0"
    assert first["candidateSpec"]["kind"] == "engineering_analysis_spec"
    assert first["candidateSpec"]["analysisType"] == "LINEAR_STATIC"
    assert first["candidateSpec"]["definition"]["loadCases"] == source["loadCases"]
    assert first["source"]["schemaVersion"] == "1.0"
    assert first["target"]["schemaVersion"] == "2.0"
    assert first["source"]["analysisSpecFingerprint"] != first["target"]["analysisSpecFingerprint"]


def test_v2_source_is_not_migrated_again() -> None:
    report = migrate_engineering_analysis_spec_v1_to_v2(load_v2_static())

    assert report["schema"] == "FEMAGENT_ANALYSIS_SPEC_MIGRATION_V1_TO_V2"
    assert report["status"] == "UNSUPPORTED_SOURCE"
    assert report["candidateSpec"] is None


def test_invalid_v1_source_is_rejected() -> None:
    source = load_v1()
    source["units"]["force"] = "lbf"

    report = migrate_engineering_analysis_spec_v1_to_v2(source)

    assert report["status"] == "INVALID_SOURCE"
    assert report["candidateSpec"] is None


def test_migration_preserves_result_requests_semantically() -> None:
    source = load_v1()
    source["resultRequests"] = [
        {
            "requestId": "R2",
            "loadCaseId": "LC1",
            "quantity": "GENERALIZED_FORCE",
            "target": {"type": "ELEMENT", "id": 1},
            "component": "MZ",
            "location": "END_J",
        },
        {
            "requestId": "R1",
            "loadCaseId": "LC1",
            "quantity": "DISPLACEMENT",
            "target": {"type": "NODE", "id": 2},
            "component": "Y",
        },
    ]

    source_validation = validate_engineering_analysis_spec(source)
    assert source_validation["status"] == "VALID"

    report = migrate_engineering_analysis_spec_v1_to_v2(source)

    assert report["status"] == "MIGRATED"
    assert report["candidateSpec"]["resultRequests"] == source_validation["normalizedSpec"]["resultRequests"]


def test_migrated_candidate_is_valid_v2_and_uses_target_fingerprint() -> None:
    report = migrate_engineering_analysis_spec_v1_to_v2(load_v1())

    target_validation = validate_engineering_analysis_spec(report["candidateSpec"])

    assert target_validation["status"] == "VALID"
    assert target_validation["normalizedSpec"] == report["candidateSpec"]
    assert target_validation["analysisSpecFingerprint"] == report["target"]["analysisSpecFingerprint"]


def test_migration_does_not_mutate_source() -> None:
    source = load_v1()
    before = copy.deepcopy(source)

    migrate_engineering_analysis_spec_v1_to_v2(source)

    assert source == before
