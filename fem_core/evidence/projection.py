from __future__ import annotations

from typing import Any

from .models import EvidenceArtifactRef, EvidenceStatus, EngineeringEvidence
from .validation import validate_evidence


def project_claim(
    evidence_id: str,
    claim: str,
    artifact: str | None,
    sha256: str | None,
    metric: dict[str, Any] | None = None,
    *,
    entity: dict[str, Any] | None = None,
    provenance: dict[str, Any] | None = None,
) -> EngineeringEvidence:
    refs = (
        ()
        if artifact is None
        else (
            EvidenceArtifactRef(
                artifact=artifact,
                sha256=sha256,
                entity=entity or {},
            ),
        )
    )

    evidence = EngineeringEvidence(
        evidence_id=evidence_id,
        claim=claim,
        status=EvidenceStatus.UNVERIFIED,
        artifacts=refs,
        metric=metric or {},
        provenance=provenance or {},
    )

    return EngineeringEvidence(
        evidence_id=evidence.evidence_id,
        claim=evidence.claim,
        status=validate_evidence(evidence),
        artifacts=evidence.artifacts,
        metric=evidence.metric,
        provenance=evidence.provenance,
    )
