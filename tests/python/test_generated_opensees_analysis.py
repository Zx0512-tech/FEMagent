from __future__ import annotations

import json
from hashlib import sha256
from pathlib import Path
from typing import Any

import pytest

from fem_core.analysis_spec.opensees_renderer import render_opensees_linear_static_analysis
from fem_core.errors import FemCoreError
from fem_core.model_spec.validator import validate_engineering_model_spec
from fem_core.solvers import get_solver_adapter
from fem_core.solvers.opensees_generated_analysis import verify_generated_analysis_bundle

FIXTURE = Path("tests/fixtures/model_spec/simple-portal-frame.json")


def _model_spec() -> dict[str, Any]:
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


def _analysis_spec(model: dict[str, Any]) -> dict[str, Any]:
    validation = validate_engineering_model_spec(model)
    assert validation["status"] == "VALID"
    return {
        "schemaVersion": "1.0",
        "kind": "engineering_analysis_spec",
        "modelSpecFingerprint": validation["modelSpecFingerprint"],
        "analysisType": "LINEAR_STATIC",
        "units": {"force": model["units"]["force"]},
        "loadCases": [
            {
                "loadCaseId": "LC1",
                "nodalLoads": [{"nodeId": 3, "FX": 0.0, "FY": -10000.0, "MZ": 0.0}],
            }
        ],
        "resultRequests": [
            {
                "requestId": "R_DISP",
                "loadCaseId": "LC1",
                "quantity": "DISPLACEMENT",
                "target": {"type": "NODE", "id": 3},
                "component": "Y",
            },
            {
                "requestId": "R_RY",
                "loadCaseId": "LC1",
                "quantity": "REACTION_FORCE",
                "target": {"type": "NODE", "id": 1},
                "component": "Y",
            },
            {
                "requestId": "R_MZ",
                "loadCaseId": "LC1",
                "quantity": "REACTION_MOMENT",
                "target": {"type": "NODE", "id": 1},
                "component": "Z",
            },
            {
                "requestId": "R_ELE",
                "loadCaseId": "LC1",
                "quantity": "GENERALIZED_FORCE",
                "target": {"type": "ELEMENT", "id": 2},
                "component": "MZ",
                "location": "END_J",
            },
        ],
    }


def _render(tmp_path: Path) -> dict[str, Any]:
    model = _model_spec()
    report = render_opensees_linear_static_analysis(tmp_path, model, _analysis_spec(model))
    assert report["status"] == "RENDERED"
    return report


def _path(tmp_path: Path, report: dict[str, Any], key: str) -> Path:
    return tmp_path / Path(report["artifacts"][key])


def _verify(tmp_path: Path, report: dict[str, Any]) -> dict[str, Any]:
    return verify_generated_analysis_bundle(
        tmp_path,
        model_path=report["artifacts"]["analysisPath"],
        response_plan_path=report["artifacts"]["responsePlanPath"],
        manifest_path=report["artifacts"]["manifestPath"],
    )


def _generated_options(report: dict[str, Any]) -> dict[str, str]:
    return {
        "responsePlanPath": report["artifacts"]["responsePlanPath"],
        "analysisManifestPath": report["artifacts"]["manifestPath"],
    }


def _opensees_adapter() -> Any:
    adapter = get_solver_adapter("opensees")
    if not adapter.status()["available"]:
        pytest.skip("OpenSeesPy optional dependency is unavailable")
    return adapter


def _cantilever_model_spec() -> dict[str, Any]:
    return {
        "schemaVersion": "1.0",
        "kind": "engineering_model_spec",
        "dimension": "2D",
        "family": "FRAME",
        "coordinateSystem": "CARTESIAN_XY",
        "units": {"length": "m", "force": "N", "time": "s"},
        "nodes": [
            {"id": 1, "x": 0.0, "y": 0.0},
            {"id": 2, "x": 2.0, "y": 0.0},
        ],
        "materials": [
            {"id": 1, "type": "LINEAR_ELASTIC", "youngsModulus": 210000000000.0}
        ],
        "sections": [
            {"id": 1, "type": "FRAME_2D", "area": 0.01, "iz": 0.0001}
        ],
        "elements": [
            {
                "id": 1,
                "type": "ELASTIC_FRAME_2D",
                "formulation": "EULER_BERNOULLI",
                "nodeI": 1,
                "nodeJ": 2,
                "materialId": 1,
                "sectionId": 1,
            }
        ],
        "constraints": [{"nodeId": 1, "dofs": ["UX", "UY", "RZ"]}],
        "nodalMasses": [],
    }


