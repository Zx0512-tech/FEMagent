from __future__ import annotations

import copy
import json
from pathlib import Path

from fem_core.model_spec import validate_engineering_model_spec

FIXTURE = Path("tests/fixtures/model_spec/simple-portal-frame.json")


def load_spec() -> dict:
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


def fingerprint(spec: dict) -> str:
    result = validate_engineering_model_spec(spec)
    assert result["status"] == "VALID"
    assert result["modelSpecFingerprint"] is not None
    return result["modelSpecFingerprint"]


def test_entity_and_dof_order_do_not_change_fingerprint() -> None:
    baseline = load_spec()
    reordered = copy.deepcopy(baseline)
    for field in ("nodes", "materials", "sections", "elements", "constraints", "nodalMasses"):
        reordered[field] = list(reversed(reordered[field]))
    for constraint in reordered["constraints"]:
        constraint["dofs"] = list(reversed(constraint["dofs"]))

    assert fingerprint(reordered) == fingerprint(baseline)


def test_engineering_content_changes_change_fingerprint() -> None:
    baseline = load_spec()
    baseline_fp = fingerprint(baseline)

    changed_e = copy.deepcopy(baseline)
    changed_e["materials"][0]["youngsModulus"] *= 0.95
    assert fingerprint(changed_e) != baseline_fp

    changed_coordinate = copy.deepcopy(baseline)
    changed_coordinate["nodes"][2]["x"] += 0.1
    assert fingerprint(changed_coordinate) != baseline_fp

    changed_units = copy.deepcopy(baseline)
    changed_units["units"] = {"length": "mm", "force": "N", "time": "s"}
    assert fingerprint(changed_units) != baseline_fp

    changed_constraint = copy.deepcopy(baseline)
    changed_constraint["constraints"][0]["dofs"] = ["UX", "UY"]
    assert fingerprint(changed_constraint) != baseline_fp
