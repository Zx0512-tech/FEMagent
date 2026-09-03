from __future__ import annotations

from pathlib import Path

import pytest

from fem_core.load_standardization import standardize_load
from fem_core.solvers.registry import get_solver_adapter


def _canonical_load(tmp_path: Path) -> str:
    source = tmp_path / "earthquake.csv"
    source.write_text(
        "time_s,acceleration_g\n0.00,0.00\n0.02,0.10\n0.04,-0.15\n0.06,0.05\n",
        encoding="utf-8",
    )
    result = standardize_load(
        tmp_path,
        "earthquake.csv",
        {
            "version": 1,
            "loadKind": "EARTHQUAKE",
            "timeColumn": "time_s",
            "timeUnit": "s",
            "valueColumn": "acceleration_g",
            "quantity": "ACCELERATION",
            "sourceUnit": "g",
            "applicationType": "UNIFORM_EXCITATION",
            "component": "X",
            "scale": 1.0,
        },
    )
    return str(result["output"]["path"])


def _model(tmp_path: Path) -> str:
    model = tmp_path / "model.json"
    fixture = Path("tests/fixtures/opensees_sdof.json").read_text(encoding="utf-8")
    model.write_text(fixture, encoding="utf-8")
    return "model.json"


def test_opensees_preflight_is_deterministic_without_solving(tmp_path: Path) -> None:
    adapter = get_solver_adapter("opensees")
    report = adapter.preflight(tmp_path, model_path=_model(tmp_path), load_path=_canonical_load(tmp_path))
    assert report["kind"] == "solver_preflight"
    assert report["model"]["modelType"] == "ELASTIC_SDOF"
    assert report["load"]["unit"] == "m/s2"
    assert report["executionEstimate"]["analysisSteps"] == 3


def test_opensees_real_transient_solver_produces_run_manifest(tmp_path: Path) -> None:
    adapter = get_solver_adapter("opensees")
    if not adapter.status()["available"]:
        pytest.skip("opensees optional dependency is not installed")
    result = adapter.run(tmp_path, model_path=_model(tmp_path), load_path=_canonical_load(tmp_path))
    assert result["status"] == "COMPLETED"
    assert result["solver"]["name"] == "OPENSEESPY"
    assert result["analysis"]["analysisSteps"] == 3
    assert result["summary"]["absolutePeakDisplacementM"] > 0.0
    assert (tmp_path / result["outputs"]["responseCsv"]).is_file()
    assert (tmp_path / result["outputs"]["runManifest"]).is_file()
