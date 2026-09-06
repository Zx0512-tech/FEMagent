"""Read-only project evidence API built on recorded Result Intelligence artifacts."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from fem_core.result_intelligence import inspect_result, query_result

from .report import project_engineering_report
from .result_projection import project_result_evidence

_RESULT_ARTIFACT_ROLE = {
    "ANSYS": "binaryResult",
    "OPENSEESPY": "responseCsv",
}


def _result_artifact(
    inspection: dict[str, Any],
    result: dict[str, Any],
) -> tuple[str | None, str | None]:
    integrity = inspection.get("integrity")
    artifacts = integrity.get("artifacts") if isinstance(integrity, dict) else None
    if not isinstance(artifacts, list):
        return None, None

    source = result.get("source")
    source_path = source.get("artifact") if isinstance(source, dict) else None
    if isinstance(source_path, str) and source_path:
        for artifact in artifacts:
            if not isinstance(artifact, dict) or artifact.get("path") != source_path:
                continue
            if artifact.get("status") != "VERIFIED":
                return source_path, None
            digest = artifact.get("sha256")
            return source_path, digest if isinstance(digest, str) else None

    solver = inspection.get("solver")
    solver_name = str(solver.get("name") if isinstance(solver, dict) else "").upper()
    preferred_role = _RESULT_ARTIFACT_ROLE.get(solver_name)
    if preferred_role is None:
        return None, None
    for artifact in artifacts:
        if not isinstance(artifact, dict) or artifact.get("role") != preferred_role:
            continue
        path = artifact.get("path")
        if not isinstance(path, str) or not path:
            return None, None
        if artifact.get("status") == "VERIFIED":
            digest = artifact.get("sha256")
            return path, digest if isinstance(digest, str) else None
        return path, None
    return None, None


def project_run_evidence(
    workspace: Path,
    *,
    project_id: str,
    run_ref: str,
    evidence_id: str,
    query: dict[str, Any],
) -> dict[str, Any]:
    """Project one recorded result query into an auditable project evidence report.

    `inspect_result()` is deliberately called before `query_result()` so declared
    result artifact hashes are verified before a numerical payload can be
    promoted into EngineeringEvidence.
    """

    inspection = inspect_result(workspace, run_ref)
    result = query_result(workspace, run_ref, query)
    artifact, artifact_sha256 = _result_artifact(inspection, result)

    solver = inspection.get("solver")
    solver_name = str(solver.get("name") if isinstance(solver, dict) else "").upper()
    provenance = {
        "runId": inspection["runId"],
        "caseFingerprint": inspection["caseFingerprint"],
        "solver": solver_name,
    }
    evidence = project_result_evidence(
        evidence_id=evidence_id,
        result=result,
        artifact=artifact,
        artifact_sha256=artifact_sha256,
        provenance=provenance,
    )

    return project_engineering_report(
        project_id,
        [evidence],
        [
            {
                "runId": inspection["runId"],
                "solver": solver_name,
                "caseFingerprint": inspection["caseFingerprint"],
            }
        ],
    )
