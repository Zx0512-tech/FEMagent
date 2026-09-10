from __future__ import annotations

import json
from hashlib import sha256
from pathlib import Path
from typing import Any

from fem_core.analysis_spec import opensees_renderer as renderer_v1
from fem_core.analysis_spec import opensees_renderer_v2 as renderer_v2
from fem_core.analysis_spec.opensees_profiles import (
    OPENSEES_MODAL_V2,
    OPENSEES_STATIC_V2,
    OPENSEES_TRANSIENT_BASE_V2,
    OPENSEES_TRANSIENT_NODAL_V2,
)
from fem_core.analysis_spec.opensees_profiles.modal_v2 import build_modal_response_plan
from fem_core.analysis_spec.readiness import (
    READINESS_PROFILE,
    evaluate_engineering_analysis_readiness,
)
from fem_core.analysis_spec.transient_artifact import read_transient_load_artifact
from fem_core.analysis_spec.validator import validate_engineering_analysis_spec
from fem_core.errors import FemCoreError
from fem_core.model_spec.validator import validate_engineering_model_spec
from fem_core.pathing import resolve_workspace_file, workspace_relative_path

VERIFICATION_SCHEMA = "FEMAGENT_GENERATED_ANALYSIS_VERIFICATION_V1"
VERIFICATION_SCHEMA_V2 = "FEMAGENT_GENERATED_ANALYSIS_VERIFICATION_V2"
_RESPONSE_CONTEXT_KIND = "verified_structural_response_context"
_MODAL_CONTEXT_KIND = "verified_modal_response_context"
_V2_PROFILES = {
    OPENSEES_STATIC_V2,
    OPENSEES_MODAL_V2,
    OPENSEES_TRANSIENT_NODAL_V2,
    OPENSEES_TRANSIENT_BASE_V2,
}
_TRANSIENT_PROFILES = {OPENSEES_TRANSIENT_NODAL_V2, OPENSEES_TRANSIENT_BASE_V2}


def _sha256_bytes(content: bytes) -> str:
    return sha256(content).hexdigest()


def _manifest_error(message: str, *, details: dict[str, Any] | None = None) -> FemCoreError:
    return FemCoreError(
        "GENERATED_ANALYSIS_MANIFEST_INVALID",
        message,
        details=details or {},
    )


def _load_json_object(path: Path, *, label: str) -> dict[str, Any]:
    try:
        loaded = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise _manifest_error(
            f"Generated-analysis {label} must be valid UTF-8 JSON",
            details={"path": str(path)},
        ) from exc
    if not isinstance(loaded, dict):
        raise _manifest_error(
            f"Generated-analysis {label} must be a JSON object",
            details={"path": str(path)},
        )
    return loaded


def _required_object(container: dict[str, Any], key: str) -> dict[str, Any]:
    value = container.get(key)
    if not isinstance(value, dict):
        raise _manifest_error(f"Generated-analysis manifest field '{key}' must be an object")
    return value


def _required_text(container: dict[str, Any], key: str) -> str:
    value = container.get(key)
    if not isinstance(value, str) or not value:
        raise _manifest_error(f"Generated-analysis manifest field '{key}' must be a non-empty string")
    return value


