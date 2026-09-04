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
from fem_core.solvers.ansys_load import (
    inject_ansys_uniform_excitation,
    inspect_ansys_transient_injection,
    read_ansys_canonical_uniform_excitation,
    write_ansys_uniform_excitation,
)
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


def _find_binary_result(working_directory: Path, jobname: str) -> Path | None:
    for suffix in _ANSYS_BINARY_RESULT_SUFFIXES:
        candidate = (working_directory / f"{jobname}{suffix}").resolve()
        if candidate.is_file():
            return candidate
    return None


def _model_units(solver_options: dict[str, Any] | None) -> dict[str, str]:
    if not isinstance(solver_options, dict):
        raise FemCoreError(
            "ANSYS_MODEL_UNITS_REQUIRED",
            "ANSYS canonical load injection requires solverOptions.modelUnits",
        )
    model_units = solver_options.get("modelUnits")
    if not isinstance(model_units, dict):
        raise FemCoreError(
            "ANSYS_MODEL_UNITS_REQUIRED",
            "ANSYS canonical load injection requires solverOptions.modelUnits",
        )
    return {str(key): str(value) for key, value in model_units.items()}


def _canonical_load_summary(
    workspace: Path,
    load_file: Path,
    load: dict[str, Any],
    hook: dict[str, Any],
    *,
    injected: bool,
    injection_status: str,
    execution_input_fingerprint: str | None = None,
) -> dict[str, Any]:
    report: dict[str, Any] = {
        "mode": "FEMAGENT_CANONICAL_UNIFORM_EXCITATION",
        "path": workspace_relative_path(workspace, load_file),
        "sourceSha256": load["sha256"],
        "format": load["format"],
        "loadKind": load["loadKind"],
        "applicationType": load["applicationType"],
        "channelId": load["channelId"],
        "component": load["component"],
        "quantity": load["quantity"],
        "canonicalUnit": load["canonicalUnit"],
        "sampleCount": load["sampleCount"],
        "modelUnits": load["modelUnits"],
        "conversion": load["conversion"],
        "signConvention": load["signConvention"],
        "injected": injected,
        "injectionStatus": injection_status,
        "hook": hook,
    }
    if execution_input_fingerprint is not None:
        report["executionInputFingerprint"] = execution_input_fingerprint
    return report


def _failed_load_summary(
    workspace: Path,
    load_path: str,
    error: FemCoreError,
) -> dict[str, Any]:
    report: dict[str, Any] = {
        "mode": "FEMAGENT_CANONICAL_UNIFORM_EXCITATION",
        "providedPath": load_path,
        "injected": False,
        "injectionStatus": "BLOCKED",
        "error": {
            "code": error.code,
            "message": error.message,
            "details": error.details,
        },
    }
    try:
        load_file = resolve_workspace_file(workspace, load_path)
    except FemCoreError:
        return report
    report["providedPath"] = workspace_relative_path(workspace, load_file)
    report["sourceSha256"] = _sha256_file(load_file)
    return report


