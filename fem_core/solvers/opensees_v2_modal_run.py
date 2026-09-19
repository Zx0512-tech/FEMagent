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
from fem_core.pathing import workspace_relative_path
from fem_core.solvers.opensees_generated_analysis import verify_generated_analysis_bundle
from fem_core.solvers.opensees_python import (
    _SCRIPT_RUN_TIMEOUT_S,
    _generated_summary,
    _sha256_file,
)


def _required_generated(
    workspace: Path,
    *,
    model_path: str,
    solver_options: dict[str, Any] | None,
) -> dict[str, Any]:
    if not isinstance(solver_options, dict):
        raise FemCoreError(
            "INVALID_GENERATED_ANALYSIS_ADMISSION",
            "Verified modal execution requires generated-analysis solver options",
        )
    response_plan = solver_options.get("responsePlanPath")
    manifest = solver_options.get("analysisManifestPath")
    if not isinstance(response_plan, str) or not isinstance(manifest, str):
        raise FemCoreError(
            "INVALID_GENERATED_ANALYSIS_ADMISSION",
            "Verified modal execution requires response-plan and manifest provenance",
        )
    generated = verify_generated_analysis_bundle(
        workspace,
        model_path=model_path,
        response_plan_path=response_plan,
        manifest_path=manifest,
    )
    if generated.get("executionMode") != "MODAL":
        raise FemCoreError(
            "INVALID_GENERATED_ANALYSIS_ADMISSION",
            "Generated-analysis verifier did not admit modal execution",
        )
    return generated


def run_verified_modal_bundle(
    adapter: Any,
    workspace: Path,
    *,
    model_path: str,
    solver_options: dict[str, Any] | None,
) -> dict[str, Any]:
    generated = _required_generated(
        workspace,
        model_path=model_path,
        solver_options=solver_options,
    )
    preflight = adapter.preflight(
        workspace,
        model_path=model_path,
        load_path=None,
        solver_options=solver_options,
    )
    if preflight["status"] != "READY":
        raise FemCoreError(
            "SOLVER_PREFLIGHT_FAILED",
            "OpenSees modal analysis cannot run because solver preflight is blocked",
            details={"checks": preflight["checks"]},
        )

    generated = _required_generated(
        workspace,
        model_path=model_path,
        solver_options=solver_options,
    )
    static = inspect_opensees_python(workspace, model_path)
    run_id = f"run_{uuid4().hex[:16]}"
    run_dir = workspace.resolve() / ".femagent" / "runs" / run_id
    run_dir.mkdir(parents=True, exist_ok=False)
    stage_root = run_dir / "model_bundle"
    for file_info in static["bundle"]["files"]:
        source = workspace.resolve() / str(file_info["path"])
        destination = stage_root / str(file_info["path"])
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination)
    staged_model = stage_root / static["source"]["path"]
    if _sha256_file(staged_model) != generated["artifacts"]["analysisSha256"]:
        raise FemCoreError(
            "GENERATED_ANALYSIS_ARTIFACT_MISMATCH",
            "Staged OpenSees modal analysis differs from verified provenance",
        )

    context_path = run_dir / "response_context.verified.json"
    context_path.write_text(
        json.dumps(generated["responseContext"], indent=2, sort_keys=True),
        encoding="utf-8",
    )
    worker_result = run_dir / "worker_result.json"
    solver_log = run_dir / "solver.log"
    command = [
        sys.executable,
        "-m",
        "fem_core.solvers.opensees_worker",
        "--mode",
        "modal-run",
        "--model",
        str(staged_model),
        "--run-dir",
        str(run_dir),
        "--response-context",
        str(context_path),
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
            "OpenSees modal worker exceeded the execution timeout",
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
        except (OSError, UnicodeDecodeError, json.JSONDecodeError):
            worker = None
    if completed.returncode != 0:
        if worker is not None and isinstance(worker.get("code"), str):
            raise FemCoreError(
                str(worker["code"]),
                str(worker.get("message") or "OpenSees modal worker failed"),
                details={"runId": run_id, "returnCode": completed.returncode},
            )
        raise FemCoreError(
            "OPENSEES_WORKER_FAILED",
            "The isolated OpenSees modal worker failed",
            details={"runId": run_id, "returnCode": completed.returncode},
        )
    if worker is None or worker.get("status") != "COMPLETED":
        raise FemCoreError(
            "INVALID_SOLVER_RESULT",
            "OpenSees modal worker did not complete successfully",
            details={"runId": run_id, "result": worker},
        )

    summary_path = run_dir / "result_summary.json"
    modal_path = run_dir / "modal_results.json"
    if not summary_path.is_file() or not modal_path.is_file():
        raise FemCoreError(
            "INVALID_SOLVER_RESULT",
            "OpenSees modal worker did not produce canonical modal artifacts",
            details={"runId": run_id},
        )

    outputs = {
        "runManifest": workspace_relative_path(workspace, run_dir / "run_manifest.json"),
        "resultSummary": workspace_relative_path(workspace, summary_path),
        "resultSummarySha256": _sha256_file(summary_path),
        "solverLog": workspace_relative_path(workspace, solver_log),
        "solverLogSha256": _sha256_file(solver_log),
        "stagedBundleRoot": workspace_relative_path(workspace, stage_root),
        "modalResults": workspace_relative_path(workspace, modal_path),
        "modalResultsSha256": _sha256_file(modal_path),
    }
    fingerprint = sha256(
        json.dumps(
            {
                "solver": "OPENSEESPY",
                "bundleFingerprint": static["bundle"]["bundleFingerprint"],
                "analysis": "MODAL",
                "analysisRenderFingerprint": generated["analysisRenderFingerprint"],
                "modalResultsSha256": outputs["modalResultsSha256"],
            },
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()
    manifest = {
        "schemaVersion": "1.0",
        "kind": "solver_run",
        "runId": run_id,
        "caseFingerprint": fingerprint,
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
        "load": {"mode": "GENERATED_ANALYSIS_EMBEDDED"},
        "responsePlan": {
            "mode": "GENERATED_ANALYSIS_VERIFIED",
            "path": generated["artifacts"]["responsePlanPath"],
            "sha256": generated["artifacts"]["responsePlanSha256"],
        },
        "generatedAnalysis": _generated_summary(generated),
        "analysis": worker.get("analysis"),
        "summary": worker.get("summary"),
        "outputs": outputs,
    }
    (run_dir / "run_manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    return manifest


__all__ = ["run_verified_modal_bundle"]
