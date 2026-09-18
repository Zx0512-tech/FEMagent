from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path
from typing import Any

import pytest

from fem_core.analysis_spec import render_opensees_analysis
from fem_core.model_spec.validator import validate_engineering_model_spec
from fem_core.result_intelligence import inspect_result, query_result
from fem_core.solvers import get_solver_adapter

MODEL_FIXTURE = Path("tests/fixtures/model_spec/simple-portal-frame.json")
_HEADER = (
    "time_s,load_kind,channel_id,application_type,target_type,target_id,"
    "component,quantity,value,unit\n"
)


def _model() -> dict[str, Any]:
    model = json.loads(MODEL_FIXTURE.read_text(encoding="utf-8"))
    model["nodalMasses"] = [{"nodeId": 3, "mUX": 100.0, "mUY": 100.0}]
    return model


def _fingerprint(model: dict[str, Any]) -> str:
    report = validate_engineering_model_spec(model)
    assert report["status"] == "VALID"
    return str(report["modelSpecFingerprint"])


def _write_load(workspace: Path, rel_path: str, *, base: bool) -> str:
    path = workspace / rel_path
    path.parent.mkdir(parents=True, exist_ok=True)
    if base:
        rows = (
            "0.00,TRANSIENT,EQX,UNIFORM_EXCITATION,,,X,ACCELERATION,0.0,m/s2\n"
            "0.01,TRANSIENT,EQX,UNIFORM_EXCITATION,,,X,ACCELERATION,0.2,m/s2\n"
            "0.02,TRANSIENT,EQX,UNIFORM_EXCITATION,,,X,ACCELERATION,0.0,m/s2\n"
        )
    else:
        rows = (
            "0.00,TRANSIENT,FY3,NODAL_FORCE,NODE,3,Y,FORCE,0.0,N\n"
            "0.01,TRANSIENT,FY3,NODAL_FORCE,NODE,3,Y,FORCE,100.0,N\n"
            "0.02,TRANSIENT,FY3,NODAL_FORCE,NODE,3,Y,FORCE,0.0,N\n"
        )
    content = _HEADER + rows
    path.write_text(content, encoding="utf-8")
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def _static(model: dict[str, Any]) -> dict[str, Any]:
    return {
        "schemaVersion": "2.0",
        "kind": "engineering_analysis_spec",
        "modelSpecFingerprint": _fingerprint(model),
        "analysisType": "LINEAR_STATIC",
        "units": {"force": "N"},
        "definition": {
            "loadCases": [
                {
                    "loadCaseId": "LC1",
                    "nodalLoads": [
                        {"nodeId": 3, "FX": 0.0, "FY": -1000.0, "MZ": 0.0}
                    ],
                }
            ]
        },
        "resultRequests": [
            {
                "requestId": "U3Y",
                "loadCaseId": "LC1",
                "quantity": "DISPLACEMENT",
                "target": {"type": "NODE", "id": 3},
                "component": "Y",
            }
        ],
    }


def _modal(model: dict[str, Any]) -> dict[str, Any]:
    return {
        "schemaVersion": "2.0",
        "kind": "engineering_analysis_spec",
        "modelSpecFingerprint": _fingerprint(model),
        "analysisType": "MODAL",
        "units": {},
        "definition": {"modeCount": 1},
        "resultRequests": [
            {"requestId": "E1", "quantity": "EIGENVALUE", "mode": 1},
            {"requestId": "F1", "quantity": "NATURAL_FREQUENCY", "mode": 1},
            {"requestId": "P1", "quantity": "PERIOD", "mode": 1},
            {
                "requestId": "S1",
                "quantity": "MODE_SHAPE",
                "mode": 1,
                "target": {"type": "NODE", "id": 3},
                "component": "Y",
            },
        ],
    }


