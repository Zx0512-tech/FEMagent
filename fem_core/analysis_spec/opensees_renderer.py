from __future__ import annotations

import json
import shutil
from hashlib import sha256
from pathlib import Path
from typing import Any
from uuid import uuid4

from fem_core.analysis_spec.readiness import (
    READINESS_PROFILE,
    evaluate_engineering_analysis_readiness,
)
from fem_core.analysis_spec.validator import validate_engineering_analysis_spec
from fem_core.errors import FemCoreError
from fem_core.model_spec.opensees_source import (
    build_opensees_frame_2d_model_source,
    format_opensees_number,
)
from fem_core.model_spec.validator import validate_engineering_model_spec
from fem_core.pathing import workspace_relative_path

RENDER_SCHEMA = "FEMAGENT_OPENSEES_ANALYSIS_RENDER_V1"
RENDERER_NAME = "OPENSEES_FRAME_2D_LINEAR_STATIC_V1"
RENDERER_VERSION = "1.0"


def _write_text(path: Path, content: str) -> None:
    path.write_text(content, encoding="utf-8")


def _sha256_text(content: str) -> str:
    return sha256(content.encode("utf-8")).hexdigest()


def _new_render_id() -> str:
    return f"analysis_render_{uuid4().hex[:16]}"


def _artifact_root(workspace: Path) -> Path:
    root = workspace.resolve()
    generated = (root / ".femagent" / "generated-analyses").resolve()
    try:
        generated.relative_to(root)
    except ValueError as exc:
        raise FemCoreError(
            "OPENSEES_ANALYSIS_RENDER_WRITE_FAILED",
            "Generated-analysis artifact directory resolves outside the active workspace",
        ) from exc
    return generated


def _blocked_result(readiness: dict[str, Any]) -> dict[str, Any]:
    return {
        "schema": RENDER_SCHEMA,
        "status": "BLOCKED",
        "reason": "ANALYSIS_NOT_READY",
        "readiness": readiness,
        "analysisRenderId": None,
        "artifacts": None,
        "analysisRenderFingerprint": None,
    }


def build_opensees_linear_static_analysis_source(
    normalized_model_spec: dict[str, Any],
    normalized_analysis_spec: dict[str, Any],
) -> str:
    source = build_opensees_frame_2d_model_source(normalized_model_spec)
    lines = [
        source.rstrip("\n"),
        "",
        'ops.timeSeries("Linear", 1)',
        'ops.pattern("Plain", 1, 1)',
    ]
    load_case = normalized_analysis_spec["loadCases"][0]
    for load in sorted(load_case["nodalLoads"], key=lambda item: item["nodeId"]):
        lines.append(
            "ops.load("
            f"{load['nodeId']}, {format_opensees_number(load['FX'])}, "
            f"{format_opensees_number(load['FY'])}, {format_opensees_number(load['MZ'])})"
        )
    lines.extend(
        [
            "",
            'ops.constraints("Plain")',
            'ops.numberer("Plain")',
            'ops.system("BandGeneral")',
            'ops.algorithm("Linear")',
            'ops.integrator("LoadControl", 1.0)',
            'ops.analysis("Static")',
            "_femagent_code = int(ops.analyze(1))",
            "if _femagent_code != 0:",
            "    raise RuntimeError(",
            '        f"FEMagent OpenSees linear-static analysis failed with code {_femagent_code}"',
            "    )",
        ]
    )
    return "\n".join(lines) + "\n"


def build_structural_response_plan(normalized_analysis_spec: dict[str, Any]) -> dict[str, Any]:
    channels: list[dict[str, Any]] = []
    for request in sorted(normalized_analysis_spec["resultRequests"], key=lambda item: item["requestId"]):
        channel: dict[str, Any] = {
            "channelId": request["requestId"],
            "quantity": request["quantity"],
            "target": dict(request["target"]),
            "component": request["component"],
        }
        if "location" in request:
            channel["location"] = request["location"]
        channels.append(channel)
    return {
        "schemaVersion": "1.0",
        "kind": "structural_response_plan",
        "channels": channels,
    }


def _canonical_json(value: dict[str, Any]) -> str:
    return json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False) + "\n"


