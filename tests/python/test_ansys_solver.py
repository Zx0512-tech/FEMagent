from __future__ import annotations

import os
from pathlib import Path

from fem_core.solvers.registry import get_solver_adapter


def _model(tmp_path: Path, *, with_solve: bool = False) -> str:
    model = tmp_path / "main.txt"
    text = (
        "/PREP7\n"
        "N,1,0,0,0\n"
        "N,2,1,0,0\n"
        "E,1,2\n"
    )
    if with_solve:
        text += "FINISH\n/SOLU\nSOLVE\nFINISH\n"
    model.write_text(text, encoding="utf-8")
    return "main.txt"


def _fake_ansys_runtime(tmp_path: Path, *, write_result: bool = False) -> Path:
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
        "    print('build-only input attempted solution', file=sys.stderr)\n"
        "    raise SystemExit(9)\n"
        "output_path.write_text('FAKE ANSYS OK\\n' + input_path.name + '\\n', encoding='utf-8')\n"
        f"write_result = {write_result!r}\n"
        "if write_result:\n"
        "    (Path.cwd() / f'{job_name}.rst').write_bytes(b'FEMagent fake RST')\n"
        "(Path.cwd() / 'fake_runtime_cwd.txt').write_text(str(Path.cwd()), encoding='utf-8')\n",
        encoding="utf-8",
    )
    executable.chmod(executable.stat().st_mode | 0o111)
    return executable


def test_ansys_status_is_unavailable_without_configuration(monkeypatch) -> None:
    monkeypatch.delenv("FEM_ANSYS_EXECUTABLE", raising=False)

    status = get_solver_adapter("ansys").status()

    assert status["kind"] == "solver_status"
    assert status["solver"] == "ANSYS"
    assert status["available"] is False
    assert status["configuredPath"] is None
    assert status["configuration"] == {"environmentVariable": "FEM_ANSYS_EXECUTABLE"}
    assert status["reason"] == "NOT_CONFIGURED"


def test_ansys_status_accepts_configured_runtime_file(tmp_path: Path, monkeypatch) -> None:
    executable = _fake_ansys_runtime(tmp_path)
    monkeypatch.setenv("FEM_ANSYS_EXECUTABLE", str(executable))

    status = get_solver_adapter("ansys").status()

    assert status["available"] is True
    assert status["configuredPath"] == str(executable.resolve())
    assert status["reason"] is None
    assert "APDL_MODEL_BUNDLE" in status["capabilities"]


def test_ansys_status_rejects_missing_configured_runtime(tmp_path: Path, monkeypatch) -> None:
    missing = tmp_path / "missing_ansys"
    monkeypatch.setenv("FEM_ANSYS_EXECUTABLE", str(missing))

    status = get_solver_adapter("ansys").status()

    assert status["available"] is False
    assert status["configuredPath"] == str(missing.resolve())
    assert status["reason"] == "CONFIGURED_PATH_NOT_FILE"