def _transient(
    model: dict[str, Any],
    *,
    rel_path: str,
    sha256: str,
    base: bool,
) -> dict[str, Any]:
    if base:
        units: dict[str, str] = {}
        excitation: dict[str, Any] = {
            "type": "UNIFORM_BASE_EXCITATION",
            "component": "X",
            "quantity": "ACCELERATION",
            "loadArtifact": {"path": rel_path, "sha256": sha256},
        }
        requests: list[dict[str, Any]] = [
            {
                "requestId": "U3X",
                "quantity": "DISPLACEMENT",
                "target": {"type": "NODE", "id": 3},
                "component": "X",
            },
            {
                "requestId": "V3X",
                "quantity": "VELOCITY",
                "target": {"type": "NODE", "id": 3},
                "component": "X",
            },
            {
                "requestId": "AR3X",
                "quantity": "RELATIVE_ACCELERATION",
                "target": {"type": "NODE", "id": 3},
                "component": "X",
            },
        ]
    else:
        units = {"force": "N"}
        excitation = {
            "type": "NODAL_TIME_HISTORY",
            "nodeId": 3,
            "component": "Y",
            "quantity": "FORCE",
            "loadArtifact": {"path": rel_path, "sha256": sha256},
        }
        requests = [
            {
                "requestId": "U3Y",
                "quantity": "DISPLACEMENT",
                "target": {"type": "NODE", "id": 3},
                "component": "Y",
            }
        ]
    return {
        "schemaVersion": "2.0",
        "kind": "engineering_analysis_spec",
        "modelSpecFingerprint": _fingerprint(model),
        "analysisType": "TRANSIENT",
        "units": units,
        "definition": {
            "time": {"timeStep": 0.01, "duration": 0.02},
            "damping": {"type": "NONE"},
            "excitation": excitation,
        },
        "resultRequests": requests,
    }


def _adapter() -> Any:
    adapter = get_solver_adapter("opensees")
    if not adapter.status()["available"]:
        pytest.skip("OpenSeesPy optional dependency is unavailable")
    return adapter


def _render_run(
    workspace: Path,
    model: dict[str, Any],
    analysis: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, Any]]:
    rendered = render_opensees_analysis(workspace, model, analysis)
    assert rendered["status"] == "RENDERED"
    options = {
        "responsePlanPath": rendered["artifacts"]["responsePlanPath"],
        "analysisManifestPath": rendered["artifacts"]["manifestPath"],
    }
    adapter = _adapter()
    preflight = adapter.preflight(
        workspace,
        model_path=rendered["artifacts"]["analysisPath"],
        load_path=None,
        solver_options=options,
    )
    assert preflight["status"] == "READY"
    assert preflight["generatedAnalysis"]["status"] == "VERIFIED"
    run = adapter.run(
        workspace,
        model_path=rendered["artifacts"]["analysisPath"],
        load_path=None,
        solver_options=options,
    )
    assert run["status"] == "COMPLETED"
    return rendered, run


def _series_values(series: dict[str, Any]) -> tuple[list[float], list[float]]:
    abscissa = [float(item["abscissa"]) for item in series["series"]]
    values = [float(item["value"]) for item in series["series"]]
    return abscissa, values


def test_v2_linear_static_real_golden_path(tmp_path: Path) -> None:
    model = _model()
    rendered, run = _render_run(tmp_path, model, _static(model))

    assert rendered["renderer"]["name"] == "OPENSEES_FRAME_2D_LINEAR_STATIC_V2"
    inspected = inspect_result(tmp_path, run["runId"])
    assert inspected["integrity"]["status"] == "VALID"
    assert {item["quantity"] for item in inspected["queryCapabilities"]} == {"DISPLACEMENT"}
    result = query_result(
        tmp_path,
        run["runId"],
        {
            "quantity": "DISPLACEMENT",
            "target": {"type": "NODE", "id": 3},
            "component": "Y",
            "operation": "SUMMARY",
        },
    )
    assert result["summary"]["sampleCount"] >= 1
    assert math.isfinite(float(result["summary"]["absolutePeak"]))


