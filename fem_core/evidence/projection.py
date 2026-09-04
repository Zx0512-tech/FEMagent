from __future__ import annotations

from .models import EvidenceArtifactRef, EvidenceStatus, EngineeringEvidence
from .validation import validate_evidence


def project_claim(
    evidence_id: str,
    claim: str,
    artifact: str | None,
    sha256: str | None,
    metric: dict | None = None,
) -> EngineeringEvidence:
    refs = () if artifact is None else (
        EvidenceArtifactRef(artifact=artifact, sha256=sha256),
    )

    evidence = EngineeringEvidence(
        evidence_id=evidence_id,
        claim=claim,
        status=EvidenceStatus.UNVERIFIED,
        artifacts=refs,
        metric=metric or {},
    )

    return EngineeringEvidence(
        evidence_id=evidence.evidence_id,
        claim=evidence.claim,
        status=validate_evidence(evidence),
        artifacts=evidence.artifacts,
        metric=evidence.metric,
        provenance=evidence.provenance,
    )
