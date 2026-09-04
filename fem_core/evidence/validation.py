from __future__ import annotations

from .models import EvidenceStatus, EngineeringEvidence


def validate_evidence(evidence: EngineeringEvidence) -> EvidenceStatus:
    """Validate that a claim is backed by auditable artifacts.

    Claims without artifacts are never promoted to verified evidence.
    """
    if not evidence.artifacts:
        return EvidenceStatus.UNVERIFIED

    for artifact in evidence.artifacts:
        if not artifact.artifact:
            return EvidenceStatus.INVALID
        if artifact.sha256 is None:
            return EvidenceStatus.LIMITED

    return EvidenceStatus.VERIFIED
