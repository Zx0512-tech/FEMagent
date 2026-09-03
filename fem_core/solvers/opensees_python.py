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
from fem_core.pathing import resolve_workspace_file, workspace_relative_path
from fem_core.solvers.opensees import OpenSeesAdapter

_BUILD_TIMEOUT_S = 60.0
_SCRIPT_RUN_TIMEOUT_S = 60.0


def _sha256_file(path: Path) -> str:
    return sha256(path.read_bytes()).hexdigest()


class OpenSeesBundleAdapter(OpenSeesAdapter):
    """OpenSees adapter extended with safe bundle inspection for Python entrypoints."""

    def status(self) -> dict[str, Any]:
        report = super().status()
        if report["available"]:
            report["capabilities"] = [
                *report["capabilities"],
                "PYTHON_MODEL_BUNDLE",
                "BUILD_ONLY_INSPECTION",
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
            "nodeTags": [int(tag) for tag in result.get("nodeTags", [])],
            "elementTags": [int(tag) for tag in result.get("elementTags", [])],
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
    ) -> dict[str, Any]:
        model_file = resolve_workspace_file(workspace, model_path)
        if model_file.suffix.lower() != ".py":
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
        domain_nonempty = bool(build and build["nodeTags"] and build["elementTags"])
        checks = [
            {"code": "SOLVER_AVAILABLE", "status": "PASSED" if status["available"] else "FAILED"},
            {"code": "PYTHON_MODEL_STATIC_SAFETY", "status": "PASSED" if model_safe else "FAILED"},
            {"code": "MODEL_BUNDLE_INTEGRITY", "status": "PASSED" if bundle_valid else "FAILED"},
            {"code": "BUILD_INSPECTION_DOMAIN", "status": "PASSED" if domain_nonempty else "FAILED"},
        ]
        warnings: list[dict[str, Any]] = []
        load: dict[str, Any] = {"mode": "MODEL_SCRIPT_MANAGED"}
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
                    "message": "PR6 executes OpenSees Python scripts with their own load/analysis definitions; the provided load is recorded but not injected",
                }
            )

        ready = all(check["status"] == "PASSED" for check in checks)
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
                },
            },
            "load": load,
            "executionEstimate": {"analysisSteps": None, "mode": "MODEL_SCRIPT"},
        }

    def run(
        self,
        workspace: Path,
        *,
        model_path: str,
        load_path: str | None = None,
    ) -> dict[str, Any]:
        model_file = resolve_workspace_file(workspace, model_path)
        if model_file.suffix.lower() != ".py":
            if not load_path:
                raise FemCoreError(
                    "LOAD_REQUIRED",
                    "Controlled OpenSees JSON models require a canonical external load",
                )
            return super().run(workspace, model_path=model_path, load_path=load_path)

        preflight = self.preflight(workspace, model_path=model_path, load_path=load_path)
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
        worker_result = run_dir / "worker_result.json"
        solver_log = run_dir / "solver.log"
        command = [
            sys.executable,
            "-m",
            "fem_core.solvers.opensees_worker",
            "--mode",
            "script-run",
            "--model",
            str(staged_model),
            "--run-dir",
            str(run_dir),
            "--result",
            str(worker_result),
        ]
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
        if completed.returncode != 0 or not worker_result.is_file():
            raise FemCoreError(
                "OPENSEES_WORKER_FAILED",
                "The isolated OpenSees Python model worker failed",
                details={
                    "runId": run_id,
                    "returnCode": completed.returncode,
                    "logPath": workspace_relative_path(workspace, solver_log),
                },
            )
        try:
            worker = json.loads(worker_result.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise FemCoreError(
                "INVALID_SOLVER_RESULT",
                "OpenSees Python model worker returned invalid JSON",
                details={"runId": run_id},
            ) from exc
        if not isinstance(worker, dict) or worker.get("status") != "COMPLETED":
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
        load: dict[str, Any] = {"mode": "MODEL_SCRIPT_MANAGED"}
        load_identity: dict[str, Any] = {"mode": "MODEL_SCRIPT_MANAGED"}
        if load_path:
            load_file = resolve_workspace_file(workspace, load_path)
            load = {
                "mode": "MODEL_SCRIPT_MANAGED",
                "providedPath": workspace_relative_path(workspace, load_file),
                "providedSha256": _sha256_file(load_file),
                "injected": False,
            }
            load_identity = {"providedSha256": _sha256_file(load_file), "injected": False}

        fingerprint_payload = json.dumps(
            {
                "solver": "OPENSEESPY",
                "packageVersion": worker.get("packageVersion"),
                "engineVersion": worker.get("engineVersion"),
                "bundleFingerprint": static["bundle"]["bundleFingerprint"],
                "load": load_identity,
                "analysis": "MODEL_SCRIPT",
            },
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
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
            "analysis": worker.get("analysis"),
            "summary": worker.get("summary"),
            "outputs": {
                "runManifest": workspace_relative_path(workspace, run_dir / "run_manifest.json"),
                "resultSummary": workspace_relative_path(workspace, result_summary),
                "resultSummarySha256": _sha256_file(result_summary),
                "solverLog": workspace_relative_path(workspace, solver_log),
                "solverLogSha256": _sha256_file(solver_log),
                "stagedBundleRoot": workspace_relative_path(workspace, stage_root),
            },
        }
        manifest_path = run_dir / "run_manifest.json"
        manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8")
        return manifest
