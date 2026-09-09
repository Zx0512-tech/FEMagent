from __future__ import annotations

from collections.abc import Callable
from typing import Any

from fem_core.analysis_spec.v1 import validate_engineering_analysis_spec_v1
from fem_core.analysis_spec.v2 import validate_engineering_analysis_spec_v2

_AnalysisSpecValidator = Callable[[Any], dict[str, Any]]
_VALIDATORS: dict[str, _AnalysisSpecValidator] = {
    "1.0": validate_engineering_analysis_spec_v1,
    "2.0": validate_engineering_analysis_spec_v2,
}


def validate_engineering_analysis_spec(spec: Any) -> dict[str, Any]:
    if isinstance(spec, dict):
        version = spec.get("schemaVersion")
        if isinstance(version, str):
            validator = _VALIDATORS.get(version)
            if validator is not None:
                return validator(spec)
    return validate_engineering_analysis_spec_v1(spec)
