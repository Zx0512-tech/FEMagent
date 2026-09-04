"""Engineering evidence primitives.

PR12 introduces the deterministic evidence boundary between solver artifacts
and engineering claims.
"""

from .models import EvidenceStatus, EngineeringEvidence
from .validation import validate_evidence
from .projection import project_claim
from .result_projection import project_result_evidence

__all__ = [
    "EvidenceStatus",
    "EngineeringEvidence",
    "validate_evidence",
    "project_claim",
    "project_result_evidence",
]
