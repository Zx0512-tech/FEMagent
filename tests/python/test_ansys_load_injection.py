from __future__ import annotations

from pathlib import Path

import pytest

from fem_core import ansys_bundle, errors
from fem_core.solvers import ansys_load, ansys_runner

CANONICAL_HEADER = (
    "time_s,load_kind,channel_id,application_type,target_type,target_id,component,quantity,value,unit\n"
)


def _write_model(tmp_path: Path, body: str, *, name: str = "model.inp") -> Path:
    path = tmp_path / name
    path.write_text(body, encoding="utf-8")
    return path


def _write_load(tmp_path: Path, component: str = "X") -> dict:
    path = tmp_path / "earthquake.standardized.csv"
    path.write_text(
        CANONICAL_HEADER
        + f"0,EARTHQUAKE,eq,UNIFORM_EXCITATION,,,{component},ACCELERATION,0,m/s2\n"
        + f"0.5,EARTHQUAKE,eq,UNIFORM_EXCITATION,,,{component},ACCELERATION,1.5,m/s2\n"
        + f"1,EARTHQUAKE,eq,UNIFORM_EXCITATION,,,{component},ACCELERATION,-0.5,m/s2\n",
        encoding="utf-8",
    )
    return ansys_load.read_ansys_canonical_uniform_excitation(
        path,
        {"length": "mm", "time": "s"},
    )


def _supported_transient_model() -> str:
    return (
        "/PREP7\n"
        "N,1,0,0,0\n"
        "N,2,1,0,0\n"
        "E,1,2\n"
        "FINISH\n"
        "/SOLU\n"
        "ANTYPE,TRANS\n"
        "TRNOPT,FULL\n"
        "SOLVE\n"
        "FINISH\n"
    )


def test_ansys_injection_inspection_finds_unique_full_transient_hook(tmp_path: Path) -> None:
    _write_model(tmp_path, _supported_transient_model())
    bundle = ansys_bundle.discover_ansys_bundle(tmp_path, "model.inp")

    hook = ansys_load.inspect_ansys_transient_injection(tmp_path, bundle)

    assert hook["path"] == "model.inp"
    assert hook["line"] == 7
    assert hook["command"].upper() == "ANTYPE,TRANS"
    assert hook["solutionCommandCount"] == 1
    assert hook["transientMode"] == "FULL"


@pytest.mark.parametrize(
    ("body", "expected_code"),
    [
        (
            "/PREP7\nN,1,0,0,0\nE,1,1\nFINISH\n/SOLU\nSOLVE\n",
            "ANSYS_TRANSIENT_HOOK_NOT_FOUND",
        ),
        (
            _supported_transient_model() + "ANTYPE,TRANS\nSOLVE\n",
            "ANSYS_TRANSIENT_HOOK_AMBIGUOUS",
        ),
        (
            _supported_transient_model().replace("TRNOPT,FULL", "TRNOPT,MSUP"),
            "ANSYS_MSUP_CANONICAL_LOAD_NOT_SUPPORTED",
        ),
        (
            _supported_transient_model().replace("TRNOPT,FULL", "ACEL,1,0,0\nTRNOPT,FULL"),
            "ANSYS_ACCELERATION_LOAD_CONFLICT",
        ),
        (
            _supported_transient_model().replace("SOLVE\n", ""),
            "ANSYS_SOLVE_COMMAND_NOT_FOUND",
        ),
    ],
)
def test_ansys_injection_inspection_fails_closed_for_ambiguous_or_conflicting_models(
    tmp_path: Path,
    body: str,
    expected_code: str,
) -> None:
    _write_model(tmp_path, body)
    bundle = ansys_bundle.discover_ansys_bundle(tmp_path, "model.inp")

    with pytest.raises(errors.FemCoreError) as exc_info:
        ansys_load.inspect_ansys_transient_injection(tmp_path, bundle)

    assert exc_info.value.code == expected_code


def test_ansys_uniform_excitation_writes_deterministic_table_and_macro(tmp_path: Path) -> None:
    load = _write_load(tmp_path, "Y")
    working_directory = tmp_path / "stage" / "project"
    working_directory.mkdir(parents=True)

    artifacts = ansys_load.write_ansys_uniform_excitation(working_directory, load)

    table = working_directory / "femagent_load_table.txt"
    macro = working_directory / "femagent_load.mac"
    assert table.is_file()
    assert macro.is_file()
    table_lines = table.read_text(encoding="utf-8").splitlines()
    assert table_lines[:2] == [
        "! FEMagent PR10 generated canonical uniform excitation",
        "! time_model acceleration_model",
    ]
    assert table_lines[2:] == ["0\t0", "0.5\t1500", "1\t-500"]
    macro_text = macro.read_text(encoding="utf-8")
    assert "*DIM,FEMAGAC,TABLE,3,1,1,TIME" in macro_text
    assert "*TREAD,FEMAGAC,femagent_load_table,txt,,2" in macro_text
    assert "ACEL,0,%FEMAGAC%,0" in macro_text
    assert artifacts["tableSha256"]
    assert artifacts["macroSha256"]


def test_ansys_injection_modifies_only_staged_hook_file(tmp_path: Path) -> None:
    source = _write_model(tmp_path, _supported_transient_model())
    source_before = source.read_bytes()
    bundle = ansys_bundle.discover_ansys_bundle(tmp_path, "model.inp")
    hook = ansys_load.inspect_ansys_transient_injection(tmp_path, bundle)
    stage_root = tmp_path / ".stage"
    staged = ansys_runner.stage_ansys_bundle(
        tmp_path,
        bundle,
        stage_root,
        sanitize_for_build=False,
    )

    result = ansys_load.inject_ansys_uniform_excitation(staged["stageRoot"], hook)

    assert source.read_bytes() == source_before
    staged_text = staged["entrypoint"].read_text(encoding="utf-8")
    assert "ANTYPE,TRANS\n/INPUT,'femagent_load','mac'\nTRNOPT,FULL" in staged_text
    assert result["injected"] is True
    assert result["hook"]["path"] == "model.inp"
    assert result["stagedHookFileSha256"]


def test_build_sanitization_can_validate_generated_load_without_solve() -> None:
    text = _supported_transient_model()

    sanitized = ansys_runner.sanitize_apdl_for_build(
        text,
        load_include_command="/INPUT,'femagent_load','mac'",
    )

    upper = sanitized.upper()
    assert "/INPUT,'FEMAGENT_LOAD','MAC'" in upper
    assert "/SOLU" not in upper
    assert "SOLVE" not in upper
    assert "FEMAGENT BUILD-ONLY STOPPED BEFORE" in upper
