from __future__ import annotations

import json
import math
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from fem_core.analysis_spec.opensees_renderer_v2 import build_opensees_modal_v2_source
from fem_core.errors import FemCoreError
from fem_core.modal_results import canonicalize_modal_results
from fem_core.model_spec.validator import validate_engineering_model_spec
from fem_core.solvers.opensees_worker import (
    _sample_response_channel,
    run_build_inspection,
    run_modal_model,
    run_python_model,
)

MODEL_FIXTURE = Path("tests/fixtures/model_spec/simple-portal-frame.json")


def test_sample_response_channel_supports_node_velocity_and_acceleration() -> None:
    ops = SimpleNamespace(
        nodeVel=lambda node, dof: 12.5 if (node, dof) == (3, 2) else 0.0,
        nodeAccel=lambda node, dof: -4.25 if (node, dof) == (3, 1) else 0.0,
    )
    vel = {"channelId": "V3Y", "target": {"type": "NODE", "id": 3}}
    acc = {"channelId": "A3X", "target": {"type": "NODE", "id": 3}}

    assert _sample_response_channel(ops, channel=vel, mapping={"access": "NODE_VEL", "dof": 2}) == 12.5
    assert _sample_response_channel(ops, channel=acc, mapping={"access": "NODE_ACCEL", "dof": 1}) == -4.25


