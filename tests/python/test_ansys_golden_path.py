from __future__ import annotations

import importlib.util
from pathlib import Path
from types import ModuleType

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
