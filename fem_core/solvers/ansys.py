from __future__ import annotations

import os
from hashlib import sha256
from pathlib import Path
from typing import Any

from fem_core.errors import FemCoreError
from fem_core.model_inspection import inspect_model
from fem_core.pathing import resolve_workspace_file, workspace_relative_path
from fem_core.solvers.base import SolverAdapter

_ANSYS_EXECUTABLE_ENV = "FEM_ANSYS_EXECUTABLE"


def _sha256_file(path: Path) -> str:
    return sha256(path.read_bytes()).hexdigest()


class AnsysAdapter(SolverAdapter):
    """ANSYS MAPDL adapter with workspace-bounded Model Bundle preflight."""

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

    def preflight(
        self,
        workspace: Path,
        *,
        model_path: str,
        load_path: str | None = None,
    ) -> dict[str, Any]:
        inspection = inspect_model(workspace, model_path)
        if inspection.get("format") != "ANSYS_APDL_TEXT":
            raise FemCoreError(
                "SOLVER_MODEL_MISMATCH",
                "ANSYS SolverAdapter requires an ANSYS APDL/CDB Model Bundle",
                details={"format": inspection.get("format")},
            )

        status = self.status()
        eligibility = str(inspection["validation"]["executionEligibility"])
        model_safe = eligibility not in {"REJECTED", "INCOMPLETE"}
        bundle_valid = inspection["bundle"]["integrity"] == "VALID"

        checks = [
            {"code": "SOLVER_AVAILABLE", "status": "PASSED" if status["available"] else "FAILED"},
            {"code": "ANSYS_MODEL_STATIC_SAFETY", "status": "PASSED" if model_safe else "FAILED"},
            {"code": "MODEL_BUNDLE_INTEGRITY", "status": "PASSED" if bundle_valid else "FAILED"},
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
                    "message": "The provided external load is recorded as provenance only; PR8 has no ANSYS load-injection contract",
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
                "buildInspection": None,
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
        raise FemCoreError(
            "ANSYS_EXECUTION_NOT_IMPLEMENTED",
            "ANSYS staged execution is introduced in the next PR8 implementation task",
        )
