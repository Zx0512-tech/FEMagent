from __future__ import annotations

import csv
import io
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

_METERS_PER_LENGTH_UNIT = {"m": 1.0, "cm": 0.01, "mm": 0.001}
_SECONDS_PER_TIME_UNIT = {"s": 1.0, "ms": 0.001}
_FORCE_N_TO_MODEL = {"N": 1.0, "kN": 0.001}
_INVARIANT_FIELDS = (
    "load_kind",
    "channel_id",
    "application_type",
    "target_type",
    "target_id",
    "component",
    "quantity",
    "unit",
)


def force_n_to_model_factor(force_unit: str) -> float:
    try:
        return _FORCE_N_TO_MODEL[force_unit]
    except KeyError as exc:
        raise FemCoreError(
            "TRANSIENT_ARTIFACT_UNSUPPORTED_FORCE_UNIT",
            "Transient artifact force conversion supports N and kN only",
            details={"forceUnit": force_unit},
        ) from exc


def seconds_to_model_time_factor(time_unit: str) -> float:
    try:
        return 1.0 / _SECONDS_PER_TIME_UNIT[time_unit]
    except KeyError as exc:
        raise FemCoreError(
            "TRANSIENT_ARTIFACT_UNSUPPORTED_TIME_UNIT",
            "Transient artifact time conversion supports s and ms only",
            details={"timeUnit": time_unit},
        ) from exc


def acceleration_m_s2_to_model_factor(length_unit: str, time_unit: str) -> tuple[float, str]:
    try:
        meters_per_length = _METERS_PER_LENGTH_UNIT[length_unit]
        seconds_per_time = _SECONDS_PER_TIME_UNIT[time_unit]
    except KeyError as exc:
        raise FemCoreError(
            "TRANSIENT_ARTIFACT_UNSUPPORTED_ACCELERATION_UNIT",
            "Transient artifact acceleration conversion supports length m/cm/mm and time s/ms",
            details={"lengthUnit": length_unit, "timeUnit": time_unit},
        ) from exc
    factor = (1.0 / meters_per_length) * seconds_per_time**2
    return factor, f"{length_unit}/{time_unit}2"


def _finite(value: Any, field: str) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise FemCoreError(
            "TRANSIENT_ARTIFACT_INVALID_NUMBER",
            f"Transient artifact field '{field}' must be numeric",
            details={"field": field, "value": value},
        ) from exc
    if not math.isfinite(number):
        raise FemCoreError(
            "TRANSIENT_ARTIFACT_INVALID_NUMBER",
            f"Transient artifact field '{field}' must be finite",
            details={"field": field, "value": value},
        )
    return number


def _resolve_artifact_path(workspace: Path, raw_path: str) -> Path:
    root = workspace.resolve()
    candidate = Path(raw_path)
    if candidate.is_absolute():
        raise FemCoreError(
            "TRANSIENT_ARTIFACT_PATH_ESCAPE",
            "Transient artifact path must be workspace-relative",
            details={"path": raw_path},
        )
    resolved = (root / candidate).resolve()
    try:
        resolved.relative_to(root)
    except ValueError as exc:
        raise FemCoreError(
            "TRANSIENT_ARTIFACT_PATH_ESCAPE",
            "Transient artifact path resolves outside the active workspace",
            details={"path": raw_path},
        ) from exc
    return resolved


