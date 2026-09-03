from pathlib import Path

from fem_core.load_inspection import inspect_load


def test_csv_load_inspection_profiles_columns(tmp_path: Path) -> None:
    load = tmp_path / "eq.csv"
    load.write_text("time_s,acceleration_g\n0,0\n0.02,0.1\n0.04,-0.2\n", encoding="utf-8")
    report = inspect_load(tmp_path, "eq.csv")
    assert report["rowCount"] == 3
    assert report["columnCount"] == 2
    assert report["columns"][0]["timeCandidate"] is True
    assert report["columns"][1]["min"] == -0.2
    assert "NO_EXPLICIT_TIME_COLUMN_CANDIDATE" not in report["warnings"]
