from __future__ import annotations

import json
import os
from hashlib import sha256
from pathlib import Path
from typing import Any
from uuid import uuid4

from fem_core.errors import FemCoreError
from fem_core.model_inspection import inspect_model
from fem_core.pathing import resolve_workspace_file, workspace_relative_path
from fem_core.solvers.ansys_runner import (
    run_ansys_process,
    stage_ansys_bundle,
    write_build_only_wrapper,
)
from fem_core.solvers.base import SolverAdapter

_ANSYS_EXECUTABLE_ENV = "FEM_ANSYS_EXECUTABLE"
_ANSYS_BINARY_RESULT_SUFFIXES = (".rst", ".rth", ".rfl", ".rmg")


def _sha256_file(path: Path) -> str:
    return sha256(path.read_bytes()).hexdigest()


def _write_process_log(path: Path, process: dict[str, Any]) -> None:
    path.write_text(
        "[command]\n"
        + " ".join(str(value) for value in process["command"])
        + "\n[stdout]\n"
        + str(process["stdout"])
        + "\n[stderr]\n"
        + str(process["stderr"]),
        encoding="utf-8",
    )


def _load_provenance(workspace: Path, load_path: str | None) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    if not load_path:
        return {"mode": "MODEL_SCRIPT_MANAGED"}, []
    load_file = resolve_workspace_file(workspace, load_path)
    return (
        {
            "mode": "MODEL_SCRIPT_MANAGED",
            "providedPath": workspace_relative_path(workspace, load_file),
            "providedSha256": _sha256_file(load_file),
            "injected": False,
        },
        [
            {
                "code": "EXTERNAL_LOAD_NOT_INJECTED",
                "message": "The provided external load is recorded as provenance only; PR8 has no ANSYS load-injection contract",
            }
        ],
    )


def _find_binary_result(working_directory: Path, jobname: str) -> Path | None:
    for suffix in _ANSYS_BINARY_RESULT_SUFFIXES:
        candidate = (working_directory / f"{jobname}{suffix}").resolve()
        if candidate.is_file():
            return candidate
    return None


