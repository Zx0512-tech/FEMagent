from __future__ import annotations

import csv
import math
from hashlib import sha256
from itertools import pairwise
from pathlib import Path
from typing import Any

from fem_core.errors import FemCoreError

CANONICAL_LOAD_COLUMNS = (
    "time_s",
    "load_kind",
    "channel_id",
    "application_type",
    "target_type",
    "target_id",
    "component",
    "quantity",
    "value",
    "unit",
)

_COMPONENT_ALIASES = {
    "X": "X",
    "UX": "X",
    "U1": "X",
    "1": "X",
    "Y": "Y",
    "UY": "Y",
    "U2": "Y",
    "2": "Y",
    "Z": "Z",
    "UZ": "Z",
    "U3": "Z",
    "3": "Z",
}
_LENGTH_UNITS_PER_METER = {"m": 1.0, "cm": 100.0, "mm": 1000.0}
_TIME_UNITS_PER_SECOND = {"s": 1.0, "ms": 1000.0}


def _finite(value: Any, field: str) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise FemCoreError(
            "INVALID_CANONICAL_LOAD",
            f"Canonical load field '{field}' must be numeric",
            details={"field": field, "value": value},
        ) from exc
    if not math.isfinite(number):
        raise FemCoreError(
            "INVALID_CANONICAL_LOAD",
            f"Canonical load field '{field}' must be finite",
            details={"field": field, "value": value},
        )
    return number


def _model_unit_conversion(model_units: dict[str, str]) -> dict[str, Any]:
    if not isinstance(model_units, dict):
        raise FemCoreError(
            "ANSYS_MODEL_UNITS_REQUIRED",
            "ANSYS canonical load injection requires explicit model length/time units",
        )
    length = model_units.get("length")
    time = model_units.get("time")
    if not isinstance(length, str) or not length.strip() or not isinstance(time, str) or not time.strip():
        raise FemCoreError(
            "ANSYS_MODEL_UNITS_REQUIRED",
            "ANSYS canonical load injection requires explicit model length/time units",
            details={"required": {"length": sorted(_LENGTH_UNITS_PER_METER), "time": sorted(_TIME_UNITS_PER_SECOND)}},
        )
    length = length.strip().lower()
    time = time.strip().lower()
    if length not in _LENGTH_UNITS_PER_METER or time not in _TIME_UNITS_PER_SECOND:
        raise FemCoreError(
            "UNSUPPORTED_ANSYS_MODEL_UNITS",
            "ANSYS canonical load injection supports length m/cm/mm and time s/ms in PR10",
            details={"length": length, "time": time},
        )
    length_factor = _LENGTH_UNITS_PER_METER[length]
    time_factor = _TIME_UNITS_PER_SECOND[time]
    acceleration_factor = length_factor / (time_factor * time_factor)
    return {
        "modelUnits": {
            "length": length,
            "time": time,
            "acceleration": f"{length}/{time}2",
        },
        "conversion": {
            "timeUnitsPerSecond": time_factor,
            "lengthUnitsPerMeter": length_factor,
            "accelerationFactorFromMPerS2": acceleration_factor,
        },
    }


