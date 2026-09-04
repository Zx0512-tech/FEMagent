"""Deterministic engineering report projection from verified evidence."""

from __future__ import annotations

from typing import Any, Iterable

from .models import EngineeringEvidence, EvidenceStatus


def project_engineering_report(
    project_id: str,
    evidences: Iterable[EngineeringEvidence],
    solver_runs: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Create a deterministic report projection.

    The report only promotes evidence objects that have passed the evidence
    validation boundary. It does not create new engineering claims.
    """
    evidence_list = list(evidences)

    verified = [
        evidence.to_dict()
        for evidence in evidence_list
        if evidence.status == EvidenceStatus.VERIFIED
    ]

    limitations = [
        {
            "evidenceId": evidence.evidence_id,
            "status": evidence.status.value,
            "claim": evidence.claim,
        }
        for evidence in evidence_list
        if evidence.status != EvidenceStatus.VERIFIED
    ]

    return {
        "projectId": project_id,
        "solverRuns": solver_runs or [],
        "verifiedEvidence": verified,
        "limitations": limitations,
    }
