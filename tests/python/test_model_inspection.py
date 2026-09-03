from pathlib import Path

import pytest

from fem_core.errors import FemCoreError
from fem_core.model_inspection import inspect_model


def test_static_apdl_inspection_reports_only_explicit_commands(tmp_path: Path) -> None:
    model = tmp_path / "bridge.apdl"
    model.write_text("/PREP7\nET,1,BEAM188\nN,1,0,0,0\nN,2,1,0,0\nE,1,2\n", encoding="utf-8")
    report = inspect_model(tmp_path, "bridge.apdl")
    assert report["format"] == "ANSYS_APDL_TEXT"
    assert report["summary"]["explicitNodeCommandCount"] == 2
    assert report["summary"]["explicitElementCommandCount"] == 1
    assert report["elementTypes"] == ["BEAM188"]


def test_model_path_cannot_escape_workspace(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    outside = tmp_path / "outside.apdl"
    outside.write_text("/PREP7\n", encoding="utf-8")
    with pytest.raises(FemCoreError) as exc:
        inspect_model(workspace, "../outside.apdl")
    assert exc.value.code == "PATH_OUTSIDE_WORKSPACE"
