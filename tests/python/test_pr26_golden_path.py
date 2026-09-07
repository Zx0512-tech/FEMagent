from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path
from typing import Any, Callable

import pytest

from fem_core.analysis_spec.opensees_renderer import render_opensees_linear_static_analysis
from fem_core.analysis_spec.readiness import evaluate_engineering_analysis_readiness
from fem_core.analysis_spec.validator import validate_engineering_analysis_spec
from fem_core.errors import FemCoreError
from fem_core.model_spec.validator import validate_engineering_model_spec
from fem_core.result_intelligence import inspect_result, query_result
from fem_core.solvers import get_solver_adapter


def _model_spec() -> dict[str, Any]:
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
        "sections": [{"id": 1, "type": "FRAME_2D", "area": 0.01, "iz": 0.0001}],
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


def _analysis_spec(model: dict[str, Any]) -> dict[str, Any]:
    model_validation = validate_engineering_model_spec(model)
    assert model_validation["status"] == "VALID"
    return {
        "schemaVersion": "1.0",
        "kind": "engineering_analysis_spec",
        "modelSpecFingerprint": model_validation["modelSpecFingerprint"],
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


def _adapter() -> Any:
    adapter = get_solver_adapter("opensees")
    if not adapter.status()["available"]:
        pytest.skip("OpenSeesPy optional dependency is unavailable")
    return adapter


def _options(rendered: dict[str, Any]) -> dict[str, str]:
    return {
        "responsePlanPath": rendered["artifacts"]["responsePlanPath"],
        "analysisManifestPath": rendered["artifacts"]["manifestPath"],
    }


def _summary_query(
    workspace: Path,
    run_id: str,
    *,
    quantity: str,
    target_type: str,
    target_id: int,
    component: str,
    location: str | None = None,
) -> dict[str, Any]:
    query: dict[str, Any] = {
        "quantity": quantity,
        "target": {"type": target_type, "id": target_id},
        "component": component,
        "operation": "SUMMARY",
    }
    if location is not None:
        query["location"] = location
    return query_result(workspace, run_id, query)


def test_pr26_full_generated_opensees_analysis_golden_path(tmp_path: Path) -> None:
    model = _model_spec()
    analysis = _analysis_spec(model)

    model_validation = validate_engineering_model_spec(model)
    analysis_validation = validate_engineering_analysis_spec(analysis)
    assert model_validation["status"] == "VALID"
    assert analysis_validation["status"] == "VALID"

    readiness = evaluate_engineering_analysis_readiness(model, analysis)
    assert readiness["status"] == "READY"

    rendered = render_opensees_linear_static_analysis(tmp_path, model, analysis)
    assert rendered["status"] == "RENDERED"

    adapter = _adapter()
    preflight = adapter.preflight(
        tmp_path,
        model_path=rendered["artifacts"]["analysisPath"],
        load_path=None,
        solver_options=_options(rendered),
    )
    assert preflight["status"] == "READY"
    assert preflight["generatedAnalysis"]["status"] == "VERIFIED"

    run = adapter.run(
        tmp_path,
        model_path=rendered["artifacts"]["analysisPath"],
        load_path=None,
        solver_options=_options(rendered),
    )
    assert run["status"] == "COMPLETED"
    assert run["generatedAnalysis"]["analysisRenderFingerprint"] == (
        rendered["analysisRenderFingerprint"]
    )

    inspection = inspect_result(tmp_path, run["runId"])
    assert inspection["integrity"]["status"] == "VALID"
    assert len(inspection["queryCapabilities"]) == 6

    tip_uy = _summary_query(
        tmp_path,
        run["runId"],
        quantity="DISPLACEMENT",
        target_type="NODE",
        target_id=2,
        component="Y",
    )
    base_ry = _summary_query(
        tmp_path,
        run["runId"],
        quantity="REACTION_FORCE",
        target_type="NODE",
        target_id=1,
        component="Y",
    )
    base_mz = _summary_query(
        tmp_path,
        run["runId"],
        quantity="REACTION_MOMENT",
        target_type="NODE",
        target_id=1,
        component="Z",
    )
    element_n = _summary_query(
        tmp_path,
        run["runId"],
        quantity="GENERALIZED_FORCE",
        target_type="ELEMENT",
        target_id=1,
        component="N",
        location="END_I",
    )
    element_vy = _summary_query(
        tmp_path,
        run["runId"],
        quantity="GENERALIZED_FORCE",
        target_type="ELEMENT",
        target_id=1,
        component="VY",
        location="END_I",
    )
    element_mz = _summary_query(
        tmp_path,
        run["runId"],
        quantity="GENERALIZED_FORCE",
        target_type="ELEMENT",
        target_id=1,
        component="MZ",
        location="END_I",
    )

    assert tip_uy["unit"] == "m"
    assert tip_uy["summary"]["min"] < 0.0
    assert base_ry["unit"] == "N"
    assert base_ry["summary"]["absolutePeak"] == pytest.approx(1000.0, rel=1e-9)
    assert base_mz["unit"] == "N*m"
    assert base_mz["summary"]["absolutePeak"] == pytest.approx(2000.0, rel=1e-9)
    assert element_n["unit"] == "N"
    assert element_n["summary"]["absolutePeak"] == pytest.approx(0.0, abs=1e-7)
    assert element_vy["unit"] == "N"
    assert element_vy["summary"]["absolutePeak"] == pytest.approx(1000.0, rel=1e-9)
    assert element_mz["unit"] == "N*m"
    assert element_mz["summary"]["absolutePeak"] == pytest.approx(2000.0, rel=1e-9)


def test_pr26_render_identity_is_invariant_to_semantic_collection_order(tmp_path: Path) -> None:
    model_a = _model_spec()
    analysis_a = _analysis_spec(model_a)

    model_b = deepcopy(model_a)
    model_b["nodes"] = list(reversed(model_b["nodes"]))
    model_b["constraints"] = list(reversed(model_b["constraints"]))
    model_b_validation = validate_engineering_model_spec(model_b)
    assert model_b_validation["status"] == "VALID"

    analysis_b = deepcopy(analysis_a)
    analysis_b["modelSpecFingerprint"] = model_b_validation["modelSpecFingerprint"]
    analysis_b["resultRequests"] = list(reversed(analysis_b["resultRequests"]))

    rendered_a = render_opensees_linear_static_analysis(tmp_path, model_a, analysis_a)
    rendered_b = render_opensees_linear_static_analysis(tmp_path, model_b, analysis_b)
    assert rendered_a["status"] == "RENDERED"
    assert rendered_b["status"] == "RENDERED"

    assert rendered_a["input"]["modelSpecFingerprint"] == rendered_b["input"]["modelSpecFingerprint"]
    assert rendered_a["input"]["analysisSpecFingerprint"] == (
        rendered_b["input"]["analysisSpecFingerprint"]
    )
    assert rendered_a["artifacts"]["analysisSha256"] == rendered_b["artifacts"]["analysisSha256"]
    assert rendered_a["artifacts"]["responsePlanSha256"] == (
        rendered_b["artifacts"]["responsePlanSha256"]
    )
    assert rendered_a["artifacts"]["readinessSha256"] == (
        rendered_b["artifacts"]["readinessSha256"]
    )
    assert rendered_a["analysisRenderFingerprint"] == rendered_b["analysisRenderFingerprint"]
    assert rendered_a["analysisRenderId"] != rendered_b["analysisRenderId"]


def _tamper_analysis_source(tmp_path: Path, rendered: dict[str, Any]) -> None:
    path = tmp_path / rendered["artifacts"]["analysisPath"]
    path.write_text(path.read_text(encoding="utf-8") + "\n# tamper\n", encoding="utf-8")


def _tamper_response_plan(tmp_path: Path, rendered: dict[str, Any]) -> None:
    path = tmp_path / rendered["artifacts"]["responsePlanPath"]
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["channels"][0]["component"] = "X"
    path.write_text(json.dumps(payload), encoding="utf-8")


def _tamper_readiness(tmp_path: Path, rendered: dict[str, Any]) -> None:
    path = tmp_path / rendered["artifacts"]["readinessPath"]
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["status"] = "NOT_READY"
    path.write_text(json.dumps(payload), encoding="utf-8")


def _tamper_manifest_path(tmp_path: Path, rendered: dict[str, Any]) -> None:
    path = tmp_path / rendered["artifacts"]["manifestPath"]
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["artifacts"]["analysisPath"] = payload["artifacts"]["responsePlanPath"]
    path.write_text(json.dumps(payload), encoding="utf-8")


def _tamper_manifest_hash(tmp_path: Path, rendered: dict[str, Any]) -> None:
    path = tmp_path / rendered["artifacts"]["manifestPath"]
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["artifacts"]["analysisSha256"] = "0" * 64
    payload["analysisRenderFingerprint"] = "1" * 64
    path.write_text(json.dumps(payload), encoding="utf-8")


def _tamper_embedded_spec(tmp_path: Path, rendered: dict[str, Any]) -> None:
    path = tmp_path / rendered["artifacts"]["manifestPath"]
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["input"]["normalizedAnalysisSpec"]["loadCases"][0]["nodalLoads"][0]["FY"] = -999.0
    path.write_text(json.dumps(payload), encoding="utf-8")


@pytest.mark.parametrize(
    "tamper",
    [
        _tamper_analysis_source,
        _tamper_response_plan,
        _tamper_readiness,
        _tamper_manifest_path,
        _tamper_manifest_hash,
        _tamper_embedded_spec,
    ],
)
def test_pr26_preflight_rejects_tampering_before_any_solver_run_directory(
    tmp_path: Path,
    tamper: Callable[[Path, dict[str, Any]], None],
) -> None:
    model = _model_spec()
    analysis = _analysis_spec(model)
    rendered = render_opensees_linear_static_analysis(tmp_path, model, analysis)
    assert rendered["status"] == "RENDERED"
    tamper(tmp_path, rendered)

    runs_root = tmp_path / ".femagent" / "runs"
    before = sorted(runs_root.iterdir()) if runs_root.exists() else []
    adapter = _adapter()
    with pytest.raises(FemCoreError):
        adapter.preflight(
            tmp_path,
            model_path=rendered["artifacts"]["analysisPath"],
            load_path=None,
            solver_options=_options(rendered),
        )
    after = sorted(runs_root.iterdir()) if runs_root.exists() else []
    assert after == before
