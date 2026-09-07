from __future__ import annotations

import json
import re
from pathlib import Path

from fem_core.analysis_spec import validate_engineering_analysis_spec

FIXTURE = Path("tests/fixtures/analysis_spec/simple-linear-static.json")


def load_spec() -> dict:
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


def test_valid_spec_returns_normalized_spec_and_fingerprint() -> None:
    result = validate_engineering_analysis_spec(load_spec())

    assert result["status"] == "VALID"
    assert result["issues"] == []
    assert result["normalizedSpec"] is not None
    assert re.fullmatch(r"[0-9a-f]{64}", result["analysisSpecFingerprint"])
