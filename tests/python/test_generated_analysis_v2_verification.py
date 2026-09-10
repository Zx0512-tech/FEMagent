from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from fem_core.analysis_spec import render_opensees_analysis
from fem_core.errors import FemCoreError
from fem_core.model_spec.validator import validate_engineering_model_spec
from fem_core.solvers.opensees_generated_analysis import verify_generated_analysis_bundle

MODEL_FIXTURE = Path("tests/fixtures/model_spec/simple-portal-frame.json")


def _model() -> dict[str, Any]:
    model = json.loads(MODEL_FIXTURE.read_text(encoding="utf-8"))
    model["nodalMasses"] = [{"nodeId": 3, "mUX": 100.0, "mUY": 100.0}]
    return model


def _analysis(model: dict[str, Any]) -> dict[str, Any]:
    validation = validate_engineering_model_spec(model)
    assert validation["status"] == "VALID"
    return {
        "schemaVersion": "2.0",
        "kind": "engineering_analysis_spec",
        "modelSpecFingerprint": validation["modelSpecFingerprint"],
        "analysisType": "MODAL",
        "units": {},
        "definition": {"modeCount": 2},
        "resultRequests": [
            {"requestId": "EIG_1", "quantity": "EIGENVALUE", "mode": 1},
            {"requestId": "FREQ_1", "quantity": "NATURAL_FREQUENCY", "mode": 1},
            {
                "requestId": "MODE_1_Y",
                "quantity": "MODE_SHAPE",
                "mode": 1,
                "target": {"type": "NODE", "id": 3},
                "component": "Y",
            },
        ],
    }


def _render(tmp_path: Path) -> dict[str, Any]:
    return render_opensees_analysis(tmp_path, _model(), _analysis(_model()))


def _verify(tmp_path: Path, rendered: dict[str, Any]) -> dict[str, Any]:
    return verify_generated_analysis_bundle(
        tmp_path,
        model_path=rendered["artifacts"]["analysisPath"],
        response_plan_path=rendered["artifacts"]["responsePlanPath"],
        manifest_path=rendered["artifacts"]["manifestPath"],
    )


def test_v2_modal_bundle_verifies_to_trusted_modal_context(tmp_path: Path) -> None:
    rendered = _render(tmp_path)

    verified = _verify(tmp_path, rendered)

    assert verified["schema"] == "FEMAGENT_GENERATED_ANALYSIS_VERIFICATION_V2"
    assert verified["status"] == "VERIFIED"
    assert verified["executionMode"] == "MODAL"
    assert verified["analysisRenderFingerprint"] == rendered["analysisRenderFingerprint"]
    assert verified["responseContext"] == {
        "schemaVersion": "1.0",
        "kind": "verified_modal_response_context",
        "modeCount": 2,
        "modelTimeUnit": "s",
        "requests": [
            {"requestId": "EIG_1", "quantity": "EIGENVALUE", "mode": 1},
            {"requestId": "FREQ_1", "quantity": "NATURAL_FREQUENCY", "mode": 1},
            {
                "requestId": "MODE_1_Y",
                "quantity": "MODE_SHAPE",
                "mode": 1,
                "target": {"type": "NODE", "id": 3},
                "component": "Y",
            },
        ],
    }


@pytest.mark.parametrize("artifact_key", ["analysisPath", "responsePlanPath", "readinessPath"])
def test_v2_verifier_rejects_tampered_generated_artifact(
    tmp_path: Path,
    artifact_key: str,
) -> None:
    rendered = _render(tmp_path)
    path = tmp_path / rendered["artifacts"][artifact_key]
    path.write_text(path.read_text(encoding="utf-8") + "\n", encoding="utf-8")

    with pytest.raises(FemCoreError) as exc_info:
        _verify(tmp_path, rendered)

    assert exc_info.value.code == "GENERATED_ANALYSIS_ARTIFACT_MISMATCH"


def test_v2_verifier_rejects_tampered_manifest_identity(tmp_path: Path) -> None:
    rendered = _render(tmp_path)
    manifest_path = tmp_path / rendered["artifacts"]["manifestPath"]
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["analysisRenderFingerprint"] = "0" * 64
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    with pytest.raises(FemCoreError) as exc_info:
        _verify(tmp_path, rendered)

    assert exc_info.value.code == "GENERATED_ANALYSIS_FINGERPRINT_MISMATCH"