def _cantilever_analysis_spec(model: dict[str, Any]) -> dict[str, Any]:
    validation = validate_engineering_model_spec(model)
    assert validation["status"] == "VALID"
    return {
        "schemaVersion": "1.0",
        "kind": "engineering_analysis_spec",
        "modelSpecFingerprint": validation["modelSpecFingerprint"],
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
                "requestId": "TIP_UY",
                "loadCaseId": "LC1",
                "quantity": "DISPLACEMENT",
                "target": {"type": "NODE", "id": 2},
                "component": "Y",
            },
            {
                "requestId": "BASE_RY",
                "loadCaseId": "LC1",
                "quantity": "REACTION_FORCE",
                "target": {"type": "NODE", "id": 1},
                "component": "Y",
            },
            {
                "requestId": "BASE_MZ",
                "loadCaseId": "LC1",
                "quantity": "REACTION_MOMENT",
                "target": {"type": "NODE", "id": 1},
                "component": "Z",
            },
            {
                "requestId": "ELE_N_I",
                "loadCaseId": "LC1",
                "quantity": "GENERALIZED_FORCE",
                "target": {"type": "ELEMENT", "id": 1},
                "component": "N",
                "location": "END_I",
            },
            {
                "requestId": "ELE_VY_I",
                "loadCaseId": "LC1",
                "quantity": "GENERALIZED_FORCE",
                "target": {"type": "ELEMENT", "id": 1},
                "component": "VY",
                "location": "END_I",
            },
            {
                "requestId": "ELE_MZ_I",
                "loadCaseId": "LC1",
                "quantity": "GENERALIZED_FORCE",
                "target": {"type": "ELEMENT", "id": 1},
                "component": "MZ",
                "location": "END_I",
            },
        ],
    }


def test_fresh_generated_analysis_bundle_verifies_semantically(tmp_path: Path) -> None:
    report = _render(tmp_path)

    verified = _verify(tmp_path, report)

    assert verified["status"] == "VERIFIED"
    assert verified["analysisRenderFingerprint"] == report["analysisRenderFingerprint"]
    assert verified["modelSpecFingerprint"] == report["input"]["modelSpecFingerprint"]
    assert verified["analysisSpecFingerprint"] == report["input"]["analysisSpecFingerprint"]
    assert verified["readiness"]["status"] == "READY"
    assert [item["channelId"] for item in verified["responseContext"]["channels"]] == [
        "R_DISP",
        "R_ELE",
        "R_MZ",
        "R_RY",
    ]


def test_generated_analysis_rejects_manifest_schema_or_missing_specs(tmp_path: Path) -> None:
    report = _render(tmp_path)
    manifest_path = _path(tmp_path, report, "manifestPath")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["schema"] = "BROKEN"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    with pytest.raises(FemCoreError) as raised:
        _verify(tmp_path, report)
    assert raised.value.code == "GENERATED_ANALYSIS_MANIFEST_INVALID"


def test_generated_analysis_rejects_mixed_paths(tmp_path: Path) -> None:
    first = _render(tmp_path)
    second = _render(tmp_path)

    with pytest.raises(FemCoreError) as raised:
        verify_generated_analysis_bundle(
            tmp_path,
            model_path=second["artifacts"]["analysisPath"],
            response_plan_path=first["artifacts"]["responsePlanPath"],
            manifest_path=first["artifacts"]["manifestPath"],
        )
    assert raised.value.code == "GENERATED_ANALYSIS_PATH_MISMATCH"


@pytest.mark.parametrize("key", ["analysisPath", "responsePlanPath", "readinessPath"])
def test_generated_analysis_rejects_artifact_byte_tamper(tmp_path: Path, key: str) -> None:
    report = _render(tmp_path)
    artifact = _path(tmp_path, report, key)
    artifact.write_text(artifact.read_text(encoding="utf-8") + "\n# tampered\n", encoding="utf-8")

    with pytest.raises(FemCoreError) as raised:
        _verify(tmp_path, report)
    assert raised.value.code == "GENERATED_ANALYSIS_ARTIFACT_MISMATCH"


def test_generated_analysis_rejects_embedded_spec_or_render_fingerprint_tamper(tmp_path: Path) -> None:
    report = _render(tmp_path)
    manifest_path = _path(tmp_path, report, "manifestPath")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["input"]["normalizedAnalysisSpec"]["loadCases"][0]["nodalLoads"][0]["FY"] = -9999.0
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    with pytest.raises(FemCoreError) as raised:
        _verify(tmp_path, report)
    assert raised.value.code == "GENERATED_ANALYSIS_FINGERPRINT_MISMATCH"