def _require_manifest_shape(manifest: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    if manifest.get("schema") != renderer_v1.RENDER_SCHEMA or manifest.get("status") != "RENDERED":
        raise _manifest_error(
            "Generated-analysis manifest schema/status is not the PR26 rendered-analysis contract"
        )
    renderer = _required_object(manifest, "renderer")
    if renderer != {"name": renderer_v1.RENDERER_NAME, "version": renderer_v1.RENDERER_VERSION}:
        raise _manifest_error("Generated-analysis renderer identity is unsupported")
    input_info = _required_object(manifest, "input")
    artifacts = _required_object(manifest, "artifacts")
    for key in ("modelSpecFingerprint", "analysisSpecFingerprint", "readinessProfile"):
        _required_text(input_info, key)
    if not isinstance(input_info.get("normalizedModelSpec"), dict):
        raise _manifest_error("Generated-analysis manifest is missing embedded normalizedModelSpec")
    if not isinstance(input_info.get("normalizedAnalysisSpec"), dict):
        raise _manifest_error("Generated-analysis manifest is missing embedded normalizedAnalysisSpec")
    if not isinstance(input_info.get("units"), dict):
        raise _manifest_error("Generated-analysis manifest is missing embedded model units")
    for key in (
        "analysisPath",
        "analysisSha256",
        "responsePlanPath",
        "responsePlanSha256",
        "readinessPath",
        "readinessSha256",
        "manifestPath",
    ):
        _required_text(artifacts, key)
    if not isinstance(manifest.get("responseMappings"), list):
        raise _manifest_error("Generated-analysis manifest responseMappings must be an array")
    _required_text(manifest, "analysisRenderFingerprint")
    _required_text(manifest, "loadCaseId")
    return input_info, artifacts


def _require_manifest_shape_v2(
    manifest: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, Any], str]:
    if manifest.get("schema") != renderer_v2.RENDER_SCHEMA_V2 or manifest.get("status") != "RENDERED":
        raise _manifest_error("Generated-analysis manifest schema/status is not the V2 render contract")
    renderer = _required_object(manifest, "renderer")
    renderer_name = _required_text(renderer, "name")
    if renderer.get("version") != renderer_v2.RENDERER_VERSION_V2:
        raise _manifest_error("Generated-analysis V2 renderer version is unsupported")
    if renderer_name not in _V2_PROFILES:
        raise _manifest_error("Generated-analysis V2 renderer profile is unsupported")
    input_info = _required_object(manifest, "input")
    artifacts = _required_object(manifest, "artifacts")
    for key in ("modelSpecFingerprint", "analysisSpecFingerprint", "readinessProfile"):
        _required_text(input_info, key)
    if input_info.get("readinessProfile") != renderer_name:
        raise _manifest_error("Generated-analysis V2 renderer/readiness profile identity differs")
    if not isinstance(input_info.get("normalizedModelSpec"), dict):
        raise _manifest_error("Generated-analysis manifest is missing embedded normalizedModelSpec")
    if not isinstance(input_info.get("normalizedAnalysisSpec"), dict):
        raise _manifest_error("Generated-analysis manifest is missing embedded normalizedAnalysisSpec")
    if not isinstance(input_info.get("units"), dict):
        raise _manifest_error("Generated-analysis manifest is missing embedded model units")
    for key in (
        "analysisPath",
        "analysisSha256",
        "responsePlanPath",
        "responsePlanSha256",
        "readinessPath",
        "readinessSha256",
        "manifestPath",
    ):
        _required_text(artifacts, key)
    for key in ("responseMappings", "externalArtifacts", "unitConversions"):
        if not isinstance(manifest.get(key), list):
            raise _manifest_error(f"Generated-analysis manifest {key} must be an array")
    _required_text(manifest, "analysisRenderFingerprint")
    return input_info, artifacts, renderer_name


def _require_same_path(
    workspace: Path,
    actual: Path,
    declared: str,
    *,
    label: str,
) -> None:
    actual_rel = workspace_relative_path(workspace, actual)
    declared_file = resolve_workspace_file(workspace, declared)
    declared_rel = workspace_relative_path(workspace, declared_file)
    if actual_rel != declared_rel:
        raise FemCoreError(
            "GENERATED_ANALYSIS_PATH_MISMATCH",
            f"Supplied {label} does not match the path declared by the generated-analysis manifest",
            details={"supplied": actual_rel, "declared": declared_rel},
        )


def _fingerprint_error(message: str, *, details: dict[str, Any] | None = None) -> FemCoreError:
    return FemCoreError(
        "GENERATED_ANALYSIS_FINGERPRINT_MISMATCH",
        message,
        details=details or {},
    )


def _artifact_error(message: str, *, details: dict[str, Any] | None = None) -> FemCoreError:
    return FemCoreError(
        "GENERATED_ANALYSIS_ARTIFACT_MISMATCH",
        message,
        details=details or {},
    )


