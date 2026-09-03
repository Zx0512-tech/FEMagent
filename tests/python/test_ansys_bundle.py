from pathlib import Path

import pytest

from fem_core.ansys_bundle import discover_ansys_bundle, has_ansys_model_signals
from fem_core.errors import FemCoreError
from fem_core.model_inspection import inspect_model


def test_txt_requires_apdl_content_signals_before_model_promotion(tmp_path: Path) -> None:
    model = tmp_path / "main.txt"
    model.write_text("/PREP7\nN,1,0,0,0\nN,2,1,0,0\nE,1,2\n", encoding="utf-8")
    notes = tmp_path / "notes.txt"
    notes.write_text("ordinary engineering notes\n", encoding="utf-8")

    assert has_ansys_model_signals(model.read_text(encoding="utf-8")) is True
    assert has_ansys_model_signals(notes.read_text(encoding="utf-8")) is False
    assert inspect_model(tmp_path, "main.txt")["format"] == "ANSYS_APDL_TEXT"
    with pytest.raises(FemCoreError) as exc_info:
        inspect_model(tmp_path, "notes.txt")
    assert exc_info.value.code == "NOT_ANSYS_MODEL"


def test_ansys_bundle_recursively_resolves_input_and_use_dependencies(tmp_path: Path) -> None:
    project = tmp_path / "bridge"
    project.mkdir()
    (project / "main.txt").write_text(
        "/PREP7\n/INPUT,geometry,mac\n*USE,materials.dat\n",
        encoding="utf-8",
    )
    (project / "geometry.mac").write_text(
        "N,1,0,0,0\nN,2,10,0,0\n/INPUT,sections,mac\nE,1,2\n",
        encoding="utf-8",
    )
    (project / "sections.mac").write_text("SECTYPE,1,BEAM,RECT\n", encoding="utf-8")
    (project / "materials.dat").write_text("MP,EX,1,2.1E11\n", encoding="utf-8")

    bundle = discover_ansys_bundle(tmp_path, "bridge/main.txt")

    assert bundle["integrity"] == "VALID"
    paths = {item["path"] for item in bundle["files"]}
    assert paths == {
        "bridge/main.txt",
        "bridge/geometry.mac",
        "bridge/sections.mac",
        "bridge/materials.dat",
    }
    dependency_types = {item["type"] for item in bundle["dependencies"]}
    assert dependency_types == {"APDL_INPUT", "APDL_USE"}
    assert len(bundle["bundleFingerprint"]) == 64


def test_ansys_bundle_fingerprint_changes_when_dependency_changes(tmp_path: Path) -> None:
    (tmp_path / "main.apdl").write_text("/PREP7\n/INPUT,geometry,mac\n", encoding="utf-8")
    dependency = tmp_path / "geometry.mac"
    dependency.write_text("N,1,0,0,0\nE,1\n", encoding="utf-8")
    first = discover_ansys_bundle(tmp_path, "main.apdl")["bundleFingerprint"]
    dependency.write_text("N,1,0,0,0\nN,2,1,0,0\nE,1,2\n", encoding="utf-8")
    second = discover_ansys_bundle(tmp_path, "main.apdl")["bundleFingerprint"]
    assert first != second


def test_missing_ansys_include_blocks_bundle_integrity(tmp_path: Path) -> None:
    (tmp_path / "main.apdl").write_text("/PREP7\n/INPUT,missing,mac\nN,1,0,0,0\nE,1\n", encoding="utf-8")
    bundle = discover_ansys_bundle(tmp_path, "main.apdl")
    assert bundle["integrity"] == "BLOCKED"
    assert bundle["dependencies"][0]["status"] == "UNRESOLVED"


def test_ansys_include_cannot_escape_workspace(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (tmp_path / "outside.mac").write_text("N,1,0,0,0\n", encoding="utf-8")
    (workspace / "main.apdl").write_text(
        "/PREP7\n/INPUT,../outside,mac\nN,1,0,0,0\nE,1\n",
        encoding="utf-8",
    )
    bundle = discover_ansys_bundle(workspace, "main.apdl")
    assert bundle["integrity"] == "BLOCKED"
    assert bundle["dependencies"][0]["status"] == "BLOCKED_OUTSIDE_WORKSPACE"


def test_ansys_absolute_include_is_blocked_to_preserve_staged_execution(tmp_path: Path) -> None:
    dependency = tmp_path / "geometry.mac"
    dependency.write_text("N,1,0,0,0\nE,1\n", encoding="utf-8")
    (tmp_path / "main.apdl").write_text(
        f"/PREP7\n/INPUT,{dependency.as_posix()}\n",
        encoding="utf-8",
    )

    bundle = discover_ansys_bundle(tmp_path, "main.apdl")

    assert bundle["integrity"] == "BLOCKED"
    assert bundle["dependencies"][0]["status"] == "BLOCKED_ABSOLUTE_REFERENCE"
