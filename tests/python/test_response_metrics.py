from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path
from typing import Any

import pytest

from fem_core.errors import FemCoreError
from fem_core.model_inspection import inspect_model
from fem_core.response_metrics import (
    REQUEST_SCHEMA,
    compute_engineering_response_metrics,
)


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write_model(tmp_path: Path) -> str:
    path = tmp_path / "model.py"
    path.write_text(
        "import openseespy.opensees as ops\n"
        "ops.model('basic', '-ndm', 2, '-ndf', 3)\n"
        "ops.node(1, 0.0, 0.0)\n"
        "ops.node(2, 6.0, 0.0)\n"
        "ops.node(3, 6.0, 4.0)\n"
        "ops.node(4, 0.0, 4.0)\n"
        "ops.geomTransf('Linear', 1)\n"
        "ops.element('elasticBeamColumn', 41, 1, 4, 0.02, 2.0e11, 8.0e-5, 1)\n"
        "ops.element('elasticBeamColumn', 42, 4, 3, 0.02, 2.0e11, 8.0e-5, 1)\n",
        encoding="utf-8",
    )
    return path.name


def _write_semantic_manifest(tmp_path: Path, model_path: str) -> str:
    fingerprint = inspect_model(tmp_path, model_path)["bundle"]["bundleFingerprint"]
    path = tmp_path / "semantic-roles.json"
    path.write_text(
        json.dumps(
            {
                "schemaVersion": "1.0",
                "kind": "engineering_semantic_roles",
                "model": {"bundleFingerprint": fingerprint},
                "roles": [
                    {
                        "roleId": "TOWER_BASE_LEFT",
                        "roleType": "TOWER_BASE",
                        "entity": {"type": "NODE", "id": 1},
                    },
                    {
                        "roleId": "SUPPORT_RIGHT",
                        "roleType": "SUPPORT",
                        "entity": {"type": "NODE", "id": 2},
                    },
                    {
                        "roleId": "GIRDER_END_RIGHT",
                        "roleType": "GIRDER_END",
                        "entity": {"type": "NODE", "id": 3},
                    },
                    {
                        "roleId": "GIRDER_END_LEFT",
                        "roleType": "GIRDER_END",
                        "entity": {"type": "NODE", "id": 4},
                    },
                    {
                        "roleId": "TOWER_BASE_ELEMENT",
                        "roleType": "TOWER_BASE",
                        "entity": {"type": "ELEMENT", "id": 41},
                    },
                ],
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    return path.name


def _channel(
    channel_id: str,
    *,
    quantity: str,
    target_type: str,
    target_id: int,
    component: str,
    values: list[float],
    unit: str | None,
    reference_frame: str,
    times: list[float] | None = None,
    location: str | None = None,
) -> dict[str, Any]:
    sample_times = times or [0.0, 0.1, 0.2, 0.3]
    result: dict[str, Any] = {
        "channelId": channel_id,
        "quantity": quantity,
        "target": {"type": target_type, "id": target_id},
        "component": component,
        "unit": unit,
        "referenceFrame": reference_frame,
        "abscissaSemantic": "TIME",
        "abscissaUnit": "s",
        "abscissaValues": sample_times,
        "values": values,
    }
    if location is not None:
        result["location"] = location
    return result


def _default_channels() -> list[dict[str, Any]]:
    return [
        _channel(
            "u_girder_right_x",
            quantity="DISPLACEMENT",
            target_type="NODE",
            target_id=3,
            component="X",
            values=[0.0, 0.02, -0.03, 0.01],
            unit="m",
            reference_frame="GLOBAL",
        ),
        _channel(
            "u_girder_left_x",
            quantity="DISPLACEMENT",
            target_type="NODE",
            target_id=4,
            component="X",
            values=[0.0, 0.005, -0.01, 0.002],
            unit="m",
            reference_frame="GLOBAL",
        ),
        _channel(
            "r_tower_x",
            quantity="REACTION_FORCE",
            target_type="NODE",
            target_id=1,
            component="X",
            values=[10.0, -20.0, 30.0, -5.0],
            unit="N",
            reference_frame="GLOBAL",
        ),
        _channel(
            "r_tower_y",
            quantity="REACTION_FORCE",
            target_type="NODE",
            target_id=1,
            component="Y",
            values=[4.0, 3.0, -8.0, 1.0],
            unit="N",
            reference_frame="GLOBAL",
        ),
        _channel(
            "r_support_x",
            quantity="REACTION_FORCE",
            target_type="NODE",
            target_id=2,
            component="X",
            values=[-2.0, 5.0, 7.0, 0.0],
            unit="N",
            reference_frame="GLOBAL",
        ),
        _channel(
            "r_support_y",
            quantity="REACTION_FORCE",
            target_type="NODE",
            target_id=2,
            component="Y",
            values=[1.0, -1.0, -6.0, 2.0],
            unit="N",
            reference_frame="GLOBAL",
        ),
        _channel(
            "v_tower_i",
            quantity="GENERALIZED_FORCE",
            target_type="ELEMENT",
            target_id=41,
            component="VY",
            location="END_I",
            values=[1.0, -3.0, 2.0, 4.0],
            unit="N",
            reference_frame="ELEMENT_LOCAL",
        ),
    ]


def _write_run(
    tmp_path: Path,
    *,
    model_path: str,
    channels: list[dict[str, Any]],
    run_id: str = "run_pr34_metrics001",
    fingerprint_override: str | None = None,
) -> str:
    model_fingerprint = inspect_model(
        tmp_path,
        model_path,
    )["bundle"]["bundleFingerprint"]
    run_dir = tmp_path / ".femagent" / "runs" / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    structural = run_dir / "structural_response.json"
    structural.write_text(
        json.dumps(
            {
                "schemaVersion": "1.0",
                "kind": "structural_response_series",
                "channels": channels,
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    manifest = {
        "schemaVersion": "1.0",
        "kind": "solver_run",
        "runId": run_id,
        "caseFingerprint": "c" * 64,
        "status": "COMPLETED",
        "solver": {
            "name": "OPENSEESPY",
            "executionMode": "ISOLATED_WORKER_PROCESS",
        },
        "model": {
            "path": model_path,
            "bundleFingerprint": fingerprint_override or model_fingerprint,
        },
        "load": {"mode": "MODEL_SCRIPT_MANAGED"},
        "analysis": {"type": "TRANSIENT"},
        "summary": {},
        "outputs": {
            "runManifest": f".femagent/runs/{run_id}/run_manifest.json",
            "structuralResponse": (
                f".femagent/runs/{run_id}/structural_response.json"
            ),
            "structuralResponseSha256": _sha(structural),
        },
    }
    (run_dir / "run_manifest.json").write_text(
        json.dumps(manifest, indent=2),
        encoding="utf-8",
    )
    return run_id


def _request(
    run_id: str,
    model_path: str,
    semantic_manifest_path: str,
    metrics: list[dict[str, Any]],
) -> dict[str, Any]:
    return {
        "schema": REQUEST_SCHEMA,
        "runRef": run_id,
        "modelPath": model_path,
        "semanticManifestPath": semantic_manifest_path,
        "metrics": metrics,
    }


def _workspace(tmp_path: Path) -> tuple[str, str, str]:
    model_path = _write_model(tmp_path)
    manifest_path = _write_semantic_manifest(tmp_path, model_path)
    run_id = _write_run(
        tmp_path,
        model_path=model_path,
        channels=_default_channels(),
    )
    return model_path, manifest_path, run_id


def test_role_peak_supports_girder_displacement_and_element_tower_shear(
    tmp_path: Path,
) -> None:
    model_path, manifest_path, run_id = _workspace(tmp_path)

    report = compute_engineering_response_metrics(
        tmp_path,
        _request(
            run_id,
            model_path,
            manifest_path,
            [
                {
                    "metricId": "girder_disp_x",
                    "type": "ROLE_ABSOLUTE_PEAK",
                    "roleId": "GIRDER_END_RIGHT",
                    "quantity": "DISPLACEMENT",
                    "component": "X",
                },
                {
                    "metricId": "tower_shear_vy",
                    "type": "ROLE_ABSOLUTE_PEAK",
                    "roleId": "TOWER_BASE_ELEMENT",
                    "quantity": "GENERALIZED_FORCE",
                    "component": "VY",
                    "location": "END_I",
                },
            ],
        ),
    )

    assert report["status"] == "COMPLETED"
    assert report["issues"] == []
    by_id = {item["metricId"]: item for item in report["metrics"]}
    girder = by_id["girder_disp_x"]
    assert girder["absolutePeak"] == pytest.approx(0.03)
    assert girder["abscissaAtAbsolutePeak"] == pytest.approx(0.2)
    assert girder["unit"] == "m"
    assert girder["role"]["roleType"] == "GIRDER_END"
    assert girder["target"] == {"type": "NODE", "id": 3}

    shear = by_id["tower_shear_vy"]
    assert shear["absolutePeak"] == pytest.approx(4.0)
    assert shear["location"] == "END_I"
    assert shear["referenceFrame"] == "ELEMENT_LOCAL"
    assert shear["role"]["entity"] == {"type": "ELEMENT", "id": 41}


def test_relative_displacement_peak_uses_exact_simultaneous_samples(
    tmp_path: Path,
) -> None:
    model_path, manifest_path, run_id = _workspace(tmp_path)

    report = compute_engineering_response_metrics(
        tmp_path,
        _request(
            run_id,
            model_path,
            manifest_path,
            [
                {
                    "metricId": "girder_relative_x",
                    "type": "ROLE_RELATIVE_DISPLACEMENT_PEAK",
                    "targetRoleId": "GIRDER_END_RIGHT",
                    "referenceRoleId": "GIRDER_END_LEFT",
                    "component": "X",
                }
            ],
        ),
    )

    metric = report["metrics"][0]
    assert report["status"] == "COMPLETED"
    assert metric["sampleCount"] == 4
    assert metric["formula"] == "target - reference"
    assert metric["min"] == pytest.approx(-0.02)
    assert metric["max"] == pytest.approx(0.015)
    assert metric["valueAtAbsolutePeak"] == pytest.approx(-0.02)
    assert metric["absolutePeak"] == pytest.approx(0.02)
    assert metric["abscissaAtAbsolutePeak"] == pytest.approx(0.2)


def test_group_reaction_resultant_sums_signed_components_before_magnitude(
    tmp_path: Path,
) -> None:
    model_path, manifest_path, run_id = _workspace(tmp_path)

    report = compute_engineering_response_metrics(
        tmp_path,
        _request(
            run_id,
            model_path,
            manifest_path,
            [
                {
                    "metricId": "support_resultant",
                    "type": "ROLE_GROUP_REACTION_RESULTANT_PEAK",
                    "roleIds": ["SUPPORT_RIGHT", "TOWER_BASE_LEFT"],
                    "components": ["Y", "X"],
                }
            ],
        ),
    )

    metric = report["metrics"][0]
    expected = math.hypot(37.0, -14.0)
    assert report["status"] == "COMPLETED"
    assert metric["roles"][0]["roleId"] == "SUPPORT_RIGHT"
    assert metric["roles"][1]["roleId"] == "TOWER_BASE_LEFT"
    assert metric["components"] == ["X", "Y"]
    assert metric["aggregation"] == (
        "SIGNED_COMPONENT_SUM_THEN_VECTOR_MAGNITUDE"
    )
    assert metric["absolutePeak"] == pytest.approx(expected)
    assert metric["maxResultant"] == pytest.approx(expected)
    assert metric["abscissaAtAbsolutePeak"] == pytest.approx(0.2)
    assert metric["componentSumsAtAbsolutePeak"] == {
        "X": pytest.approx(37.0),
        "Y": pytest.approx(-14.0),
    }


def test_single_support_resultant_is_supported(tmp_path: Path) -> None:
    model_path, manifest_path, run_id = _workspace(tmp_path)

    report = compute_engineering_response_metrics(
        tmp_path,
        _request(
            run_id,
            model_path,
            manifest_path,
            [
                {
                    "metricId": "tower_base_resultant",
                    "type": "ROLE_GROUP_REACTION_RESULTANT_PEAK",
                    "roleIds": ["TOWER_BASE_LEFT"],
                    "components": ["X", "Y"],
                }
            ],
        ),
    )

    metric = report["metrics"][0]
    assert metric["absolutePeak"] == pytest.approx(math.hypot(30.0, -8.0))
    assert metric["abscissaAtAbsolutePeak"] == pytest.approx(0.2)


def test_batch_is_limited_when_one_metric_channel_is_unavailable(
    tmp_path: Path,
) -> None:
    model_path, manifest_path, run_id = _workspace(tmp_path)

    report = compute_engineering_response_metrics(
        tmp_path,
        _request(
            run_id,
            model_path,
            manifest_path,
            [
                {
                    "metricId": "good",
                    "type": "ROLE_ABSOLUTE_PEAK",
                    "roleId": "GIRDER_END_RIGHT",
                    "quantity": "DISPLACEMENT",
                    "component": "X",
                },
                {
                    "metricId": "missing",
                    "type": "ROLE_ABSOLUTE_PEAK",
                    "roleId": "GIRDER_END_LEFT",
                    "quantity": "REACTION_FORCE",
                    "component": "Y",
                },
            ],
        ),
    )

    assert report["status"] == "LIMITED"
    assert [item["metricId"] for item in report["metrics"]] == ["good"]
    assert report["issues"][0]["metricId"] == "missing"
    assert report["issues"][0]["code"] == "RESULT_SERIES_UNAVAILABLE"


def test_composite_metric_rejects_misaligned_series_without_resampling(
    tmp_path: Path,
) -> None:
    model_path = _write_model(tmp_path)
    manifest_path = _write_semantic_manifest(tmp_path, model_path)
    channels = _default_channels()
    for channel in channels:
        if channel["channelId"] == "r_support_y":
            channel["abscissaValues"] = [0.0, 0.1, 0.21, 0.3]
    run_id = _write_run(
        tmp_path,
        model_path=model_path,
        channels=channels,
    )

    report = compute_engineering_response_metrics(
        tmp_path,
        _request(
            run_id,
            model_path,
            manifest_path,
            [
                {
                    "metricId": "misaligned",
                    "type": "ROLE_GROUP_REACTION_RESULTANT_PEAK",
                    "roleIds": ["TOWER_BASE_LEFT", "SUPPORT_RIGHT"],
                    "components": ["X", "Y"],
                }
            ],
        ),
    )

    assert report["status"] == "LIMITED"
    assert report["metrics"] == []
    assert report["issues"][0]["code"] == (
        "ENGINEERING_RESPONSE_METRIC_SERIES_MISMATCH"
    )


def test_full_series_paging_exceeds_result_query_page_limit(
    tmp_path: Path,
) -> None:
    model_path = _write_model(tmp_path)
    manifest_path = _write_semantic_manifest(tmp_path, model_path)
    count = 5001
    times = [index * 0.01 for index in range(count)]
    target = [float(index) / 1000.0 for index in range(count)]
    reference = [float(index) / 2000.0 for index in range(count)]
    channels = [
        _channel(
            "paged_target",
            quantity="DISPLACEMENT",
            target_type="NODE",
            target_id=3,
            component="X",
            values=target,
            unit="m",
            reference_frame="GLOBAL",
            times=times,
        ),
        _channel(
            "paged_reference",
            quantity="DISPLACEMENT",
            target_type="NODE",
            target_id=4,
            component="X",
            values=reference,
            unit="m",
            reference_frame="GLOBAL",
            times=times,
        ),
    ]
    run_id = _write_run(
        tmp_path,
        model_path=model_path,
        channels=channels,
        run_id="run_pr34_paging001",
    )

    report = compute_engineering_response_metrics(
        tmp_path,
        _request(
            run_id,
            model_path,
            manifest_path,
            [
                {
                    "metricId": "paged_relative",
                    "type": "ROLE_RELATIVE_DISPLACEMENT_PEAK",
                    "targetRoleId": "GIRDER_END_RIGHT",
                    "referenceRoleId": "GIRDER_END_LEFT",
                    "component": "X",
                }
            ],
        ),
    )

    metric = report["metrics"][0]
    assert metric["sampleCount"] == 5001
    assert metric["absolutePeak"] == pytest.approx(2.5)
    assert metric["abscissaAtAbsolutePeak"] == pytest.approx(50.0)


def test_run_must_match_semantic_model_bundle(tmp_path: Path) -> None:
    model_path = _write_model(tmp_path)
    manifest_path = _write_semantic_manifest(tmp_path, model_path)
    run_id = _write_run(
        tmp_path,
        model_path=model_path,
        channels=_default_channels(),
        fingerprint_override="f" * 64,
    )

    with pytest.raises(FemCoreError) as exc_info:
        compute_engineering_response_metrics(
            tmp_path,
            _request(
                run_id,
                model_path,
                manifest_path,
                [
                    {
                        "metricId": "girder",
                        "type": "ROLE_ABSOLUTE_PEAK",
                        "roleId": "GIRDER_END_RIGHT",
                        "quantity": "DISPLACEMENT",
                        "component": "X",
                    }
                ],
            ),
        )

    assert exc_info.value.code == "ENGINEERING_RESPONSE_METRIC_RUN_MODEL_MISMATCH"


def test_invalid_request_fails_before_result_access(tmp_path: Path) -> None:
    with pytest.raises(FemCoreError) as exc_info:
        compute_engineering_response_metrics(
            tmp_path,
            {
                "schema": REQUEST_SCHEMA,
                "runRef": "run_missing",
                "modelPath": "missing.py",
                "semanticManifestPath": "missing.json",
                "metrics": [
                    {
                        "metricId": "dup",
                        "type": "ROLE_GROUP_REACTION_RESULTANT_PEAK",
                        "roleIds": ["TOWER_BASE_LEFT", "TOWER_BASE_LEFT"],
                        "components": ["X", "Y"],
                    }
                ],
            },
        )

    assert exc_info.value.code == "INVALID_ENGINEERING_RESPONSE_METRIC_REQUEST"
