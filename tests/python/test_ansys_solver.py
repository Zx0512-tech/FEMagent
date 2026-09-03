from __future__ import annotations

from pathlib import Path

from fem_core.solvers.registry import get_solver_adapter


def _model(tmp_path: Path) -> str:
    model = tmp_path / "main.txt"
    model.write_text(
        "/PREP7\n"
        "N,1,0,0,0\n"
        "N,2,1,0,0\n"
        "E,1,2\n",
        encoding="utf-8",
    )
    return "main.txt"


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
    executable = tmp_path / "ansys_fake"
    executable.write_text("fake runtime", encoding="utf-8")
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
