from __future__ import annotations

import copy
import hashlib
import json
import math
from collections.abc import Callable
from pathlib import Path
from typing import Any
from uuid import uuid4

from fem_core import result_intelligence_legacy as _result_legacy
from fem_core.analysis_requirements import complete_engineering_analysis_requirement
from fem_core.analysis_spec import evaluate_engineering_analysis_readiness, render_opensees_analysis
from fem_core.errors import FemCoreError
from fem_core.model_inspection import inspect_model
from fem_core.model_spec import (
    render_ansys_frame_2d,
    validate_engineering_model_spec,
)
from fem_core.pathing import resolve_workspace_file, workspace_relative_path
from fem_core.result_intelligence import inspect_result, query_result
from fem_core.solvers import get_solver_adapter

WORKFLOW_SCHEMA = "FEMAGENT_EARTHQUAKE_WORKFLOW_V1"
WORKFLOW_PREPARATION_SCHEMA = "FEMAGENT_EARTHQUAKE_WORKFLOW_PREPARATION_V1"
WORKFLOW_SUMMARY_SCHEMA = "FEMAGENT_EARTHQUAKE_WORKFLOW_SUMMARY_V1"


def _canonical_sha256(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        ).encode("utf-8")
    ).hexdigest()


def _file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _new_workflow_id() -> str:
    return f"eqwf_{uuid4().hex[:16]}"


def _base_prepare_report(
    *,
    solver: str,
    completion: dict[str, Any],
) -> dict[str, Any]:
    return {
        "schema": WORKFLOW_PREPARATION_SCHEMA,
        "status": "NEEDS_INPUT",
        "solver": solver,
        "analysisCompletion": completion,
        "analysisReadiness": None,
        "render": None,
        "modelInspection": None,
        "preflight": None,
        "solverRunRequest": None,
        "workflowManifest": None,
        "warnings": [],
    }


def _positive_excited_mass(
    normalized_model: dict[str, Any],
    component: str,
) -> dict[str, Any]:
    field = "mUX" if component == "X" else "mUY"
    positive_nodes = sorted(
        int(item["nodeId"])
        for item in normalized_model["nodalMasses"]
        if isinstance(item, dict)
        and isinstance(item.get("nodeId"), int)
        and isinstance(item.get(field), (int, float))
        and not isinstance(item.get(field), bool)
        and math.isfinite(float(item[field]))
        and float(item[field]) > 0.0
    )
    return {
        "status": "PASS" if positive_nodes else "FAIL",
        "component": component,
        "massField": field,
        "positiveMassNodeIds": positive_nodes,
    }


def _workflow_artifact_root(workspace: Path, workflow_id: str) -> Path:
    root = workspace.resolve()
    path = (root / ".femagent" / "workflows" / workflow_id).resolve()
    try:
        path.relative_to(root)
    except ValueError as exc:
        raise FemCoreError(
            "EARTHQUAKE_WORKFLOW_WRITE_FAILED",
            "Workflow artifact path resolves outside the active workspace",
        ) from exc
    return path


