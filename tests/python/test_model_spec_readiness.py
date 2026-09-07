from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path

from fem_core.model_spec import (
    evaluate_engineering_model_readiness,
    validate_engineering_model_spec,
)

FIXTURE = Path("tests/fixtures/model_spec/simple-portal-frame.json")


def _load_spec() -> dict:
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


def _element(template: dict, element_id: int, node_i: int, node_j: int) -> dict:
    item = deepcopy(template)
    item.update({"id": element_id, "nodeI": node_i, "nodeJ": node_j})
    return item


def test_portal_frame_is_ready_and_preserves_pr21_fingerprint() -> None:
    spec = _load_spec()
    validation = validate_engineering_model_spec(spec)
    result = evaluate_engineering_model_readiness(spec)

    assert result["schema"] == "FEMAGENT_MODEL_SPEC_READINESS_V1"
    assert result["status"] == "READY"
    assert result["profile"] == "FRAME_2D_ELASTIC_READINESS_V1"
    assert result["checks"]["connectivity"]["componentCount"] == 1
    restraint = result["checks"]["rigidBodyRestraint"]["components"][0]
    assert restraint["constraintRank"] == 3
    assert restraint["deficiency"] == 0
    assert result["modelSpecFingerprint"] == validation["modelSpecFingerprint"]


def test_free_frame_is_not_ready_with_rank_zero() -> None:
    spec = _load_spec()
    spec["constraints"] = []
    result = evaluate_engineering_model_readiness(spec)

    assert result["status"] == "NOT_READY"
    restraint = result["checks"]["rigidBodyRestraint"]["components"][0]
    assert restraint["constraintRank"] == 0
    assert restraint["deficiency"] == 3
    assert any(
        issue["code"] == "MODEL_READINESS_RIGID_BODY_RESTRAINT_INSUFFICIENT"
        for issue in result["issues"]
    )


def test_single_fixed_translation_pair_is_rank_two() -> None:
    spec = _load_spec()
    spec["constraints"] = [{"nodeId": 1, "dofs": ["UX", "UY"]}]
    result = evaluate_engineering_model_readiness(spec)

    restraint = result["checks"]["rigidBodyRestraint"]["components"][0]
    assert restraint["constraintRank"] == 2
    assert restraint["deficiency"] == 1
    assert result["status"] == "NOT_READY"


def test_simple_support_geometry_has_rank_three() -> None:
    spec = _load_spec()
    spec["constraints"] = [
        {"nodeId": 1, "dofs": ["UX", "UY"]},
        {"nodeId": 2, "dofs": ["UY"]},
    ]
    result = evaluate_engineering_model_readiness(spec)

    restraint = result["checks"]["rigidBodyRestraint"]["components"][0]
    assert restraint["constraintRank"] == 3
    assert result["status"] == "READY"


def test_disconnected_fully_restrained_components_are_ready_with_warning() -> None:
    spec = _load_spec()
    template = spec["elements"][0]
    spec["nodes"] = [
        {"id": 1, "x": 0.0, "y": 0.0},
        {"id": 2, "x": 1.0, "y": 0.0},
        {"id": 3, "x": 10.0, "y": 0.0},
        {"id": 4, "x": 11.0, "y": 0.0},
    ]
    spec["elements"] = [_element(template, 1, 1, 2), _element(template, 2, 3, 4)]
    spec["constraints"] = [
        {"nodeId": 1, "dofs": ["UX", "UY"]},
        {"nodeId": 2, "dofs": ["UY"]},
        {"nodeId": 3, "dofs": ["UX", "UY"]},
        {"nodeId": 4, "dofs": ["UY"]},
    ]
    result = evaluate_engineering_model_readiness(spec)

    assert result["status"] == "READY"
    assert result["checks"]["connectivity"]["componentCount"] == 2
    assert result["checks"]["connectivity"]["status"] == "WARN"
    assert any(
        issue["code"] == "MODEL_READINESS_DISCONNECTED_COMPONENTS"
        for issue in result["issues"]
    )


def test_disconnected_component_without_restraint_blocks_readiness() -> None:
    spec = _load_spec()
    template = spec["elements"][0]
    spec["nodes"] = [
        {"id": 1, "x": 0.0, "y": 0.0},
        {"id": 2, "x": 1.0, "y": 0.0},
        {"id": 3, "x": 10.0, "y": 0.0},
        {"id": 4, "x": 11.0, "y": 0.0},
    ]
    spec["elements"] = [_element(template, 1, 1, 2), _element(template, 2, 3, 4)]
    spec["constraints"] = [
        {"nodeId": 1, "dofs": ["UX", "UY"]},
        {"nodeId": 2, "dofs": ["UY"]},
    ]
    result = evaluate_engineering_model_readiness(spec)

    assert result["status"] == "NOT_READY"
    ranks = [c["constraintRank"] for c in result["checks"]["rigidBodyRestraint"]["components"]]
    assert ranks == [3, 0]


def test_isolated_unconstrained_node_blocks_readiness() -> None:
    spec = _load_spec()
    spec["nodes"].append({"id": 99, "x": 99.0, "y": 99.0})
    result = evaluate_engineering_model_readiness(spec)

    assert result["status"] == "NOT_READY"
    isolated = next(
        component
        for component in result["checks"]["rigidBodyRestraint"]["components"]
        if component["nodeIds"] == [99]
    )
    assert isolated["constraintRank"] == 0
    assert any(
        issue["code"] == "MODEL_SPEC_UNUSED_NODE"
        for issue in result["validation"]["issues"]
    )


def test_parallel_connectivity_warns_without_blocking_ready_model() -> None:
    spec = _load_spec()
    duplicate = deepcopy(spec["elements"][0])
    duplicate["id"] = 99
    spec["elements"].append(duplicate)
    result = evaluate_engineering_model_readiness(spec)

    assert result["status"] == "READY"
    assert result["checks"]["parallelConnectivity"]["status"] == "WARN"
    assert result["checks"]["parallelConnectivity"]["groups"] == [
        {"nodeIds": [1, 4], "elementIds": [1, 99]}
    ]
    assert any(
        issue["code"] == "MODEL_READINESS_PARALLEL_CONNECTIVITY"
        for issue in result["issues"]
    )


def test_invalid_pr21_spec_skips_readiness() -> None:
    spec = _load_spec()
    del spec["units"]
    result = evaluate_engineering_model_readiness(spec)

    assert result["status"] == "INVALID_SPEC"
    assert result["modelSpecFingerprint"] is None
    assert result["validation"]["status"] == "INVALID"
    assert result["checks"]["connectivity"]["status"] == "SKIPPED"
    assert result["checks"]["rigidBodyRestraint"]["status"] == "SKIPPED"
    assert result["checks"]["parallelConnectivity"]["status"] == "SKIPPED"
    assert result["issues"] == [
        {
            "severity": "ERROR",
            "code": "MODEL_READINESS_INVALID_SPEC",
            "path": "",
            "message": "Engineering readiness requires a PR21-valid ModelSpec",
        }
    ]


def test_readiness_is_deterministic_under_collection_reordering() -> None:
    spec = _load_spec()
    reordered = deepcopy(spec)
    reordered["nodes"] = list(reversed(reordered["nodes"]))
    reordered["elements"] = list(reversed(reordered["elements"]))
    reordered["constraints"] = list(reversed(reordered["constraints"]))

    assert evaluate_engineering_model_readiness(reordered) == evaluate_engineering_model_readiness(spec)