def _verified_response_context(readiness: dict[str, Any]) -> dict[str, Any]:
    channels: list[dict[str, Any]] = []
    mappings = readiness["checks"]["responseMapping"]["channels"]
    for mapping in mappings:
        channel = dict(mapping)
        request_id = str(channel.pop("requestId"))
        channel["channelId"] = request_id
        channels.append(channel)
    channels.sort(key=lambda item: str(item["channelId"]))
    return {
        "schemaVersion": "1.0",
        "kind": _RESPONSE_CONTEXT_KIND,
        "channels": channels,
    }


def _verified_v2_structural_context(
    readiness: dict[str, Any],
    *,
    analysis_type: str,
    abscissa_semantic: str,
    abscissa_unit: str | None,
) -> dict[str, Any]:
    channels: list[dict[str, Any]] = []
    for mapping in readiness["checks"]["responseMapping"]["channels"]:
        channel = dict(mapping)
        channel["channelId"] = str(channel.pop("requestId"))
        channels.append(channel)
    channels.sort(key=lambda item: str(item["channelId"]))
    return {
        "schemaVersion": "2.0",
        "kind": _RESPONSE_CONTEXT_KIND,
        "analysisType": analysis_type,
        "abscissaSemantic": abscissa_semantic,
        "abscissaUnit": abscissa_unit,
        "channels": channels,
    }


def _verified_modal_context(
    normalized_model: dict[str, Any],
    normalized_analysis: dict[str, Any],
) -> dict[str, Any]:
    plan = build_modal_response_plan(normalized_analysis)
    return {
        "schemaVersion": "1.0",
        "kind": _MODAL_CONTEXT_KIND,
        "modeCount": int(plan["modeCount"]),
        "modelTimeUnit": str(normalized_model["units"]["time"]),
        "requests": list(plan["requests"]),
    }