def _write_workflow_manifest(
    workspace: Path,
    manifest: dict[str, Any],
) -> dict[str, str]:
    workflow_id = str(manifest["workflowId"])
    directory = _workflow_artifact_root(workspace, workflow_id)
    try:
        directory.mkdir(parents=True, exist_ok=False)
        path = directory / "workflow_manifest.json"
        path.write_text(
            json.dumps(manifest, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
    except OSError as exc:
        raise FemCoreError(
            "EARTHQUAKE_WORKFLOW_WRITE_FAILED",
            "Unable to publish the earthquake workflow manifest",
            details={"workflowId": workflow_id},
        ) from exc
    return {
        "path": workspace_relative_path(workspace, path),
        "sha256": _file_sha256(path),
    }


def _postprocess_plan(analysis_spec: dict[str, Any]) -> list[dict[str, Any]]:
    plan: list[dict[str, Any]] = []
    for request in analysis_spec["resultRequests"]:
        plan.append(
            {
                "requestId": str(request["requestId"]),
                "query": {
                    "quantity": request["quantity"],
                    "target": copy.deepcopy(request["target"]),
                    "component": request["component"],
                    "operation": "SUMMARY",
                },
            }
        )
    return plan


def _normalize_solver(solver: str) -> str:
    normalized = solver.strip().lower()
    if normalized in {"opensees", "openseespy"}:
        return "opensees"
    if normalized in {"ansys", "mapdl", "ansys-mapdl"}:
        return "ansys"
    raise FemCoreError(
        "EARTHQUAKE_WORKFLOW_UNSUPPORTED_SOLVER",
        "PR31 supports OpenSeesPy or ANSYS MAPDL only",
        details={"solver": solver},
    )


def _open_sees_prepare(
    workspace: Path,
    *,
    report: dict[str, Any],
    model_spec: dict[str, Any],
    analysis_spec: dict[str, Any],
    adapter_factory: Callable[[str], Any],
) -> dict[str, Any]:
    readiness = evaluate_engineering_analysis_readiness(
        model_spec,
        analysis_spec,
        workspace=workspace,
    )
    report["analysisReadiness"] = readiness
    if readiness.get("status") != "READY":
        report["status"] = "ANALYSIS_NOT_READY"
        return report

    model_validation = validate_engineering_model_spec(model_spec)
    normalized_model = model_validation.get("normalizedSpec")
    if not isinstance(normalized_model, dict):
        report["status"] = "ANALYSIS_NOT_READY"
        return report

    component = str(analysis_spec["definition"]["excitation"]["component"])
    mass_check = _positive_excited_mass(normalized_model, component)
    readiness.setdefault("checks", {})["workflowExcitedMass"] = mass_check
    if mass_check["status"] != "PASS":
        issue = {
            "severity": "ERROR",
            "code": "EARTHQUAKE_WORKFLOW_OPENSEES_EXCITED_MASS_UNPROVEN",
            "path": "modelSpec.nodalMasses",
            "message": (
                f"Generated OpenSees uniform-base execution requires at least one positive "
                f"{mass_check['massField']} nodal mass in the excited {component} direction"
            ),
        }
        readiness.setdefault("issues", []).append(issue)
        readiness["status"] = "NOT_READY"
        report["status"] = "ANALYSIS_NOT_READY"
        return report

    rendered = render_opensees_analysis(workspace, model_spec, analysis_spec)
    report["render"] = rendered
    if rendered.get("status") != "RENDERED":
        report["status"] = "ANALYSIS_NOT_READY"
        return report

    artifacts = rendered["artifacts"]
    solver_options = {
        "responsePlanPath": artifacts["responsePlanPath"],
        "analysisManifestPath": artifacts["manifestPath"],
    }
    request = {
        "solver": "opensees",
        "modelPath": artifacts["analysisPath"],
        "solverOptions": solver_options,
    }
    adapter = adapter_factory("opensees")
    preflight = adapter.preflight(
        workspace,
        model_path=request["modelPath"],
        load_path=None,
        solver_options=solver_options,
    )
    report["preflight"] = preflight
    if preflight.get("status") != "READY":
        report["status"] = "PREFLIGHT_BLOCKED"
        return report

    return _freeze_ready_workflow(
        workspace,
        report=report,
        model_spec=model_spec,
        analysis_spec=analysis_spec,
        solver_run_request=request,
        solver_binding={
            "mode": "GENERATED_OPENSEES_ANALYSIS",
            "analysisRenderFingerprint": rendered["analysisRenderFingerprint"],
            "analysisManifestPath": artifacts["manifestPath"],
            "analysisManifestSha256": artifacts.get("manifestSha256"),
        },
    )


def _ansys_prepare(
    workspace: Path,
    *,
    report: dict[str, Any],
    model_spec: dict[str, Any],
    analysis_spec: dict[str, Any],
    solver_model_path: str | None,
    adapter_factory: Callable[[str], Any],
) -> dict[str, Any]:
    model_validation = validate_engineering_model_spec(model_spec)
    normalized_model = model_validation.get("normalizedSpec")
    if not isinstance(normalized_model, dict):
        report["status"] = "PREFLIGHT_BLOCKED"
        return report

    render_manifest_path: str | None = None
    generated_from_model_spec = (
        not isinstance(solver_model_path, str) or not solver_model_path.strip()
    )
    if generated_from_model_spec:
        component = str(analysis_spec["definition"]["excitation"]["component"])
        mass_check = _positive_excited_mass(normalized_model, component)
        if mass_check["status"] != "PASS":
            report["analysisReadiness"] = {
                "status": "NOT_READY",
                "checks": {"workflowExcitedMass": mass_check},
                "issues": [
                    {
                        "severity": "ERROR",
                        "code": "EARTHQUAKE_WORKFLOW_ANSYS_EXCITED_MASS_UNPROVEN",
                        "path": "modelSpec.nodalMasses",
                        "message": (
                            "Generated ANSYS uniform-base execution requires at least "
                            f"one positive {mass_check['massField']} nodal mass in the "
                            f"excited {component} direction"
                        ),
                    }
                ],
            }
            report["status"] = "ANALYSIS_NOT_READY"
            return report

        rendered = render_ansys_frame_2d(workspace, model_spec)
        report["render"] = rendered
        if rendered.get("status") != "RENDERED":
            report["status"] = "ANALYSIS_NOT_READY"
            return report
        artifacts = rendered["artifacts"]
        solver_model_path = str(artifacts["modelPath"])
        render_manifest_path = str(artifacts["manifestPath"])

    assert isinstance(solver_model_path, str)
    inspection = inspect_model(workspace, solver_model_path)
    report["modelInspection"] = inspection
    if inspection.get("format") != "ANSYS_APDL_TEXT":
        report["status"] = "PREFLIGHT_BLOCKED"
        report["warnings"].append(
            {
                "code": "EARTHQUAKE_WORKFLOW_ANSYS_MODEL_MISMATCH",
                "message": "ANSYS workflow requires an ANSYS APDL Model Bundle",
            }
        )
        return report
    bundle = inspection.get("bundle")
    bundle_fingerprint = (
        bundle.get("bundleFingerprint") if isinstance(bundle, dict) else None
    )
    if (
        not isinstance(bundle, dict)
        or bundle.get("integrity") != "VALID"
        or not isinstance(bundle_fingerprint, str)
        or len(bundle_fingerprint) != 64
    ):
        report["status"] = "PREFLIGHT_BLOCKED"
        report["warnings"].append(
            {
                "code": "EARTHQUAKE_WORKFLOW_ANSYS_BUNDLE_INVALID",
                "message": "ANSYS workflow requires a valid exact Model Bundle fingerprint",
            }
        )
        return report

    model_units = {
        "length": normalized_model["units"]["length"],
        "time": normalized_model["units"]["time"],
    }
    ansys_v2_options: dict[str, Any] = {
        "analysisSpec": copy.deepcopy(analysis_spec),
        "confirmedBundleFingerprint": bundle_fingerprint,
    }
    if render_manifest_path is not None:
        ansys_v2_options["renderManifestPath"] = render_manifest_path
    solver_options = {
        "modelUnits": model_units,
        "ansysV2": ansys_v2_options,
    }
    request = {
        "solver": "ansys",
        "modelPath": solver_model_path,
        "solverOptions": solver_options,
    }
    adapter = adapter_factory("ansys")
    preflight = adapter.preflight(
        workspace,
        model_path=solver_model_path,
        load_path=None,
        solver_options=solver_options,
    )
    report["preflight"] = preflight
    if preflight.get("status") != "READY":
        report["status"] = "PREFLIGHT_BLOCKED"
        return report

    admission = preflight.get("analysisAdmission")
    if not isinstance(admission, dict) or admission.get("status") != "ADMITTED":
        report["status"] = "PREFLIGHT_BLOCKED"
        report["warnings"].append(
            {
                "code": "EARTHQUAKE_WORKFLOW_ANSYS_ADMISSION_MISSING",
                "message": "READY ANSYS preflight did not expose the expected V2 admission record",
            }
        )
        return report

    binding = admission.get("binding")
    if not isinstance(binding, dict):
        report["status"] = "PREFLIGHT_BLOCKED"
        report["warnings"].append(
            {
                "code": "EARTHQUAKE_WORKFLOW_ANSYS_ADMISSION_BINDING_MISSING",
                "message": "ANSYS admission did not expose a deterministic binding record",
            }
        )
        return report

    if binding.get("semanticEquivalence") == "NOT_MACHINE_PROVEN":
        report["warnings"].append(
            {
                "code": "EARTHQUAKE_WORKFLOW_ANSYS_SEMANTIC_EQUIVALENCE_NOT_PROVEN",
                "message": (
                    "ANSYS execution is bound to exact APDL bundle bytes; semantic "
                    "equivalence to the AnalysisSpec ModelSpec fingerprint is not "
                    "machine-proven"
                ),
            }
        )

    solver_binding = {
        "mode": (
            "DETERMINISTIC_ANSYS_MODEL_RENDER"
            if binding.get("mode") == "DETERMINISTIC_MODEL_SPEC_RENDER"
            else "EXPLICIT_ANSYS_BUNDLE_BINDING"
        ),
        "bundleFingerprint": bundle_fingerprint,
        "targetIdPolicy": binding.get("targetIdPolicy"),
        "semanticEquivalence": binding.get("semanticEquivalence"),
        "executionIntentFingerprint": admission.get("executionIntentFingerprint"),
    }
    if binding.get("mode") == "DETERMINISTIC_MODEL_SPEC_RENDER":
        solver_binding.update(
            {
                "renderManifestPath": binding.get("renderManifestPath"),
                "renderFingerprint": binding.get("renderFingerprint"),
                "renderer": copy.deepcopy(binding.get("renderer")),
            }
        )

    return _freeze_ready_workflow(
        workspace,
        report=report,
        model_spec=model_spec,
        analysis_spec=analysis_spec,
        solver_run_request=request,
        solver_binding=solver_binding,
    )


def _freeze_ready_workflow(
    workspace: Path,
    *,
    report: dict[str, Any],
    model_spec: dict[str, Any],
    analysis_spec: dict[str, Any],
    solver_run_request: dict[str, Any],
    solver_binding: dict[str, Any],
) -> dict[str, Any]:
    model_validation = validate_engineering_model_spec(model_spec)
    model_fingerprint = model_validation.get("modelSpecFingerprint")
    completion = report["analysisCompletion"]
    analysis_fingerprint = completion.get("analysisSpecFingerprint")
    load = completion.get("context", {}).get("loadArtifact")
    if (
        not isinstance(model_fingerprint, str)
        or not isinstance(analysis_fingerprint, str)
        or not isinstance(load, dict)
    ):
        raise FemCoreError(
            "EARTHQUAKE_WORKFLOW_INTERNAL_INVARIANT",
            "READY workflow lacks deterministic model, analysis, or load identity",
        )

    frozen_request = copy.deepcopy(solver_run_request)
    workflow_payload = {
        "solver": report["solver"],
        "modelSpecFingerprint": model_fingerprint,
        "analysisSpecFingerprint": analysis_fingerprint,
        "loadArtifactSha256": load.get("sha256"),
        "solverRunRequest": frozen_request,
        "solverBinding": solver_binding,
    }
    workflow_fingerprint = _canonical_sha256(workflow_payload)
    workflow_id = _new_workflow_id()
    manifest = {
        "schema": WORKFLOW_SCHEMA,
        "status": "READY_FOR_CONFIRMATION",
        "workflowId": workflow_id,
        "workflowFingerprint": workflow_fingerprint,
        "solver": report["solver"],
        "modelSpecFingerprint": model_fingerprint,
        "analysisSpecFingerprint": analysis_fingerprint,
        "analysisSpec": copy.deepcopy(analysis_spec),
        "loadArtifact": copy.deepcopy(load),
        "solverBinding": copy.deepcopy(solver_binding),
        "solverRunRequest": frozen_request,
        "preflight": copy.deepcopy(report["preflight"]),
        "postprocessPlan": _postprocess_plan(analysis_spec),
        "limitations": copy.deepcopy(report["warnings"]),
    }
    manifest_ref = _write_workflow_manifest(workspace, manifest)
    report["status"] = "READY_FOR_CONFIRMATION"
    report["solverRunRequest"] = frozen_request
    report["workflowManifest"] = manifest_ref
    return report


def prepare_earthquake_workflow(
    workspace: Path,
    *,
    solver: str,
    draft: dict[str, Any],
    model_spec: dict[str, Any],
    load_artifact_path: str,
    semantic_context: dict[str, Any] | None = None,
    solver_model_path: str | None = None,
    solver_adapter_factory: Callable[[str], Any] | None = None,
) -> dict[str, Any]:
    normalized_solver = _normalize_solver(solver)
    completion = complete_engineering_analysis_requirement(
        workspace,
        draft=draft,
        model_spec=model_spec,
        load_artifact_path=load_artifact_path,
        semantic_context=semantic_context,
    )
    report = _base_prepare_report(
        solver=normalized_solver,
        completion=completion,
    )
    if completion.get("status") != "COMPLETE":
        return report

    analysis_spec = completion.get("candidateAnalysisSpec")
    if not isinstance(analysis_spec, dict):
        raise FemCoreError(
            "EARTHQUAKE_WORKFLOW_INTERNAL_INVARIANT",
            "COMPLETE PR30 result did not provide a candidate AnalysisSpec",
        )
    adapter_factory = solver_adapter_factory or get_solver_adapter
    if normalized_solver == "opensees":
        return _open_sees_prepare(
            workspace,
            report=report,
            model_spec=model_spec,
            analysis_spec=analysis_spec,
            adapter_factory=adapter_factory,
        )
    return _ansys_prepare(
        workspace,
        report=report,
        model_spec=model_spec,
        analysis_spec=analysis_spec,
        solver_model_path=solver_model_path,
        adapter_factory=adapter_factory,
    )


def _load_workflow_manifest(
    workspace: Path,
    *,
    manifest_path: str,
    declared_sha256: str,
) -> tuple[Path, dict[str, Any]]:
    path = resolve_workspace_file(workspace, manifest_path)
    actual_sha = _file_sha256(path)
    if actual_sha != declared_sha256:
        raise FemCoreError(
            "EARTHQUAKE_WORKFLOW_MANIFEST_HASH_MISMATCH",
            "Workflow manifest SHA-256 does not match the prepared workflow reference",
            details={"expected": declared_sha256, "actual": actual_sha},
        )
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise FemCoreError(
            "EARTHQUAKE_WORKFLOW_MANIFEST_INVALID",
            "Workflow manifest must be valid UTF-8 JSON",
        ) from exc
    if (
        not isinstance(payload, dict)
        or payload.get("schema") != WORKFLOW_SCHEMA
        or payload.get("status") != "READY_FOR_CONFIRMATION"
        or not isinstance(payload.get("workflowId"), str)
        or not isinstance(payload.get("analysisSpecFingerprint"), str)
        or not isinstance(payload.get("modelSpecFingerprint"), str)
        or not isinstance(payload.get("postprocessPlan"), list)
    ):
        raise FemCoreError(
            "EARTHQUAKE_WORKFLOW_MANIFEST_INVALID",
            "Workflow manifest does not satisfy the PR31 READY contract",
        )
    return path, payload


def _bind_run_to_workflow(
    workflow: dict[str, Any],
    run_manifest: dict[str, Any],
) -> None:
    expected_solver = "OPENSEESPY" if workflow["solver"] == "opensees" else "ANSYS"
    run_solver = str(run_manifest.get("solver", {}).get("name") or "").upper()
    if run_solver != expected_solver:
        raise FemCoreError(
            "EARTHQUAKE_WORKFLOW_RUN_SOLVER_MISMATCH",
            "Completed run solver does not match the prepared earthquake workflow",
            details={"expected": expected_solver, "received": run_solver},
        )

    expected_analysis = str(workflow["analysisSpecFingerprint"])
    if workflow["solver"] == "opensees":
        generated = run_manifest.get("generatedAnalysis")
        received_analysis = (
            generated.get("analysisSpecFingerprint")
            if isinstance(generated, dict)
            else None
        )
        received_model = (
            generated.get("modelSpecFingerprint")
            if isinstance(generated, dict)
            else None
        )
        expected_render = workflow.get("solverBinding", {}).get(
            "analysisRenderFingerprint"
        )
        received_render = (
            generated.get("analysisRenderFingerprint")
            if isinstance(generated, dict)
            else None
        )
        if received_model != workflow["modelSpecFingerprint"]:
            raise FemCoreError(
                "EARTHQUAKE_WORKFLOW_RUN_MODEL_MISMATCH",
                "OpenSees run ModelSpec fingerprint does not match the workflow",
            )
        if received_render != expected_render:
            raise FemCoreError(
                "EARTHQUAKE_WORKFLOW_RUN_RENDER_MISMATCH",
                "OpenSees run generated-analysis identity does not match the workflow",
            )
    else:
        analysis = run_manifest.get("analysis")
        received_analysis = (
            analysis.get("analysisSpecFingerprint")
            if isinstance(analysis, dict)
            else None
        )
        received_model = (
            analysis.get("declaredModelSpecFingerprint")
            if isinstance(analysis, dict)
            else None
        )
        expected_bundle = workflow.get("solverBinding", {}).get(
            "bundleFingerprint"
        )
        received_bundle = run_manifest.get("model", {}).get(
            "bundleFingerprint"
        )
        if received_model != workflow["modelSpecFingerprint"]:
            raise FemCoreError(
                "EARTHQUAKE_WORKFLOW_RUN_MODEL_MISMATCH",
                "ANSYS run declared ModelSpec fingerprint does not match the workflow",
            )
        if received_bundle != expected_bundle:
            raise FemCoreError(
                "EARTHQUAKE_WORKFLOW_RUN_BUNDLE_MISMATCH",
                "ANSYS run Model Bundle fingerprint does not match the workflow",
            )
    if received_analysis != expected_analysis:
        raise FemCoreError(
            "EARTHQUAKE_WORKFLOW_RUN_ANALYSIS_MISMATCH",
            "Completed run AnalysisSpec fingerprint does not match the prepared workflow",
            details={
                "expected": expected_analysis,
                "received": received_analysis,
            },
        )


def summarize_earthquake_workflow(
    workspace: Path,
    *,
    workflow_manifest_path: str,
    workflow_manifest_sha256: str,
    run_ref: str,
) -> dict[str, Any]:
    manifest_path, workflow = _load_workflow_manifest(
        workspace,
        manifest_path=workflow_manifest_path,
        declared_sha256=workflow_manifest_sha256,
    )
    run_manifest_path, run_manifest = _result_legacy._load_run_manifest(
        workspace,
        run_ref,
    )
    _bind_run_to_workflow(workflow, run_manifest)

    inspection = inspect_result(workspace, run_ref)
    integrity = inspection.get("integrity", {})
    results: list[dict[str, Any]] = []
    issues: list[dict[str, Any]] = []
    if integrity.get("status") == "VALID":
        for item in workflow["postprocessPlan"]:
            query = copy.deepcopy(item["query"])
            try:
                response = query_result(workspace, run_ref, query)
            except FemCoreError as exc:
                issues.append(
                    {
                        "code": exc.code,
                        "requestId": item["requestId"],
                        "message": exc.message,
                        "details": exc.details,
                    }
                )
                continue
            summary = response.get("summary")
            if not isinstance(summary, dict):
                issues.append(
                    {
                        "code": "EARTHQUAKE_WORKFLOW_RESULT_SUMMARY_UNAVAILABLE",
                        "requestId": item["requestId"],
                        "message": "Result Intelligence did not return a SUMMARY for the planned response",
                    }
                )
                continue
            results.append(
                {
                    "requestId": item["requestId"],
                    "quantity": response.get("quantity"),
                    "target": copy.deepcopy(response.get("target")),
                    "component": response.get("component"),
                    "unit": response.get("unit"),
                    "referenceFrame": response.get("referenceFrame"),
                    "abscissa": copy.deepcopy(response.get("abscissa")),
                    "sampleCount": summary.get("sampleCount"),
                    "min": summary.get("min"),
                    "max": summary.get("max"),
                    "absolutePeak": summary.get("absolutePeak"),
                    "abscissaAtAbsolutePeak": summary.get(
                        "abscissaAtAbsolutePeak"
                    ),
                }
            )
    else:
        issues.append(
            {
                "code": "EARTHQUAKE_WORKFLOW_RESULT_INTEGRITY_NOT_VALID",
                "message": "Result Intelligence did not validate the recorded run artifacts",
                "integrityStatus": integrity.get("status"),
            }
        )

    return {
        "schema": WORKFLOW_SUMMARY_SCHEMA,
        "status": "COMPLETED" if not issues else "LIMITED",
        "workflowId": workflow["workflowId"],
        "workflowFingerprint": workflow["workflowFingerprint"],
        "workflowManifest": {
            "path": workspace_relative_path(workspace, manifest_path),
            "sha256": workflow_manifest_sha256,
        },
        "run": {
            "runId": run_manifest["runId"],
            "caseFingerprint": run_manifest["caseFingerprint"],
            "manifestPath": workspace_relative_path(
                workspace,
                run_manifest_path,
            ),
            "solver": copy.deepcopy(run_manifest["solver"]),
        },
        "analysisSpecFingerprint": workflow["analysisSpecFingerprint"],
        "modelSpecFingerprint": workflow["modelSpecFingerprint"],
        "resultInspection": inspection,
        "engineeringSummary": results,
        "issues": issues,
        "limitations": copy.deepcopy(workflow.get("limitations", [])),
    }


__all__ = [
    "WORKFLOW_PREPARATION_SCHEMA",
    "WORKFLOW_SCHEMA",
    "WORKFLOW_SUMMARY_SCHEMA",
    "prepare_earthquake_workflow",
    "summarize_earthquake_workflow",
]
