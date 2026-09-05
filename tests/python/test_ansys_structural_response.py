from __future__ import annotations

import json
import math
import shutil
from hashlib import sha256
from pathlib import Path

import pytest
from ansys.mapdl import reader as pymapdl_reader
from ansys.mapdl.reader import examples

from fem_core.ansys_result_reader import (
    describe_ansys_binary_result,
    query_ansys_structural_result,
)
from fem_core.errors import FemCoreError
from fem_core.result_intelligence import inspect_result, query_result


def _sha(path: Path) -> str:
    return sha256(path.read_bytes()).hexdigest()


def _write_ansys_run(tmp_path: Path) -> Path:
    run_id = "run_ansysstruct001"
    run_dir = tmp_path / ".femagent" / "runs" / run_id
    run_dir.mkdir(parents=True)
    binary = run_dir / "fem_result.rst"
    shutil.copyfile(examples.rstfile, binary)
    manifest = {
        "schemaVersion": "1.0",
        "kind": "solver_run",
        "runId": run_id,
        "caseFingerprint": "f" * 64,
        "status": "COMPLETED",
        "solver": {
            "name": "ANSYS",
            "runtime": "ANSYS_MAPDL",
            "executionMode": "ISOLATED_PROCESS",
        },
        "model": {"path": "main.inp", "sha256": "e" * 64},
        "load": {"mode": "MODEL_SCRIPT_MANAGED"},
        "analysis": {"type": "MODEL_SCRIPT"},
        "summary": {"processReturnCode": 0},
        "outputs": {
            "runManifest": f".femagent/runs/{run_id}/run_manifest.json",
            "binaryResult": f".femagent/runs/{run_id}/fem_result.rst",
            "binaryResultSha256": _sha(binary),
        },
    }
    (run_dir / "run_manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return run_dir


def _first_finite_node(raw, method_name: str, component_index: int) -> int:
    method = getattr(raw, method_name)
    nnum, values = method(0)
    for node, row in zip(nnum, values):
        if component_index < len(row) and math.isfinite(float(row[component_index])):
            return int(node)
    raise AssertionError(f"Packaged RST has no finite {method_name} component {component_index}")


def _first_element_id(raw) -> int:
    _stress, elements, _nodes = raw.element_stress(0)
    return int(elements[0])


def test_queries_real_nodal_component_stress_without_inventing_units() -> None:
    path = Path(examples.rstfile)
    raw = pymapdl_reader.read_binary(path, parse_vtk=False)
    node_id = _first_finite_node(raw, "nodal_stress", 0)

    result = query_ansys_structural_result(
        path,
        quantity="STRESS",
        target={"type": "NODE", "id": node_id},
        component="SX",
    )

    assert result["quantity"] == "STRESS"
    assert result["target"] == {"type": "NODE", "id": node_id}
    assert result["component"] == "SX"
    assert result["stressLocation"] == "NODAL_AVERAGED"
    assert result["unit"] is None
    assert result["referenceFrame"] == "GLOBAL"
    assert result["abscissaUnit"] is None
    assert len(result["values"]) == len(result["abscissaValues"]) >= 1
    assert all(math.isfinite(value) for value in result["values"])


def test_queries_real_principal_nodal_seqv_without_collapsing_semantics() -> None:
    path = Path(examples.rstfile)
    raw = pymapdl_reader.read_binary(path, parse_vtk=False)
    node_id = _first_finite_node(raw, "principal_nodal_stress", 4)

    result = query_ansys_structural_result(
        path,
        quantity="PRINCIPAL_STRESS",
        target={"type": "NODE", "id": node_id},
        component="SEQV",
    )

    assert result["component"] == "SEQV"
    assert result["stressLocation"] == "NODAL_AVERAGED"
    assert result["unit"] is None
    assert result["referenceFrame"] == "GLOBAL"
    assert len(result["values"]) == len(result["abscissaValues"]) >= 1


def test_description_advertises_stress_but_not_unproven_reaction_moment() -> None:
    report = describe_ansys_binary_result(Path(examples.rstfile))

    assert "STRESS" in report["quantities"]
    assert "PRINCIPAL_STRESS" in report["quantities"]
    if not any(label in {"ROTX", "ROTY", "ROTZ"} for label in report["dofLabels"]):
        assert "REACTION_MOMENT" not in report["quantities"]


def test_result_intelligence_exposes_and_queries_real_ansys_seqv(tmp_path: Path) -> None:
    run_dir = _write_ansys_run(tmp_path)
    binary = run_dir / "fem_result.rst"
    raw = pymapdl_reader.read_binary(binary, parse_vtk=False)
    node_id = _first_finite_node(raw, "principal_nodal_stress", 4)

    inspection = inspect_result(tmp_path, run_dir.name)
    assert any(
        capability["quantity"] == "PRINCIPAL_STRESS"
        and capability["component"] == "SEQV"
        and capability["target"]["type"] == "NODE"
        for capability in inspection["queryCapabilities"]
    )

    result = query_result(
        tmp_path,
        run_dir.name,
        {
            "quantity": "PRINCIPAL_STRESS",
            "target": {"type": "NODE", "id": node_id},
            "component": "SEQV",
            "operation": "SUMMARY",
        },
    )
    assert result["quantity"] == "PRINCIPAL_STRESS"
    assert result["component"] == "SEQV"
    assert result["unit"] is None
    assert result["stressLocation"] == "NODAL_AVERAGED"
    assert result["summary"]["sampleCount"] >= 1


def test_element_stress_requires_explicit_native_location_instead_of_silent_collapse() -> None:
    path = Path(examples.rstfile)
    raw = pymapdl_reader.read_binary(path, parse_vtk=False)
    element_id = _first_element_id(raw)

    with pytest.raises(FemCoreError) as exc_info:
        query_ansys_structural_result(
            path,
            quantity="STRESS",
            target={"type": "ELEMENT", "id": element_id},
            component="SX",
        )

    assert exc_info.value.code == "STRUCTURAL_RESPONSE_LOCATION_REQUIRED"


def test_generalized_force_fails_closed_without_proven_formulation_mapping() -> None:
    path = Path(examples.rstfile)
    raw = pymapdl_reader.read_binary(path, parse_vtk=False)
    element_id = _first_element_id(raw)

    with pytest.raises(FemCoreError) as exc_info:
        query_ansys_structural_result(
            path,
            quantity="GENERALIZED_FORCE",
            target={"type": "ELEMENT", "id": element_id},
            component="MY",
            location="END_I",
        )

    assert exc_info.value.code == "STRUCTURAL_RESPONSE_MAPPING_UNAVAILABLE"


def test_result_intelligence_preserves_generalized_force_mapping_error(tmp_path: Path) -> None:
    run_dir = _write_ansys_run(tmp_path)
    binary = run_dir / "fem_result.rst"
    raw = pymapdl_reader.read_binary(binary, parse_vtk=False)
    element_id = _first_element_id(raw)

    with pytest.raises(FemCoreError) as exc_info:
        query_result(
            tmp_path,
            run_dir.name,
            {
                "quantity": "GENERALIZED_FORCE",
                "target": {"type": "ELEMENT", "id": element_id},
                "component": "MY",
                "location": "END_I",
                "operation": "SUMMARY",
            },
        )

    assert exc_info.value.code == "STRUCTURAL_RESPONSE_MAPPING_UNAVAILABLE"
