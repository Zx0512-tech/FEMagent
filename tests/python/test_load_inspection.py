from pathlib import Path

from openpyxl import Workbook

from fem_core.load_inspection import inspect_load


def test_csv_load_inspection_builds_manifest_and_non_binding_mapping(tmp_path: Path) -> None:
    load = tmp_path / "eq.csv"
    load.write_text("time_s,acceleration_g\n0,0\n0.02,0.1\n0.04,-0.2\n", encoding="utf-8")

    report = inspect_load(tmp_path, "eq.csv")

    assert report["schemaVersion"] == "1.1"
    assert report["rowCount"] == 3
    assert report["columnCount"] == 2
    assert report["columns"][0]["timeCandidate"] is True
    assert report["columns"][1]["min"] == -0.2
    assert report["manifest"]["time"]["stepS"] == 0.02
    assert report["manifest"]["channels"][0]["unitHint"] == "g"
    suggestion = report["suggestedMapping"]
    assert suggestion["mapping"]["valueColumn"] == "acceleration_g"
    assert suggestion["mapping"]["sourceUnit"] == "g"
    assert suggestion["mapping"]["component"] is None
    assert suggestion["standardizeDecision"] == "ASK"
    assert "component" in suggestion["requiredConfirmations"]


def test_peer_record_uses_declared_header_metadata(tmp_path: Path) -> None:
    load = tmp_path / "record.AT2"
    load.write_text(
        "PEER NGA RECORD\n"
        "Example event\n"
        "ACCELERATION TIME SERIES IN UNITS OF G\n"
        "NPTS= 4, DT= 0.020 SEC\n"
        "0.0 0.10 -0.20 0.05\n",
        encoding="utf-8",
    )

    report = inspect_load(tmp_path, "record.AT2")

    assert report["format"] == "PEER_NGA"
    assert report["inspectionLevel"] == "SELF_DESCRIBING_RECORD"
    assert report["declaredMetadata"]["declaredNpts"] == 4
    assert report["declaredMetadata"]["declaredDt"] == 0.02
    assert report["declaredMetadata"]["declaredUnit"] == "g"
    assert report["manifest"]["time"]["stepS"] == 0.02
    assert report["suggestedMapping"]["unitSource"] == "DECLARED_IN_HEADER"
    assert report["suggestedMapping"]["mapping"]["component"] is None


def test_xlsx_load_inspection_reads_first_worksheet(tmp_path: Path) -> None:
    path = tmp_path / "motion.xlsx"
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "Motion"
    sheet.append(["time_s", "acceleration(g)"])
    sheet.append([0.0, 0.0])
    sheet.append([0.01, 0.1])
    sheet.append([0.02, -0.1])
    workbook.save(path)
    workbook.close()

    report = inspect_load(tmp_path, "motion.xlsx")

    assert report["format"] == "XLSX"
    assert report["rowCount"] == 3
    assert report["declaredMetadata"]["worksheet"] == "Motion"
    assert report["manifest"]["channels"][0]["unitHint"] == "g"
