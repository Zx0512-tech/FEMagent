from __future__ import annotations

from pathlib import Path
from typing import Any

from fem_core.errors import FemCoreError
from fem_core.evidence.api import project_run_evidence
from fem_core.result_intelligence import inspect_result

from .resolver import resolve_semantic_role


def project_role_evidence(
    workspace: Path,
    *,
    project_id: str,
    model_path: str,
    manifest_path: str,
    role_id: str,
    run_ref: str,
    evidence_id: str,
    quantity: str,
    component: str,
    operation: str,
    offset: int = 0,
    limit: int = 500,
) -> dict[str, Any]:
    """Project a semantic NODE role through the existing verified Evidence path.

    The semantic declaration is resolved against the current Model Bundle first.
    The recorded solver run must then prove that it belongs to that same Model
    Bundle before any Result Intelligence query is made through PR12's run-backed
    evidence projection.
    """

    resolution = resolve_semantic_role(
        workspace,
        model_path=model_path,
        manifest_path=manifest_path,
        role_id=role_id,
    )
    inspection = inspect_result(workspace, run_ref)
    recorded_model = inspection.get("model")
    run_bundle_fingerprint = (
        recorded_model.get("bundleFingerprint") if isinstance(recorded_model, dict) else None
    )
    semantic_bundle_fingerprint = resolution["modelBundleFingerprint"]
    if run_bundle_fingerprint != semantic_bundle_fingerprint:
        raise FemCoreError(
            "SEMANTIC_ROLE_RUN_MODEL_MISMATCH",
            "Recorded solver run does not belong to the Model Bundle bound by the semantic role manifest",
            details={
                "roleId": role_id,
                "semanticModelBundleFingerprint": semantic_bundle_fingerprint,
                "runModelBundleFingerprint": run_bundle_fingerprint,
                "runId": inspection["runId"],
            },
        )

    entity = resolution["entity"]
    query: dict[str, Any] = {
        "quantity": quantity,
        "target": {"type": "NODE", "id": entity["id"]},
        "component": component,
        "operation": operation,
    }
    if str(operation).upper() == "SERIES":
        query["offset"] = offset
        query["limit"] = limit

    report = project_run_evidence(
        workspace,
        project_id=project_id,
        run_ref=run_ref,
        evidence_id=evidence_id,
        query=query,
    )

    semantic_provenance = {
        "roleId": resolution["roleId"],
        "roleType": resolution["roleType"],
        "entity": dict(resolution["entity"]),
        "entityValidation": resolution["entityValidation"],
        "manifestSha256": resolution["manifestSha256"],
        "modelBundleFingerprint": semantic_bundle_fingerprint,
    }
    for evidence in report.get("verifiedEvidence", []):
        if not isinstance(evidence, dict):
            continue
        provenance = evidence.get("provenance")
        if not isinstance(provenance, dict):
            provenance = {}
            evidence["provenance"] = provenance
        provenance["semanticRole"] = dict(semantic_provenance)

    report["semanticRole"] = semantic_provenance
    return report
