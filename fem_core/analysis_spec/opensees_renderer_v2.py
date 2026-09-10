from __future__ import annotations

import json
import shutil
from hashlib import sha256
from pathlib import Path
from typing import Any
from uuid import uuid4

from fem_core.analysis_spec.opensees_profiles import OPENSEES_STATIC_V2
from fem_core.analysis_spec.opensees_renderer import (
    build_structural_response_plan,
    render_opensees_linear_static_analysis,
)
from fem_core.analysis_spec.readiness import evaluate_engineering_analysis_readiness
from fem_core.analysis_spec.validator import validate_engineering_analysis_spec
from fem_core.errors import FemCoreError
from fem_core.model_spec.opensees_source import (
    build_opensees_frame_2d_model_source,
    format_opensees_number,
)
from fem_core.model_spec.validator import validate_engineering_model_spec
from fem_core.pathing import workspace_relative_path

RENDER_SCHEMA_V2 = "FEMAGENT_OPENSEES_ANALYSIS_RENDER_V2"
RENDERER_VERSION_V2 = "2.0"


def _canonical_json(value: dict[str, Any]) -> str:
    return json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False) + "\n"


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


def build_opensees_linear_static_v2_source(
    normalized_model_spec: dict[str, Any],
    normalized_load_cases: list[dict[str, Any]],
) -> str:
    if len(normalized_load_cases) != 1:
        raise FemCoreError(
            "OPENSEES_ANALYSIS_RENDER_INTERNAL_INVARIANT",
            "V2 linear-static compiler requires exactly one normalized load case",
        )
    source = build_opensees_frame_2d_model_source(normalized_model_spec)
    lines = [
        source.rstrip("\n"),
        "",
        'ops.timeSeries("Linear", 1)',
        'ops.pattern("Plain", 1, 1)',
    ]
    for load in sorted(normalized_load_cases[0]["nodalLoads"], key=lambda item: item["nodeId"]):
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