class AnsysAdapter(SolverAdapter):
    """ANSYS MAPDL adapter with workspace-bounded Model Bundle execution."""

    name = "ansys"

    def status(self) -> dict[str, Any]:
        configured = os.environ.get(_ANSYS_EXECUTABLE_ENV, "").strip()
        configured_path: Path | None = Path(configured).expanduser().resolve() if configured else None
        if configured_path is None:
            available = False
            reason: str | None = "NOT_CONFIGURED"
        elif not configured_path.is_file():
            available = False
            reason = "CONFIGURED_PATH_NOT_FILE"
        else:
            available = True
            reason = None

        return {
            "schemaVersion": "1.0",
            "kind": "solver_status",
            "solver": "ANSYS",
            "available": available,
            "runtime": "ANSYS_MAPDL",
            "configuredPath": None if configured_path is None else str(configured_path),
            "configuration": {"environmentVariable": _ANSYS_EXECUTABLE_ENV},
            "reason": reason,
            "executionMode": "ISOLATED_PROCESS",
            "capabilities": [
                "APDL_MODEL_BUNDLE",
                "BUILD_ONLY_INSPECTION",
                "STAGED_EXECUTION",
            ],
        }

    def _inspection(self, workspace: Path, model_path: str) -> dict[str, Any]:
        inspection = inspect_model(workspace, model_path)
        if inspection.get("format") != "ANSYS_APDL_TEXT":
            raise FemCoreError(
                "SOLVER_MODEL_MISMATCH",
                "ANSYS SolverAdapter requires an ANSYS APDL/CDB Model Bundle",
                details={"format": inspection.get("format")},
            )
        return inspection

    def build_inspect(self, workspace: Path, *, model_path: str) -> dict[str, Any]:
        inspection = self._inspection(workspace, model_path)
        eligibility = str(inspection["validation"]["executionEligibility"])
        if eligibility in {"REJECTED", "INCOMPLETE"}:
            raise FemCoreError(
                "MODEL_NOT_SAFE_TO_BUILD",
                "ANSYS model did not pass static safety/completeness checks",
                details={"executionEligibility": eligibility},
            )
        if inspection["bundle"]["integrity"] != "VALID":
            raise FemCoreError(
                "MODEL_BUNDLE_BLOCKED",
                "ANSYS Model Bundle contains blocked or unresolved dependencies",
                details={"bundle": inspection["bundle"]},
            )

        status = self.status()
        if not status["available"] or not status["configuredPath"]:
            raise FemCoreError(
                "SOLVER_UNAVAILABLE",
                "ANSYS runtime is unavailable for build-only inspection",
                details={"status": status},
            )

        inspection_id = f"build_{uuid4().hex[:16]}"
        inspection_dir = (workspace.resolve() / ".femagent" / "build-inspections" / inspection_id).resolve()
        inspection_dir.mkdir(parents=True, exist_ok=False)
        staged = stage_ansys_bundle(
            workspace,
            inspection["bundle"],
            inspection_dir / "model_bundle",
            sanitize_for_build=True,
        )
        input_path = write_build_only_wrapper(staged)
        runtime_output = inspection_dir / "ansys_build.out"
        solver_log = inspection_dir / "solver.log"
        process = run_ansys_process(
            Path(str(status["configuredPath"])),
            input_path=input_path,
            output_path=runtime_output,
            cwd=staged["workingDirectory"],
            jobname=f"fem_build_{inspection_id[-8:]}",
        )
        _write_process_log(solver_log, process)
        if process["returnCode"] != 0:
            raise FemCoreError(
                "ANSYS_BUILD_FAILED",
                "ANSYS build-only process returned a nonzero exit code",
                details={
                    "inspectionId": inspection_id,
                    "returnCode": process["returnCode"],
                    "logPath": workspace_relative_path(workspace, solver_log),
                },
            )
        if not runtime_output.is_file():
            raise FemCoreError(
                "ANSYS_BUILD_OUTPUT_MISSING",
                "ANSYS build-only process completed without its requested output file",
                details={"inspectionId": inspection_id},
            )

        return {
            "schemaVersion": "1.0",
            "kind": "solver_build_inspection",
            "solver": "ANSYS",
            "inspectionId": inspection_id,
            "mode": "BUILD_ONLY",
            "status": "COMPLETED",
            "analysisAdvanced": False,
            "bundleFingerprint": inspection["bundle"]["bundleFingerprint"],
            "inputPath": workspace_relative_path(workspace, input_path),
            "runtimeOutput": workspace_relative_path(workspace, runtime_output),
            "runtimeOutputSha256": _sha256_file(runtime_output),
            "logPath": workspace_relative_path(workspace, solver_log),
            "logSha256": _sha256_file(solver_log),
            "stagedBundleRoot": workspace_relative_path(workspace, staged["stageRoot"]),
        }

    def preflight(
        self,
        workspace: Path,
        *,
        model_path: str,
        load_path: str | None = None,
    ) -> dict[str, Any]:
        inspection = self._inspection(workspace, model_path)
        status = self.status()
        eligibility = str(inspection["validation"]["executionEligibility"])
        model_safe = eligibility not in {"REJECTED", "INCOMPLETE"}
        bundle_valid = inspection["bundle"]["integrity"] == "VALID"

        build: dict[str, Any] | None = None
        build_error: dict[str, Any] | None = None
        if status["available"] and model_safe and bundle_valid:
            try:
                build = self.build_inspect(workspace, model_path=model_path)
            except FemCoreError as exc:
                build_error = {"code": exc.code, "message": exc.message, "details": exc.details}

        build_status = (
            "PASSED"
            if build is not None
            else "FAILED"
            if status["available"] and model_safe and bundle_valid
            else "SKIPPED"
        )
        checks = [
            {"code": "SOLVER_AVAILABLE", "status": "PASSED" if status["available"] else "FAILED"},
            {"code": "ANSYS_MODEL_STATIC_SAFETY", "status": "PASSED" if model_safe else "FAILED"},
            {"code": "MODEL_BUNDLE_INTEGRITY", "status": "PASSED" if bundle_valid else "FAILED"},
            {"code": "BUILD_ONLY_INSPECTION", "status": build_status},
        ]
        load, warnings = _load_provenance(workspace, load_path)
        if build_error:
            warnings.append(
                {
                    "code": "BUILD_ONLY_INSPECTION_FAILED",
                    "message": build_error["message"],
                    "details": {"errorCode": build_error["code"], **build_error["details"]},
                }
            )

        ready = all(check["status"] == "PASSED" for check in checks)
        return {
            "schemaVersion": "1.0",
            "kind": "solver_preflight",
            "solver": "ANSYS",
            "status": "READY" if ready else "BLOCKED",
            "checks": checks,
            "warnings": warnings,
            "model": {
                "path": inspection["source"]["path"],
                "sha256": inspection["source"]["sha256"],
                "format": inspection["format"],
                "executionEligibility": eligibility,
                "bundleFingerprint": inspection["bundle"]["bundleFingerprint"],
                "fileCount": len(inspection["bundle"]["files"]),
                "dependencyCount": len(inspection["bundle"]["dependencies"]),
                "buildInspection": build,
            },
            "load": load,
            "executionEstimate": {"mode": "ANSYS_APDL_BUNDLE", "analysisSteps": None},
        }

    def run(
        self,
        workspace: Path,
        *,
        model_path: str,
        load_path: str | None = None,
    ) -> dict[str, Any]:
        preflight = self.preflight(workspace, model_path=model_path, load_path=load_path)
        if preflight["status"] != "READY":
            raise FemCoreError(
                "SOLVER_PREFLIGHT_FAILED",
                "ANSYS execution is blocked because solver preflight did not pass",
                details={"checks": preflight["checks"]},
            )

        inspection = self._inspection(workspace, model_path)
        status = self.status()
        if not status["available"] or not status["configuredPath"]:
            raise FemCoreError("SOLVER_UNAVAILABLE", "ANSYS runtime became unavailable after preflight")

        run_id = f"run_{uuid4().hex[:16]}"
        run_dir = (workspace.resolve() / ".femagent" / "runs" / run_id).resolve()
        run_dir.mkdir(parents=True, exist_ok=False)
        staged = stage_ansys_bundle(
            workspace,
            inspection["bundle"],
            run_dir / "model_bundle",
            sanitize_for_build=False,
        )
        runtime_output = run_dir / "ansys.out"
        solver_log = run_dir / "solver.log"
        jobname = f"fem_{run_id[-8:]}"
        process = run_ansys_process(
            Path(str(status["configuredPath"])),
            input_path=staged["entrypoint"],
            output_path=runtime_output,
            cwd=staged["workingDirectory"],
            jobname=jobname,
        )
        _write_process_log(solver_log, process)
        if process["returnCode"] != 0:
            raise FemCoreError(
                "ANSYS_PROCESS_FAILED",
                "ANSYS process returned a nonzero exit code",
                details={
                    "runId": run_id,
                    "returnCode": process["returnCode"],
                    "logPath": workspace_relative_path(workspace, solver_log),
                },
            )
        if not runtime_output.is_file():
            raise FemCoreError(
                "ANSYS_OUTPUT_MISSING",
                "ANSYS process completed without its requested output file",
                details={"runId": run_id},
            )

        binary_result = _find_binary_result(staged["workingDirectory"], jobname)
        load, _ = _load_provenance(workspace, load_path)
        fingerprint_payload = json.dumps(
            {
                "solver": "ANSYS",
                "runtime": str(status["configuredPath"]),
                "bundleFingerprint": inspection["bundle"]["bundleFingerprint"],
                "load": load,
                "analysis": "MODEL_SCRIPT",
            },
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        manifest_path = run_dir / "run_manifest.json"
        outputs = {
            "runManifest": workspace_relative_path(workspace, manifest_path),
            "runtimeOutput": workspace_relative_path(workspace, runtime_output),
            "runtimeOutputSha256": _sha256_file(runtime_output),
            "solverLog": workspace_relative_path(workspace, solver_log),
            "solverLogSha256": _sha256_file(solver_log),
            "stagedBundleRoot": workspace_relative_path(workspace, staged["stageRoot"]),
        }
        if binary_result is not None:
            outputs["binaryResult"] = workspace_relative_path(workspace, binary_result)
            outputs["binaryResultSha256"] = _sha256_file(binary_result)

        manifest = {
            "schemaVersion": "1.0",
            "kind": "solver_run",
            "runId": run_id,
            "caseFingerprint": sha256(fingerprint_payload).hexdigest(),
            "status": "COMPLETED",
            "solver": {
                "name": "ANSYS",
                "runtime": "ANSYS_MAPDL",
                "configuredPath": str(status["configuredPath"]),
                "executionMode": "ISOLATED_PROCESS",
                "solverOutcome": "NOT_YET_VALIDATED_BY_RESULT_INTELLIGENCE",
            },
            "model": {
                "path": inspection["source"]["path"],
                "sha256": inspection["source"]["sha256"],
                "format": inspection["format"],
                "bundleFingerprint": inspection["bundle"]["bundleFingerprint"],
                "files": inspection["bundle"]["files"],
            },
            "load": load,
            "analysis": {"type": "MODEL_SCRIPT", "managedBy": "ANSYS_APDL_BUNDLE"},
            "summary": {
                "processReturnCode": process["returnCode"],
                "resultExtraction": "NOT_IMPLEMENTED_IN_PR8",
            },
            "outputs": outputs,
        }
        manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8")
        return manifest
