from __future__ import annotations

from pathlib import Path

from openpyxl import Workbook

from fem_core.load_standardization import standardize_load
from fem_core.solvers.registry import get_solver_adapter

CANONICAL_HEADER = (
    "time_s,load_kind,channel_id,application_type,target_type,target_id,component,quantity,value,unit\n"
)


def _transient_model(tmp_path: Path) -> str:
    path = tmp_path / "bridge.inp"
    path.write_text(
        "/PREP7\n"
        "N,1,0,0,0\n"
        "N,2,1,0,0\n"
        "E,1,2\n"
        "FINISH\n"
        "/SOLU\n"
        "ANTYPE,TRANS\n"
        "TRNOPT,FULL\n"
        "SOLVE\n"
        "FINISH\n",
        encoding="utf-8",
    )
    return path.name


def _canonical_load(tmp_path: Path, *, peak: float = 1.5) -> str:
    path = tmp_path / "earthquake.standardized.csv"
    path.write_text(
        CANONICAL_HEADER
        + "0,EARTHQUAKE,eq_x,UNIFORM_EXCITATION,,,X,ACCELERATION,0,m/s2\n"
        + f"0.5,EARTHQUAKE,eq_x,UNIFORM_EXCITATION,,,X,ACCELERATION,{peak},m/s2\n"
        + "1,EARTHQUAKE,eq_x,UNIFORM_EXCITATION,,,X,ACCELERATION,-0.5,m/s2\n",
        encoding="utf-8",
    )
    return path.name


def _fake_ansys_runtime(tmp_path: Path) -> Path:
    executable = tmp_path / "ansys_fake"
    executable.write_text(
        "#!/usr/bin/env python3\n"
        "import sys\n"
        "from pathlib import Path\n"
        "args = sys.argv[1:]\n"
        "input_path = Path(args[args.index('-i') + 1]).resolve()\n"
        "output_path = Path(args[args.index('-o') + 1]).resolve()\n"
        "job_name = args[args.index('-j') + 1]\n"
        "text = input_path.read_text(encoding='utf-8')\n"
        "active = [line.strip().upper() for line in text.splitlines() if line.strip() and not line.lstrip().startswith('!')]\n"
        "if input_path.name == 'build_only.inp' and any(line.startswith('/SOLU') or line.startswith('SOLVE') for line in active):\n"
        "    print('build-only wrapper attempted solution', file=sys.stderr)\n"
        "    raise SystemExit(9)\n"
        "output_path.write_text('FAKE ANSYS OK\\n' + input_path.name + '\\n', encoding='utf-8')\n"
        "(Path.cwd() / f'{job_name}.rst').write_bytes(b'FEMagent fake RST')\n"
        "(Path.cwd() / 'fake_runtime_cwd.txt').write_text(str(Path.cwd()), encoding='utf-8')\n",
        encoding="utf-8",
    )
    executable.chmod(executable.stat().st_mode | 0o111)
    return executable


def _solver_options() -> dict:
    return {"modelUnits": {"length": "mm", "time": "s"}}


def test_ansys_canonical_preflight_blocks_without_model_units(tmp_path: Path, monkeypatch) -> None:
    executable = _fake_ansys_runtime(tmp_path)
    monkeypatch.setenv("FEM_ANSYS_EXECUTABLE", str(executable))
    adapter = get_solver_adapter("ansys")

    report = adapter.preflight(
        tmp_path,
        model_path=_transient_model(tmp_path),
        load_path=_canonical_load(tmp_path),
    )

    assert report["status"] == "BLOCKED"
    checks = {check["code"]: check["status"] for check in report["checks"]}
    assert checks["CANONICAL_LOAD_INJECTION"] == "FAILED"
    assert report["load"]["injected"] is False
    assert report["load"]["error"]["code"] == "ANSYS_MODEL_UNITS_REQUIRED"


