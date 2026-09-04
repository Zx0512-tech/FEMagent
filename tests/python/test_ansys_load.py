from __future__ import annotations

from pathlib import Path

import pytest

from fem_core.errors import FemCoreError
from fem_core.solvers.ansys_load import read_ansys_canonical_uniform_excitation


CANONICAL_HEADER = (
    "time_s,load_kind,channel_id,application_type,target_type,target_id,component,quantity,value,unit\n"
)


def _write_load(
    tmp_path: Path,
    rows: list[str],
    *,
    name: str = "earthquake.standardized.csv",
) -> Path:
    path = tmp_path / name
    path.write_text(CANONICAL_HEADER + "".join(rows), encoding="utf-8")
    return path


def test_ansys_canonical_load_converts_si_to_declared_mm_s_units(tmp_path: Path) -> None:
    path = _write_load(
        tmp_path,
        [
            "0,EARTHQUAKE,eq_x,UNIFORM_EXCITATION,,,UX,ACCELERATION,1,m/s2\n",
            "0.25,EARTHQUAKE,eq_x,UNIFORM_EXCITATION,,,UX,ACCELERATION,-2,m/s2\n",
            "1,EARTHQUAKE,eq_x,UNIFORM_EXCITATION,,,UX,ACCELERATION,0.5,m/s2\n",
        ],
    )

    result = read_ansys_canonical_uniform_excitation(
        path,
        {"length": "mm", "time": "s"},
    )

    assert result["component"] == "X"
    assert result["timesCanonicalS"] == [0.0, 0.25, 1.0]
    assert result["valuesCanonicalMPerS2"] == [1.0, -2.0, 0.5]
    assert result["timesModel"] == [0.0, 0.25, 1.0]
    assert result["valuesModel"] == [1000.0, -2000.0, 500.0]
    assert result["modelUnits"] == {
        "length": "mm",
        "time": "s",
        "acceleration": "mm/s2",
    }
    assert result["conversion"] == {
        "timeUnitsPerSecond": 1.0,
        "lengthUnitsPerMeter": 1000.0,
        "accelerationFactorFromMPerS2": 1000.0,
    }
    assert result["sampleCount"] == 3
    assert len(result["sha256"]) == 64


@pytest.mark.parametrize(
    ("component", "expected"),
    [("X", "X"), ("U1", "X"), ("2", "Y"), ("UY", "Y"), ("UZ", "Z"), ("3", "Z")],
)
def test_ansys_canonical_load_normalizes_cartesian_component_aliases(
    tmp_path: Path,
    component: str,
    expected: str,
) -> None:
    path = _write_load(
        tmp_path,
        [
            f"0,EARTHQUAKE,eq,UNIFORM_EXCITATION,,,{component},ACCELERATION,0,m/s2\n",
            f"1,EARTHQUAKE,eq,UNIFORM_EXCITATION,,,{component},ACCELERATION,1,m/s2\n",
        ],
        name=f"{component}.csv",
    )

    result = read_ansys_canonical_uniform_excitation(path, {"length": "m", "time": "s"})

    assert result["component"] == expected


def test_ansys_canonical_load_converts_seconds_and_acceleration_for_ms_time_units(tmp_path: Path) -> None:
    path = _write_load(
        tmp_path,
        [
            "0,EARTHQUAKE,eq_y,UNIFORM_EXCITATION,,,Y,ACCELERATION,1,m/s2\n",
            "0.002,EARTHQUAKE,eq_y,UNIFORM_EXCITATION,,,Y,ACCELERATION,2,m/s2\n",
        ],
    )

    result = read_ansys_canonical_uniform_excitation(path, {"length": "m", "time": "ms"})

    assert result["timesModel"] == [0.0, 2.0]
    assert result["valuesModel"] == pytest.approx([1.0e-6, 2.0e-6])
    assert result["modelUnits"]["acceleration"] == "m/ms2"


