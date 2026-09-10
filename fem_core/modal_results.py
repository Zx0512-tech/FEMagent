from __future__ import annotations

import math
from typing import Any

from fem_core.errors import FemCoreError

_SECONDS_PER_MODEL_TIME_UNIT = {"s": 1.0, "ms": 0.001}


def _invalid(message: str, **details: Any) -> FemCoreError:
    return FemCoreError("INVALID_MODAL_RESULT", message, details=details)


def _finite_positive_eigenvalues(eigenvalues: list[float]) -> list[float]:
    values: list[float] = []
    for index, raw in enumerate(eigenvalues, start=1):
        try:
            value = float(raw)
        except (TypeError, ValueError) as exc:
            raise _invalid("OpenSees modal eigenvalues must be numeric", mode=index) from exc
        if not math.isfinite(value) or value <= 0.0:
            raise _invalid(
                "OpenSees modal eigenvalues must be finite and positive",
                mode=index,
                eigenvalue=value,
            )
        values.append(value)
    if not values:
        raise _invalid("OpenSees modal analysis returned no eigenvalues")
    return values


def canonicalize_modal_results(
    *,
    eigenvalues: list[float],
    requests: list[dict[str, Any]],
    model_time_unit: str,
    mode_shapes: dict[str, float],
) -> dict[str, Any]:
    seconds_per_time_unit = _SECONDS_PER_MODEL_TIME_UNIT.get(model_time_unit)
    if seconds_per_time_unit is None:
        raise _invalid("Modal result conversion supports model time units s and ms only", timeUnit=model_time_unit)

    values = _finite_positive_eigenvalues(eigenvalues)
    results: list[dict[str, Any]] = []
    for request in requests:
        request_id = request.get("requestId")
        quantity = request.get("quantity")
        mode = request.get("mode")
        if (
            not isinstance(request_id, str)
            or not request_id
            or not isinstance(mode, int)
            or isinstance(mode, bool)
            or mode < 1
            or mode > len(values)
        ):
            raise _invalid("Modal request does not reference a captured eigenmode", requestId=request_id, mode=mode)

        eigenvalue = values[mode - 1]
        omega_native = math.sqrt(eigenvalue)
        base: dict[str, Any] = {
            "requestId": request_id,
            "quantity": quantity,
            "mode": mode,
        }
        if quantity == "EIGENVALUE":
            base.update({"value": eigenvalue, "unit": f"1/{model_time_unit}2"})
        elif quantity == "NATURAL_FREQUENCY":
            base.update(
                {
                    "value": omega_native / (2.0 * math.pi * seconds_per_time_unit),
                    "unit": "Hz",
                }
            )
        elif quantity == "PERIOD":
            base.update({"value": 2.0 * math.pi / omega_native, "unit": model_time_unit})
        elif quantity == "MODE_SHAPE":
            if request_id not in mode_shapes:
                raise _invalid("Requested OpenSees mode-shape component was not captured", requestId=request_id)
            shape_value = float(mode_shapes[request_id])
            if not math.isfinite(shape_value):
                raise _invalid("OpenSees mode-shape result must be finite", requestId=request_id)
            target = request.get("target")
            component = request.get("component")
            if not isinstance(target, dict) or target.get("type") != "NODE" or component not in {"X", "Y", "RZ"}:
                raise _invalid("Mode-shape request identity is invalid", requestId=request_id)
            base.update(
                {
                    "target": dict(target),
                    "component": component,
                    "value": shape_value,
                    "unit": "1",
                    "normalization": "OPENSEES_NATIVE",
                }
            )
        else:
            raise _invalid("Unsupported modal result quantity", requestId=request_id, quantity=quantity)
        results.append(base)

    return {
        "schemaVersion": "1.0",
        "kind": "modal_result_set",
        "modelTimeUnit": model_time_unit,
        "results": results,
    }


__all__ = ["canonicalize_modal_results"]