def _render_fingerprint(
    *,
    renderer_name: str,
    model_spec_fingerprint: str,
    analysis_spec_fingerprint: str,
    analysis_sha256: str,
    response_plan_sha256: str,
    readiness_sha256: str,
    external_artifacts: list[dict[str, Any]],
    unit_conversions: list[dict[str, Any]],
) -> str:
    payload = json.dumps(
        {
            "rendererName": renderer_name,
            "rendererVersion": RENDERER_VERSION_V2,
            "modelSpecFingerprint": model_spec_fingerprint,
            "analysisSpecFingerprint": analysis_spec_fingerprint,
            "analysisSha256": analysis_sha256,
            "responsePlanSha256": response_plan_sha256,
            "readinessSha256": readiness_sha256,
            "externalArtifacts": external_artifacts,
            "unitConversions": unit_conversions,
        },
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")
    return sha256(payload).hexdigest()


def _blocked_result(readiness: dict[str, Any]) -> dict[str, Any]:
    return {
        "schema": RENDER_SCHEMA_V2,
        "status": "BLOCKED",
        "reason": "ANALYSIS_NOT_READY",
        "readiness": readiness,
        "analysisRenderId": None,
        "artifacts": None,
        "analysisRenderFingerprint": None,
    }


def _publish_v2_bundle(
    *,
    workspace: Path,
    renderer_name: str,
    readiness: dict[str, Any],
    normalized_model: dict[str, Any],
    normalized_analysis: dict[str, Any],
    model_fingerprint: str,
    analysis_fingerprint: str,
    analysis_source: str,
    response_plan: dict[str, Any],
    external_artifacts: list[dict[str, Any]] | None = None,
    unit_conversions: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    external_artifacts = list(external_artifacts or [])
    unit_conversions = list(unit_conversions or [])
    response_plan_text = _canonical_json(response_plan)
    readiness_text = _canonical_json(readiness)
    analysis_sha256 = _sha256_text(analysis_source)
    response_plan_sha256 = _sha256_text(response_plan_text)
    readiness_sha256 = _sha256_text(readiness_text)
    render_fingerprint = _render_fingerprint(
        renderer_name=renderer_name,
        model_spec_fingerprint=model_fingerprint,
        analysis_spec_fingerprint=analysis_fingerprint,
        analysis_sha256=analysis_sha256,
        response_plan_sha256=response_plan_sha256,
        readiness_sha256=readiness_sha256,
        external_artifacts=external_artifacts,
        unit_conversions=unit_conversions,
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

    report = {
        "schema": RENDER_SCHEMA_V2,
        "status": "RENDERED",
        "analysisRenderId": render_id,
        "renderer": {"name": renderer_name, "version": RENDERER_VERSION_V2},
        "input": {
            "modelSpecFingerprint": model_fingerprint,
            "analysisSpecFingerprint": analysis_fingerprint,
            "readinessProfile": renderer_name,
            "units": dict(normalized_model["units"]),
            "normalizedModelSpec": normalized_model,
            "normalizedAnalysisSpec": normalized_analysis,
        },
        "responseMappings": list(readiness["checks"]["responseMapping"]["channels"]),
        "externalArtifacts": external_artifacts,
        "unitConversions": unit_conversions,
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
        analysis_path.write_text(analysis_source, encoding="utf-8")
        response_plan_path.write_text(response_plan_text, encoding="utf-8")
        readiness_path.write_text(readiness_text, encoding="utf-8")
        manifest_path.write_text(_canonical_json(report), encoding="utf-8")
    except OSError as exc:
        shutil.rmtree(render_dir, ignore_errors=True)
        raise FemCoreError(
            "OPENSEES_ANALYSIS_RENDER_WRITE_FAILED",
            "Unable to publish the OpenSees generated-analysis artifact bundle",
            details={"analysisRenderId": render_id},
        ) from exc
    return report


def render_opensees_analysis(
    workspace: Path,
    model_spec: dict[str, Any],
    analysis_spec: dict[str, Any],
) -> dict[str, Any]:
    if not isinstance(model_spec, dict) or not isinstance(analysis_spec, dict):
        raise FemCoreError(
            "OPENSEES_ANALYSIS_RENDER_SPEC_NOT_OBJECT",
            "OpenSees analysis renderer requires ModelSpec and AnalysisSpec JSON objects",
        )
    if analysis_spec.get("schemaVersion") == "1.0":
        return render_opensees_linear_static_analysis(workspace, model_spec, analysis_spec)

    readiness = evaluate_engineering_analysis_readiness(
        model_spec,
        analysis_spec,
        workspace=workspace,
    )
    if readiness["status"] != "READY":
        return _blocked_result(readiness)

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
            "Analysis Readiness and intrinsic validation disagree at the V2 renderer boundary",
        )

    profile = readiness.get("profile")
    if profile != OPENSEES_STATIC_V2:
        raise FemCoreError(
            "OPENSEES_ANALYSIS_RENDER_UNSUPPORTED_PROFILE",
            "Selected V2 OpenSees readiness profile has no renderer yet",
            details={"profile": profile},
        )
    definition = normalized_analysis["definition"]
    analysis_source = build_opensees_linear_static_v2_source(
        normalized_model,
        definition["loadCases"],
    )
    response_plan = build_structural_response_plan(normalized_analysis)
    return _publish_v2_bundle(
        workspace=workspace,
        renderer_name=OPENSEES_STATIC_V2,
        readiness=readiness,
        normalized_model=normalized_model,
        normalized_analysis=normalized_analysis,
        model_fingerprint=model_fingerprint,
        analysis_fingerprint=analysis_fingerprint,
        analysis_source=analysis_source,
        response_plan=response_plan,
    )


__all__ = [
    "RENDERER_VERSION_V2",
    "RENDER_SCHEMA_V2",
    "build_opensees_linear_static_v2_source",
    "render_opensees_analysis",
]