def test_build_inspection_intercepts_eigen_without_solving(tmp_path: Path) -> None:
    source = tmp_path / "modal.py"
    source.write_text(
        "\n".join(
            [
                "import openseespy.opensees as ops",
                'ops.model("basic", "-ndm", 1, "-ndf", 1)',
                "ops.node(1, 0.0)",
                "_femagent_eigenvalues = ops.eigen(1)",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    report = run_build_inspection(source)

    assert report["status"] == "COMPLETED"
    assert report["analysisAdvanced"] is False
    assert report["interceptedAnalyzeCalls"] == 0
    assert report["interceptedEigenCalls"] == 1
    assert report["analysisTime"] == pytest.approx(0.0)


def test_modal_canonicalization_uses_exact_time_unit_formulas_and_rejects_bad_lambda() -> None:
    result = canonicalize_modal_results(
        eigenvalues=[4.0],
        requests=[
            {"requestId": "E1", "quantity": "EIGENVALUE", "mode": 1},
            {"requestId": "F1", "quantity": "NATURAL_FREQUENCY", "mode": 1},
            {"requestId": "P1", "quantity": "PERIOD", "mode": 1},
        ],
        model_time_unit="ms",
        mode_shapes={},
    )
    omega_native = 2.0
    expected_period_ms = 2.0 * math.pi / omega_native
    expected_frequency_hz = omega_native / (2.0 * math.pi * 0.001)
    by_id = {item["requestId"]: item for item in result["results"]}
    assert by_id["E1"]["value"] == pytest.approx(4.0)
    assert by_id["E1"]["unit"] == "1/ms2"
    assert by_id["P1"]["value"] == pytest.approx(expected_period_ms)
    assert by_id["P1"]["unit"] == "ms"
    assert by_id["F1"]["value"] == pytest.approx(expected_frequency_hz)
    assert by_id["F1"]["unit"] == "Hz"

    for invalid in (0.0, -1.0, float("nan"), float("inf")):
        with pytest.raises(FemCoreError) as exc_info:
            canonicalize_modal_results(
                eigenvalues=[invalid],
                requests=[{"requestId": "E1", "quantity": "EIGENVALUE", "mode": 1}],
                model_time_unit="s",
                mode_shapes={},
            )
        assert exc_info.value.code == "INVALID_MODAL_RESULT"


def _modal_model() -> dict[str, Any]:
    model = json.loads(MODEL_FIXTURE.read_text(encoding="utf-8"))
    model["nodalMasses"] = [{"nodeId": 3, "mUX": 100.0, "mUY": 100.0}]
    report = validate_engineering_model_spec(model)
    assert report["status"] == "VALID"
    return report["normalizedSpec"]


def test_modal_run_captures_single_eigen_solve_and_writes_canonical_results(tmp_path: Path) -> None:
    model = _modal_model()
    source = tmp_path / "modal.py"
    source.write_text(build_opensees_modal_v2_source(model, 1), encoding="utf-8")
    context = {
        "schemaVersion": "1.0",
        "kind": "verified_modal_response_context",
        "modeCount": 1,
        "modelTimeUnit": "s",
        "requests": [
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
    context_path = tmp_path / "modal_context.json"
    context_path.write_text(json.dumps(context), encoding="utf-8")

    run = run_modal_model(source, tmp_path / "run", context_path)

    assert run["status"] == "COMPLETED"
    assert run["capturedEigenCalls"] == 1
    modal_path = Path(run["modalResults"])
    payload = json.loads(modal_path.read_text(encoding="utf-8"))
    assert payload["schemaVersion"] == "1.0"
    assert payload["kind"] == "modal_result_set"
    by_id = {item["requestId"]: item for item in payload["results"]}
    assert by_id["E1"]["value"] > 0.0
    assert by_id["F1"]["value"] > 0.0
    assert by_id["P1"]["value"] > 0.0
    assert by_id["F1"]["value"] * by_id["P1"]["value"] == pytest.approx(1.0)
    assert math.isfinite(by_id["S1"]["value"])
    assert by_id["S1"]["unit"] == "1"
    assert by_id["S1"]["normalization"] == "OPENSEES_NATIVE"


def test_v2_transient_context_samples_only_after_each_step(tmp_path: Path) -> None:
    source = tmp_path / "transient.py"
    source.write_text(
        "\n".join(
            [
                "import openseespy.opensees as ops",
                'ops.model("basic", "-ndm", 1, "-ndf", 1)',
                "ops.node(1, 0.0)",
                "ops.node(2, 0.0)",
                "ops.fix(1, 1)",
                "ops.mass(2, 1.0)",
                'ops.uniaxialMaterial("Elastic", 1, 100.0)',
                'ops.element("zeroLength", 1, 1, 2, "-mat", 1, "-dir", 1)',
                'ops.timeSeries("Path", 1, "-dt", 0.01, "-values", 0.0, 1.0, 0.0, 0.0)',
                'ops.pattern("Plain", 1, 1)',
                "ops.load(2, 1.0)",
                'ops.constraints("Plain")',
                'ops.numberer("Plain")',
                'ops.system("BandGeneral")',
                'ops.algorithm("Linear")',
                'ops.integrator("Newmark", 0.5, 0.25)',
                'ops.analysis("Transient")',
                "for _step in range(3):",
                "    if int(ops.analyze(1, 0.01)) != 0:",
                '        raise RuntimeError("transient failed")',
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    context = {
        "schemaVersion": "2.0",
        "kind": "verified_structural_response_context",
        "analysisType": "TRANSIENT",
        "abscissaSemantic": "TIME",
        "abscissaUnit": "s",
        "channels": [
            {
                "channelId": "U2",
                "quantity": "DISPLACEMENT",
                "target": {"type": "NODE", "id": 2},
                "component": "X",
                "access": "NODE_DISP",
                "dof": 1,
                "referenceFrame": "GLOBAL",
                "unit": "m",
            }
        ],
    }
    context_path = tmp_path / "response_context.json"
    context_path.write_text(json.dumps(context), encoding="utf-8")

    run = run_python_model(source, tmp_path / "run", response_context_path=context_path)

    response_path = Path(run["structuralResponse"])
    response = json.loads(response_path.read_text(encoding="utf-8"))
    channel = response["channels"][0]
    assert channel["abscissaSemantic"] == "TIME"
    assert channel["abscissaUnit"] == "s"
    assert channel["abscissaValues"] == pytest.approx([0.01, 0.02, 0.03])
    assert len(channel["values"]) == 3
    assert all(math.isfinite(value) for value in channel["values"])