def test_regeneration_detects_self_consistent_source_tamper(tmp_path: Path) -> None:
    report = _render(tmp_path)
    source_path = _path(tmp_path, report, "analysisPath")
    manifest_path = _path(tmp_path, report, "manifestPath")
    source = source_path.read_text(encoding="utf-8").replace('ops.algorithm("Linear")', 'ops.algorithm("Newton")')
    source_path.write_text(source, encoding="utf-8")

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["artifacts"]["analysisSha256"] = sha256(source.encode("utf-8")).hexdigest()
    identity = {
        "rendererName": manifest["renderer"]["name"],
        "rendererVersion": manifest["renderer"]["version"],
        "modelSpecFingerprint": manifest["input"]["modelSpecFingerprint"],
        "analysisSpecFingerprint": manifest["input"]["analysisSpecFingerprint"],
        "analysisSha256": manifest["artifacts"]["analysisSha256"],
        "responsePlanSha256": manifest["artifacts"]["responsePlanSha256"],
        "readinessSha256": manifest["artifacts"]["readinessSha256"],
    }
    manifest["analysisRenderFingerprint"] = sha256(
        json.dumps(identity, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    ).hexdigest()
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    with pytest.raises(FemCoreError) as raised:
        _verify(tmp_path, report)
    assert raised.value.code == "GENERATED_ANALYSIS_ARTIFACT_MISMATCH"


def test_generated_analysis_preflight_accepts_mixed_verified_response_channels(tmp_path: Path) -> None:
    report = _render(tmp_path)
    adapter = _opensees_adapter()

    preflight = adapter.preflight(
        tmp_path,
        model_path=report["artifacts"]["analysisPath"],
        load_path=None,
        solver_options=_generated_options(report),
    )

    assert preflight["status"] == "READY"
    assert preflight["generatedAnalysis"]["status"] == "VERIFIED"
    assert preflight["generatedAnalysis"]["analysisRenderFingerprint"] == report["analysisRenderFingerprint"]
    assert preflight["generatedAnalysis"]["modelSpecFingerprint"] == report["input"]["modelSpecFingerprint"]
    assert preflight["generatedAnalysis"]["analysisSpecFingerprint"] == report["input"]["analysisSpecFingerprint"]


def test_generated_analysis_preflight_requires_plan_with_manifest(tmp_path: Path) -> None:
    report = _render(tmp_path)
    adapter = _opensees_adapter()

    with pytest.raises(FemCoreError) as raised:
        adapter.preflight(
            tmp_path,
            model_path=report["artifacts"]["analysisPath"],
            load_path=None,
            solver_options={"analysisManifestPath": report["artifacts"]["manifestPath"]},
        )
    assert raised.value.code == "UNSUPPORTED_SOLVER_OPTIONS"


def test_generated_analysis_preflight_rejects_external_load_path(tmp_path: Path) -> None:
    report = _render(tmp_path)
    adapter = _opensees_adapter()
    external_load = tmp_path / "external.csv"
    external_load.write_text("time,value\n0,1\n", encoding="utf-8")

    with pytest.raises(FemCoreError) as raised:
        adapter.preflight(
            tmp_path,
            model_path=report["artifacts"]["analysisPath"],
            load_path="external.csv",
            solver_options=_generated_options(report),
        )
    assert raised.value.code == "UNSUPPORTED_SOLVER_OPTIONS"


def test_generated_analysis_run_records_real_mixed_responses_with_trusted_units(tmp_path: Path) -> None:
    adapter = _opensees_adapter()
    model = _cantilever_model_spec()
    analysis = _cantilever_analysis_spec(model)
    rendered = render_opensees_linear_static_analysis(tmp_path, model, analysis)
    assert rendered["status"] == "RENDERED"

    run = adapter.run(
        tmp_path,
        model_path=rendered["artifacts"]["analysisPath"],
        load_path=None,
        solver_options=_generated_options(rendered),
    )

    structural_path = tmp_path / run["outputs"]["structuralResponse"]
    structural = json.loads(structural_path.read_text(encoding="utf-8"))
    channels = {channel["channelId"]: channel for channel in structural["channels"]}

    assert channels["BASE_RY"]["values"][0] == pytest.approx(1000.0, rel=1e-9, abs=1e-7)
    assert abs(channels["BASE_MZ"]["values"][0]) == pytest.approx(2000.0, rel=1e-9, abs=1e-7)
    assert abs(channels["ELE_VY_I"]["values"][0]) == pytest.approx(1000.0, rel=1e-9, abs=1e-7)
    assert abs(channels["ELE_MZ_I"]["values"][0]) == pytest.approx(2000.0, rel=1e-9, abs=1e-7)
    assert channels["TIP_UY"]["values"][0] < 0.0
    assert channels["TIP_UY"]["unit"] == "m"
    assert channels["BASE_RY"]["unit"] == "N"
    assert channels["BASE_MZ"]["unit"] == "N*m"
    assert channels["ELE_N_I"]["unit"] == "N"
    assert channels["ELE_VY_I"]["unit"] == "N"
    assert channels["ELE_MZ_I"]["unit"] == "N*m"
