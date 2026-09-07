from __future__ import annotations

import json
from pathlib import Path

import pytest

from fem_core.errors import FemCoreError
from fem_core.result_intelligence import inspect_result, query_result
from fem_core.solvers.registry import get_solver_adapter


def _beam_model(tmp_path: Path) -> str:
    path = tmp_path / "beam.py"
    path.write_text(
        "import openseespy.opensees as ops\n"
        "ops.model('basic', '-ndm', 2, '-ndf', 3)\n"
        "ops.node(1, 0.0, 0.0)\n"
        "ops.node(2, 1.0, 0.0)\n"
        "ops.fix(1, 1, 1, 1)\n"
        "ops.geomTransf('Linear', 1)\n"
        "ops.element('elasticBeamColumn', 41, 1, 2, 2.0, 30000.0, 100.0, 1)\n"
        "ops.timeSeries('Linear', 1)\n"
        "ops.pattern('Plain', 1, 1)\n"
        "ops.load(2, 0.0, -10.0, 0.0)\n"
        "ops.constraints('Plain')\n"
        "ops.numberer('Plain')\n"
        "ops.system('BandGeneral')\n"
        "ops.algorithm('Linear')\n"
        "ops.integrator('LoadControl', 1.0)\n"
        "ops.analysis('Static')\n"
        "ops.analyze(1)\n",
        encoding="utf-8",
    )
    return path.name


def _plan(tmp_path: Path, *, element_id: int = 41, component: str = "MZ") -> str:
    path = tmp_path / "response-plan.json"
    path.write_text(
        json.dumps(
            {
                "schemaVersion": "1.0",
                "kind": "structural_response_plan",
                "channels": [
                    {
                        "channelId": "beam_end_i",
                        "quantity": "GENERALIZED_FORCE",
                        "target": {"type": "ELEMENT", "id": element_id},
                        "component": component,
                        "location": "END_I",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    return path.name


def test_real_opensees_beam_records_hashed_structural_response_and_queries_it(tmp_path: Path) -> None:
    adapter = get_solver_adapter("opensees")
    if not adapter.status()["available"]:
        pytest.skip("opensees optional dependency is not installed")

    run = adapter.run(
        tmp_path,
        model_path=_beam_model(tmp_path),
        load_path=None,
        solver_options={"responsePlanPath": _plan(tmp_path)},
    )

    assert run["status"] == "COMPLETED"
    assert run["responsePlan"]["path"] == "response-plan.json"
    assert len(run["responsePlan"]["sha256"]) == 64
    assert run.get("generatedAnalysis") is None
    assert len(run["outputs"]["structuralResponseSha256"]) == 64
    structural_path = tmp_path / run["outputs"]["structuralResponse"]
    assert structural_path.is_file()

    inspection = inspect_result(tmp_path, run["runId"])
    assert any(
        capability.get("quantity") == "GENERALIZED_FORCE"
        and capability.get("target") == {"type": "ELEMENT", "id": 41}
        and capability.get("component") == "MZ"
        and capability.get("location") == "END_I"
        for capability in inspection["queryCapabilities"]
    )

    result = query_result(
        tmp_path,
        run["runId"],
        {
            "quantity": "GENERALIZED_FORCE",
            "target": {"type": "ELEMENT", "id": 41},
            "component": "MZ",
            "location": "END_I",
            "operation": "SUMMARY",
        },
    )
    assert result["target"] == {"type": "ELEMENT", "id": 41}
    assert result["component"] == "MZ"
    assert result["location"] == "END_I"
    assert result["unit"] is None
    assert result["referenceFrame"] == "ELEMENT_LOCAL"
    assert result["summary"]["sampleCount"] == 1
    assert result["summary"]["absolutePeak"] > 0.0


def test_opensees_response_plan_rejects_unproven_element_mapping_before_analysis(tmp_path: Path) -> None:
    adapter = get_solver_adapter("opensees")
    if not adapter.status()["available"]:
        pytest.skip("opensees optional dependency is not installed")

    model = tmp_path / "zero.py"
    model.write_text(
        "import openseespy.opensees as ops\n"
        "ops.model('basic', '-ndm', 1, '-ndf', 1)\n"
        "ops.node(1, 0.0)\n"
        "ops.node(2, 0.0)\n"
        "ops.fix(1, 1)\n"
        "ops.uniaxialMaterial('Elastic', 1, 10.0)\n"
        "ops.element('zeroLength', 41, 1, 2, '-mat', 1, '-dir', 1)\n"
        "ops.timeSeries('Linear', 1)\n"
        "ops.pattern('Plain', 1, 1)\n"
        "ops.load(2, 1.0)\n"
        "ops.constraints('Plain')\n"
        "ops.numberer('Plain')\n"
        "ops.system('BandGeneral')\n"
        "ops.algorithm('Linear')\n"
        "ops.integrator('LoadControl', 1.0)\n"
        "ops.analysis('Static')\n"
        "ops.analyze(1)\n",
        encoding="utf-8",
    )

    with pytest.raises(FemCoreError) as exc_info:
        adapter.run(
            tmp_path,
            model_path=model.name,
            load_path=None,
            solver_options={"responsePlanPath": _plan(tmp_path)},
        )

    assert exc_info.value.code == "STRUCTURAL_RESPONSE_MAPPING_UNAVAILABLE"
