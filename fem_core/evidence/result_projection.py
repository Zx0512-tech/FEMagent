"""Projection helpers from verified result intelligence outputs to evidence.

This module intentionally requires artifact provenance. Raw summaries cannot
become engineering claims without an auditable result artifact.
"""

from __future__ import annotations

from typing import Any

from .models import EngineeringEvidence
from .projection import project_claim

_RESULT_METRIC_KEYS = (
    "quantity",
    "target",
    "component",
    "location",
    "stressLocation",
    "unit",
    "referenceFrame",
    "operation",
    "abscissa",
    "summary",
    "series",
    "value",
)


def project_result_evidence(
    *,
    evidence_id: str,
    result: dict[str, Any],
    artifact: str | None,
    artifact_sha256: str | None,
    provenance: dict[str, Any] | None = None,
) -> EngineeringEvidence:
    """Promote a Result Intelligence payload only with auditable provenance."""

    metric = {key: result[key] for key in _RESULT_METRIC_KEYS if key in result}
    target = result.get("target")
    entity = dict(target) if isinstance(target, dict) else {}
    component = result.get("component")
    if isinstance(component, str) and component:
        entity["component"] = component

    quantity = result.get("quantity")
    quantity_text = quantity if isinstance(quantity, str) and quantity else "RESULT"
    claim = f"Recorded {quantity_text} engineering response"

    return project_claim(
        evidence_id=evidence_id,
        claim=claim,
        artifact=artifact,
        sha256=artifact_sha256,
        metric=metric,
        entity=entity,
        provenance=provenance,
    )