def _render_fingerprint(
    *,
    model_spec_fingerprint: str,
    analysis_spec_fingerprint: str,
    analysis_sha256: str,
    response_plan_sha256: str,
    readiness_sha256: str,
) -> str:
    payload = json.dumps(
        {
            "rendererName": RENDERER_NAME,
            "rendererVersion": RENDERER_VERSION,
            "modelSpecFingerprint": model_spec_fingerprint,
            "analysisSpecFingerprint": analysis_spec_fingerprint,
            "analysisSha256": analysis_sha256,
            "responsePlanSha256": response_plan_sha256,
            "readinessSha256": readiness_sha256,
        },
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")
    return sha256(payload).hexdigest()


def render_opensees_linear_static_analysis(
    workspace: Path,
    model_spec: dict[str, Any],
    analysis_spec: dict[str, Any],
) -> dict[str, Any]:
    if not isinstance(model_spec, dict) or not isinstance(analysis_spec, dict):
        raise FemCoreError(
            "OPENSEES_ANALYSIS_RENDER_SPEC_NOT_OBJECT",
            "OpenSees analysis renderer requires ModelSpec and AnalysisSpec JSON objects",
        )

    readiness = evaluate_engineering_analysis_readiness(model_spec, analysis_spec)
    if readiness["status"] != "READY":
        return _blocked_result(readiness)
    if readiness.get("profile") != READINESS_PROFILE:
        raise FemCoreError(
            "OPENSEES_ANALYSIS_RENDER_UNSUPPORTED_PROFILE",
            "OpenSees analysis renderer received an unsupported readiness profile",
            details={"expected": READINESS_PROFILE, "received": readiness.get("profile")},
        )

    model_validation = validate_engineering_model_spec(model_spec)
    analysis_validation = validate_engineering_analysis_spec(analysis_spec)
    normalized_model = model_validation.get("normalizedSpec")
    normalized_analysis = analysis_validation.get("normalizedSpec")
    model_fingerprint = model_validation.get("modelSpecFingerprint")
    analysis_fingerprint = analysis_validation.get("analysisSpecFingerprint")
    if (
        not isinstance(normalized_model, dict)
        or not isinstance(normalized_analysis, dict)
        or not isinstance(model_fingerprint, str)
        or not isinstance(analysis_fingerprint, str)
        or model_fingerprint != readiness.get("modelSpecFingerprint")
        or analysis_fingerprint != readiness.get("analysisSpecFingerprint")
    ):
        raise FemCoreError(
            "OPENSEES_ANALYSIS_RENDER_INTERNAL_INVARIANT",
            "Analysis Readiness and intrinsic validation disagree at the renderer boundary",
        )

    analysis_source = build_opensees_linear_static_analysis_source(
        normalized_model,
        normalized_analysis,
    )
    response_plan = build_structural_response_plan(normalized_analysis)
    response_plan_text = _canonical_json(response_plan)
    readiness_text = _canonical_json(readiness)
    analysis_sha256 = _sha256_text(analysis_source)
    response_plan_sha256 = _sha256_text(response_plan_text)
    readiness_sha256 = _sha256_text(readiness_text)
    render_fingerprint = _render_fingerprint(
        model_spec_fingerprint=model_fingerprint,
        analysis_spec_fingerprint=analysis_fingerprint,
        analysis_sha256=analysis_sha256,
        response_plan_sha256=response_plan_sha256,
        readiness_sha256=readiness_sha256,
    )

    render_id = _new_render_id()
    generated_root = _artifact_root(workspace)
    render_dir = generated_root / render_id
    try:
        generated_root.mkdir(parents=True, exist_ok=True)
        render_dir.mkdir(exist_ok=False)
    except FileExistsError as exc:
        raise FemCoreError(
            "OPENSEES_ANALYSIS_RENDER_ARTIFACT_EXISTS",
            "OpenSees analysis renderer will not overwrite an existing artifact directory",
            details={"analysisRenderId": render_id},
        ) from exc
    except OSError as exc:
        raise FemCoreError(
            "OPENSEES_ANALYSIS_RENDER_WRITE_FAILED",
            "Unable to create the generated-analysis artifact directory",
            details={"analysisRenderId": render_id},
        ) from exc

    analysis_path = render_dir / "analysis.py"
    response_plan_path = render_dir / "response_plan.json"
    readiness_path = render_dir / "analysis_readiness.json"
    manifest_path = render_dir / "analysis_manifest.json"

    response_mappings = list(readiness["checks"]["responseMapping"]["channels"])
    report = {
        "schema": RENDER_SCHEMA,
        "status": "RENDERED",
        "analysisRenderId": render_id,
        "renderer": {"name": RENDERER_NAME, "version": RENDERER_VERSION},
        "input": {
            "modelSpecFingerprint": model_fingerprint,
            "analysisSpecFingerprint": analysis_fingerprint,
            "readinessProfile": READINESS_PROFILE,
            "units": dict(normalized_model["units"]),
            "normalizedModelSpec": normalized_model,
            "normalizedAnalysisSpec": normalized_analysis,
        },
        "loadCaseId": normalized_analysis["loadCases"][0]["loadCaseId"],
        "responseMappings": response_mappings,
        "artifacts": {
            "analysisPath": workspace_relative_path(workspace, analysis_path),
            "analysisSha256": analysis_sha256,
            "responsePlanPath": workspace_relative_path(workspace, response_plan_path),
            "responsePlanSha256": response_plan_sha256,
            "readinessPath": workspace_relative_path(workspace, readiness_path),
            "readinessSha256": readiness_sha256,
            "manifestPath": workspace_relative_path(workspace, manifest_path),
        },
        "analysisRenderFingerprint": render_fingerprint,
    }

    try:
        _write_text(analysis_path, analysis_source)
        _write_text(response_plan_path, response_plan_text)
        _write_text(readiness_path, readiness_text)
        _write_text(manifest_path, _canonical_json(report))
    except OSError as exc:
        shutil.rmtree(render_dir, ignore_errors=True)
        raise FemCoreError(
            "OPENSEES_ANALYSIS_RENDER_WRITE_FAILED",
            "Unable to publish the OpenSees generated-analysis artifact bundle",
            details={"analysisRenderId": render_id},
        ) from exc

    return report


__all__ = [
    "RENDERER_NAME",
    "RENDERER_VERSION",
    "RENDER_SCHEMA",
    "build_opensees_linear_static_analysis_source",
    "build_structural_response_plan",
    "render_opensees_linear_static_analysis",
]
