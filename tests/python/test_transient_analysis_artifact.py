from __future__ import annotations

from hashlib import sha256
from pathlib import Path

import pytest

from fem_core.analysis_spec.transient_artifact import (
    acceleration_m_s2_to_model_factor,
    force_n_to_model_factor,
    read_transient_load_artifact,
    seconds_to_model_time_factor,
)
from fem_core.errors import FemCoreError

HEADER = (
    "time_s,load_kind,channel_id,application_type,target_type,target_id,"
    "component,quantity,value,unit\n"
)


def _write(workspace: Path, rel: str, rows: str, *, header: str = HEADER) -> dict[str, str]:
    path = workspace / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    raw = (header + rows).encode("utf-8")
    path.write_bytes(raw)
    return {"path": rel, "sha256": sha256(raw).hexdigest()}


def _code(exc: pytest.ExceptionInfo[FemCoreError]) -> str:
    return exc.value.code


def test_reads_one_invariant_canonical_nodal_force_channel(tmp_path: Path) -> None:
    ref = _write(
        tmp_path,
        "loads/force.csv",
        "0,TRANSIENT,force-y,NODAL_FORCE,NODE,3,Y,FORCE,0,N\n"
        "0.01,TRANSIENT,force-y,NODAL_FORCE,NODE,3,Y,FORCE,100,N\n"
        "0.02,TRANSIENT,force-y,NODAL_FORCE,NODE,3,Y,FORCE,-25,N\n",
    )

    result = read_transient_load_artifact(tmp_path, ref)

    assert result["timesS"] == [0.0, 0.01, 0.02]
    assert result["values"] == [0.0, 100.0, -25.0]
    assert result["dtS"] == 0.01
    assert result["timeStartS"] == 0.0
    assert result["timeEndS"] == 0.02
    assert result["channelId"] == "force-y"
    assert result["applicationType"] == "NODAL_FORCE"
    assert result["targetType"] == "NODE"
    assert result["targetId"] == "3"
    assert result["component"] == "Y"
    assert result["quantity"] == "FORCE"
    assert result["unit"] == "N"
    assert result["path"] == "loads/force.csv"
    assert result["sha256"] == ref["sha256"]


def test_structurally_valid_nonzero_start_is_reported_not_policy_rejected(tmp_path: Path) -> None:
    ref = _write(
        tmp_path,
        "loads/nonzero.csv",
        "0.01,TRANSIENT,force-y,NODAL_FORCE,NODE,3,Y,FORCE,1,N\n"
        "0.02,TRANSIENT,force-y,NODAL_FORCE,NODE,3,Y,FORCE,2,N\n",
    )
    result = read_transient_load_artifact(tmp_path, ref)
    assert result["timeStartS"] == 0.01
    assert result["dtS"] == 0.01


def test_requires_exact_femagent_load_csv_v1_column_order(tmp_path: Path) -> None:
    ref = _write(
        tmp_path,
        "loads/bad.csv",
        "0,TRANSIENT,c,NODAL_FORCE,NODE,3,Y,FORCE,1,N\n",
        header="value,time_s,load_kind,channel_id,application_type,target_type,target_id,component,quantity,unit\n",
    )
    with pytest.raises(FemCoreError) as exc:
        read_transient_load_artifact(tmp_path, ref)
    assert _code(exc) == "TRANSIENT_ARTIFACT_INVALID_SCHEMA"


def test_rejects_missing_file_and_workspace_escape(tmp_path: Path) -> None:
    missing = {"path": "loads/missing.csv", "sha256": "0" * 64}
    with pytest.raises(FemCoreError) as exc:
        read_transient_load_artifact(tmp_path, missing)
    assert _code(exc) == "TRANSIENT_ARTIFACT_NOT_FOUND"

    with pytest.raises(FemCoreError) as exc:
        read_transient_load_artifact(tmp_path, {"path": "../escape.csv", "sha256": "0" * 64})
    assert _code(exc) == "TRANSIENT_ARTIFACT_PATH_ESCAPE"


def test_rejects_malformed_utf8_and_sha_mismatch(tmp_path: Path) -> None:
    path = tmp_path / "loads/binary.csv"
    path.parent.mkdir(parents=True)
    path.write_bytes(b"\xff\xfe")
    with pytest.raises(FemCoreError) as exc:
        read_transient_load_artifact(tmp_path, {"path": "loads/binary.csv", "sha256": sha256(b"\xff\xfe").hexdigest()})
    assert _code(exc) == "TRANSIENT_ARTIFACT_INVALID_UTF8"

    ref = _write(
        tmp_path,
        "loads/hash.csv",
        "0,TRANSIENT,c,NODAL_FORCE,NODE,3,Y,FORCE,1,N\n"
        "0.01,TRANSIENT,c,NODAL_FORCE,NODE,3,Y,FORCE,2,N\n",
    )
    with pytest.raises(FemCoreError) as exc:
        read_transient_load_artifact(tmp_path, {**ref, "sha256": "0" * 64})
    assert _code(exc) == "TRANSIENT_ARTIFACT_HASH_MISMATCH"