def test_ansys_canonical_preflight_build_checks_generated_load(tmp_path: Path, monkeypatch) -> None:
    executable = _fake_ansys_runtime(tmp_path)
    monkeypatch.setenv("FEM_ANSYS_EXECUTABLE", str(executable))

    report = get_solver_adapter("ansys").preflight(
        tmp_path,
        model_path=_transient_model(tmp_path),
        load_path=_canonical_load(tmp_path),
        solver_options=_solver_options(),
    )

    assert report["status"] == "READY"
    checks = {check["code"]: check["status"] for check in report["checks"]}
    assert checks["CANONICAL_LOAD_INJECTION"] == "PASSED"
    assert checks["BUILD_ONLY_INSPECTION"] == "PASSED"
    assert report["load"]["mode"] == "FEMAGENT_CANONICAL_UNIFORM_EXCITATION"
    assert report["load"]["injected"] is False
    assert report["load"]["injectionStatus"] == "VALIDATED_FOR_STAGING"
    assert report["load"]["unit"] == "m/s2"
    assert report["load"]["modelUnits"]["length"] == "mm"
    build = report["model"]["buildInspection"]
    assert build["loadInjectionValidated"] is True
    table = tmp_path / build["generatedLoad"]["tablePath"]
    macro = tmp_path / build["generatedLoad"]["macroPath"]
    assert table.is_file()
    assert macro.is_file()
    assert len(build["generatedLoad"]["tableSha256"]) == 64
    assert len(build["generatedLoad"]["macroSha256"]) == 64


def test_ansys_canonical_real_run_injects_only_staged_bundle_and_records_identity(
    tmp_path: Path,
    monkeypatch,
) -> None:
    executable = _fake_ansys_runtime(tmp_path)
    monkeypatch.setenv("FEM_ANSYS_EXECUTABLE", str(executable))
    model_path = _transient_model(tmp_path)
    load_path = _canonical_load(tmp_path)
    source_model_before = (tmp_path / model_path).read_bytes()
    source_load_before = (tmp_path / load_path).read_bytes()

    result = get_solver_adapter("ansys").run(
        tmp_path,
        model_path=model_path,
        load_path=load_path,
        solver_options=_solver_options(),
    )

    assert result["status"] == "COMPLETED"
    assert result["load"]["mode"] == "FEMAGENT_CANONICAL_UNIFORM_EXCITATION"
    assert result["load"]["injected"] is True
    assert result["load"]["component"] == "X"
    assert result["load"]["unit"] == "m/s2"
    assert result["load"]["canonicalUnit"] == "m/s2"
    assert result["load"]["modelUnits"]["acceleration"] == "mm/s2"
    assert len(result["load"]["executionInputFingerprint"]) == 64
    assert result["executionInputFingerprint"] == result["load"]["executionInputFingerprint"]
    assert len(result["caseFingerprint"]) == 64
    staged_root = tmp_path / result["outputs"]["stagedBundleRoot"]
    staged_entrypoint = staged_root / "bridge.inp"
    staged_text = staged_entrypoint.read_text(encoding="utf-8")
    assert "ANTYPE,TRANS\n/INPUT,'femagent_load','mac'\nTRNOPT,FULL" in staged_text
    table = tmp_path / result["outputs"]["generatedLoadTable"]
    macro = tmp_path / result["outputs"]["generatedLoadMacro"]
    assert table.is_file()
    assert macro.is_file()
    assert result["outputs"]["generatedLoadTableSha256"]
    assert result["outputs"]["generatedLoadMacroSha256"]
    assert result["load"]["hook"]["path"] == "bridge.inp"
    assert (tmp_path / model_path).read_bytes() == source_model_before
    assert (tmp_path / load_path).read_bytes() == source_load_before


