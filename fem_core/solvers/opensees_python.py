from __future__ import annotations

import json
import shutil
import subprocess
import sys
from hashlib import sha256
from pathlib import Path
from typing import Any
from uuid import uuid4

from fem_core.errors import FemCoreError
from fem_core.opensees_python_inspection import inspect_opensees_python
from fem_core.opensees_response_plan import (
    load_opensees_response_plan,
    validate_opensees_response_plan_domain,
)
from fem_core.pathing import resolve_workspace_file, workspace_relative_path
from fem_core.solvers.opensees import OpenSeesAdapter
from fem_core.solvers.opensees_generated_analysis import verify_generated_analysis_bundle

_BUILD_TIMEOUT_S = 60.0
_SCRIPT_RUN_TIMEOUT_S = 60.0


def _sha256_file(path: Path) -> str:
    return sha256(path.read_bytes()).hexdigest()


def _solver_options(
    workspace: Path,
    *,
    model_path: str,
    load_path: str | None,
    solver_options: dict[str, Any] | None,
) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    if solver_options is None:
        return None, None
    if not isinstance(solver_options, dict):
        raise FemCoreError("UNSUPPORTED_SOLVER_OPTIONS", "OpenSees solverOptions must be a JSON object")
    unknown = sorted(set(solver_options) - {"responsePlanPath", "analysisManifestPath"})
    if unknown:
        raise FemCoreError(
            "UNSUPPORTED_SOLVER_OPTIONS",
            "OpenSees accepts only responsePlanPath and analysisManifestPath",
            details={"unsupported": unknown},
        )

    response_plan_path = solver_options.get("responsePlanPath")
    manifest_path = solver_options.get("analysisManifestPath")
    if manifest_path is not None:
        if not isinstance(manifest_path, str) or not manifest_path.strip():
            raise FemCoreError(
                "UNSUPPORTED_SOLVER_OPTIONS",
                "OpenSees analysisManifestPath must be a non-empty string when provided",
            )
        if not isinstance(response_plan_path, str) or not response_plan_path.strip():
            raise FemCoreError(
                "UNSUPPORTED_SOLVER_OPTIONS",
                "Generated OpenSees analyses require responsePlanPath from the same render",
            )
        if load_path is not None:
            raise FemCoreError(
                "UNSUPPORTED_SOLVER_OPTIONS",
                "Generated OpenSees analyses embed their approved loads; loadPath must be omitted",
            )
        generated = verify_generated_analysis_bundle(
            workspace,
            model_path=model_path,
            response_plan_path=response_plan_path,
            manifest_path=manifest_path,
        )
        return None, generated

    if not isinstance(response_plan_path, str) or not response_plan_path.strip():
        raise FemCoreError(
            "UNSUPPORTED_SOLVER_OPTIONS",
            "OpenSees responsePlanPath must be a non-empty string",
        )
    return load_opensees_response_plan(workspace, response_plan_path), None


def _generated_summary(generated: dict[str, Any] | None) -> dict[str, Any] | None:
    if generated is None:
        return None
    return {
        "status": generated["status"],
        "analysisRenderFingerprint": generated["analysisRenderFingerprint"],
        "modelSpecFingerprint": generated["modelSpecFingerprint"],
        "analysisSpecFingerprint": generated["analysisSpecFingerprint"],
        "analysisManifestSha256": generated["analysisManifestSha256"],
    }


def _validate_generated_build_domain(
    generated: dict[str, Any],
    build: dict[str, Any],
) -> None:
    normalized_model = generated["normalizedModelSpec"]
    expected_nodes = sorted(int(node["id"]) for node in normalized_model["nodes"])
    expected_elements = sorted(int(element["id"]) for element in normalized_model["elements"])
    actual_nodes = sorted(int(tag) for tag in build["nodeTags"])
    actual_elements = sorted(int(tag) for tag in build["elementTags"])
    if actual_nodes != expected_nodes or actual_elements != expected_elements:
        raise FemCoreError(
            "GENERATED_ANALYSIS_MODEL_DOMAIN_MISMATCH",
            "Built OpenSees model domain differs from the verified embedded ModelSpec",
            details={
                "expectedNodeTags": expected_nodes,
                "actualNodeTags": actual_nodes,
                "expectedElementTags": expected_elements,
                "actualElementTags": actual_elements,
            },
        )


