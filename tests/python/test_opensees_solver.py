from __future__ import annotations

from pathlib import Path

import pytest

from fem_core.errors import FemCoreError
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


def _python_bundle(tmp_path: Path) -> str:
    project = tmp_path / "project"
    project.mkdir(exist_ok=True)
    (project / "materials.py").write_text(
        Path("tests/fixtures/opensees_bundle/materials.py").read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    (project / "main.py").write_text(
        Path("tests/fixtures/opensees_bundle/main.py").read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    return "project/main.py"


def test_opensees_preflight_is_deterministic_without_solving(tmp_path: Path) -> None:
    adapter = get_solver_adapter("opensees")
    report = adapter.preflight(tmp_path, model_path=_model(tmp_path), load_path=_canonical_load(tmp_path))
    assert report["kind"] == "solver_preflight"
    assert report["model"]["modelType"] == "ELASTIC_SDOF"
    assert report["load"]["unit"] == "m/s2"
    assert report["executionEstimate"]["analysisSteps"] == 3


def test_opensees_rejects_ansys_solver_options(tmp_path: Path) -> None:
    adapter = get_solver_adapter("opensees")

    with pytest.raises(FemCoreError) as exc_info:
        adapter.preflight(
            tmp_path,
            model_path=_model(tmp_path),
            load_path=_canonical_load(tmp_path),
            solver_options={"modelUnits": {"length": "mm", "time": "s"}},
        )

    assert exc_info.value.code == "UNSUPPORTED_SOLVER_OPTIONS"


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


def test_opensees_python_build_inspection_realizes_domain_without_analyzing(tmp_path: Path) -> None:
    adapter = get_solver_adapter("opensees")
    if not adapter.status()["available"]:
        pytest.skip("opensees optional dependency is not installed")

    report = adapter.build_inspect(tmp_path, model_path=_python_bundle(tmp_path))

    assert report["kind"] == "solver_build_inspection"
    assert report["solver"] == "OPENSEESPY"
    assert report["analysisAdvanced"] is False
    assert report["interceptedAnalyzeCalls"] == 1
    assert report["nodeTags"] == [1, 2]
    assert report["elementTags"] == [1]
    assert report["nodeCoordinates"]["1"] == [0.0]
    assert report["nodeCoordinates"]["2"] == [0.0]


def test_opensees_python_bundle_preflight_uses_build_inspection_without_external_load(tmp_path: Path) -> None:
    adapter = get_solver_adapter("opensees")
    if not adapter.status()["available"]:
        pytest.skip("opensees optional dependency is not installed")
    model_path = _python_bundle(tmp_path)

    report = adapter.preflight(tmp_path, model_path=model_path, load_path=None)

    assert report["status"] == "READY"
    assert report["model"]["format"] == "OPENSEES_PYTHON"
    assert report["model"]["bundleFingerprint"]
    assert report["model"]["buildInspection"]["nodeCount"] == 2
    assert report["model"]["buildInspection"]["elementCount"] == 1
    assert report["load"] == {"mode": "MODEL_SCRIPT_MANAGED"}


def test_opensees_python_bundle_executes_original_script_and_records_bundle_identity(tmp_path: Path) -> None:
    adapter = get_solver_adapter("opensees")
    if not adapter.status()["available"]:
        pytest.skip("opensees optional dependency is not installed")
    model_path = _python_bundle(tmp_path)

    result = adapter.run(tmp_path, model_path=model_path, load_path=None)

    assert result["status"] == "COMPLETED"
    assert result["model"]["format"] == "OPENSEES_PYTHON"
    assert len(result["model"]["bundleFingerprint"]) == 64
    assert len(result["model"]["files"]) == 2
    assert result["load"] == {"mode": "MODEL_SCRIPT_MANAGED"}
    assert result["analysis"]["type"] == "MODEL_SCRIPT"
    assert result["summary"]["nodeCount"] == 2
    assert result["summary"]["elementCount"] == 1
    assert result["summary"]["analysisTime"] == 1.0
    assert (tmp_path / result["outputs"]["runManifest"]).is_file()
    assert (tmp_path / result["outputs"]["resultSummary"]).is_file()
