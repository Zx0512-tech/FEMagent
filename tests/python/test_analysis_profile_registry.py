from __future__ import annotations

import importlib
import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

from fem_core.analysis_spec.readiness import evaluate_engineering_analysis_readiness
from fem_core.analysis_spec.validator import validate_engineering_analysis_spec
from fem_core.model_spec.validator import validate_engineering_model_spec

ANALYSIS_FIXTURE_DIR = Path("tests/fixtures/analysis_spec")
MODEL_FIXTURE = Path("tests/fixtures/model_spec/simple-portal-frame.json")
REGISTRY_PATH = Path("fem_core/analysis_spec/opensees_profiles/registry.py")


def _selector() -> Callable[[dict[str, Any]], str]:
    assert REGISTRY_PATH.is_file(), "PR28 OpenSees profile registry is not implemented"
    module = importlib.import_module("fem_core.analysis_spec.opensees_profiles.registry")
    selector = getattr(module, "select_opensees_analysis_profile", None)
    assert callable(selector), "select_opensees_analysis_profile is not implemented"
    return selector


def _validated_fixture(name: str) -> dict[str, Any]:
    spec = json.loads((ANALYSIS_FIXTURE_DIR / name).read_text(encoding="utf-8"))
    report = validate_engineering_analysis_spec(spec)
    assert report["status"] == "VALID"
    normalized = report["normalizedSpec"]
    assert isinstance(normalized, dict)
    return normalized


@pytest.mark.parametrize(
    ("fixture_name", "profile"),
    [
        ("simple-linear-static-v2.json", "OPENSEES_FRAME_2D_LINEAR_STATIC_V2"),
        ("simple-modal-v2.json", "OPENSEES_FRAME_2D_MODAL_V2"),
        ("simple-transient-nodal-v2.json", "OPENSEES_FRAME_2D_TRANSIENT_NODAL_FORCE_V2"),
        ("simple-transient-base-v2.json", "OPENSEES_FRAME_2D_TRANSIENT_UNIFORM_BASE_V2"),
    ],
)
def test_selects_exact_v2_profile(fixture_name: str, profile: str) -> None:
    selector = _selector()
    assert selector(_validated_fixture(fixture_name)) == profile


def test_selects_legacy_v1_static_profile() -> None:
    spec = {
        "schemaVersion": "1.0",
        "kind": "engineering_analysis_spec",
        "modelSpecFingerprint": "0" * 64,
        "analysisType": "LINEAR_STATIC",
        "units": {"force": "N"},
        "loadCases": [
            {
                "loadCaseId": "LC1",
                "nodalLoads": [{"nodeId": 2, "FX": 0.0, "FY": -1000.0, "MZ": 0.0}],
            }
        ],
        "resultRequests": [
            {
                "requestId": "R1",
                "loadCaseId": "LC1",
                "quantity": "DISPLACEMENT",
                "target": {"type": "NODE", "id": 2},
                "component": "Y",
            }
        ],
    }
    validation = validate_engineering_analysis_spec(spec)
    assert validation["status"] == "VALID"
    selector = _selector()
    assert selector(validation["normalizedSpec"]) == "OPENSEES_FRAME_2D_LINEAR_STATIC_V1"


def test_unimplemented_v2_profile_remains_a_selected_not_ready_shell() -> None:
    model = json.loads(MODEL_FIXTURE.read_text(encoding="utf-8"))
    model_validation = validate_engineering_model_spec(model)
    assert model_validation["status"] == "VALID"

    analysis = json.loads(
        (ANALYSIS_FIXTURE_DIR / "simple-modal-v2.json").read_text(encoding="utf-8")
    )
    analysis["modelSpecFingerprint"] = model_validation["modelSpecFingerprint"]
    validation = validate_engineering_analysis_spec(analysis)
    assert validation["status"] == "VALID"

    report = evaluate_engineering_analysis_readiness(model, analysis)

    assert report["schema"] == "FEMAGENT_ANALYSIS_READINESS_V2"
    assert report["status"] == "NOT_READY"
    assert report["profile"] == "OPENSEES_FRAME_2D_MODAL_V2"
    assert all(check["status"] == "SKIPPED" for check in report["checks"].values())
