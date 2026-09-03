from __future__ import annotations

import math
import re
from dataclasses import dataclass
from typing import Any

from fem_core.load_formats import LoadTable, number_or_none

_TIME_STEP_RTOL = 1.0e-6
_TIME_COLUMN_NAMES = frozenset(
    {
        "t",
        "time",
        "time_s",
        "times",
        "timestamp",
        "sec",
        "second",
        "seconds",
        "时间",
        "时间(s)",
        "时间（s）",
        "时刻",
        "秒",
    }
)
_ACCELERATION_NAME_HINTS = ("acc", "accel", "a_", "ag", "加速度", "地震", "quake", "eq")
_UNIT_TOKENS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("mm/s2", ("mm/s2", "mm/s^2", "mm/sec2", "mm/sec^2")),
    ("cm/s2", ("cm/s2", "cm/s^2", "cm/sec2", "cm/sec^2", "gal")),
    ("m/s2", ("m/s2", "m/s^2", "m/sec2", "m/sec^2")),
    ("kN", ("kn",)),
    ("N", ("n",)),
    ("g", ("g",)),
)

UNIT_SOURCE_HEADER = "DECLARED_IN_HEADER"
UNIT_SOURCE_COLUMN_NAME = "DECLARED_IN_COLUMN_NAME"
UNIT_SOURCE_MAGNITUDE = "GUESSED_FROM_MAGNITUDE"
UNIT_SOURCE_UNKNOWN = "UNKNOWN"


@dataclass(frozen=True)
class TimeDetection:
    column: str | None
    step_s: float | None
    uniform: bool
    source_unit: str | None
    reason: str


def detect_time_column(profiles: list[dict[str, Any]], rows: tuple[dict[str, str], ...]) -> TimeDetection:
    if len(rows) < 2:
        return TimeDetection(None, None, False, None, "ROW_COUNT_TOO_SMALL")

    candidates: list[tuple[int, int, str, float, str]] = []
    for index, profile in enumerate(profiles):
        name = str(profile["name"])
        values = _numeric_column(rows, name)
        if values is None or len(values) < 2:
            continue
        if any(current <= previous for previous, current in zip(values, values[1:])):
            continue
        step = _uniform_step(values)
        if step is None:
            continue
        named = 0 if _normalized_time_name(name) in _TIME_COLUMN_NAMES else 1
        unit = _time_unit_from_name(name)
        factor = 0.001 if unit == "ms" else 1.0
        candidates.append((named, index, name, step * factor, unit or "s"))

    if not candidates:
        return TimeDetection(None, None, False, None, "NO_MONOTONIC_UNIFORM_COLUMN")

    named_profiles = [profile for profile in profiles if _normalized_time_name(str(profile["name"])) in _TIME_COLUMN_NAMES]
    if named_profiles and all(candidate[0] for candidate in candidates):
        return TimeDetection(None, None, False, None, "NAMED_TIME_COLUMN_NOT_UNIFORM")

    candidates.sort(key=lambda item: (item[0], item[1]))
    _, _, column, step_s, unit = candidates[0]
    return TimeDetection(column, step_s, True, unit, "UNIFORM_INCREASING_COLUMN")


def build_mapping_suggestion(
    table: LoadTable,
    profiles: list[dict[str, Any]],
    *,
    file_name: str,
) -> dict[str, Any]:
    if table.self_describing:
        unit = str(table.metadata["declaredUnit"])
        return {
            "mapping": {
                "version": 1,
                "loadKind": "EARTHQUAKE",
                "timeColumn": "time_s",
                "timeUnit": "s",
                "timeStepS": float(table.metadata["declaredDt"]),
                "valueColumn": "acceleration",
                "quantity": "ACCELERATION",
                "sourceUnit": unit,
                "applicationType": "UNIFORM_EXCITATION",
                "component": None,
                "scale": 1.0,
            },
            "confidence": "HIGH",
            "reasons": [
                "PEER header declares sampling interval, acceleration quantity and source unit",
            ],
            "warnings": ["Excitation component/direction must still be confirmed"],
            "alternatives": {},
            "unitSource": UNIT_SOURCE_HEADER,
            "standardizeDecision": "ASK",
            "requiredConfirmations": ["component"],
        }

    time = detect_time_column(profiles, table.rows)
    value_column, value_reason = _pick_value_column(profiles, table.rows, time.column, file_name)
    if value_column is None:
        return {
            "mapping": {},
            "confidence": "LOW",
            "reasons": [],
            "warnings": ["No reliable numeric load-value column was found"],
            "alternatives": {},
            "unitSource": UNIT_SOURCE_UNKNOWN,
            "standardizeDecision": "ASK",
            "requiredConfirmations": ["mapping"],
        }

    values = _numeric_column(table.rows, value_column) or []
    peak_abs = max((abs(value) for value in values), default=0.0)
    declared_unit = unit_from_name(value_column)
    acceleration_hint = _looks_like_acceleration(value_column, file_name)
    if declared_unit is not None:
        unit = declared_unit
        unit_source = UNIT_SOURCE_COLUMN_NAME
        unit_confidence = "HIGH"
        unit_reason = f"Column name declares unit {unit}"
    elif acceleration_hint:
        unit, unit_confidence, unit_reason = infer_acceleration_unit(peak_abs)
        unit_source = UNIT_SOURCE_MAGNITUDE if unit is not None else UNIT_SOURCE_UNKNOWN
    else:
        unit = None
        unit_source = UNIT_SOURCE_UNKNOWN
        unit_confidence = "LOW"
        unit_reason = "No trustworthy physical unit declaration was found"

    reasons = [value_reason, unit_reason]
    warnings: list[str] = []
    required: list[str] = []
    if time.column is None:
        warnings.append("No trustworthy uniform time column was found; provide timeStepS explicitly")
        required.append("timeStepS")
    else:
        reasons.append(f"Time column {time.column} is strictly increasing with uniform step {time.step_s:.8g} s")
    if unit is None or unit_source == UNIT_SOURCE_MAGNITUDE:
        warnings.append("Source unit is not declared by file content and must be confirmed")
        required.append("sourceUnit")
    if not acceleration_hint:
        warnings.append("Load quantity/kind cannot be determined from the table alone")
        required.extend(["loadKind", "quantity", "applicationType"])
    required.append("component")

    mapping = {
        "version": 1,
        "loadKind": "EARTHQUAKE" if acceleration_hint else None,
        "timeColumn": time.column,
        "timeUnit": time.source_unit or "s",
        "timeStepS": time.step_s if time.column is None else None,
        "valueColumn": value_column,
        "quantity": "ACCELERATION" if acceleration_hint else None,
        "sourceUnit": unit,
        "applicationType": "UNIFORM_EXCITATION" if acceleration_hint else None,
        "component": None,
        "scale": 1.0,
    }
    alternatives = {
        "valueColumns": [
            str(profile["name"])
            for profile in profiles
            if str(profile["name"]) not in {time.column, value_column}
            and int(profile.get("numericCount") or 0) > 0
        ]
    }
    confidence = _combine_confidence(acceleration_hint, unit_confidence, time.column is not None)
    return {
        "mapping": mapping,
        "confidence": confidence,
        "reasons": reasons,
        "warnings": warnings,
        "alternatives": alternatives,
        "unitSource": unit_source,
        "standardizeDecision": "ASK",
        "requiredConfirmations": sorted(set(required)),
    }


