from pathlib import Path

import pytest

from fem_core.errors import FemCoreError
from fem_core.model_inspection import inspect_model


def test_static_apdl_builds_manifest_from_explicit_engineering_signals(tmp_path: Path) -> None:
    model = tmp_path / "bridge.apdl"
    model.write_text(
        "/PREP7\n"
        "ET,1,BEAM188\n"
        "MP,EX,1,2.1E11\n"
        "MP,PRXY,1,0.3\n"
        "SECTYPE,1,BEAM,RECT,MAIN_GIRDER\n"
        "N,1,0,0,0\n"
        "N,2,10,0,0\n"
        "EN,1,1,2\n"
        "CM,GIRDER,ELEM\n"
        "D,1,UX,0\n"
        "F,2,FX,1000\n",
        encoding="utf-8",
    )

    report = inspect_model(tmp_path, "bridge.apdl")

    assert report["schemaVersion"] == "1.1"
    assert report["validation"]["status"] == "PASSED"
    assert report["validation"]["executionEligibility"] == "STATICALLY_ELIGIBLE"
    assert report["summary"]["explicitNodeCommandCount"] == 2
    assert report["summary"]["materialDefinitionCount"] == 1
    assert report["summary"]["sectionDefinitionCount"] == 1
    assert report["summary"]["componentDefinitionCount"] == 1

    manifest = report["manifest"]
    assert manifest["topology"]["nodeCount"] == {
        "value": 2,
        "basis": "UNIQUE_EXPLICIT_NODE_IDS",
    }
    assert manifest["topology"]["elementCount"]["value"] == 1
    assert manifest["topology"]["coordinateBounds"]["x"] == {"min": 0.0, "max": 10.0}
    assert manifest["topology"]["elementTypes"] == [{"id": "1", "name": "BEAM188"}]
    assert manifest["materials"] == [{"id": "1", "properties": ["EX", "PRXY"]}]
    assert manifest["components"] == [{"name": "GIRDER", "entity": "ELEM"}]
    assert manifest["boundaries"] == {
        "explicitConstraintCommandCount": 1,
        "labels": ["UX"],
    }
    assert manifest["existingLoadSignals"] == [{"command": "F", "count": 1}]


def test_parametric_or_block_model_defers_final_topology_to_solver_inspection(tmp_path: Path) -> None:
    model = tmp_path / "parametric.cdb"
    model.write_text(
        "/PREP7\n*DO,I,1,10\nN,I,I,0,0\n*ENDDO\nNBLOCK,6,SOLID\nEBLOCK,19,SOLID\n",
        encoding="utf-8",
    )

    report = inspect_model(tmp_path, "parametric.cdb")

    assert report["validation"]["status"] == "LIMITED"
    assert report["validation"]["executionEligibility"] == "REQUIRES_SOLVER_INSPECTION"
    assert report["summary"]["parametricModel"] is True
    assert report["summary"]["blockBasedModel"] is True
    assert report["manifest"]["topology"]["nodeCount"]["value"] is None
    assert report["manifest"]["topology"]["elementCount"]["value"] is None
    assert report["manifest"]["solverCompatibility"]["ansys"] == "REQUIRES_SOLVER_INSPECTION"


def test_forbidden_apdl_is_inspectable_but_rejected_for_execution(tmp_path: Path) -> None:
    model = tmp_path / "unsafe.apdl"
    model.write_text("/PREP7\nN,1,0,0,0\nE,1\n/SYS,whoami\n", encoding="utf-8")

    report = inspect_model(tmp_path, "unsafe.apdl")

    assert report["validation"]["status"] == "REJECTED"
    assert report["validation"]["executionEligibility"] == "REJECTED"
    assert report["validation"]["checks"]["forbiddenCommandScan"] == "FAILED"
    assert report["validation"]["forbiddenCommands"][0]["marker"] == "/sys"
    assert report["manifest"]["solverCompatibility"]["ansys"] == "REJECTED_UNSAFE"


def test_incomplete_model_reports_missing_structural_signals(tmp_path: Path) -> None:
    model = tmp_path / "incomplete.apdl"
    model.write_text("ET,1,BEAM188\nN,1,0,0,0\n", encoding="utf-8")

    report = inspect_model(tmp_path, "incomplete.apdl")

    assert report["validation"]["executionEligibility"] == "INCOMPLETE"
    codes = {issue["code"] for issue in report["validation"]["issues"]}
    assert codes == {"MISSING_PREP7", "NO_ELEMENT_DEFINITIONS"}
    assert report["manifest"]["solverCompatibility"]["ansys"] == "INCOMPLETE_MODEL"


def test_model_path_cannot_escape_workspace(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    outside = tmp_path / "outside.apdl"
    outside.write_text("/PREP7\n", encoding="utf-8")
    with pytest.raises(FemCoreError) as exc:
        inspect_model(workspace, "../outside.apdl")
    assert exc.value.code == "PATH_OUTSIDE_WORKSPACE"
