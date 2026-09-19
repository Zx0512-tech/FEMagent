from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any

from fem_core.errors import FemCoreError

_SECONDS_PER_MODEL_TIME_UNIT = {"s": 1.0, "ms": 0.001}
_MODAL_SCALAR_UNITS = {
    "NATURAL_FREQUENCY": "Hz",
}
_MODAL_QUANTITIES = frozenset({"EIGENVALUE", "NATURAL_FREQUENCY", "PERIOD", "MODE_SHAPE"})


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


def _finite_modal_value(raw: Any, *, request_id: str) -> float:
    try:
        value = float(raw)
    except (TypeError, ValueError) as exc:
        raise _invalid("Canonical modal result value must be numeric", requestId=request_id) from exc
    if not math.isfinite(value):
        raise _invalid("Canonical modal result value must be finite", requestId=request_id)
    return value


def read_modal_result_set(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise _invalid("Canonical modal result artifact must be valid UTF-8 JSON") from exc
    if (
        not isinstance(payload, dict)
        or payload.get("schemaVersion") != "1.0"
        or payload.get("kind") != "modal_result_set"
        or payload.get("modelTimeUnit") not in _SECONDS_PER_MODEL_TIME_UNIT
        or not isinstance(payload.get("results"), list)
        or not payload["results"]
    ):
        raise _invalid("Canonical modal result artifact has an invalid schema")

    model_time_unit = str(payload["modelTimeUnit"])
    seen_ids: set[str] = set()
    normalized: list[dict[str, Any]] = []
    for index, raw in enumerate(payload["results"]):
        if not isinstance(raw, dict):
            raise _invalid("Canonical modal result entry must be an object", resultIndex=index)
        request_id = raw.get("requestId")
        quantity = raw.get("quantity")
        mode = raw.get("mode")
        unit = raw.get("unit")
        if not isinstance(request_id, str) or not request_id or request_id in seen_ids:
            raise _invalid("Canonical modal requestId must be unique and non-empty", resultIndex=index)
        seen_ids.add(request_id)
        if quantity not in _MODAL_QUANTITIES:
            raise _invalid("Canonical modal result quantity is unsupported", requestId=request_id)
        if not isinstance(mode, int) or isinstance(mode, bool) or mode <= 0:
            raise _invalid("Canonical modal result mode must be a positive integer", requestId=request_id)
        value = _finite_modal_value(raw.get("value"), request_id=request_id)

        expected_unit: str
        item: dict[str, Any] = {
            "requestId": request_id,
            "quantity": quantity,
            "mode": mode,
            "value": value,
        }
        if quantity == "EIGENVALUE":
            expected_unit = f"1/{model_time_unit}2"
        elif quantity == "PERIOD":
            expected_unit = model_time_unit
        elif quantity in _MODAL_SCALAR_UNITS:
            expected_unit = _MODAL_SCALAR_UNITS[str(quantity)]
        else:
            expected_unit = "1"
            target = raw.get("target")
            component = raw.get("component")
            normalization = raw.get("normalization")
            target_id = target.get("id") if isinstance(target, dict) else None
            if (
                not isinstance(target, dict)
                or target.get("type") != "NODE"
                or not isinstance(target_id, int)
                or isinstance(target_id, bool)
                or target_id <= 0
                or component not in {"X", "Y", "RZ"}
                or normalization != "OPENSEES_NATIVE"
            ):
                raise _invalid("Canonical mode-shape identity is invalid", requestId=request_id)
            item.update(
                {
                    "target": {"type": "NODE", "id": target_id},
                    "component": component,
                    "normalization": normalization,
                }
            )
        if unit != expected_unit:
            raise _invalid(
                "Canonical modal result unit does not match its quantity",
                requestId=request_id,
                expectedUnit=expected_unit,
                receivedUnit=unit,
            )
        item["unit"] = expected_unit
        normalized.append(item)

    return {
        "schemaVersion": "1.0",
        "kind": "modal_result_set",
        "modelTimeUnit": model_time_unit,
        "results": normalized,
    }


__all__ = ["canonicalize_modal_results", "read_modal_result_set"]