def test_rejects_multiple_or_noninvariant_channels(tmp_path: Path) -> None:
    ref = _write(
        tmp_path,
        "loads/multi.csv",
        "0,TRANSIENT,a,NODAL_FORCE,NODE,3,Y,FORCE,1,N\n"
        "0.01,TRANSIENT,b,NODAL_FORCE,NODE,3,Y,FORCE,2,N\n",
    )
    with pytest.raises(FemCoreError) as exc:
        read_transient_load_artifact(tmp_path, ref)
    assert _code(exc) == "TRANSIENT_ARTIFACT_MULTIPLE_CHANNELS"

    ref = _write(
        tmp_path,
        "loads/noninvariant.csv",
        "0,TRANSIENT,a,NODAL_FORCE,NODE,3,Y,FORCE,1,N\n"
        "0.01,TRANSIENT,a,NODAL_FORCE,NODE,4,Y,FORCE,2,N\n",
    )
    with pytest.raises(FemCoreError) as exc:
        read_transient_load_artifact(tmp_path, ref)
    assert _code(exc) == "TRANSIENT_ARTIFACT_MULTIPLE_CHANNELS"


def test_rejects_malformed_numeric_nonincreasing_and_nonuniform_time(tmp_path: Path) -> None:
    ref = _write(
        tmp_path,
        "loads/numeric.csv",
        "0,TRANSIENT,a,NODAL_FORCE,NODE,3,Y,FORCE,abc,N\n"
        "0.01,TRANSIENT,a,NODAL_FORCE,NODE,3,Y,FORCE,2,N\n",
    )
    with pytest.raises(FemCoreError) as exc:
        read_transient_load_artifact(tmp_path, ref)
    assert _code(exc) == "TRANSIENT_ARTIFACT_INVALID_NUMBER"

    ref = _write(
        tmp_path,
        "loads/order.csv",
        "0,TRANSIENT,a,NODAL_FORCE,NODE,3,Y,FORCE,1,N\n"
        "0,TRANSIENT,a,NODAL_FORCE,NODE,3,Y,FORCE,2,N\n",
    )
    with pytest.raises(FemCoreError) as exc:
        read_transient_load_artifact(tmp_path, ref)
    assert _code(exc) == "TRANSIENT_ARTIFACT_TIME_NOT_INCREASING"

    ref = _write(
        tmp_path,
        "loads/nonuniform.csv",
        "0,TRANSIENT,a,NODAL_FORCE,NODE,3,Y,FORCE,1,N\n"
        "0.01,TRANSIENT,a,NODAL_FORCE,NODE,3,Y,FORCE,2,N\n"
        "0.025,TRANSIENT,a,NODAL_FORCE,NODE,3,Y,FORCE,3,N\n",
    )
    with pytest.raises(FemCoreError) as exc:
        read_transient_load_artifact(tmp_path, ref)
    assert _code(exc) == "TRANSIENT_ARTIFACT_TIME_NOT_UNIFORM"


def test_rejects_too_short_or_malformed_csv(tmp_path: Path) -> None:
    ref = _write(
        tmp_path,
        "loads/short.csv",
        "0,TRANSIENT,a,NODAL_FORCE,NODE,3,Y,FORCE,1,N\n",
    )
    with pytest.raises(FemCoreError) as exc:
        read_transient_load_artifact(tmp_path, ref)
    assert _code(exc) == "TRANSIENT_ARTIFACT_TOO_SHORT"

    ref = _write(
        tmp_path,
        "loads/malformed.csv",
        '0,TRANSIENT,a,NODAL_FORCE,NODE,3,Y,FORCE,"unterminated,N\n',
    )
    with pytest.raises(FemCoreError) as exc:
        read_transient_load_artifact(tmp_path, ref)
    assert _code(exc) == "TRANSIENT_ARTIFACT_INVALID_CSV"


def test_unit_conversion_anchors_are_exact() -> None:
    assert force_n_to_model_factor("N") == 1.0
    assert force_n_to_model_factor("kN") == 0.001
    assert seconds_to_model_time_factor("s") == 1.0
    assert seconds_to_model_time_factor("ms") == 1000.0
    assert acceleration_m_s2_to_model_factor("mm", "ms") == (0.001, "mm/ms2")