def _verify_v1_generated_analysis_bundle(
    workspace: Path,
    *,
    model_file: Path,
    response_plan_file: Path,
    manifest_file: Path,
    manifest: dict[str, Any],
) -> dict[str, Any]:
    input_info, artifacts = _require_manifest_shape(manifest)

    _require_same_path(workspace, model_file, artifacts["analysisPath"], label="analysis.py")
    _require_same_path(
        workspace,
        response_plan_file,
        artifacts["responsePlanPath"],
        label="response_plan.json",
    )
    _require_same_path(
        workspace,
        manifest_file,
        artifacts["manifestPath"],
        label="analysis_manifest.json",
    )
    readiness_file = resolve_workspace_file(workspace, artifacts["readinessPath"])

    embedded_model = input_info["normalizedModelSpec"]
    embedded_analysis = input_info["normalizedAnalysisSpec"]
    model_validation = validate_engineering_model_spec(embedded_model)
    analysis_validation = validate_engineering_analysis_spec(embedded_analysis)
    if model_validation["status"] != "VALID" or analysis_validation["status"] != "VALID":
        raise _fingerprint_error(
            "Embedded normalized engineering specifications no longer validate",
            details={
                "modelStatus": model_validation["status"],
                "analysisStatus": analysis_validation["status"],
            },
        )

    normalized_model = model_validation["normalizedSpec"]
    normalized_analysis = analysis_validation["normalizedSpec"]
    model_fingerprint = model_validation["modelSpecFingerprint"]
    analysis_fingerprint = analysis_validation["analysisSpecFingerprint"]
    if not isinstance(normalized_model, dict) or not isinstance(normalized_analysis, dict):
        raise _fingerprint_error("Validated embedded specifications lack normalized forms")
    if not isinstance(model_fingerprint, str) or not isinstance(analysis_fingerprint, str):
        raise _fingerprint_error("Validated embedded specifications lack deterministic fingerprints")
    if model_fingerprint != input_info["modelSpecFingerprint"]:
        raise _fingerprint_error("Embedded ModelSpec fingerprint does not match manifest identity")
    if analysis_fingerprint != input_info["analysisSpecFingerprint"]:
        raise _fingerprint_error("Embedded AnalysisSpec fingerprint does not match manifest identity")
    if input_info["readinessProfile"] != READINESS_PROFILE:
        raise _fingerprint_error("Manifest readiness profile does not match the supported PR26 profile")
    if input_info["units"] != normalized_model["units"]:
        raise _fingerprint_error("Manifest unit identity does not match the embedded normalized ModelSpec")
    if manifest["loadCaseId"] != normalized_analysis["loadCases"][0]["loadCaseId"]:
        raise _fingerprint_error("Manifest load-case identity does not match the embedded AnalysisSpec")

    readiness = evaluate_engineering_analysis_readiness(normalized_model, normalized_analysis)
    if readiness.get("status") != "READY" or readiness.get("profile") != READINESS_PROFILE:
        raise _fingerprint_error(
            "Embedded engineering specifications no longer pass PR26 Analysis Readiness",
            details={"status": readiness.get("status"), "profile": readiness.get("profile")},
        )
    if readiness.get("modelSpecFingerprint") != model_fingerprint:
        raise _fingerprint_error("Recomputed Analysis Readiness ModelSpec fingerprint differs")
    if readiness.get("analysisSpecFingerprint") != analysis_fingerprint:
        raise _fingerprint_error("Recomputed Analysis Readiness AnalysisSpec fingerprint differs")

    expected_mappings = readiness["checks"]["responseMapping"]["channels"]
    if manifest["responseMappings"] != expected_mappings:
        raise _fingerprint_error("Manifest response mappings differ from recomputed trusted mappings")

    expected_source = renderer_v1.build_opensees_linear_static_analysis_source(
        normalized_model,
        normalized_analysis,
    )
    expected_plan_text = renderer_v1._canonical_json(
        renderer_v1.build_structural_response_plan(normalized_analysis)
    )
    expected_readiness_text = renderer_v1._canonical_json(readiness)
    try:
        actual_source = model_file.read_text(encoding="utf-8")
        actual_plan_text = response_plan_file.read_text(encoding="utf-8")
        actual_readiness_text = readiness_file.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        raise _artifact_error("Generated-analysis artifacts must remain readable UTF-8 text") from exc

    artifact_pairs = (
        ("analysis.py", actual_source, expected_source, "analysisSha256"),
        ("response_plan.json", actual_plan_text, expected_plan_text, "responsePlanSha256"),
        ("analysis_readiness.json", actual_readiness_text, expected_readiness_text, "readinessSha256"),
    )
    computed_hashes: dict[str, str] = {}
    for label, actual_text, expected_text, hash_key in artifact_pairs:
        actual_hash = _sha256_bytes(actual_text.encode("utf-8"))
        computed_hashes[hash_key] = actual_hash
        if actual_hash != artifacts[hash_key]:
            raise _artifact_error(
                f"Generated-analysis {label} hash differs from the manifest",
                details={"actual": actual_hash, "declared": artifacts[hash_key]},
            )
        if actual_text != expected_text:
            raise _artifact_error(f"Generated-analysis {label} differs from deterministic regeneration")

    render_fingerprint = renderer_v1._render_fingerprint(
        model_spec_fingerprint=model_fingerprint,
        analysis_spec_fingerprint=analysis_fingerprint,
        analysis_sha256=computed_hashes["analysisSha256"],
        response_plan_sha256=computed_hashes["responsePlanSha256"],
        readiness_sha256=computed_hashes["readinessSha256"],
    )
    if render_fingerprint != manifest["analysisRenderFingerprint"]:
        raise _fingerprint_error(
            "Generated-analysis render fingerprint differs from deterministic recomputation"
        )

    return {
        "schema": VERIFICATION_SCHEMA,
        "status": "VERIFIED",
        "analysisRenderFingerprint": render_fingerprint,
        "modelSpecFingerprint": model_fingerprint,
        "analysisSpecFingerprint": analysis_fingerprint,
        "analysisManifestSha256": _sha256_bytes(manifest_file.read_bytes()),
        "readiness": readiness,
        "responseContext": _verified_response_context(readiness),
        "normalizedModelSpec": normalized_model,
        "normalizedAnalysisSpec": normalized_analysis,
        "artifacts": {
            "analysisPath": workspace_relative_path(workspace, model_file),
            "analysisSha256": computed_hashes["analysisSha256"],
            "responsePlanPath": workspace_relative_path(workspace, response_plan_file),
            "responsePlanSha256": computed_hashes["responsePlanSha256"],
            "readinessPath": workspace_relative_path(workspace, readiness_file),
            "readinessSha256": computed_hashes["readinessSha256"],
            "manifestPath": workspace_relative_path(workspace, manifest_file),
        },
    }