def read_ansys_canonical_uniform_excitation(
    path: Path,
    model_units: dict[str, str],
) -> dict[str, Any]:
    unit_conversion = _model_unit_conversion(model_units)
    try:
        raw_bytes = path.read_bytes()
        text = raw_bytes.decode("utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        raise FemCoreError(
            "INVALID_CANONICAL_LOAD",
            "ANSYS canonical load must be a readable UTF-8 CSV file",
        ) from exc

    reader = csv.DictReader(text.splitlines())
    if tuple(reader.fieldnames or ()) != CANONICAL_LOAD_COLUMNS:
        raise FemCoreError(
            "UNSUPPORTED_CANONICAL_LOAD",
            "ANSYS PR10 requires FEMAGENT_LOAD_CSV_V1 column order",
            details={"expected": list(CANONICAL_LOAD_COLUMNS), "received": reader.fieldnames},
        )
    rows = list(reader)
    if len(rows) < 2:
        raise FemCoreError("LOAD_TOO_SHORT", "ANSYS transient excitation requires at least two samples")

    channel_ids = {str(row.get("channel_id") or "").strip() for row in rows}
    if len(channel_ids) != 1:
        raise FemCoreError(
            "MULTI_CHANNEL_ANSYS_LOAD_NOT_SUPPORTED",
            "ANSYS PR10 accepts exactly one canonical uniform-excitation channel",
        )

    invariant_fields = {
        key: {str(row.get(key) or "").strip() for row in rows}
        for key in ("load_kind", "application_type", "component", "quantity", "unit")
    }
    if any(len(values) != 1 for values in invariant_fields.values()):
        raise FemCoreError(
            "MULTI_CHANNEL_ANSYS_LOAD_NOT_SUPPORTED",
            "ANSYS PR10 accepts one invariant canonical load channel",
        )

    load_kind = next(iter(invariant_fields["load_kind"])).upper()
    application_type = next(iter(invariant_fields["application_type"])).upper()
    quantity = next(iter(invariant_fields["quantity"])).upper()
    unit = next(iter(invariant_fields["unit"]))
    raw_component = next(iter(invariant_fields["component"])).upper()
    component = _COMPONENT_ALIASES.get(raw_component)
    if (
        load_kind != "EARTHQUAKE"
        or application_type != "UNIFORM_EXCITATION"
        or quantity != "ACCELERATION"
        or unit != "m/s2"
        or component is None
    ):
        raise FemCoreError(
            "UNSUPPORTED_ANSYS_CANONICAL_LOAD",
            "ANSYS PR10 supports EARTHQUAKE + UNIFORM_EXCITATION + ACCELERATION in m/s2 on X/Y/Z only",
            details={
                "loadKind": load_kind,
                "applicationType": application_type,
                "quantity": quantity,
                "unit": unit,
                "component": raw_component,
            },
        )

    targets = {
        (str(row.get("target_type") or "").strip(), str(row.get("target_id") or "").strip())
        for row in rows
    }
    if targets != {("", "")}:
        raise FemCoreError(
            "ANSYS_UNIFORM_EXCITATION_MUST_BE_GLOBAL",
            "ANSYS ACEL uniform excitation is global and may not carry a node/element target",
            details={"targets": sorted(targets)},
        )

    times_s = [_finite(row.get("time_s"), "time_s") for row in rows]
    values_m_s2 = [_finite(row.get("value"), "value") for row in rows]
    if any(current <= previous for previous, current in pairwise(times_s)):
        raise FemCoreError(
            "TIME_NOT_STRICTLY_INCREASING",
            "ANSYS canonical load time values must be strictly increasing",
        )

    time_factor = float(unit_conversion["conversion"]["timeUnitsPerSecond"])
    acceleration_factor = float(unit_conversion["conversion"]["accelerationFactorFromMPerS2"])
    return {
        "format": "FEMAGENT_LOAD_CSV_V1",
        "path": str(path),
        "sha256": sha256(raw_bytes).hexdigest(),
        "loadKind": "EARTHQUAKE",
        "applicationType": "UNIFORM_EXCITATION",
        "channelId": next(iter(channel_ids)),
        "component": component,
        "quantity": "ACCELERATION",
        "canonicalUnit": "m/s2",
        "sampleCount": len(rows),
        "timesCanonicalS": times_s,
        "valuesCanonicalMPerS2": values_m_s2,
        "timesModel": [value * time_factor for value in times_s],
        "valuesModel": [value * acceleration_factor for value in values_m_s2],
        **unit_conversion,
        "signConvention": "CANONICAL_SUPPORT_ACCELERATION_TO_ACEL_DIRECT",
    }
