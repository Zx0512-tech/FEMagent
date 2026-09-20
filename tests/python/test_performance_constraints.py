from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import pytest

from fem_core.errors import FemCoreError
from fem_core.model_inspection import inspect_model
from fem_core.performance_constraints import (
    REQUEST_SCHEMA,
    evaluate_engineering_performance,
)


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write_model(tmp_path: Path) -> str:
    path = tmp_path / "model.py"
    path.write_text(
        "import openseespy.opensees as ops\n"
        "ops.model('basic', '-ndm', 2, '-ndf', 3)\n"
        "ops.node(1, 0.0, 0.0)\n"
        "ops.node(2, 1.0, 0.0)\n"
        "ops.geomTransf('Linear', 1)\n"
        "ops.element('elasticBeamColumn', 41, 1, 2, 0.02, 2.0e11, 8.0e-5, 1)\n"
        "ops.element('elasticBeamColumn', 42, 1, 2, 0.02, 2.0e11, 8.0e-5, 1)\n",
        encoding="utf-8",
    )
    return path.name


def _write_semantics(tmp_path: Path, model_path: str) -> str:
    fingerprint = inspect_model(tmp_path, model_path)["bundle"]["bundleFingerprint"]
    path = tmp_path / "semantic.json"
    path.write_text(
        json.dumps(
            {
                "schemaVersion": "1.0",
                "kind": "engineering_semantic_roles",
                "model": {"bundleFingerprint": fingerprint},
                "roles": [
                    {
                        "roleId": "SUPPORT_LEFT",
                        "roleType": "SUPPORT",
                        "entity": {"type": "NODE", "id": 1},
                    },
                    {
                        "roleId": "GIRDER_END_RIGHT",
                        "roleType": "GIRDER_END",
                        "entity": {"type": "NODE", "id": 2},
                    },
                    {
                        "roleId": "DAMPER_DEVICE",
                        "roleType": "DAMPER_ATTACHMENT",
                        "entity": {"type": "ELEMENT", "id": 42},
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
) -> dict[str, Any]:
    return {
        "channelId": channel_id,
        "quantity": quantity,
        "target": {"type": target_type, "id": target_id},
        "component": component,
        "unit": unit,
        "referenceFrame": (
            "ELEMENT_LOCAL" if target_type == "ELEMENT" else "GLOBAL"
        ),
        "abscissaSemantic": "TIME",
        "abscissaUnit": "s",
        "abscissaValues": [0.0, 0.1, 0.2, 0.3],
        "values": values,
    }


def _channels() -> list[dict[str, Any]]:
    return [
        _channel(
            "girder_x",
            quantity="DISPLACEMENT",
            target_type="NODE",
            target_id=2,
            component="X",
            values=[0.0, 0.02, -0.03, 0.01],
            unit="m",
        ),
        _channel(
            "support_x",
            quantity="REACTION_FORCE",
            target_type="NODE",
            target_id=1,
            component="X",
            values=[0.0, 10.0, -20.0, 5.0],
            unit="N",
        ),
        _channel(
            "damper_force",
            quantity="DAMPER_RESPONSE",
            target_type="ELEMENT",
            target_id=42,
            component="FORCE",
            values=[0.0, 120.0, -150.0, 60.0],
            unit="N",
        ),
        _channel(
            "damper_deformation",
            quantity="DAMPER_RESPONSE",
            target_type="ELEMENT",
            target_id=42,
            component="DEFORMATION",
            values=[0.0, 0.05, -0.08, 0.02],
            unit="m",
        ),
        _channel(
            "damper_velocity_zero",
            quantity="DAMPER_RESPONSE",
            target_type="ELEMENT",
            target_id=42,
            component="VELOCITY",
            values=[0.0, 0.0, 0.0, 0.0],
            unit="m/s",
        ),
        _channel(
            "damper_energy_unknown",
            quantity="DAMPER_RESPONSE",
            target_type="ELEMENT",
            target_id=42,
            component="DISSIPATED_ENERGY",
            values=[0.0, 1.0, 2.0, 3.0],
            unit=None,
        ),
    ]


def _write_run(
    tmp_path: Path,
    *,
    model_path: str,
    channels: list[dict[str, Any]] | None = None,
    run_id: str = "run_pr35_performance1",
) -> str:
    fingerprint = inspect_model(tmp_path, model_path)["bundle"]["bundleFingerprint"]
    run_dir = tmp_path / ".femagent" / "runs" / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    structural = run_dir / "structural_response.json"
    structural.write_text(
        json.dumps(
            {
                "schemaVersion": "1.0",
                "kind": "structural_response_series",
                "channels": channels or _channels(),
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    manifest = {
        "schemaVersion": "1.0",
        "kind": "solver_run",
        "runId": run_id,
        "caseFingerprint": "d" * 64,
        "status": "COMPLETED",
        "solver": {
            "name": "OPENSEESPY",
            "executionMode": "ISOLATED_WORKER_PROCESS",
        },
        "model": {
            "path": model_path,
            "bundleFingerprint": fingerprint,
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


def _metrics_request(
    run_id: str,
    model_path: str,
    semantic_path: str,
    *,
    include_missing: bool = False,
) -> dict[str, Any]:
    metrics: list[dict[str, Any]] = [
        {
            "metricId": "girder_disp",
            "type": "ROLE_ABSOLUTE_PEAK",
            "roleId": "GIRDER_END_RIGHT",
            "quantity": "DISPLACEMENT",
            "component": "X",
        },
        {
            "metricId": "damper_force",
            "type": "ROLE_ABSOLUTE_PEAK",
            "roleId": "DAMPER_DEVICE",
            "quantity": "DAMPER_RESPONSE",
            "component": "FORCE",
        },
        {
            "metricId": "damper_stroke",
            "type": "ROLE_ABSOLUTE_PEAK",
            "roleId": "DAMPER_DEVICE",
            "quantity": "DAMPER_RESPONSE",
            "component": "DEFORMATION",
        },
        {
            "metricId": "damper_zero_velocity",
            "type": "ROLE_ABSOLUTE_PEAK",
            "roleId": "DAMPER_DEVICE",
            "quantity": "DAMPER_RESPONSE",
            "component": "VELOCITY",
        },
        {
            "metricId": "damper_energy_unknown",
            "type": "ROLE_ABSOLUTE_PEAK",
            "roleId": "DAMPER_DEVICE",
            "quantity": "DAMPER_RESPONSE",
            "component": "DISSIPATED_ENERGY",
        },
    ]
    if include_missing:
        metrics.append(
            {
                "metricId": "missing_support_y",
                "type": "ROLE_ABSOLUTE_PEAK",
                "roleId": "SUPPORT_LEFT",
                "quantity": "REACTION_FORCE",
                "component": "Y",
            }
        )
    return {
        "schema": "FEMAGENT_ENGINEERING_RESPONSE_METRIC_REQUEST_V1",
        "runRef": run_id,
        "modelPath": model_path,
        "semanticManifestPath": semantic_path,
        "metrics": metrics,
    }


def _request(
    metrics_request: dict[str, Any],
    constraints: list[dict[str, Any]],
) -> dict[str, Any]:
    return {
        "schema": REQUEST_SCHEMA,
        "metricsRequest": metrics_request,
        "constraints": constraints,
    }


def _workspace(tmp_path: Path) -> tuple[str, str, str]:
    model_path = _write_model(tmp_path)
    semantic_path = _write_semantics(tmp_path, model_path)
    run_id = _write_run(tmp_path, model_path=model_path)
    return model_path, semantic_path, run_id


def test_all_explicit_limits_satisfied_is_feasible(tmp_path: Path) -> None:
    model_path, semantic_path, run_id = _workspace(tmp_path)
    report = evaluate_engineering_performance(
        tmp_path,
        _request(
            _metrics_request(run_id, model_path, semantic_path),
            [
                {
                    "constraintId": "girder_limit",
                    "metricId": "girder_disp",
                    "operator": "MAXIMUM",
                    "limit": 0.04,
                    "unit": "m",
                },
                {
                    "constraintId": "stroke_limit",
                    "metricId": "damper_stroke",
                    "operator": "MAXIMUM",
                    "limit": 0.10,
                    "unit": "m",
                },
                {
                    "constraintId": "force_limit",
                    "metricId": "damper_force",
                    "operator": "MAXIMUM",
                    "limit": 160.0,
                    "unit": "N",
                },
            ],
        ),
    )

    assert report["status"] == "FEASIBLE"
    assert report["summary"] == {
        "constraintCount": 3,
        "satisfied": 3,
        "violated": 0,
        "notEvaluable": 0,
    }
    by_id = {item["constraintId"]: item for item in report["constraints"]}
    assert by_id["girder_limit"]["observed"] == pytest.approx(0.03)
    assert by_id["stroke_limit"]["observed"] == pytest.approx(0.08)
    assert by_id["force_limit"]["observed"] == pytest.approx(150.0)
    assert by_id["force_limit"]["utilization"] == pytest.approx(0.9375)
    assert by_id["force_limit"]["reserve"] == pytest.approx(10.0)
    assert report["governingConstraint"]["constraintId"] == "force_limit"
    assert len(report["constraintSetFingerprint"]) == 64
    assert len(report["evaluationFingerprint"]) == 64


def test_proven_violation_makes_constraint_set_infeasible(tmp_path: Path) -> None:
    model_path, semantic_path, run_id = _workspace(tmp_path)
    report = evaluate_engineering_performance(
        tmp_path,
        _request(
            _metrics_request(run_id, model_path, semantic_path),
            [
                {
                    "constraintId": "force_limit",
                    "metricId": "damper_force",
                    "operator": "MAXIMUM",
                    "limit": 100.0,
                    "unit": "N",
                }
            ],
        ),
    )

    assert report["status"] == "INFEASIBLE"
    item = report["constraints"][0]
    assert item["status"] == "VIOLATED"
    assert item["observed"] == pytest.approx(150.0)
    assert item["utilization"] == pytest.approx(1.5)
    assert item["reserve"] == pytest.approx(-50.0)


def test_exact_limit_equality_is_satisfied_without_hidden_tolerance(
    tmp_path: Path,
) -> None:
    model_path, semantic_path, run_id = _workspace(tmp_path)
    report = evaluate_engineering_performance(
        tmp_path,
        _request(
            _metrics_request(run_id, model_path, semantic_path),
            [
                {
                    "constraintId": "equal",
                    "metricId": "girder_disp",
                    "operator": "MAXIMUM",
                    "limit": 0.03,
                    "unit": "m",
                }
            ],
        ),
    )

    item = report["constraints"][0]
    assert report["status"] == "FEASIBLE"
    assert item["status"] == "SATISFIED"
    assert item["utilization"] == pytest.approx(1.0)
    assert item["reserve"] == pytest.approx(0.0)


def test_zero_limit_zero_response_is_satisfied(tmp_path: Path) -> None:
    model_path, semantic_path, run_id = _workspace(tmp_path)
    report = evaluate_engineering_performance(
        tmp_path,
        _request(
            _metrics_request(run_id, model_path, semantic_path),
            [
                {
                    "constraintId": "zero_velocity",
                    "metricId": "damper_zero_velocity",
                    "operator": "MAXIMUM",
                    "limit": 0.0,
                    "unit": "m/s",
                }
            ],
        ),
    )

    item = report["constraints"][0]
    assert report["status"] == "FEASIBLE"
    assert item["utilization"] == pytest.approx(0.0)
    assert item["reserve"] == pytest.approx(0.0)
    assert report["governingConstraint"]["basis"] == "MAXIMUM_UTILIZATION"


def test_unit_mismatch_is_limited_and_never_converted(tmp_path: Path) -> None:
    model_path, semantic_path, run_id = _workspace(tmp_path)
    report = evaluate_engineering_performance(
        tmp_path,
        _request(
            _metrics_request(run_id, model_path, semantic_path),
            [
                {
                    "constraintId": "millimetre_limit",
                    "metricId": "girder_disp",
                    "operator": "MAXIMUM",
                    "limit": 40.0,
                    "unit": "mm",
                }
            ],
        ),
    )

    item = report["constraints"][0]
    assert report["status"] == "LIMITED"
    assert item["status"] == "NOT_EVALUABLE"
    assert item["issue"]["code"] == "ENGINEERING_CONSTRAINT_UNIT_MISMATCH"
    assert item["observed"] is None
    assert report["governingConstraint"] is None


def test_unknown_metric_unit_is_not_evaluable(tmp_path: Path) -> None:
    model_path, semantic_path, run_id = _workspace(tmp_path)
    report = evaluate_engineering_performance(
        tmp_path,
        _request(
            _metrics_request(run_id, model_path, semantic_path),
            [
                {
                    "constraintId": "energy_limit",
                    "metricId": "damper_energy_unknown",
                    "operator": "MAXIMUM",
                    "limit": 10.0,
                    "unit": "J",
                }
            ],
        ),
    )

    assert report["status"] == "LIMITED"
    assert report["constraints"][0]["issue"]["code"] == (
        "ENGINEERING_CONSTRAINT_UNIT_UNPROVEN"
    )


def test_missing_metric_channel_is_not_evaluable(tmp_path: Path) -> None:
    model_path, semantic_path, run_id = _workspace(tmp_path)
    report = evaluate_engineering_performance(
        tmp_path,
        _request(
            _metrics_request(
                run_id,
                model_path,
                semantic_path,
                include_missing=True,
            ),
            [
                {
                    "constraintId": "missing_reaction",
                    "metricId": "missing_support_y",
                    "operator": "MAXIMUM",
                    "limit": 20.0,
                    "unit": "N",
                }
            ],
        ),
    )

    assert report["status"] == "LIMITED"
    assert report["metricsStatus"] == "LIMITED"
    issue = report["constraints"][0]["issue"]
    assert issue["code"] == "ENGINEERING_CONSTRAINT_METRIC_NOT_COMPUTED"
    assert issue["details"]["metricIssues"][0]["code"] == (
        "RESULT_SERIES_UNAVAILABLE"
    )


def test_violation_dominates_other_not_evaluable_constraints(
    tmp_path: Path,
) -> None:
    model_path, semantic_path, run_id = _workspace(tmp_path)
    report = evaluate_engineering_performance(
        tmp_path,
        _request(
            _metrics_request(
                run_id,
                model_path,
                semantic_path,
                include_missing=True,
            ),
            [
                {
                    "constraintId": "force_fail",
                    "metricId": "damper_force",
                    "operator": "MAXIMUM",
                    "limit": 100.0,
                    "unit": "N",
                },
                {
                    "constraintId": "missing",
                    "metricId": "missing_support_y",
                    "operator": "MAXIMUM",
                    "limit": 20.0,
                    "unit": "N",
                },
            ],
        ),
    )

    assert report["status"] == "INFEASIBLE"
    assert report["summary"]["violated"] == 1
    assert report["summary"]["notEvaluable"] == 1
    assert report["governingConstraint"] is None


def test_constraint_fingerprints_are_order_invariant(tmp_path: Path) -> None:
    model_path, semantic_path, run_id = _workspace(tmp_path)
    metrics_request = _metrics_request(run_id, model_path, semantic_path)
    first = [
        {
            "constraintId": "a",
            "metricId": "girder_disp",
            "operator": "MAXIMUM",
            "limit": 0.04,
            "unit": "m",
        },
        {
            "constraintId": "b",
            "metricId": "damper_force",
            "operator": "MAXIMUM",
            "limit": 160.0,
            "unit": "N",
        },
    ]
    left = evaluate_engineering_performance(
        tmp_path,
        _request(metrics_request, first),
    )
    right = evaluate_engineering_performance(
        tmp_path,
        _request(metrics_request, list(reversed(first))),
    )

    assert left["constraintSetFingerprint"] == right[
        "constraintSetFingerprint"
    ]
    assert left["evaluationFingerprint"] == right["evaluationFingerprint"]


def test_unknown_constraint_metric_id_is_rejected(tmp_path: Path) -> None:
    model_path, semantic_path, run_id = _workspace(tmp_path)
    with pytest.raises(FemCoreError) as exc_info:
        evaluate_engineering_performance(
            tmp_path,
            _request(
                _metrics_request(run_id, model_path, semantic_path),
                [
                    {
                        "constraintId": "unknown",
                        "metricId": "not_requested",
                        "operator": "MAXIMUM",
                        "limit": 1.0,
                        "unit": "m",
                    }
                ],
            ),
        )

    assert exc_info.value.code == "INVALID_ENGINEERING_PERFORMANCE_REQUEST"


def test_result_tamper_propagates_before_constraint_evaluation(
    tmp_path: Path,
) -> None:
    model_path, semantic_path, run_id = _workspace(tmp_path)
    structural = (
        tmp_path
        / ".femagent"
        / "runs"
        / run_id
        / "structural_response.json"
    )
    structural.write_text(
        structural.read_text(encoding="utf-8") + "\n",
        encoding="utf-8",
    )

    with pytest.raises(FemCoreError) as exc_info:
        evaluate_engineering_performance(
            tmp_path,
            _request(
                _metrics_request(run_id, model_path, semantic_path),
                [
                    {
                        "constraintId": "girder",
                        "metricId": "girder_disp",
                        "operator": "MAXIMUM",
                        "limit": 0.04,
                        "unit": "m",
                    }
                ],
            ),
        )

    assert exc_info.value.code == "RESULT_ARTIFACT_HASH_MISMATCH"