def _execution_input_fingerprint(
    *,
    bundle_fingerprint: str,
    load: dict[str, Any],
    artifacts: dict[str, Any],
    hook: dict[str, Any],
) -> str:
    payload = json.dumps(
        {
            "bundleFingerprint": bundle_fingerprint,
            "loadSha256": load["sha256"],
            "modelUnits": load["modelUnits"],
            "conversion": load["conversion"],
            "component": load["component"],
            "tableSha256": artifacts["tableSha256"],
            "macroSha256": artifacts["macroSha256"],
            "hook": {
                "path": hook["path"],
                "line": hook["line"],
                "command": hook["command"],
            },
        },
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return sha256(payload).hexdigest()


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
                "CANONICAL_UNIFORM_EXCITATION",
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

    def _canonical_plan(
        self,
        workspace: Path,
        *,
        inspection: dict[str, Any],
        load_path: str,
        solver_options: dict[str, Any] | None,
    ) -> tuple[Path, dict[str, Any], dict[str, Any]]:
        load_file = resolve_workspace_file(workspace, load_path)
        load = read_ansys_canonical_uniform_excitation(load_file, _model_units(solver_options))
        hook = inspect_ansys_transient_injection(workspace, inspection["bundle"])
        return load_file, load, hook

    def build_inspect(
        self,
        workspace: Path,
        *,
        model_path: str,
        canonical_load: dict[str, Any] | None = None,
        injection_hook: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
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

        load_include_command: str | None = None
        load_hook_path: str | None = None
        if canonical_load is not None:
            if injection_hook is None:
                raise FemCoreError(
                    "ANSYS_TRANSIENT_HOOK_NOT_FOUND",
                    "Canonical load build inspection requires a validated transient injection hook",
                )
            load_include_command = "/INPUT,'femagent_load','mac'"
            load_hook_path = str(injection_hook["path"])

        staged = stage_ansys_bundle(
            workspace,
            inspection["bundle"],
            inspection_dir / "model_bundle",
            sanitize_for_build=True,
            load_include_command=load_include_command,
            load_hook_path=load_hook_path,
        )

        generated_load: dict[str, Any] | None = None
        if canonical_load is not None:
            generated_load = write_ansys_uniform_excitation(staged["workingDirectory"], canonical_load)

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

        result: dict[str, Any] = {
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
            "loadInjectionValidated": canonical_load is not None,
        }
        if generated_load is not None:
            result["generatedLoad"] = {
                "tablePath": workspace_relative_path(workspace, Path(generated_load["tablePath"])),
                "tableSha256": generated_load["tableSha256"],
                "macroPath": workspace_relative_path(workspace, Path(generated_load["macroPath"])),
                "macroSha256": generated_load["macroSha256"],
                "includeCommand": generated_load["includeCommand"],
            }
        return result

    def preflight(
        self,
        workspace: Path,
        *,
        model_path: str,
        load_path: str | None = None,
        solver_options: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        inspection = self._inspection(workspace, model_path)
        status = self.status()
        eligibility = str(inspection["validation"]["executionEligibility"])
        model_safe = eligibility not in {"REJECTED", "INCOMPLETE"}
        bundle_valid = inspection["bundle"]["integrity"] == "VALID"

        canonical_load: dict[str, Any] | None = None
        injection_hook: dict[str, Any] | None = None
        load_file: Path | None = None
        load_error: FemCoreError | None = None
        if load_path:
            try:
                load_file, canonical_load, injection_hook = self._canonical_plan(
                    workspace,
                    inspection=inspection,
                    load_path=load_path,
                    solver_options=solver_options,
                )
            except FemCoreError as exc:
                load_error = exc

        build: dict[str, Any] | None = None
        build_error: dict[str, Any] | None = None
        can_build = (
            status["available"]
            and model_safe
            and bundle_valid
            and (not load_path or load_error is None)
        )
        if can_build:
            try:
                build = self.build_inspect(
                    workspace,
                    model_path=model_path,
                    canonical_load=canonical_load,
                    injection_hook=injection_hook,
                )
            except FemCoreError as exc:
                build_error = {"code": exc.code, "message": exc.message, "details": exc.details}

        build_status = "PASSED" if build is not None else "FAILED" if can_build else "SKIPPED"
        checks = [
            {"code": "SOLVER_AVAILABLE", "status": "PASSED" if status["available"] else "FAILED"},
            {"code": "ANSYS_MODEL_STATIC_SAFETY", "status": "PASSED" if model_safe else "FAILED"},
            {"code": "MODEL_BUNDLE_INTEGRITY", "status": "PASSED" if bundle_valid else "FAILED"},
        ]
        if load_path:
            checks.append(
                {
                    "code": "CANONICAL_LOAD_INJECTION",
                    "status": "PASSED" if load_error is None else "FAILED",
                }
            )
        checks.append({"code": "BUILD_ONLY_INSPECTION", "status": build_status})

        warnings: list[dict[str, Any]] = []
        if build_error:
            warnings.append(
                {
                    "code": "BUILD_ONLY_INSPECTION_FAILED",
                    "message": build_error["message"],
                    "details": {"errorCode": build_error["code"], **build_error["details"]},
                }
            )

        if not load_path:
            load_report: dict[str, Any] = {"mode": "MODEL_SCRIPT_MANAGED"}
        elif load_error is not None:
            load_report = _failed_load_summary(workspace, load_path, load_error)
        else:
            assert load_file is not None
            assert canonical_load is not None
            assert injection_hook is not None
            load_report = _canonical_load_summary(
                workspace,
                load_file,
                canonical_load,
                injection_hook,
                injected=False,
                injection_status="VALIDATED_FOR_STAGING",
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
            "load": load_report,
            "executionEstimate": {"mode": "ANSYS_APDL_BUNDLE", "analysisSteps": None},
        }

    def run(
        self,
        workspace: Path,
        *,
        model_path: str,
        load_path: str | None = None,
        solver_options: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        preflight = self.preflight(
            workspace,
            model_path=model_path,
            load_path=load_path,
            solver_options=solver_options,
        )
        if preflight["status"] != "READY":
            raise FemCoreError(
                "SOLVER_PREFLIGHT_FAILED",
                "ANSYS execution is blocked because solver preflight did not pass",
                details={"checks": preflight["checks"], "load": preflight["load"]},
            )

        inspection = self._inspection(workspace, model_path)
        status = self.status()
        if not status["available"] or not status["configuredPath"]:
            raise FemCoreError("SOLVER_UNAVAILABLE", "ANSYS runtime became unavailable after preflight")

        canonical_load: dict[str, Any] | None = None
        injection_hook: dict[str, Any] | None = None
        load_file: Path | None = None
        if load_path:
            load_file, canonical_load, injection_hook = self._canonical_plan(
                workspace,
                inspection=inspection,
                load_path=load_path,
                solver_options=solver_options,
            )

        run_id = f"run_{uuid4().hex[:16]}"
        run_dir = (workspace.resolve() / ".femagent" / "runs" / run_id).resolve()
        run_dir.mkdir(parents=True, exist_ok=False)
        staged = stage_ansys_bundle(
            workspace,
            inspection["bundle"],
            run_dir / "model_bundle",
            sanitize_for_build=False,
        )

        generated_load: dict[str, Any] | None = None
        injection: dict[str, Any] | None = None
        execution_input_fingerprint: str | None = None
        if canonical_load is not None:
            assert injection_hook is not None
            generated_load = write_ansys_uniform_excitation(
                staged["workingDirectory"],
                canonical_load,
            )
            injection = inject_ansys_uniform_excitation(
                staged["stageRoot"],
                injection_hook,
            )
            execution_input_fingerprint = _execution_input_fingerprint(
                bundle_fingerprint=inspection["bundle"]["bundleFingerprint"],
                load=canonical_load,
                artifacts=generated_load,
                hook=injection_hook,
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

        if canonical_load is None:
            load_report: dict[str, Any] = {"mode": "MODEL_SCRIPT_MANAGED"}
            injection_report: dict[str, Any] = {"injected": False}
            analysis = {"type": "MODEL_SCRIPT", "managedBy": "ANSYS_APDL_BUNDLE"}
        else:
            assert load_file is not None
            assert injection_hook is not None
            assert generated_load is not None
            assert injection is not None
            assert execution_input_fingerprint is not None
            load_report = _canonical_load_summary(
                workspace,
                load_file,
                canonical_load,
                injection_hook,
                injected=True,
                injection_status="INJECTED_IN_STAGED_BUNDLE",
                execution_input_fingerprint=execution_input_fingerprint,
            )
            injection_report = {
                "injected": True,
                "hookPath": injection_hook["path"],
                "hookLine": injection_hook["line"],
                "hookCommand": injection_hook["command"],
                "macroSha256": generated_load["macroSha256"],
                "tableSha256": generated_load["tableSha256"],
                "stagedHookFileSha256": injection["stagedHookFileSha256"],
            }
            analysis = {
                "type": "TRANSIENT_UNIFORM_EXCITATION",
                "managedBy": "FEMAGENT_CANONICAL_LOAD_APPLICATION_V1",
            }

        fingerprint_payload = json.dumps(
            {
                "solver": "ANSYS",
                "runtime": str(status["configuredPath"]),
                "bundleFingerprint": inspection["bundle"]["bundleFingerprint"],
                "executionInputFingerprint": execution_input_fingerprint,
                "analysis": analysis["type"],
            },
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        manifest_path = run_dir / "run_manifest.json"
        outputs: dict[str, str] = {
            "runManifest": workspace_relative_path(workspace, manifest_path),
            "runtimeOutput": workspace_relative_path(workspace, runtime_output),
            "runtimeOutputSha256": _sha256_file(runtime_output),
            "solverLog": workspace_relative_path(workspace, solver_log),
            "solverLogSha256": _sha256_file(solver_log),
            "stagedBundleRoot": workspace_relative_path(workspace, staged["stageRoot"]),
        }
        if generated_load is not None:
            outputs["generatedLoadTable"] = workspace_relative_path(
                workspace, Path(generated_load["tablePath"])
            )
            outputs["generatedLoadTableSha256"] = generated_load["tableSha256"]
            outputs["generatedLoadMacro"] = workspace_relative_path(
                workspace, Path(generated_load["macroPath"])
            )
            outputs["generatedLoadMacroSha256"] = generated_load["macroSha256"]
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
            "load": load_report,
            "injection": injection_report,
            "analysis": analysis,
            "summary": {
                "processReturnCode": process["returnCode"],
                "resultExtraction": "RESULT_INTELLIGENCE_V1",
            },
            "outputs": outputs,
        }
        manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8")
        return manifest
