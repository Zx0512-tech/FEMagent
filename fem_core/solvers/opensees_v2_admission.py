from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from fem_core.solvers.admission import admit_analysis_execution
from fem_core.solvers.opensees_generated_analysis import verify_generated_analysis_bundle
from fem_core.solvers.opensees_python import OpenSeesBundleAdapter, _solver_options


class OpenSeesV2BundleAdapter(OpenSeesBundleAdapter):
    """Extend generated-analysis admission without changing legacy execution paths."""

    def _admit_generated_execution(self, generated: dict[str, Any]) -> dict[str, Any]:
        return admit_analysis_execution(
            solver="opensees",
            profile=str(generated.get("profile") or ""),
            requested_quantities=[
                str(item)
                for item in generated.get("requestedQuantities", [])
                if isinstance(item, str)
            ],
        )

    def preflight(
        self,
        workspace: Path,
        *,
        model_path: str,
        load_path: str | None = None,
        solver_options: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        report = super().preflight(
            workspace,
            model_path=model_path,
            load_path=load_path,
            solver_options=solver_options,
        )
        build = report.get("model", {}).get("buildInspection")
        if isinstance(build, dict):
            inspection_id = build.get("inspectionId")
            if isinstance(inspection_id, str) and inspection_id:
                result_path = workspace / ".femagent" / "build-inspections" / inspection_id / "worker_result.json"
                if result_path.is_file():
                    payload = json.loads(result_path.read_text(encoding="utf-8"))
                    build["interceptedEigenCalls"] = int(payload.get("interceptedEigenCalls") or 0)
        if isinstance(solver_options, dict):
            response_plan = solver_options.get("responsePlanPath")
            manifest = solver_options.get("analysisManifestPath")
            if isinstance(response_plan, str) and isinstance(manifest, str):
                generated = verify_generated_analysis_bundle(
                    workspace,
                    model_path=model_path,
                    response_plan_path=response_plan,
                    manifest_path=manifest,
                )
                report["executionAdmission"] = self._admit_generated_execution(generated)
                if generated.get("executionMode") == "MODAL":
                    report["executionEstimate"] = {"analysisSteps": None, "mode": "MODAL"}
        return report

    def run(
        self,
        workspace: Path,
        *,
        model_path: str,
        load_path: str | None = None,
        solver_options: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        _, generated = _solver_options(
            workspace,
            model_path=model_path,
            load_path=load_path,
            solver_options=solver_options,
        )
        if generated is not None:
            self._admit_generated_execution(generated)
        if generated is None or generated.get("executionMode") != "MODAL":
            return super().run(
                workspace,
                model_path=model_path,
                load_path=load_path,
                solver_options=solver_options,
            )
        from fem_core.solvers.opensees_v2_modal_run import run_verified_modal_bundle

        return run_verified_modal_bundle(
            self,
            workspace,
            model_path=model_path,
            solver_options=solver_options,
        )


__all__ = ["OpenSeesV2BundleAdapter"]
