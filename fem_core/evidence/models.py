from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class EvidenceStatus(str, Enum):
    VERIFIED = "VERIFIED"
    INVALID = "INVALID"
    LIMITED = "LIMITED"
    UNVERIFIED = "UNVERIFIED"


@dataclass(frozen=True)
class EvidenceArtifactRef:
    artifact: str
    sha256: str | None = None
    entity: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class EngineeringEvidence:
    evidence_id: str
    claim: str
    status: EvidenceStatus
    artifacts: tuple[EvidenceArtifactRef, ...]
    metric: dict[str, Any] = field(default_factory=dict)
    provenance: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "evidenceId": self.evidence_id,
            "claim": self.claim,
            "status": self.status.value,
            "artifacts": [
                {
                    "artifact": a.artifact,
                    "sha256": a.sha256,
                    "entity": a.entity,
                }
                for a in self.artifacts
            ],
            "metric": self.metric,
            "provenance": self.provenance,
        }
