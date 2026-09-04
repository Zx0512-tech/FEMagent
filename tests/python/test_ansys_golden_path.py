from __future__ import annotations

import importlib.util
import shutil
from pathlib import Path
from types import ModuleType

import pytest

from fem_core.errors import FemCoreError

_REPO_ROOT = Path(__file__).resolve().parents[2]
_RUNNER_PATH = _REPO_ROOT / "examples" / "ansys" / "golden_path" / "run_golden_path.py"
_MODEL_PATH = _REPO_ROOT / "examples" / "ansys" / "golden_path" / "model.inp"


def _load_runner() -> ModuleType:
    assert _RUNNER_PATH.is_file(), "PR11 Golden Path harness must exist"
    spec = importlib.util.spec_from_file_location("femagent_ansys_golden_path", _RUNNER_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _strict_fake_ansys_runtime(tmp_path: Path) -> Path:
    executable = tmp_path / "ansys_golden_fake"
    executable.write_text(
        "#!/usr/bin/env python3\n"
        "import shutil\n"
        "import sys\n"
        "from pathlib import Path\n"
        "from ansys.mapdl.reader import examples\n"
        "args = sys.argv[1:]\n"
        "input_path = Path(args[args.index('-i') + 1]).resolve()\n"
        "output_path = Path(args[args.index('-o') + 1]).resolve()\n"
        "job_name = args[args.index('-j') + 1]\n"
        "text = input_path.read_text(encoding='utf-8')\n"
        "active = [line.strip().upper() for line in text.splitlines() "
        "if line.strip() and not line.lstrip().startswith('!')]\n"
        "if input_path.name == 'build_only.inp':\n"
        "    if any(line.startswith('/SOLU') or line.startswith('SOLVE') for line in active):\n"
        "        print('build-only wrapper attempted solution', file=sys.stderr)\n"
        "        raise SystemExit(9)\n"
        "else:\n"
        "    if \"/INPUT,'FEMAGENT_LOAD','MAC'\" not in text.upper():\n"
        "        print('canonical load hook missing from staged model', file=sys.stderr)\n"
        "        raise SystemExit(10)\n"
        "    if not (Path.cwd() / 'femagent_load_table.txt').is_file():\n"
        "        print('canonical load table missing', file=sys.stderr)\n"
        "        raise SystemExit(11)\n"
        "    if not (Path.cwd() / 'femagent_load.mac').is_file():\n"
        "        print('canonical load macro missing', file=sys.stderr)\n"
        "        raise SystemExit(12)\n"
        "    shutil.copyfile(examples.rstfile, Path.cwd() / f'{job_name}.rst')\n"
        "output_path.write_text('FEMagent PR11 fake MAPDL protocol OK\\n', encoding='utf-8')\n",
        encoding="utf-8",
    )
    executable.chmod(executable.stat().st_mode | 0o111)
    return executable


def test_golden_inputs_start_as_xlsx_and_standardize_to_canonical(tmp_path: Path) -> None:
    runner = _load_runner()
    assert _MODEL_PATH.is_file(), "PR11 Golden Model must exist"

    model_text = _MODEL_PATH.read_text(encoding="utf-8").upper()
    assert "ANTYPE,TRANS" in model_text
    assert "TRNOPT,FULL" in model_text
    assert "SOLVE" in model_text
    assert "ACEL" not in model_text
    assert "TRNOPT,MSUP" not in model_text

    source = runner.write_earthquake_xlsx(
        tmp_path,
        amplitude_scale=1.0,
        name="earthquake-base.xlsx",
    )
    before = source.read_bytes()
    report = runner.standardize_golden_load(tmp_path, source)

    assert report["format"] == "FEMAGENT_LOAD_CSV_V1"
    assert report["source"]["format"] == "XLSX"
    assert report["loadKind"] == "EARTHQUAKE"
    assert report["channels"][0]["component"] == "X"
    assert report["channels"][0]["standardUnit"] == "m/s2"
    assert source.read_bytes() == before
    assert runner.GOLDEN_MODEL_UNITS == {"modelUnits": {"length": "m", "time": "s"}}


def test_ci_golden_path_reaches_result_intelligence_without_fake_numerical_claims(
    tmp_path: Path,
    monkeypatch,
) -> None:
    runner = _load_runner()
    assert hasattr(runner, "run_golden_once"), "Task 2 Golden Path orchestrator must exist"

    model = tmp_path / "model.inp"
    shutil.copyfile(_MODEL_PATH, model)
    source_model_before = model.read_bytes()
    xlsx = runner.write_earthquake_xlsx(
        tmp_path,
        amplitude_scale=1.0,
        name="earthquake-ci.xlsx",
    )
    source_xlsx_before = xlsx.read_bytes()
    executable = _strict_fake_ansys_runtime(tmp_path)
    monkeypatch.setenv("FEM_ANSYS_EXECUTABLE", str(executable))

    result = runner.run_golden_once(
        tmp_path,
        model_path="model.inp",
        xlsx_path=xlsx,
        fixture_result_mode=True,
    )

    assert result["standardizedLoad"]["format"] == "FEMAGENT_LOAD_CSV_V1"
    assert result["preflight"]["status"] == "READY"
    assert result["preflight"]["model"]["buildInspection"]["analysisAdvanced"] is False
    assert result["run"]["status"] == "COMPLETED"
    assert result["run"]["injection"]["injected"] is True
    assert len(result["run"]["executionInputFingerprint"]) == 64
    assert len(result["run"]["caseFingerprint"]) == 64
    assert result["run"]["load"]["sourceSha256"] == result["standardizedLoad"]["output"]["sha256"]

    table = tmp_path / result["run"]["outputs"]["generatedLoadTable"]
    macro = tmp_path / result["run"]["outputs"]["generatedLoadMacro"]
    staged_model = tmp_path / result["run"]["outputs"]["stagedBundleRoot"] / "model.inp"
    binary = tmp_path / result["run"]["outputs"]["binaryResult"]
    assert table.is_file()
    assert macro.is_file()
    assert binary.is_file()
    assert len(result["run"]["outputs"]["binaryResultSha256"]) == 64
    assert "/INPUT,'femagent_load','mac'" in staged_model.read_text(encoding="utf-8")

    assert result["resultInspection"]["integrity"]["status"] == "VALID"
    assert result["resultQuery"]["quantity"] == "DISPLACEMENT"
    assert result["resultQuery"]["summary"]["sampleCount"] >= 1
    assert result["evidenceMode"] == "CI_FIXTURE_BACKED"
    assert "numericalClaim" not in result

    assert model.read_bytes() == source_model_before
    assert xlsx.read_bytes() == source_xlsx_before


def test_real_causality_response_change_threshold_is_explicit() -> None:
    runner = _load_runner()
    assert hasattr(runner, "response_changed"), "Task 3 response-change predicate must exist"

    assert runner.response_changed(1.0e-4, 2.0e-4) is True
    assert runner.response_changed(1.0e-4, 1.0e-4 + 1.0e-13) is False


def test_real_golden_path_fails_closed_without_configured_ansys(
    tmp_path: Path,
    monkeypatch,
) -> None:
    runner = _load_runner()
    assert hasattr(runner, "run_real_causality_check"), "Task 3 real ANSYS harness must exist"
    model = tmp_path / "model.inp"
    shutil.copyfile(_MODEL_PATH, model)
    monkeypatch.delenv("FEM_ANSYS_EXECUTABLE", raising=False)

    with pytest.raises(FemCoreError) as exc_info:
        runner.run_real_causality_check(tmp_path, model_path="model.inp")

    assert exc_info.value.code == "GOLDEN_PATH_ANSYS_UNAVAILABLE"
