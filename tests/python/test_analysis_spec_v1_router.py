from __future__ import annotations

import json
from pathlib import Path

from fem_core.analysis_spec import validate_engineering_analysis_spec

FIXTURE = Path("tests/fixtures/analysis_spec/simple-linear-static.json")


def load_spec() -> dict:
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


def test_public_router_matches_explicit_v1_validator() -> None:
    from fem_core.analysis_spec.v1 import validate_engineering_analysis_spec_v1

    spec = load_spec()
    assert validate_engineering_analysis_spec(spec) == validate_engineering_analysis_spec_v1(spec)
