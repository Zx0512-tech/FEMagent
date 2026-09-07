from __future__ import annotations

import copy
import json
from pathlib import Path

from fem_core.analysis_spec import validate_engineering_analysis_spec

FIXTURE = Path("tests/fixtures/analysis_spec/simple-linear-static.json")


def load_spec() -> dict:
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


def fingerprint(spec: dict) -> str:
    result = validate_engineering_analysis_spec(spec)
    assert result["status"] == "VALID"
    assert result["analysisSpecFingerprint"] is not None
    return result["analysisSpecFingerprint"]


def multi_item_spec() -> dict:
    spec = load_spec()
    spec["loadCases"][0]["nodalLoads"].append(
        {"nodeId": 5, "FX": 3, "FY": 0, "MZ": 0}
    )
    spec["resultRequests"].append(
        {
            "requestId": "R2",
            "loadCaseId": "LC1",
            "quantity": "REACTION_FORCE",
            "target": {"type": "NODE", "id": 1},
            "component": "X",
        }
    )
    return spec


def test_collection_order_does_not_change_analysis_fingerprint() -> None:
    baseline = multi_item_spec()
    reordered = copy.deepcopy(baseline)
    reordered["loadCases"][0]["nodalLoads"] = list(
        reversed(reordered["loadCases"][0]["nodalLoads"])
    )
    reordered["resultRequests"] = list(reversed(reordered["resultRequests"]))

    assert fingerprint(reordered) == fingerprint(baseline)


def test_engineering_fact_changes_change_analysis_fingerprint() -> None:
    baseline = multi_item_spec()
    baseline_fp = fingerprint(baseline)

    changed_force = copy.deepcopy(baseline)
    changed_force["loadCases"][0]["nodalLoads"][0]["FY"] = -11
    assert fingerprint(changed_force) != baseline_fp

    changed_target = copy.deepcopy(baseline)
    changed_target["resultRequests"][0]["target"]["id"] = 99
    assert fingerprint(changed_target) != baseline_fp

    changed_component = copy.deepcopy(baseline)
    changed_component["resultRequests"][1]["component"] = "Y"
    assert fingerprint(changed_component) != baseline_fp

    changed_model = copy.deepcopy(baseline)
    changed_model["modelSpecFingerprint"] = "f" * 64
    assert fingerprint(changed_model) != baseline_fp