def _preverify_external_artifact(
    workspace: Path,
    manifest: dict[str, Any],
    renderer_name: str,
) -> None:
    declared = manifest["externalArtifacts"]
    if renderer_name not in _TRANSIENT_PROFILES:
        if declared:
            raise _fingerprint_error("Static/Modal V2 bundles must not declare external artifacts")
        return
    if len(declared) != 1 or not isinstance(declared[0], dict):
        raise _manifest_error("Transient V2 bundle must declare exactly one external artifact")
    item = declared[0]
    path = item.get("path")
    digest = item.get("sha256")
    artifact_format = item.get("format")
    if not isinstance(path, str) or not isinstance(digest, str) or artifact_format != "FEMAGENT_LOAD_CSV_V1":
        raise _manifest_error("Transient V2 external artifact provenance is malformed")
    try:
        evidence = read_transient_load_artifact(
            workspace,
            {"path": path, "sha256": digest},
        )
    except FemCoreError as exc:
        raise _artifact_error(
            "Transient external artifact no longer matches rendered provenance",
            details={"artifactErrorCode": exc.code, "path": path},
        ) from exc
    if evidence.get("format") != artifact_format:
        raise _artifact_error("Transient external artifact format differs from rendered provenance")


def _expected_v2_provenance(
    readiness: dict[str, Any],
    renderer_name: str,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    if renderer_name not in _TRANSIENT_PROFILES:
        return [], []
    checks = readiness.get("checks")
    if not isinstance(checks, dict):
        raise _fingerprint_error("Transient readiness lacks deterministic checks")
    artifact_check = checks.get("loadArtifact")
    conversion_check = checks.get("unitConversions")
    if not isinstance(artifact_check, dict) or not isinstance(conversion_check, dict):
        raise _fingerprint_error("Transient readiness lacks artifact/conversion evidence")
    evidence = artifact_check.get("evidence")
    conversions = conversion_check.get("conversions")
    if not isinstance(evidence, dict) or not isinstance(conversions, list):
        raise _fingerprint_error("Transient readiness lacks verified artifact/conversion evidence")
    external = [
        {
            "path": str(evidence["path"]),
            "sha256": str(evidence["sha256"]),
            "format": str(evidence["format"]),
        }
    ]
    return external, [dict(item) for item in conversions]


def _verify_v2_generated_analysis_bundle(
    workspace: Path,
    *,
    model_file: Path,
    response_plan_file: Path,
    manifest_file: Path,
    manifest: dict[str, Any],
) -> dict[str, Any]:
    input_info, artifacts, renderer_name = _require_manifest_shape_v2(manifest)
    _require_same_path(workspace, model_file, artifacts["analysisPath"], label="analysis.py")
    _require_same_path(
        workspace,
        response_plan_file,
        artifacts["responsePlanPath"],
        label="response_plan.json",
    )
    _require_same_path(
        workspace,
        manifest_file,
        artifacts["manifestPath"],
        label="analysis_manifest.json",
    )
    readiness_file = resolve_workspace_file(workspace, artifacts["readinessPath"])
    _preverify_external_artifact(workspace, manifest, renderer_name)

    embedded_model = input_info["normalizedModelSpec"]
    embedded_analysis = input_info["normalizedAnalysisSpec"]
    model_validation = validate_engineering_model_spec(embedded_model)
    analysis_validation = validate_engineering_analysis_spec(embedded_analysis)
    if model_validation["status"] != "VALID" or analysis_validation["status"] != "VALID":
        raise _fingerprint_error(
            "Embedded normalized engineering specifications no longer validate",
            details={
                "modelStatus": model_validation["status"],
                "analysisStatus": analysis_validation["status"],
            },
        )
    normalized_model = model_validation["normalizedSpec"]
    normalized_analysis = analysis_validation["normalizedSpec"]
    model_fingerprint = model_validation["modelSpecFingerprint"]
    analysis_fingerprint = analysis_validation["analysisSpecFingerprint"]
    if not isinstance(normalized_model, dict) or not isinstance(normalized_analysis, dict):
        raise _fingerprint_error("Validated embedded specifications lack normalized forms")
    if not isinstance(model_fingerprint, str) or not isinstance(analysis_fingerprint, str):
        raise _fingerprint_error("Validated embedded specifications lack deterministic fingerprints")
    if model_fingerprint != input_info["modelSpecFingerprint"]:
        raise _fingerprint_error("Embedded ModelSpec fingerprint does not match manifest identity")
    if analysis_fingerprint != input_info["analysisSpecFingerprint"]:
        raise _fingerprint_error("Embedded AnalysisSpec fingerprint does not match manifest identity")
    if input_info["units"] != normalized_model["units"]:
        raise _fingerprint_error("Manifest unit identity does not match the embedded normalized ModelSpec")

    readiness = evaluate_engineering_analysis_readiness(
        normalized_model,
        normalized_analysis,
        workspace=workspace,
    )
    if readiness.get("status") != "READY" or readiness.get("profile") != renderer_name:
        raise _fingerprint_error(
            "Embedded engineering specifications no longer pass the declared V2 Analysis Readiness profile",
            details={"status": readiness.get("status"), "profile": readiness.get("profile")},
        )
    if readiness.get("modelSpecFingerprint") != model_fingerprint:
        raise _fingerprint_error("Recomputed Analysis Readiness ModelSpec fingerprint differs")
    if readiness.get("analysisSpecFingerprint") != analysis_fingerprint:
        raise _fingerprint_error("Recomputed Analysis Readiness AnalysisSpec fingerprint differs")
    expected_mappings = readiness["checks"]["responseMapping"]["channels"]
    if manifest["responseMappings"] != expected_mappings:
        raise _fingerprint_error("Manifest response mappings differ from recomputed trusted mappings")

    external_artifacts, unit_conversions = _expected_v2_provenance(readiness, renderer_name)
    if manifest["externalArtifacts"] != external_artifacts:
        raise _fingerprint_error("Manifest external artifact provenance differs from recomputed evidence")
    if manifest["unitConversions"] != unit_conversions:
        raise _fingerprint_error("Manifest unit conversions differ from recomputed evidence")

    if renderer_name == OPENSEES_STATIC_V2:
        definition = normalized_analysis["definition"]
        expected_source = renderer_v2.build_opensees_linear_static_v2_source(
            normalized_model,
            definition["loadCases"],
        )
        expected_plan = renderer_v1.build_structural_response_plan(normalized_analysis)
        execution_mode = "SCRIPT"
        response_context = _verified_v2_structural_context(
            readiness,
            analysis_type="LINEAR_STATIC",
            abscissa_semantic="SOLVER_NATIVE_RESULT_ABSCISSA",
            abscissa_unit=None,
        )
    elif renderer_name == OPENSEES_MODAL_V2:
        definition = normalized_analysis["definition"]
        expected_source = renderer_v2.build_opensees_modal_v2_source(
            normalized_model,
            int(definition["modeCount"]),
        )
        expected_plan = build_modal_response_plan(normalized_analysis)
        execution_mode = "MODAL"
        response_context = _verified_modal_context(normalized_model, normalized_analysis)
    elif renderer_name in _TRANSIENT_PROFILES:
        expected_source = renderer_v2.build_opensees_transient_v2_source(
            normalized_model,
            normalized_analysis,
            readiness,
        )
        expected_plan = renderer_v1.build_structural_response_plan(normalized_analysis)
        execution_mode = "SCRIPT"
        response_context = _verified_v2_structural_context(
            readiness,
            analysis_type="TRANSIENT",
            abscissa_semantic="TIME",
            abscissa_unit=str(normalized_model["units"]["time"]),
        )
    else:
        raise _manifest_error("Generated-analysis V2 renderer profile is unsupported")

    expected_plan_text = renderer_v2._canonical_json(expected_plan)
    expected_readiness_text = renderer_v2._canonical_json(readiness)
    try:
        actual_source = model_file.read_text(encoding="utf-8")
        actual_plan_text = response_plan_file.read_text(encoding="utf-8")
        actual_readiness_text = readiness_file.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        raise _artifact_error("Generated-analysis artifacts must remain readable UTF-8 text") from exc

    artifact_pairs = (
        ("analysis.py", actual_source, expected_source, "analysisSha256"),
        ("response_plan.json", actual_plan_text, expected_plan_text, "responsePlanSha256"),
        ("analysis_readiness.json", actual_readiness_text, expected_readiness_text, "readinessSha256"),
    )
    computed_hashes: dict[str, str] = {}
    for label, actual_text, expected_text, hash_key in artifact_pairs:
        actual_hash = _sha256_bytes(actual_text.encode("utf-8"))
        computed_hashes[hash_key] = actual_hash
        if actual_hash != artifacts[hash_key]:
            raise _artifact_error(
                f"Generated-analysis {label} hash differs from the manifest",
                details={"actual": actual_hash, "declared": artifacts[hash_key]},
            )
        if actual_text != expected_text:
            raise _artifact_error(f"Generated-analysis {label} differs from deterministic regeneration")

    render_fingerprint = renderer_v2._render_fingerprint(
        renderer_name=renderer_name,
        model_spec_fingerprint=model_fingerprint,
        analysis_spec_fingerprint=analysis_fingerprint,
        analysis_sha256=computed_hashes["analysisSha256"],
        response_plan_sha256=computed_hashes["responsePlanSha256"],
        readiness_sha256=computed_hashes["readinessSha256"],
        external_artifacts=external_artifacts,
        unit_conversions=unit_conversions,
    )
    if render_fingerprint != manifest["analysisRenderFingerprint"]:
        raise _fingerprint_error(
            "Generated-analysis render fingerprint differs from deterministic recomputation"
        )

    return {
        "schema": VERIFICATION_SCHEMA_V2,
        "status": "VERIFIED",
        "executionMode": execution_mode,
        "analysisRenderFingerprint": render_fingerprint,
        "modelSpecFingerprint": model_fingerprint,
        "analysisSpecFingerprint": analysis_fingerprint,
        "analysisManifestSha256": _sha256_bytes(manifest_file.read_bytes()),
        "readiness": readiness,
        "responseContext": response_context,
        "normalizedModelSpec": normalized_model,
        "normalizedAnalysisSpec": normalized_analysis,
        "externalArtifacts": external_artifacts,
        "unitConversions": unit_conversions,
        "artifacts": {
            "analysisPath": workspace_relative_path(workspace, model_file),
            "analysisSha256": computed_hashes["analysisSha256"],
            "responsePlanPath": workspace_relative_path(workspace, response_plan_file),
            "responsePlanSha256": computed_hashes["responsePlanSha256"],
            "readinessPath": workspace_relative_path(workspace, readiness_file),
            "readinessSha256": computed_hashes["readinessSha256"],
            "manifestPath": workspace_relative_path(workspace, manifest_file),
        },
    }


def verify_generated_analysis_bundle(
    workspace: Path,
    *,
    model_path: str,
    response_plan_path: str,
    manifest_path: str,
) -> dict[str, Any]:
    model_file = resolve_workspace_file(workspace, model_path)
    response_plan_file = resolve_workspace_file(workspace, response_plan_path)
    manifest_file = resolve_workspace_file(workspace, manifest_path)
    manifest = _load_json_object(manifest_file, label="manifest")
    if manifest.get("schema") == renderer_v1.RENDER_SCHEMA:
        return _verify_v1_generated_analysis_bundle(
            workspace,
            model_file=model_file,
            response_plan_file=response_plan_file,
            manifest_file=manifest_file,
            manifest=manifest,
        )
    if manifest.get("schema") == renderer_v2.RENDER_SCHEMA_V2:
        return _verify_v2_generated_analysis_bundle(
            workspace,
            model_file=model_file,
            response_plan_file=response_plan_file,
            manifest_file=manifest_file,
            manifest=manifest,
        )
    raise _manifest_error("Generated-analysis manifest schema is unsupported")


__all__ = [
    "VERIFICATION_SCHEMA",
    "VERIFICATION_SCHEMA_V2",
    "verify_generated_analysis_bundle",
]