def test_ansys_preflight_fails_closed_when_runtime_is_unavailable(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.delenv("FEM_ANSYS_EXECUTABLE", raising=False)
    adapter = get_solver_adapter("ansys")

    report = adapter.preflight(tmp_path, model_path=_model(tmp_path))

    assert report["kind"] == "solver_preflight"
    assert report["solver"] == "ANSYS"
    assert report["status"] == "BLOCKED"
    checks = {check["code"]: check["status"] for check in report["checks"]}
    assert checks["SOLVER_AVAILABLE"] == "FAILED"
    assert checks["ANSYS_MODEL_STATIC_SAFETY"] == "PASSED"
    assert checks["MODEL_BUNDLE_INTEGRITY"] == "PASSED"
    assert report["model"]["format"] == "ANSYS_APDL_TEXT"
    assert len(report["model"]["bundleFingerprint"]) == 64
    assert report["load"] == {"mode": "MODEL_SCRIPT_MANAGED"}


def test_ansys_preflight_records_but_does_not_inject_external_load(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.delenv("FEM_ANSYS_EXECUTABLE", raising=False)
    load = tmp_path / "earthquake.csv"
    load.write_text("time,value\n0,0\n1,1\n", encoding="utf-8")

    report = get_solver_adapter("ansys").preflight(
        tmp_path,
        model_path=_model(tmp_path),
        load_path="earthquake.csv",
    )

    assert report["load"]["mode"] == "MODEL_SCRIPT_MANAGED"
    assert report["load"]["providedPath"] == "earthquake.csv"
    assert len(report["load"]["providedSha256"]) == 64
    assert report["load"]["injected"] is False
    assert {warning["code"] for warning in report["warnings"]} == {"EXTERNAL_LOAD_NOT_INJECTED"}


def test_ansys_build_only_stages_sanitized_input_without_solving(tmp_path: Path, monkeypatch) -> None:
    executable = _fake_ansys_runtime(tmp_path)
    monkeypatch.setenv("FEM_ANSYS_EXECUTABLE", str(executable))
    model_path = _model(tmp_path, with_solve=True)
    source_before = (tmp_path / model_path).read_text(encoding="utf-8")

    report = get_solver_adapter("ansys").preflight(tmp_path, model_path=model_path)

    assert report["status"] == "READY"
    checks = {check["code"]: check["status"] for check in report["checks"]}
    assert checks["BUILD_ONLY_INSPECTION"] == "PASSED"
    build = report["model"]["buildInspection"]
    assert build["analysisAdvanced"] is False
    assert build["mode"] == "BUILD_ONLY"
    assert (tmp_path / build["logPath"]).is_file()
    sanitized = (tmp_path / build["inputPath"]).read_text(encoding="utf-8").upper()
    assert "/SOLU" not in sanitized
    assert "\nSOLVE" not in sanitized
    assert (tmp_path / model_path).read_text(encoding="utf-8") == source_before


def test_ansys_real_run_executes_staged_bundle_and_records_provenance(tmp_path: Path, monkeypatch) -> None:
    executable = _fake_ansys_runtime(tmp_path, write_result=True)
    monkeypatch.setenv("FEM_ANSYS_EXECUTABLE", str(executable))
    model_path = _model(tmp_path, with_solve=True)

    result = get_solver_adapter("ansys").run(tmp_path, model_path=model_path)

    assert result["kind"] == "solver_run"
    assert result["status"] == "COMPLETED"
    assert result["solver"]["name"] == "ANSYS"
    assert len(result["caseFingerprint"]) == 64
    assert len(result["model"]["bundleFingerprint"]) == 64
    assert result["load"] == {"mode": "MODEL_SCRIPT_MANAGED"}
    staged_root = tmp_path / result["outputs"]["stagedBundleRoot"]
    assert staged_root.is_dir()
    staged_entrypoint = staged_root / "main.txt"
    assert "SOLVE" in staged_entrypoint.read_text(encoding="utf-8").upper()
    assert (tmp_path / result["outputs"]["solverLog"]).is_file()
    assert (tmp_path / result["outputs"]["runtimeOutput"]).is_file()
    assert (tmp_path / result["outputs"]["runManifest"]).is_file()
    binary_result = tmp_path / result["outputs"]["binaryResult"]
    assert binary_result.is_file()
    assert binary_result.suffix == ".rst"
    assert len(result["outputs"]["binaryResultSha256"]) == 64
    runtime_cwd = staged_root / "fake_runtime_cwd.txt"
    assert runtime_cwd.is_file()
    assert Path(runtime_cwd.read_text(encoding="utf-8")).resolve() == staged_root.resolve()


def test_fake_runtime_is_executable_on_posix(tmp_path: Path) -> None:
    executable = _fake_ansys_runtime(tmp_path)
    if os.name != "nt":
        assert os.access(executable, os.X_OK)