def test_xlsx_to_canonical_csv_to_ansys_macro_and_staged_apdl_is_traceable(
    tmp_path: Path,
    monkeypatch,
) -> None:
    executable = _fake_ansys_runtime(tmp_path)
    monkeypatch.setenv("FEM_ANSYS_EXECUTABLE", str(executable))
    model_path = _transient_model(tmp_path)

    workbook = Workbook()
    sheet = workbook.active
    sheet.append(["time_s", "acceleration_g"])
    sheet.append([0.0, 0.0])
    sheet.append([0.5, 0.1])
    sheet.append([1.0, -0.05])
    workbook.save(tmp_path / "earthquake.xlsx")

    standardized = standardize_load(
        tmp_path,
        "earthquake.xlsx",
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
    canonical_path = standardized["output"]["path"]

    result = get_solver_adapter("ansys").run(
        tmp_path,
        model_path=model_path,
        load_path=canonical_path,
        solver_options=_solver_options(),
    )

    assert standardized["format"] == "FEMAGENT_LOAD_CSV_V1"
    assert result["load"]["sourceSha256"] == standardized["output"]["sha256"]
    macro = tmp_path / result["outputs"]["generatedLoadMacro"]
    assert "*TREAD,FEMAGAC,femagent_load_table,txt,,2" in macro.read_text(encoding="utf-8")
    staged_entrypoint = tmp_path / result["outputs"]["stagedBundleRoot"] / "bridge.inp"
    assert "/INPUT,'femagent_load','mac'" in staged_entrypoint.read_text(encoding="utf-8")
    assert result["injection"]["injected"] is True
    assert len(result["injection"]["macroSha256"]) == 64
    assert len(result["injection"]["tableSha256"]) == 64


def test_ansys_canonical_load_change_changes_execution_and_case_fingerprints(
    tmp_path: Path,
    monkeypatch,
) -> None:
    executable = _fake_ansys_runtime(tmp_path)
    monkeypatch.setenv("FEM_ANSYS_EXECUTABLE", str(executable))
    model_path = _transient_model(tmp_path)
    load_path = _canonical_load(tmp_path, peak=1.0)
    adapter = get_solver_adapter("ansys")

    first = adapter.run(
        tmp_path,
        model_path=model_path,
        load_path=load_path,
        solver_options=_solver_options(),
    )
    _canonical_load(tmp_path, peak=2.0)
    second = adapter.run(
        tmp_path,
        model_path=model_path,
        load_path=load_path,
        solver_options=_solver_options(),
    )

    assert first["executionInputFingerprint"] != second["executionInputFingerprint"]
    assert first["caseFingerprint"] != second["caseFingerprint"]


def test_ansys_canonical_model_bundle_change_changes_execution_fingerprint(
    tmp_path: Path,
    monkeypatch,
) -> None:
    executable = _fake_ansys_runtime(tmp_path)
    monkeypatch.setenv("FEM_ANSYS_EXECUTABLE", str(executable))
    model_path = _transient_model(tmp_path)
    load_path = _canonical_load(tmp_path)
    adapter = get_solver_adapter("ansys")

    first = adapter.run(
        tmp_path,
        model_path=model_path,
        load_path=load_path,
        solver_options=_solver_options(),
    )
    source_model = tmp_path / model_path
    source_model.write_text(source_model.read_text(encoding="utf-8") + "! bundle identity changed\n", encoding="utf-8")
    second = adapter.run(
        tmp_path,
        model_path=model_path,
        load_path=load_path,
        solver_options=_solver_options(),
    )

    assert first["model"]["bundleFingerprint"] != second["model"]["bundleFingerprint"]
    assert first["executionInputFingerprint"] != second["executionInputFingerprint"]
    assert first["caseFingerprint"] != second["caseFingerprint"]


def test_ansys_canonical_generated_artifact_change_changes_execution_fingerprint(
    tmp_path: Path,
    monkeypatch,
) -> None:
    executable = _fake_ansys_runtime(tmp_path)
    monkeypatch.setenv("FEM_ANSYS_EXECUTABLE", str(executable))
    model_path = _transient_model(tmp_path)
    load_path = _canonical_load(tmp_path)
    adapter = get_solver_adapter("ansys")

    first = adapter.run(
        tmp_path,
        model_path=model_path,
        load_path=load_path,
        solver_options={"modelUnits": {"length": "mm", "time": "s"}},
    )
    second = adapter.run(
        tmp_path,
        model_path=model_path,
        load_path=load_path,
        solver_options={"modelUnits": {"length": "cm", "time": "s"}},
    )

    assert first["injection"]["tableSha256"] != second["injection"]["tableSha256"]
    assert first["executionInputFingerprint"] != second["executionInputFingerprint"]
    assert first["caseFingerprint"] != second["caseFingerprint"]
