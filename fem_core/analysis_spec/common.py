from __future__ import annotations

import hashlib
import json
import math
import re
from typing import Any

ID_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_-]{0,63}$")
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


def issue(code: str, path: str, message: str) -> dict[str, str]:
    return {"severity": "ERROR", "code": code, "path": path, "message": message}


def is_positive_int(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value > 0


def is_finite_number(value: Any) -> bool:
    return (
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and math.isfinite(float(value))
    )


def validate_exact_keys(
    value: Any,
    expected: set[str],
    path: str,
    issues: list[dict[str, str]],
) -> bool:
    if not isinstance(value, dict):
        issues.append(
            issue(
                "ANALYSIS_SPEC_INVALID_SCHEMA",
                path,
                f"{path or 'AnalysisSpec'} must be a JSON object",
            )
        )
        return False
    for key in sorted(set(value) - expected):
        child = f"{path}.{key}" if path else key
        issues.append(
            issue(
                "ANALYSIS_SPEC_UNKNOWN_FIELD",
                child,
                f"Unknown AnalysisSpec field: {child}",
            )
        )
    for key in sorted(expected - set(value)):
        child = f"{path}.{key}" if path else key
        issues.append(
            issue(
                "ANALYSIS_SPEC_INVALID_SCHEMA",
                child,
                f"Required AnalysisSpec field is missing: {child}",
            )
        )
    return True


def validate_id_token(
    value: Any,
    path: str,
    issues: list[dict[str, str]],
) -> str | None:
    if not isinstance(value, str) or ID_RE.fullmatch(value) is None:
        issues.append(
            issue(
                "ANALYSIS_SPEC_INVALID_ID",
                path,
                f"{path} must match {ID_RE.pattern}",
            )
        )
        return None
    return value


def validate_positive_target_id(
    value: Any,
    path: str,
    issues: list[dict[str, str]],
) -> int | None:
    if not is_positive_int(value):
        issues.append(
            issue(
                "ANALYSIS_SPEC_INVALID_TARGET_ID",
                path,
                f"{path} must be a positive integer",
            )
        )
        return None
    return value


def canonical_sha256(value: Any) -> str:
    raw = json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()
