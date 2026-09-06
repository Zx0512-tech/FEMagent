from __future__ import annotations

import math

import pytest

from fem_core.errors import FemCoreError
from fem_core.structural_response import normalize_structural_query, summarize_structural_series


def test_normalizes_element_generalized_force_query() -> None:
    query = normalize_structural_query(
        {
            "quantity": "generalized_force",
            "target": {"type": "element", "id": 41},
            "component": "my",
            "location": "end_i",
            "operation": "summary",
        }
    )

    assert query == {
        "quantity": "GENERALIZED_FORCE",
        "target": {"type": "ELEMENT", "id": 41},
        "component": "MY",
        "location": "END_I",
        "operation": "SUMMARY",
    }


def test_normalizes_node_principal_stress_query() -> None:
    query = normalize_structural_query(
        {
            "quantity": "principal_stress",
            "target": {"type": "node", "id": 1024},
            "component": "seqv",
            "operation": "series",
        }
    )

    assert query == {
        "quantity": "PRINCIPAL_STRESS",
        "target": {"type": "NODE", "id": 1024},
        "component": "SEQV",
        "operation": "SERIES",
    }


def test_normalizes_damper_force_query() -> None:
    query = normalize_structural_query(
        {
            "quantity": "damper_response",
            "target": {"type": "element", "id": 7},
            "component": "force",
            "operation": "summary",
        }
    )

    assert query["quantity"] == "DAMPER_RESPONSE"
    assert query["target"] == {"type": "ELEMENT", "id": 7}
    assert query["component"] == "FORCE"
    assert "location" not in query


def test_rejects_unproven_structural_component() -> None:
    with pytest.raises(FemCoreError) as exc_info:
        normalize_structural_query(
            {
                "quantity": "GENERALIZED_FORCE",
                "target": {"type": "ELEMENT", "id": 41},
                "component": "MAGIC_MOMENT",
                "location": "END_I",
                "operation": "SUMMARY",
            }
        )

    assert exc_info.value.code == "INVALID_RESULT_QUERY"


def test_generalized_force_requires_location() -> None:
    with pytest.raises(FemCoreError) as exc_info:
        normalize_structural_query(
            {
                "quantity": "GENERALIZED_FORCE",
                "target": {"type": "ELEMENT", "id": 41},
                "component": "MY",
                "operation": "SUMMARY",
            }
        )

    assert exc_info.value.code == "INVALID_RESULT_QUERY"


def test_rejects_non_positive_or_boolean_entity_ids() -> None:
    for invalid_id in (0, -1, True):
        with pytest.raises(FemCoreError) as exc_info:
            normalize_structural_query(
                {
                    "quantity": "STRESS",
                    "target": {"type": "ELEMENT", "id": invalid_id},
                    "component": "SX",
                    "operation": "SUMMARY",
                }
            )
        assert exc_info.value.code == "INVALID_RESULT_QUERY"


def test_rejects_invalid_operation() -> None:
    with pytest.raises(FemCoreError) as exc_info:
        normalize_structural_query(
            {
                "quantity": "STRESS",
                "target": {"type": "ELEMENT", "id": 9},
                "component": "SX",
                "operation": "AVERAGE_THE_WHOLE_MODEL",
            }
        )

    assert exc_info.value.code == "INVALID_RESULT_QUERY"


def test_summarizes_structural_series_deterministically() -> None:
    result = summarize_structural_series(
        [0.0, 0.1, 0.2, 0.3],
        [-3.0, 3.0, 1.0, -2.0],
    )

    assert result == {
        "sampleCount": 4,
        "min": -3.0,
        "max": 3.0,
        "absolutePeak": 3.0,
        "abscissaAtAbsolutePeak": 0.0,
    }


def test_rejects_invalid_structural_series() -> None:
    invalid_cases = (
        ([], []),
        ([0.0], []),
        ([0.0], [math.inf]),
        ([math.nan], [1.0]),
    )
    for abscissa, values in invalid_cases:
        with pytest.raises(FemCoreError) as exc_info:
            summarize_structural_series(abscissa, values)
        assert exc_info.value.code == "INVALID_RESULT_SERIES"