def _verified_worker_mode(generated: dict[str, Any] | None) -> str:
    if generated is None:
        return "script-run"
    execution_mode = generated.get("executionMode")
    if execution_mode is None:
        return "script-run"
    if execution_mode == "SCRIPT":
        return "script-run"
    if execution_mode == "MODAL":
        return "modal-run"
    raise FemCoreError(
        "GENERATED_ANALYSIS_EXECUTION_MODE_INVALID",
        "Generated-analysis verifier returned an unsupported execution mode",
        details={"executionMode": execution_mode},
    )


class OpenSeesBundleAdapter(OpenSeesAdapter):
    """OpenSees adapter extended with safe Python bundles and controlled response plans."""

    def status(self) -> dict[str, Any]:
        report = super().status()
        if report["available"]:
            report["capabilities"] = [
                *report["capabilities"],
                "PYTHON_MODEL_BUNDLE",
                "BUILD_ONLY_INSPECTION",
                "STRUCTURAL_RESPONSE_PLAN_V1",
                "GENERATED_ANALYSIS_VERIFICATION_V1",
                "GENERATED_ANALYSIS_VERIFICATION_V2",
            ]
        return report

    def build_inspect(self, workspace: Path, *, model_path: str) -> dict[str, Any]:
        model_file = resolve_workspace_file(workspace, model_path)
        if model_file.suffix.lower() != ".py":
            raise FemCoreError(
                "BUILD_INSPECTION_NOT_REQUIRED",
                "OpenSees build inspection currently applies to Python model entrypoints",
                details={"path": model_path},
            )

        static = inspect_opensees_python(workspace, model_path)
        if static["classification"] in {"UNSAFE", "NOT_OPENSEES_MODEL"}:
            raise FemCoreError(
                "MODEL_NOT_SAFE_TO_BUILD",
                "OpenSees Python model did not pass static safety/model classification",
                details={
                    "classification": static["classification"],
                    "executionEligibility": static["executionEligibility"],
                    "safetyFindings": static["safetyFindings"],
                },
            )
        if static["bundle"]["integrity"] != "VALID":
            raise FemCoreError(
                "MODEL_BUNDLE_BLOCKED",
                "OpenSees Python model bundle contains blocked dependencies",
                details={"bundle": static["bundle"]},
            )
        if not self.status()["available"]:
            raise FemCoreError("SOLVER_UNAVAILABLE", "OpenSeesPy is not available for build inspection")

        inspection_id = f"build_{uuid4().hex[:16]}"
        inspection_dir = (
            workspace.resolve() / ".femagent" / "build-inspections" / inspection_id
        ).resolve()
        inspection_dir.mkdir(parents=True, exist_ok=False)
        result_path = inspection_dir / "worker_result.json"
        log_path = inspection_dir / "solver.log"
        command = [
            sys.executable,
            "-m",
            "fem_core.solvers.opensees_worker",
            "--mode",
            "build-inspect",
            "--model",
            str(model_file),
            "--result",
            str(result_path),
        ]
        try:
            completed = subprocess.run(
                command,
                cwd=workspace,
                capture_output=True,
                text=True,
                timeout=_BUILD_TIMEOUT_S,
                check=False,
            )
        except subprocess.TimeoutExpired as exc:
            raise FemCoreError(
                "SOLVER_BUILD_TIMEOUT",
                "OpenSees build-only inspection exceeded its timeout",
                details={"timeoutS": _BUILD_TIMEOUT_S, "inspectionId": inspection_id},
            ) from exc

        log_path.write_text(
            "[stdout]\n" + completed.stdout + "\n[stderr]\n" + completed.stderr,
            encoding="utf-8",
        )
        if completed.returncode != 0 or not result_path.is_file():
            raise FemCoreError(
                "OPENSEES_BUILD_WORKER_FAILED",
                "The isolated OpenSees build-inspection worker failed",
                details={
                    "inspectionId": inspection_id,
                    "returnCode": completed.returncode,
                    "logPath": workspace_relative_path(workspace, log_path),
                },
            )
        try:
            result = json.loads(result_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise FemCoreError(
                "INVALID_SOLVER_BUILD_RESULT",
                "OpenSees build worker returned invalid JSON",
                details={"inspectionId": inspection_id},
            ) from exc
        if not isinstance(result, dict) or result.get("status") != "COMPLETED":
            raise FemCoreError(
                "INVALID_SOLVER_BUILD_RESULT",
                "OpenSees build worker did not complete successfully",
                details={"inspectionId": inspection_id, "result": result},
            )
        return {
            "schemaVersion": "1.0",
            "kind": "solver_build_inspection",
            "solver": "OPENSEESPY",
            "inspectionId": inspection_id,
            "entrypoint": static["source"],
            "bundle": static["bundle"],
            "analysisAdvanced": bool(result.get("analysisAdvanced")),
            "interceptedAnalyzeCalls": int(result.get("interceptedAnalyzeCalls") or 0),
            "interceptedEigenCalls": int(result.get("interceptedEigenCalls") or 0),
            "nodeTags": [int(tag) for tag in result.get("nodeTags", [])],
            "elementTags": [int(tag) for tag in result.get("elementTags", [])],
            "elementTypes": {
                str(key): str(value) for key, value in dict(result.get("elementTypes") or {}).items()
            },
            "nodeCoordinates": dict(result.get("nodeCoordinates") or {}),
            "analysisTime": float(result.get("analysisTime") or 0.0),
            "packageVersion": result.get("packageVersion"),
            "engineVersion": result.get("engineVersion"),
            "logPath": workspace_relative_path(workspace, log_path),
        }

    def preflight(
        self,
        workspace: Path,
        *,
        model_path: str,
        load_path: str | None = None,
        solver_options: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        model_file = resolve_workspace_file(workspace, model_path)
        response_plan, generated = _solver_options(
            workspace,
            model_path=model_path,
            load_path=load_path,
            solver_options=solver_options,
        )
        if model_file.suffix.lower() != ".py":
            if generated is not None:
                raise FemCoreError(
                    "UNSUPPORTED_SOLVER_OPTIONS",
                    "Generated-analysis manifests apply only to OpenSees Python entrypoints",
                )
            if response_plan is not None:
                raise FemCoreError(
                    "STRUCTURAL_RESPONSE_MAPPING_UNAVAILABLE",
                    "PR15 Structural Response Plans apply only to OpenSees Python model bundles",
                )
            if not load_path:
                raise FemCoreError(
                    "LOAD_REQUIRED",
                    "Controlled OpenSees JSON models require a canonical external load",
                )
            return super().preflight(workspace, model_path=model_path, load_path=load_path)

        static = inspect_opensees_python(workspace, model_path)
        status = self.status()
        model_safe = static["classification"] not in {"UNSAFE", "NOT_OPENSEES_MODEL"}
        bundle_valid = static["bundle"]["integrity"] == "VALID"
        build: dict[str, Any] | None = None
        if status["available"] and model_safe and bundle_valid:
            build = self.build_inspect(workspace, model_path=model_path)
            if generated is not None:
                _validate_generated_build_domain(generated, build)
            elif response_plan is not None:
                validate_opensees_response_plan_domain(
                    response_plan,
                    element_types=build["elementTypes"],
                )
        domain_nonempty = bool(build and build["nodeTags"] and build["elementTags"])
        checks = [
            {"code": "SOLVER_AVAILABLE", "status": "PASSED" if status["available"] else "FAILED"},
            {"code": "PYTHON_MODEL_STATIC_SAFETY", "status": "PASSED" if model_safe else "FAILED"},
            {"code": "MODEL_BUNDLE_INTEGRITY", "status": "PASSED" if bundle_valid else "FAILED"},
            {"code": "BUILD_INSPECTION_DOMAIN", "status": "PASSED" if domain_nonempty else "FAILED"},
        ]
        if generated is not None:
            checks.extend(
                [
                    {"code": "GENERATED_ANALYSIS_VERIFIED", "status": "PASSED"},
                    {"code": "GENERATED_ANALYSIS_MODEL_DOMAIN", "status": "PASSED"},
                ]
            )
        elif response_plan is not None:
            checks.append({"code": "STRUCTURAL_RESPONSE_MAPPING", "status": "PASSED"})
        warnings: list[dict[str, Any]] = []
        load: dict[str, Any] = (
            {"mode": "GENERATED_ANALYSIS_EMBEDDED"}
            if generated is not None
            else {"mode": "MODEL_SCRIPT_MANAGED"}
        )
        if load_path:
            load_file = resolve_workspace_file(workspace, load_path)
            load = {
                "mode": "MODEL_SCRIPT_MANAGED",
                "providedPath": workspace_relative_path(workspace, load_file),
                "providedSha256": _sha256_file(load_file),
                "injected": False,
            }
            warnings.append(
                {
                    "code": "EXTERNAL_LOAD_NOT_INJECTED",
                    "message": "OpenSees Python scripts retain their own load/analysis definitions; the provided load is recorded but not injected",
                }
            )

        ready = all(check["status"] == "PASSED" for check in checks)
        response_plan_report: dict[str, Any] | None
        if generated is not None:
            response_plan_report = {
                "mode": "GENERATED_ANALYSIS_VERIFIED",
                "path": generated["artifacts"]["responsePlanPath"],
                "sha256": generated["artifacts"]["responsePlanSha256"],
            }
        else:
            response_plan_report = None if response_plan is None else dict(response_plan["plan"])
        return {
            "schemaVersion": "1.0",
            "kind": "solver_preflight",
            "solver": "OPENSEESPY",
            "status": "READY" if ready else "BLOCKED",
            "checks": checks,
            "warnings": warnings,
            "model": {
                "path": static["source"]["path"],
                "sha256": static["source"]["sha256"],
                "format": "OPENSEES_PYTHON",
                "classification": static["classification"],
                "bundleFingerprint": static["bundle"]["bundleFingerprint"],
                "fileCount": len(static["bundle"]["files"]),
                "buildInspection": None
                if build is None
                else {
                    "inspectionId": build["inspectionId"],
                    "nodeCount": len(build["nodeTags"]),
                    "elementCount": len(build["elementTags"]),
                    "analysisAdvanced": build["analysisAdvanced"],
                    "interceptedAnalyzeCalls": build["interceptedAnalyzeCalls"],
                    "interceptedEigenCalls": build["interceptedEigenCalls"],
                },
            },
            "load": load,
            "responsePlan": response_plan_report,
            "generatedAnalysis": _generated_summary(generated),
            "executionEstimate": {"analysisSteps": None, "mode": "MODEL_SCRIPT"},
        }

    def run(
        self,
        workspace: Path,
        *,
        model_path: str,
        load_path: str | None = None,
        solver_options: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        model_file = resolve_workspace_file(workspace, model_path)
        response_plan, generated = _solver_options(
            workspace,
            model_path=model_path,
            load_path=load_path,
            solver_options=solver_options,
        )
        if model_file.suffix.lower() != ".py":
            if generated is not None:
                raise FemCoreError(
                    "UNSUPPORTED_SOLVER_OPTIONS",
                    "Generated-analysis manifests apply only to OpenSees Python entrypoints",
                )
            if response_plan is not None:
                raise FemCoreError(
                    "STRUCTURAL_RESPONSE_MAPPING_UNAVAILABLE",
                    "PR15 Structural Response Plans apply only to OpenSees Python model bundles",
                )
            if not load_path:
                raise FemCoreError(
                    "LOAD_REQUIRED",
                    "Controlled OpenSees JSON models require a canonical external load",
                )
            return super().run(workspace, model_path=model_path, load_path=load_path)

        preflight = self.preflight(
            workspace,
            model_path=model_path,
            load_path=load_path,
            solver_options=solver_options,
        )
        if preflight["status"] != "READY":
            raise FemCoreError(
                "SOLVER_PREFLIGHT_FAILED",
                "OpenSees Python model cannot run because solver preflight is blocked",
                details={"checks": preflight["checks"]},
            )
        static = inspect_opensees_python(workspace, model_path)
        run_id = f"run_{uuid4().hex[:16]}"
        run_dir = (workspace.resolve() / ".femagent" / "runs" / run_id).resolve()
        run_dir.mkdir(parents=True, exist_ok=False)
        stage_root = run_dir / "model_bundle"
        for file_info in static["bundle"]["files"]:
            source = (workspace.resolve() / str(file_info["path"])).resolve()
            destination = (stage_root / str(file_info["path"])).resolve()
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, destination)
        staged_model = (stage_root / static["source"]["path"]).resolve()

        staged_plan: Path | None = None
        staged_context: Path | None = None
        worker_mode = "script-run"
        if generated is not None:
            generated = verify_generated_analysis_bundle(
                workspace,
                model_path=model_path,
                response_plan_path=generated["artifacts"]["responsePlanPath"],
                manifest_path=generated["artifacts"]["manifestPath"],
            )
            worker_mode = _verified_worker_mode(generated)
            if _sha256_file(staged_model) != generated["artifacts"]["analysisSha256"]:
                raise FemCoreError(
                    "GENERATED_ANALYSIS_ARTIFACT_MISMATCH",
                    "Staged OpenSees analysis differs from the verified generated analysis",
                )
            staged_context = run_dir / "response_context.verified.json"
            staged_context.write_text(
                json.dumps(generated["responseContext"], indent=2, sort_keys=True),
                encoding="utf-8",
            )
        elif response_plan is not None:
            staged_plan = run_dir / "response_plan.normalized.json"
            staged_plan.write_text(
                json.dumps(
                    {
                        "schemaVersion": "1.0",
                        "kind": "structural_response_plan",
                        "channels": response_plan["channels"],
                    },
                    indent=2,
                    sort_keys=True,
                ),
                encoding="utf-8",
            )

        worker_result = run_dir / "worker_result.json"
        solver_log = run_dir / "solver.log"
        command = [
            sys.executable,
            "-m",
            "fem_core.solvers.opensees_worker",
            "--mode",
            worker_mode,
            "--model",
            str(staged_model),
            "--run-dir",
            str(run_dir),
            "--result",
            str(worker_result),
        ]
        if staged_context is not None:
            command.extend(["--response-context", str(staged_context)])
        elif staged_plan is not None:
            command.extend(["--response-plan", str(staged_plan)])
        try:
            completed = subprocess.run(
                command,
                cwd=workspace,
                capture_output=True,
                text=True,
                timeout=_SCRIPT_RUN_TIMEOUT_S,
                check=False,
            )
        except subprocess.TimeoutExpired as exc:
            raise FemCoreError(
                "SOLVER_TIMEOUT",
                "OpenSees Python model worker exceeded the execution timeout",
                details={"timeoutS": _SCRIPT_RUN_TIMEOUT_S, "runId": run_id},
            ) from exc

        solver_log.write_text(
            "[stdout]\n" + completed.stdout + "\n[stderr]\n" + completed.stderr,
            encoding="utf-8",
        )
        worker: dict[str, Any] | None = None
        if worker_result.is_file():
            try:
                loaded = json.loads(worker_result.read_text(encoding="utf-8"))
                worker = loaded if isinstance(loaded, dict) else None
            except (OSError, json.JSONDecodeError):
                worker = None
        if completed.returncode != 0:
            if worker is not None and isinstance(worker.get("code"), str):
                raise FemCoreError(
                    str(worker["code"]),
                    str(worker.get("message") or "OpenSees generated-analysis worker failed"),
                    details={
                        "runId": run_id,
                        "returnCode": completed.returncode,
                        "logPath": workspace_relative_path(workspace, solver_log),
                    },
                )
            raise FemCoreError(
                "OPENSEES_WORKER_FAILED",
                "The isolated OpenSees Python model worker failed",
                details={
                    "runId": run_id,
                    "returnCode": completed.returncode,
                    "logPath": workspace_relative_path(workspace, solver_log),
                },
            )
        if worker is None or worker.get("status") != "COMPLETED":
            raise FemCoreError(
                "INVALID_SOLVER_RESULT",
                "OpenSees Python model worker did not complete successfully",
                details={"runId": run_id, "result": worker},
            )

        result_summary = run_dir / "result_summary.json"
        if not result_summary.is_file():
            raise FemCoreError(
                "INVALID_SOLVER_RESULT",
                "OpenSees Python model worker did not produce result_summary.json",
                details={"runId": run_id},
            )
        structural_response = run_dir / "structural_response.json"
        modal_results = run_dir / "modal_results.json"
        modal_requested = generated is not None and worker_mode == "modal-run"
        structural_requested = response_plan is not None or (
            generated is not None and worker_mode == "script-run"
        )
        if modal_requested and not modal_results.is_file():
            raise FemCoreError(
                "INVALID_SOLVER_RESULT",
                "OpenSees modal run did not produce modal_results.json",
                details={"runId": run_id},
            )
        if structural_requested and not structural_response.is_file():
            raise FemCoreError(
                "INVALID_SOLVER_RESULT",
                "OpenSees response run did not produce structural_response.json",
                details={"runId": run_id},
            )

        load: dict[str, Any] = (
            {"mode": "GENERATED_ANALYSIS_EMBEDDED"}
            if generated is not None
            else {"mode": "MODEL_SCRIPT_MANAGED"}
        )
        load_identity: dict[str, Any] = {"mode": load["mode"]}
        if load_path:
            load_file = resolve_workspace_file(workspace, load_path)
            load = {
                "mode": "MODEL_SCRIPT_MANAGED",
                "providedPath": workspace_relative_path(workspace, load_file),
                "providedSha256": _sha256_file(load_file),
                "injected": False,
            }
            load_identity = {"providedSha256": _sha256_file(load_file), "injected": False}

        response_plan_sha = (
            generated["artifacts"]["responsePlanSha256"]
            if generated is not None
            else response_plan["plan"]["sha256"]
            if response_plan is not None
            else None
        )
        fingerprint_payload = json.dumps(
            {
                "solver": "OPENSEESPY",
                "packageVersion": worker.get("packageVersion"),
                "engineVersion": worker.get("engineVersion"),
                "bundleFingerprint": static["bundle"]["bundleFingerprint"],
                "load": load_identity,
                "analysis": "MODEL_SCRIPT",
                "responsePlanSha256": response_plan_sha,
                "analysisRenderFingerprint": None
                if generated is None
                else generated["analysisRenderFingerprint"],
            },
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        outputs: dict[str, Any] = {
            "runManifest": workspace_relative_path(workspace, run_dir / "run_manifest.json"),
            "resultSummary": workspace_relative_path(workspace, result_summary),
            "resultSummarySha256": _sha256_file(result_summary),
            "solverLog": workspace_relative_path(workspace, solver_log),
            "solverLogSha256": _sha256_file(solver_log),
            "stagedBundleRoot": workspace_relative_path(workspace, stage_root),
        }
        if structural_requested:
            outputs["structuralResponse"] = workspace_relative_path(workspace, structural_response)
            outputs["structuralResponseSha256"] = _sha256_file(structural_response)
        if modal_requested:
            outputs["modalResults"] = workspace_relative_path(workspace, modal_results)
            outputs["modalResultsSha256"] = _sha256_file(modal_results)

        manifest = {
            "schemaVersion": "1.0",
            "kind": "solver_run",
            "runId": run_id,
            "caseFingerprint": sha256(fingerprint_payload).hexdigest(),
            "status": "COMPLETED",
            "solver": {
                "name": "OPENSEESPY",
                "packageVersion": worker.get("packageVersion"),
                "engineVersion": worker.get("engineVersion"),
                "executionMode": "ISOLATED_WORKER_PROCESS",
            },
            "model": {
                "path": static["source"]["path"],
                "sha256": static["source"]["sha256"],
                "format": "OPENSEES_PYTHON",
                "bundleFingerprint": static["bundle"]["bundleFingerprint"],
                "files": static["bundle"]["files"],
            },
            "load": load,
            "responsePlan": (
                {
                    "mode": "GENERATED_ANALYSIS_VERIFIED",
                    "path": generated["artifacts"]["responsePlanPath"],
                    "sha256": generated["artifacts"]["responsePlanSha256"],
                }
                if generated is not None
                else None
                if response_plan is None
                else dict(response_plan["plan"])
            ),
            "generatedAnalysis": _generated_summary(generated),
            "analysis": worker.get("analysis"),
            "summary": worker.get("summary"),
            "outputs": outputs,
        }
        manifest_path = run_dir / "run_manifest.json"
        manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8")
        return manifest
