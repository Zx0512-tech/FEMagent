from __future__ import annotations

import math
from typing import Any

from fem_core.errors import FemCoreError

TARGET_TYPES = frozenset({"NODE", "ELEMENT"})
OPERATIONS = frozenset({"SUMMARY", "SERIES"})
CARTESIAN_COMPONENTS = frozenset({"X", "Y", "Z"})
STRESS_COMPONENTS = frozenset({"SX", "SY", "SZ", "SXY", "SYZ", "SXZ"})
PRINCIPAL_STRESS_COMPONENTS = frozenset({"S1", "S2", "S3", "SINT", "SEQV"})
GENERALIZED_FORCE_COMPONENTS = frozenset({"N", "VY", "VZ", "T", "MY", "MZ"})
GENERALIZED_FORCE_LOCATIONS = frozenset({"END_I", "END_J", "SECTION"})
DAMPER_COMPONENTS = frozenset({"FORCE", "DEFORMATION", "VELOCITY", "DISSIPATED_ENERGY"})
NODE_CARTESIAN_QUANTITIES = frozenset(
    {"DISPLACEMENT", "VELOCITY", "ACCELERATION", "REACTION_FORCE", "REACTION_MOMENT"}
)
STRUCTURAL_QUANTITIES = frozenset(
    {
        *NODE_CARTESIAN_QUANTITIES,
        "STRESS",
        "PRINCIPAL_STRESS",
        "GENERALIZED_FORCE",
        "DAMPER_RESPONSE",
    }
)


def _invalid(message: str, **details: Any) -> FemCoreError:
    return FemCoreError("INVALID_RESULT_QUERY", message, details=details)


def _upper_string(value: Any, *, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise _invalid(f"Structural result query {field} must be a non-empty string")
    return value.strip().upper()


def normalize_structural_query(query: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(query, dict):
        raise _invalid("Structural result query must be a JSON object")

    quantity = _upper_string(query.get("quantity"), field="quantity")
    operation = _upper_string(query.get("operation"), field="operation")
    component = _upper_string(query.get("component"), field="component")
    if quantity not in STRUCTURAL_QUANTITIES:
        raise _invalid("Structural result query quantity is not supported", quantity=quantity)
    if operation not in OPERATIONS:
        raise _invalid("Structural result query operation must be SUMMARY or SERIES", operation=operation)

    target = query.get("target")
    if not isinstance(target, dict):
        raise _invalid("Structural result query target must be a JSON object")
    target_type = _upper_string(target.get("type"), field="target.type")
    if target_type not in TARGET_TYPES:
        raise _invalid("Structural result query target type must be NODE or ELEMENT", targetType=target_type)
    target_id = target.get("id")
    if not isinstance(target_id, int) or isinstance(target_id, bool) or target_id <= 0:
        raise _invalid("Structural result query target id must be a positive integer", targetId=target_id)

    location: str | None = None
    if quantity in NODE_CARTESIAN_QUANTITIES:
        if target_type != "NODE" or component not in CARTESIAN_COMPONENTS:
            raise _invalid(
                "Cartesian node response requires a NODE target and X, Y, or Z component",
                quantity=quantity,
                targetType=target_type,
                component=component,
            )
    elif quantity == "STRESS":
        if component not in STRESS_COMPONENTS:
            raise _invalid("Stress component is not supported", component=component)
    elif quantity == "PRINCIPAL_STRESS":
        if component not in PRINCIPAL_STRESS_COMPONENTS:
            raise _invalid("Principal stress component is not supported", component=component)
    elif quantity == "GENERALIZED_FORCE":
        if target_type != "ELEMENT" or component not in GENERALIZED_FORCE_COMPONENTS:
            raise _invalid(
                "Generalized force requires an ELEMENT target and controlled force component",
                targetType=target_type,
                component=component,
            )
        location = _upper_string(query.get("location"), field="location")
        if location not in GENERALIZED_FORCE_LOCATIONS:
            raise _invalid("Generalized force location must be END_I, END_J, or SECTION", location=location)
    elif quantity == "DAMPER_RESPONSE" and (
        target_type != "ELEMENT" or component not in DAMPER_COMPONENTS
    ):
        raise _invalid(
            "Damper response requires an ELEMENT target and controlled damper component",
            targetType=target_type,
            component=component,
        )

    normalized: dict[str, Any] = {
        "quantity": quantity,
        "target": {"type": target_type, "id": target_id},
        "component": component,
        "operation": operation,
    }
    if location is not None:
        normalized["location"] = location

    for paging_key in ("offset", "limit"):
        if paging_key in query:
            normalized[paging_key] = query[paging_key]
    return normalized


def summarize_structural_series(abscissa: list[float], values: list[float]) -> dict[str, Any]:
    if not isinstance(abscissa, list) or not isinstance(values, list) or not values:
        raise FemCoreError("INVALID_RESULT_SERIES", "Structural response series must be non-empty lists")
    if len(abscissa) != len(values):
        raise FemCoreError(
            "INVALID_RESULT_SERIES",
            "Structural response abscissa and value counts must match",
            details={"abscissaCount": len(abscissa), "valueCount": len(values)},
        )

    try:
        normalized_abscissa = [float(value) for value in abscissa]
        normalized_values = [float(value) for value in values]
    except (TypeError, ValueError) as exc:
        raise FemCoreError("INVALID_RESULT_SERIES", "Structural response series must be numeric") from exc
    if not all(math.isfinite(value) for value in (*normalized_abscissa, *normalized_values)):
        raise FemCoreError("INVALID_RESULT_SERIES", "Structural response series must contain finite values")

    peak_index = max(range(len(normalized_values)), key=lambda index: abs(normalized_values[index]))
    return {
        "sampleCount": len(normalized_values),
        "min": min(normalized_values),
        "max": max(normalized_values),
        "absolutePeak": abs(normalized_values[peak_index]),
        "abscissaAtAbsolutePeak": normalized_abscissa[peak_index],
    }


__all__ = [
    "CARTESIAN_COMPONENTS",
    "DAMPER_COMPONENTS",
    "GENERALIZED_FORCE_COMPONENTS",
    "GENERALIZED_FORCE_LOCATIONS",
    "NODE_CARTESIAN_QUANTITIES",
    "OPERATIONS",
    "PRINCIPAL_STRESS_COMPONENTS",
    "STRESS_COMPONENTS",
    "STRUCTURAL_QUANTITIES",
    "TARGET_TYPES",
    "normalize_structural_query",
    "summarize_structural_series",
]