def test_ansys_canonical_load_requires_explicit_supported_model_units(tmp_path: Path) -> None:
    path = _write_load(
        tmp_path,
        [
            "0,EARTHQUAKE,eq,UNIFORM_EXCITATION,,,X,ACCELERATION,0,m/s2\n",
            "1,EARTHQUAKE,eq,UNIFORM_EXCITATION,,,X,ACCELERATION,1,m/s2\n",
        ],
    )

    with pytest.raises(FemCoreError) as missing:
        read_ansys_canonical_uniform_excitation(path, {})
    assert missing.value.code == "ANSYS_MODEL_UNITS_REQUIRED"

    with pytest.raises(FemCoreError) as unsupported:
        read_ansys_canonical_uniform_excitation(path, {"length": "in", "time": "s"})
    assert unsupported.value.code == "UNSUPPORTED_ANSYS_MODEL_UNITS"


def test_ansys_canonical_load_rejects_non_global_target_and_wrong_contract(tmp_path: Path) -> None:
    targeted = _write_load(
        tmp_path,
        [
            "0,EARTHQUAKE,eq,UNIFORM_EXCITATION,NODE,10,X,ACCELERATION,0,m/s2\n",
            "1,EARTHQUAKE,eq,UNIFORM_EXCITATION,NODE,10,X,ACCELERATION,1,m/s2\n",
        ],
        name="targeted.csv",
    )
    with pytest.raises(FemCoreError) as target_error:
        read_ansys_canonical_uniform_excitation(targeted, {"length": "m", "time": "s"})
    assert target_error.value.code == "ANSYS_UNIFORM_EXCITATION_MUST_BE_GLOBAL"

    wrong = _write_load(
        tmp_path,
        [
            "0,EARTHQUAKE,eq,NODAL_FORCE,,,X,FORCE,0,N\n",
            "1,EARTHQUAKE,eq,NODAL_FORCE,,,X,FORCE,1,N\n",
        ],
        name="wrong.csv",
    )
    with pytest.raises(FemCoreError) as contract_error:
        read_ansys_canonical_uniform_excitation(wrong, {"length": "m", "time": "s"})
    assert contract_error.value.code == "UNSUPPORTED_ANSYS_CANONICAL_LOAD"


def test_ansys_canonical_load_rejects_multiple_channels_and_nonincreasing_time(tmp_path: Path) -> None:
    multi = _write_load(
        tmp_path,
        [
            "0,EARTHQUAKE,x,UNIFORM_EXCITATION,,,X,ACCELERATION,0,m/s2\n",
            "1,EARTHQUAKE,x,UNIFORM_EXCITATION,,,X,ACCELERATION,1,m/s2\n",
            "0,EARTHQUAKE,y,UNIFORM_EXCITATION,,,Y,ACCELERATION,0,m/s2\n",
            "1,EARTHQUAKE,y,UNIFORM_EXCITATION,,,Y,ACCELERATION,1,m/s2\n",
        ],
        name="multi.csv",
    )
    with pytest.raises(FemCoreError) as multi_error:
        read_ansys_canonical_uniform_excitation(multi, {"length": "m", "time": "s"})
    assert multi_error.value.code == "MULTI_CHANNEL_ANSYS_LOAD_NOT_SUPPORTED"

    bad_time = _write_load(
        tmp_path,
        [
            "0,EARTHQUAKE,eq,UNIFORM_EXCITATION,,,X,ACCELERATION,0,m/s2\n",
            "0,EARTHQUAKE,eq,UNIFORM_EXCITATION,,,X,ACCELERATION,1,m/s2\n",
        ],
        name="bad-time.csv",
    )
    with pytest.raises(FemCoreError) as time_error:
        read_ansys_canonical_uniform_excitation(bad_time, {"length": "m", "time": "s"})
    assert time_error.value.code == "TIME_NOT_STRICTLY_INCREASING"