def unit_from_name(name: str) -> str | None:
    lowered = name.lower()
    scopes = re.findall(r"[（(\[]([^）)\]]+)[）)\]]", lowered)
    scopes.extend(re.split(r"[_\s,;:]+", lowered)[1:])
    for scope in scopes:
        for canonical, tokens in _UNIT_TOKENS:
            for token in tokens:
                if re.fullmatch(rf"\s*{re.escape(token)}\s*", scope):
                    return canonical
    return None


def infer_acceleration_unit(peak_abs: float) -> tuple[str | None, str, str]:
    if not math.isfinite(peak_abs) or peak_abs <= 0:
        return None, "LOW", "Acceleration magnitude is not usable for a unit hint"
    if peak_abs <= 2.0:
        return "g", "HIGH", f"Peak magnitude {peak_abs:.4g} is consistent with a g-scaled ground motion"
    if peak_abs <= 5.0:
        return "m/s2", "MEDIUM", f"Peak magnitude {peak_abs:.4g} is ambiguous between m/s2 and extreme g values"
    if peak_abs <= 50.0:
        return "m/s2", "HIGH", f"Peak magnitude {peak_abs:.4g} is consistent with m/s2 ground motion"
    return None, "LOW", f"Peak magnitude {peak_abs:.4g} could be gal/cm/s2 or mm/s2 and cannot be inferred safely"


def _pick_value_column(
    profiles: list[dict[str, Any]],
    rows: tuple[dict[str, str], ...],
    time_column: str | None,
    file_name: str,
) -> tuple[str | None, str]:
    candidates: list[tuple[int, int, int, str]] = []
    for index, profile in enumerate(profiles):
        name = str(profile["name"])
        if name == time_column:
            continue
        numeric_count = int(profile.get("numericCount") or 0)
        if numeric_count == 0:
            continue
        full_numeric = int(numeric_count == len(rows))
        hinted = int(_looks_like_acceleration(name, file_name))
        candidates.append((-hinted, -full_numeric, index, name))
    if not candidates:
        return None, "No numeric value column"
    candidates.sort()
    name = candidates[0][3]
    if _looks_like_acceleration(name, file_name):
        return name, f"Selected {name} because its name/file context indicates acceleration"
    return name, f"Selected {name} as the first fully numeric non-time column candidate"


def _numeric_column(rows: tuple[dict[str, str], ...], name: str) -> list[float] | None:
    values: list[float] = []
    for row in rows:
        value = number_or_none(row.get(name, ""))
        if value is None:
            return None
        values.append(value)
    return values


def _uniform_step(values: list[float]) -> float | None:
    steps = [current - previous for previous, current in zip(values, values[1:])]
    if not steps or steps[0] <= 0:
        return None
    reference = steps[0]
    tolerance = max(abs(reference) * _TIME_STEP_RTOL, 1.0e-12)
    if any(abs(step - reference) > tolerance for step in steps[1:]):
        return None
    return reference


def _looks_like_acceleration(column: str, file_name: str) -> bool:
    text = f"{column} {file_name}".lower()
    return any(hint in text for hint in _ACCELERATION_NAME_HINTS)


def _normalized_time_name(name: str) -> str:
    lowered = name.strip().lower().replace("（", "(").replace("）", ")")
    return re.sub(r"\((?:s|sec|second|seconds)\)$", "", lowered).strip() or lowered


def _time_unit_from_name(name: str) -> str | None:
    lowered = name.lower()
    if "(ms)" in lowered or "（ms）" in lowered or lowered.endswith("_ms"):
        return "ms"
    if "(s)" in lowered or "（s）" in lowered or lowered.endswith("_s"):
        return "s"
    return None


def _combine_confidence(acceleration_hint: bool, unit_confidence: str, has_time: bool) -> str:
    score = int(acceleration_hint) + int(unit_confidence == "HIGH") + int(has_time)
    if score == 3:
        return "HIGH"
    if score >= 1:
        return "MEDIUM"
    return "LOW"
