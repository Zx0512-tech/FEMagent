from pathlib import Path

import pytest

from fem_core.errors import FemCoreError
from fem_core.load_standardization import standardize_load


def test_single_channel_ground_motion_standardizes_g_to_mps2(tmp_path: Path) -> None:
    source = tmp_path / "eq.csv"
    source.write_text("time_s,acceleration_g\n0,0\n0.02,0.1\n0.04,-0.2\n", encoding="utf-8")
    mapping = {
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
    }

    report = standardize_load(tmp_path, "eq.csv", mapping)

    assert report["format"] == "FEMAGENT_LOAD_CSV_V1"
    assert report["sampleCount"] == 3
    assert report["channelCount"] == 1
    assert report["channels"][0]["conversionFactor"] == 9.80665
    output = tmp_path / report["output"]["path"]
    text = output.read_text(encoding="utf-8")
    assert "0.980665" in text
    assert ",m/s2\n" in text


def test_multichannel_standardization_uses_one_time_axis(tmp_path: Path) -> None:
    source = tmp_path / "forces.csv"
    source.write_text("time_s,fx_N,fy_kN\n0,1,2\n0.1,3,4\n", encoding="utf-8")
    mapping = {
        "version": 2,
        "loadKind": "WIND",
        "time": {"column": "time_s", "unit": "s"},
        "channels": [
            {
                "channelId": "fx",
                "valueColumn": "fx_N",
                "applicationType": "NODAL_FORCE",
                "targetType": "NODE",
                "targetId": "10",
                "component": "X",
                "quantity": "FORCE",
                "sourceUnit": "N",
            },
            {
                "channelId": "fy",
                "valueColumn": "fy_kN",
                "applicationType": "NODAL_FORCE",
                "targetType": "NODE",
                "targetId": "20",
                "component": "Y",
                "quantity": "FORCE",
                "sourceUnit": "kN",
            },
        ],
    }

    report = standardize_load(tmp_path, "forces.csv", mapping, output_path="generated/forces.csv")

    assert report["channelCount"] == 2
    assert report["outputRowCount"] == 4
    assert report["channels"][1]["conversionFactor"] == 1000.0
    assert (tmp_path / "generated/forces.csv").exists()


def test_standardization_rejects_incomplete_suggested_mapping(tmp_path: Path) -> None:
    source = tmp_path / "eq.csv"
    source.write_text("time_s,acceleration_g\n0,0\n0.02,0.1\n", encoding="utf-8")
    mapping = {
        "loadKind": "EARTHQUAKE",
        "timeColumn": "time_s",
        "valueColumn": "acceleration_g",
        "quantity": "ACCELERATION",
        "sourceUnit": "g",
        "applicationType": "UNIFORM_EXCITATION",
        "component": None,
    }

    with pytest.raises(FemCoreError) as exc:
        standardize_load(tmp_path, "eq.csv", mapping)

    assert exc.value.code == "INVALID_MAPPING"


def test_standardization_rejects_non_monotonic_time(tmp_path: Path) -> None:
    source = tmp_path / "bad.csv"
    source.write_text("time_s,force_N\n0,1\n0.1,2\n0.05,3\n", encoding="utf-8")
    mapping = {
        "loadKind": "WIND",
        "timeColumn": "time_s",
        "valueColumn": "force_N",
        "quantity": "FORCE",
        "sourceUnit": "N",
        "applicationType": "NODAL_FORCE",
        "component": "X",
    }

    with pytest.raises(FemCoreError) as exc:
        standardize_load(tmp_path, "bad.csv", mapping)

    assert exc.value.code == "TIME_NOT_STRICTLY_INCREASING"
