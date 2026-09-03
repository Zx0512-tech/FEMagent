from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Any
from uuid import uuid4

from fem_core.errors import FemCoreError
from fem_core.opensees_python_inspection import inspect_opensees_python
from fem_core.pathing import resolve_workspace_file, workspace_relative_path
from fem_core.solvers.opensees import OpenSeesAdapter

_BUILD_TIMEOUT_S = 60.0


class OpenSeesBundleAdapter(OpenSeesAdapter):
    """OpenSees adapter extended with safe bundle inspection for Python entrypoints."""

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
            "solver": "OPENSEESPY",
            "packageVersion": result.get("packageVersion"),
            "engineVersion": result.get("engineVersion"),
            "logPath": workspace_relative_path(workspace, log_path),
        }