def test_v2_modal_real_golden_path(tmp_path: Path) -> None:
    model = _model()
    rendered, run = _render_run(tmp_path, model, _modal(model))

    assert rendered["renderer"]["name"] == "OPENSEES_FRAME_2D_MODAL_V2"
    inspected = inspect_result(tmp_path, run["runId"])
    assert inspected["integrity"]["status"] == "VALID"
    assert {item["quantity"] for item in inspected["queryCapabilities"]} == {
        "EIGENVALUE",
        "NATURAL_FREQUENCY",
        "PERIOD",
        "MODE_SHAPE",
    }
    eigenvalue = query_result(
        tmp_path,
        run["runId"],
        {"quantity": "EIGENVALUE", "mode": 1, "operation": "VALUE"},
    )
    frequency = query_result(
        tmp_path,
        run["runId"],
        {"quantity": "NATURAL_FREQUENCY", "mode": 1, "operation": "VALUE"},
    )
    period = query_result(
        tmp_path,
        run["runId"],
        {"quantity": "PERIOD", "mode": 1, "operation": "VALUE"},
    )
    shape = query_result(
        tmp_path,
        run["runId"],
        {
            "quantity": "MODE_SHAPE",
            "mode": 1,
            "target": {"type": "NODE", "id": 3},
            "component": "Y",
            "operation": "VALUE",
        },
    )
    assert float(eigenvalue["value"]) > 0.0
    assert float(frequency["value"]) > 0.0
    assert float(period["value"]) > 0.0
    period_seconds = float(period["value"])
    if period["unit"] == "ms":
        period_seconds *= 0.001
    assert period_seconds * float(frequency["value"]) == pytest.approx(1.0)
    assert math.isfinite(float(shape["value"]))
    assert shape["unit"] == "1"
    assert shape["normalization"] == "OPENSEES_NATIVE"


def test_v2_nodal_transient_real_golden_path(tmp_path: Path) -> None:
    model = _model()
    load_sha = _write_load(tmp_path, "loads/force.csv", base=False)
    analysis = _transient(
        model,
        rel_path="loads/force.csv",
        sha256=load_sha,
        base=False,
    )
    rendered, run = _render_run(tmp_path, model, analysis)

    assert rendered["renderer"]["name"] == "OPENSEES_FRAME_2D_TRANSIENT_NODAL_FORCE_V2"
    inspected = inspect_result(tmp_path, run["runId"])
    assert inspected["abscissa"] == {
        "semantic": "TIME",
        "unit": "s",
        "sampleCount": 2,
        "start": pytest.approx(0.01),
        "end": pytest.approx(0.02),
    }
    assert {item["quantity"] for item in inspected["queryCapabilities"]} == {"DISPLACEMENT"}
    assert inspected["queryCapabilities"][0]["referenceFrame"] == "GLOBAL"
    series = query_result(
        tmp_path,
        run["runId"],
        {
            "quantity": "DISPLACEMENT",
            "target": {"type": "NODE", "id": 3},
            "component": "Y",
            "operation": "SERIES",
        },
    )
    abscissa, values = _series_values(series)
    assert abscissa == pytest.approx([0.01, 0.02])
    assert 0.0 not in abscissa
    assert len(values) == 2
    assert all(math.isfinite(value) for value in values)


def test_v2_uniform_base_transient_real_golden_path(tmp_path: Path) -> None:
    model = _model()
    load_sha = _write_load(tmp_path, "loads/eq.csv", base=True)
    analysis = _transient(
        model,
        rel_path="loads/eq.csv",
        sha256=load_sha,
        base=True,
    )
    rendered, run = _render_run(tmp_path, model, analysis)

    assert rendered["renderer"]["name"] == "OPENSEES_FRAME_2D_TRANSIENT_UNIFORM_BASE_V2"
    inspected = inspect_result(tmp_path, run["runId"])
    assert inspected["abscissa"]["semantic"] == "TIME"
    assert inspected["abscissa"]["unit"] == "s"
    assert inspected["abscissa"]["sampleCount"] == 2
    assert inspected["abscissa"]["start"] == pytest.approx(0.01)
    assert inspected["abscissa"]["end"] == pytest.approx(0.02)
    capabilities = inspected["queryCapabilities"]
    assert {item["quantity"] for item in capabilities} == {
        "DISPLACEMENT",
        "VELOCITY",
        "RELATIVE_ACCELERATION",
    }
    assert "ABSOLUTE_ACCELERATION" not in {item["quantity"] for item in capabilities}
    assert all(item["referenceFrame"] == "RELATIVE" for item in capabilities)
    series = query_result(
        tmp_path,
        run["runId"],
        {
            "quantity": "RELATIVE_ACCELERATION",
            "target": {"type": "NODE", "id": 3},
            "component": "X",
            "operation": "SERIES",
        },
    )
    abscissa, values = _series_values(series)
    assert abscissa == pytest.approx([0.01, 0.02])
    assert 0.0 not in abscissa
    assert len(values) == 2
    assert all(math.isfinite(value) for value in values)