def read_transient_load_artifact(workspace: Path, ref: dict[str, str]) -> dict[str, Any]:
    raw_path = ref.get("path") if isinstance(ref, dict) else None
    declared_sha = ref.get("sha256") if isinstance(ref, dict) else None
    if not isinstance(raw_path, str) or not raw_path.strip():
        raise FemCoreError(
            "TRANSIENT_ARTIFACT_PATH_ESCAPE",
            "Transient artifact reference requires a non-empty workspace-relative path",
        )
    if not isinstance(declared_sha, str):
        raise FemCoreError(
            "TRANSIENT_ARTIFACT_HASH_MISMATCH",
            "Transient artifact reference requires a SHA-256 digest",
        )

    path = _resolve_artifact_path(workspace, raw_path)
    try:
        raw_bytes = path.read_bytes()
    except FileNotFoundError as exc:
        raise FemCoreError(
            "TRANSIENT_ARTIFACT_NOT_FOUND",
            "Transient load artifact does not exist in the active workspace",
            details={"path": raw_path},
        ) from exc
    except OSError as exc:
        raise FemCoreError(
            "TRANSIENT_ARTIFACT_NOT_FOUND",
            "Transient load artifact is not readable",
            details={"path": raw_path},
        ) from exc

    actual_sha = sha256(raw_bytes).hexdigest()
    if actual_sha != declared_sha:
        raise FemCoreError(
            "TRANSIENT_ARTIFACT_HASH_MISMATCH",
            "Transient load artifact SHA-256 does not match the AnalysisSpec reference",
            details={"path": raw_path, "expected": declared_sha, "actual": actual_sha},
        )

    try:
        text = raw_bytes.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise FemCoreError(
            "TRANSIENT_ARTIFACT_INVALID_UTF8",
            "Transient load artifact must be UTF-8 CSV",
            details={"path": raw_path},
        ) from exc

    try:
        reader = csv.DictReader(io.StringIO(text, newline=""), strict=True)
        fieldnames = tuple(reader.fieldnames or ())
        if fieldnames != CANONICAL_LOAD_COLUMNS:
            raise FemCoreError(
                "TRANSIENT_ARTIFACT_INVALID_SCHEMA",
                "Transient load artifact requires exact FEMAGENT_LOAD_CSV_V1 column order",
                details={"expected": list(CANONICAL_LOAD_COLUMNS), "received": list(fieldnames)},
            )
        rows = list(reader)
    except csv.Error as exc:
        raise FemCoreError(
            "TRANSIENT_ARTIFACT_INVALID_CSV",
            "Transient load artifact contains malformed CSV",
            details={"path": raw_path},
        ) from exc

    if len(rows) < 2:
        raise FemCoreError(
            "TRANSIENT_ARTIFACT_TOO_SHORT",
            "Transient load artifact requires at least two samples",
            details={"sampleCount": len(rows)},
        )

    invariant: dict[str, str] = {}
    for key in _INVARIANT_FIELDS:
        values = {str(row.get(key) or "").strip() for row in rows}
        if len(values) != 1:
            raise FemCoreError(
                "TRANSIENT_ARTIFACT_MULTIPLE_CHANNELS",
                "Transient load artifact must contain exactly one invariant channel",
                details={"field": key, "values": sorted(values)},
            )
        invariant[key] = next(iter(values))

    if not invariant["channel_id"]:
        raise FemCoreError(
            "TRANSIENT_ARTIFACT_MULTIPLE_CHANNELS",
            "Transient load artifact channel_id must be non-empty and invariant",
        )

    times_s = [_finite(row.get("time_s"), "time_s") for row in rows]
    values = [_finite(row.get("value"), "value") for row in rows]
    deltas = [current - previous for previous, current in pairwise(times_s)]
    if any(delta <= 0.0 for delta in deltas):
        raise FemCoreError(
            "TRANSIENT_ARTIFACT_TIME_NOT_INCREASING",
            "Transient artifact time values must be strictly increasing",
        )

    dt_s = deltas[0]
    if any(not math.isclose(delta, dt_s, rel_tol=1e-9, abs_tol=1e-12) for delta in deltas[1:]):
        raise FemCoreError(
            "TRANSIENT_ARTIFACT_TIME_NOT_UNIFORM",
            "Transient artifact time values must use one uniform time step",
            details={"dtS": dt_s},
        )

    return {
        "format": "FEMAGENT_LOAD_CSV_V1",
        "timesS": times_s,
        "values": values,
        "dtS": dt_s,
        "timeStartS": times_s[0],
        "timeEndS": times_s[-1],
        "sampleCount": len(rows),
        "loadKind": invariant["load_kind"].upper(),
        "channelId": invariant["channel_id"],
        "applicationType": invariant["application_type"].upper(),
        "targetType": invariant["target_type"].upper(),
        "targetId": invariant["target_id"],
        "component": invariant["component"].upper(),
        "quantity": invariant["quantity"].upper(),
        "unit": invariant["unit"],
        "path": raw_path,
        "sha256": actual_sha,
    }


__all__ = [
    "CANONICAL_LOAD_COLUMNS",
    "acceleration_m_s2_to_model_factor",
    "force_n_to_model_factor",
    "read_transient_load_artifact",
    "seconds_to_model_time_factor",
]
