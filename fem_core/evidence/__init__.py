"""Engineering evidence primitives.

PR12 introduces the deterministic evidence boundary between solver artifacts
and engineering claims.
"""

from .api import project_run_evidence
from .models import EngineeringEvidence, EvidenceStatus
from .projection import project_claim
from .result_projection import project_result_evidence
from .validation import validate_evidence

__all__ = [
    "EvidenceStatus",
    "EngineeringEvidence",
    "project_claim",
    "project_result_evidence",
    "project_run_evidence",
    "validate_evidence",
]
