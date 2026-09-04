"""Projection helpers from verified result intelligence outputs to evidence.

This module intentionally requires artifact provenance. Raw summaries cannot
become engineering claims without an auditable result artifact.
"""

from __future__ import annotations

from typing import Any

from .projection import project_claim
from .models import EngineeringEvidence


def project_result_evidence(
    *,
    evidence_id: str,
    result: dict[str, Any],
    artifact: str | None,
    artifact_sha256: str | None,
) -> EngineeringEvidence:
    """Promote a result query payload only when provenance is supplied."""

    metric = {
        key: value
        for key, value in result.items()
        if key in {"value", "unit", "node", "component"}
    }

    return project_claim(
        evidence_id=evidence_id,
        claim="Result intelligence extracted engineering response",
        artifact=artifact,
        sha256=artifact_sha256,
        metric=metric,
    )
